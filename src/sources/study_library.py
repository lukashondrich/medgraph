"""Study library: two-lane retrieval over the curated study corpus.

``select_lanes`` is a pure function and holds all the ranking rules.
``StudyLibrary`` wraps the Qdrant store and turns queries into scored
passages.

Lanes:
- matched: studies whose cohort resembles the profile on a distinguishing
  attribute, ranked by relevance lifted by match strength. Study quality
  plays no part, so a small study belongs here even when it would rank low.
- overall: everything else, ranked by relevance times evidence weight.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from src.data.profile import UserProfile
from src.knowledge_pipeline.study_schemas import StudyDesign, StudyRecord, load_records
from src.models.evidence import SourceItem

from .deeplinks import quote_links
from .matching import CohortMatch, distinguishing_attributes, match_cohort

logger = logging.getLogger(__name__)

MAX_OVERALL = 4
MAX_MATCHED = 3
MAX_GUIDELINES = 2
SEARCH_DEPTH = 2000
# Qualifying score at which a match doubles a study's rank in the matched lane.
MATCH_SCALE = 5.0
# A study must be about the question to be used. Cosine similarity of its
# best passage to the best-fitting query has to reach this value. Measured on
# the first corpus: unrelated questions peak near 0.2, related ones start
# near 0.45.
MIN_RELEVANCE = 0.30
PASSAGES_PER_STUDY = 2

_DESIGN_WEIGHT: dict[StudyDesign, float] = {
    StudyDesign.META_ANALYSIS: 1.0,
    StudyDesign.SYSTEMATIC_REVIEW: 0.95,
    StudyDesign.GUIDELINE: 0.95,
    StudyDesign.RCT: 0.9,
    StudyDesign.CONTROLLED_TRIAL: 0.85,
    StudyDesign.COHORT: 0.8,
    StudyDesign.CROSS_SECTIONAL: 0.7,
    StudyDesign.CASE_CONTROL: 0.7,
    StudyDesign.REVIEW: 0.6,
    StudyDesign.LAB_STUDY: 0.55,
    StudyDesign.OTHER: 0.5,
    StudyDesign.CASE_SERIES: 0.4,
}


class ScoredPassage(BaseModel):
    passage_id: str
    study_id: str
    text: str
    relevance: float
    section: str = "Abstract"


class LaneResult(BaseModel):
    matched: list[SourceItem] = Field(default_factory=list)
    overall: list[SourceItem] = Field(default_factory=list)
    studies_found: int = 0
    no_matched_evidence: bool = False
    unmatched_attributes: list[str] = Field(default_factory=list)

    @property
    def items(self) -> list[SourceItem]:
        return self.matched + self.overall


def evidence_weight(record: StudyRecord) -> float:
    """Quality weight in (0, 1] from study design and sample size."""
    design = _DESIGN_WEIGHT[record.design]
    if record.sample_size:
        size = 0.75 + 0.25 * min(1.0, math.log10(record.sample_size) / 4)
    else:
        size = 0.85
    return design * size


def _to_item(
    record: StudyRecord,
    passages: list[ScoredPassage],
    group: str,
    match: Optional[CohortMatch],
) -> SourceItem:
    chosen = [passages[0]] + [
        p for p in passages[1:PASSAGES_PER_STUDY] if p.relevance >= MIN_RELEVANCE
    ]
    chosen.sort(key=lambda p: p.passage_id)  # keep the paper's own order
    return SourceItem(
        id=f"study:{record.study_id}",
        source="study_library",
        group=group,
        study_id=record.study_id,
        title=record.title,
        authors=record.authors,
        year=record.year,
        design=record.design_label,
        sample_size=record.sample_size,
        cohort_summary=record.cohort.description,
        countries=record.cohort.countries,
        matched_attributes=match.matched_attributes if match else [],
        passage=" … ".join(p.text for p in chosen),
        quotes=[quote_links(record, p.text, p.section) for p in chosen],
        url=record.url,
        relevance=passages[0].relevance,
    )


def select_lanes(
    candidates: list[ScoredPassage],
    records: dict[str, StudyRecord],
    profile: UserProfile,
    *,
    max_overall: int = MAX_OVERALL,
    max_matched: int = MAX_MATCHED,
    min_relevance: float = MIN_RELEVANCE,
) -> LaneResult:
    """Split scored passages into the matched and overall lanes."""
    by_study: dict[str, list[ScoredPassage]] = {}
    for passage in candidates:
        if passage.study_id in records:  # never cite a study without a checked record
            by_study.setdefault(passage.study_id, []).append(passage)
    for passages in by_study.values():
        passages.sort(key=lambda p: p.relevance, reverse=True)
    # A study has to be about the question to be used at all, in either lane.
    by_study = {
        sid: passages for sid, passages in by_study.items()
        if passages[0].relevance >= min_relevance
    }

    matches = {sid: match_cohort(profile, records[sid]) for sid in by_study}

    matched_ids = [sid for sid in by_study if matches[sid].qualifies]
    # Rank by relevance, lifted by how strongly the cohort matches on
    # distinguishing attributes. A closer match wins between studies that
    # speak to the question equally well, but a study that answers the
    # question beats a closer match that is about something else.
    matched_ids.sort(
        key=lambda sid: (
            by_study[sid][0].relevance * (1 + matches[sid].qualifying_score / MATCH_SCALE),
            matches[sid].score,
        ),
        reverse=True,
    )
    matched_ids = matched_ids[:max_matched]

    # A study is shown once: anything in the matched lane is left out of overall.
    overall_ids = [sid for sid in by_study if sid not in matched_ids]
    overall_ids.sort(
        key=lambda sid: by_study[sid][0].relevance * evidence_weight(records[sid]),
        reverse=True,
    )
    overall_ids = overall_ids[:max_overall]

    result = LaneResult(
        matched=[_to_item(records[s], by_study[s], "matched", matches[s]) for s in matched_ids],
        overall=[_to_item(records[s], by_study[s], "overall", None) for s in overall_ids],
        studies_found=len(by_study),
    )
    # A gap is only worth reporting when the library had something to say
    # about the question but nothing from women like her.
    if by_study and not result.matched:
        result.no_matched_evidence = True
        result.unmatched_attributes = distinguishing_attributes(profile)
    return result


def select_guidelines(
    candidates: list[ScoredPassage],
    guidelines: dict[str, StudyRecord],
    *,
    max_items: int = MAX_GUIDELINES,
    min_relevance: float = MIN_RELEVANCE,
) -> list[SourceItem]:
    """Pick the guideline records that speak to the question, best first."""
    by_study: dict[str, list[ScoredPassage]] = {}
    for passage in candidates:
        if passage.study_id in guidelines and passage.relevance >= min_relevance:
            by_study.setdefault(passage.study_id, []).append(passage)
    for passages in by_study.values():
        passages.sort(key=lambda p: p.relevance, reverse=True)
    ranked = sorted(by_study, key=lambda sid: by_study[sid][0].relevance, reverse=True)
    items = [_to_item(guidelines[sid], by_study[sid], "guideline", None) for sid in ranked[:max_items]]
    for item in items:
        item.id = f"guideline:{item.study_id}"
        item.source = "guidelines"
    return items


class StudyLibrary:
    """Semantic search over the indexed study passages."""

    def __init__(
        self,
        records: Optional[dict[str, StudyRecord]] = None,
        store_path: Optional[Path | str] = None,
    ) -> None:
        from src.knowledge_pipeline.corpus import STUDY_STORE_PATH

        self.records = records if records is not None else load_records(checked_only=True)
        self.store_path = str(store_path or STUDY_STORE_PATH)
        self._pipeline = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.store_path == ":memory:" or Path(self.store_path).exists()

    def _get_pipeline(self, top_k: int):
        if self._pipeline is None:
            from src.knowledge_pipeline.corpus import STUDY_COLLECTION
            from src.knowledge_pipeline.pipeline import (
                build_retrieval_pipeline,
                get_document_store,
            )

            store = get_document_store(location=self.store_path, collection_name=STUDY_COLLECTION)
            self._pipeline = build_retrieval_pipeline(store, top_k=top_k)
        return self._pipeline

    def search(self, queries: list[str], top_k: int = SEARCH_DEPTH) -> list[ScoredPassage]:
        """Return passages for all queries, keeping each passage's best score.

        The search is deep enough to score every passage in the corpus, so
        that guidelines and small matched studies are not crowded out by the
        most similar passages; the relevance threshold does the filtering.
        """
        if not self.available:
            logger.warning("Study store not found at %s; run the corpus build", self.store_path)
            return []
        best: dict[str, ScoredPassage] = {}
        with self._lock:
            pipeline = self._get_pipeline(top_k)
            for query in queries:
                result = pipeline.run({"embedder": {"text": query}})
                for doc in result.get("retriever", {}).get("documents", []):
                    meta = doc.meta or {}
                    passage = ScoredPassage(
                        passage_id=meta.get("passage_id", doc.id),
                        study_id=meta.get("study_id", ""),
                        text=doc.content or "",
                        relevance=float(doc.score or 0.0),
                        section=meta.get("section", "Abstract"),
                    )
                    known = best.get(passage.passage_id)
                    if known is None or passage.relevance > known.relevance:
                        best[passage.passage_id] = passage
        return list(best.values())

    def _records_by_kind(self, guidelines: bool) -> dict[str, StudyRecord]:
        return {
            sid: record for sid, record in self.records.items()
            if (record.design is StudyDesign.GUIDELINE) == guidelines
        }

    def retrieve(self, queries: list[str], profile: UserProfile) -> LaneResult:
        """Two-lane retrieval over studies. Guidelines are a separate source."""
        return select_lanes(self.search(queries), self._records_by_kind(False), profile)

    def retrieve_guidelines(self, queries: list[str]) -> list[SourceItem]:
        """The most relevant guideline passages for the queries."""
        return select_guidelines(self.search(queries), self._records_by_kind(True))


_library: Optional[StudyLibrary] = None
_library_lock = threading.Lock()


def get_study_library() -> StudyLibrary:
    """Process-wide library instance (the embedded store allows one client)."""
    global _library
    with _library_lock:
        if _library is None:
            _library = StudyLibrary()
        return _library
