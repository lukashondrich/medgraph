"""Study records for the pH Companion corpus.

One ``StudyRecord`` per paper, stored as a YAML file under
``data/corpus/studies/``. The record is the source of truth; the Qdrant store
is built from checked records only.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "corpus"
STUDIES_DIR = CORPUS_DIR / "studies"


# ── Controlled vocabularies ───────────────────────────────────────────────


class StudyDesign(str, Enum):
    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    GUIDELINE = "guideline"
    RCT = "rct"
    CONTROLLED_TRIAL = "controlled_trial"  # intervention vs control, not randomised
    COHORT = "cohort"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_CONTROL = "case_control"
    CASE_SERIES = "case_series"
    LAB_STUDY = "lab_study"
    REVIEW = "review"
    OTHER = "other"


DESIGN_LABELS: dict[StudyDesign, str] = {
    StudyDesign.META_ANALYSIS: "Meta-analysis",
    StudyDesign.SYSTEMATIC_REVIEW: "Systematic review",
    StudyDesign.GUIDELINE: "Guideline",
    StudyDesign.RCT: "Randomised trial",
    StudyDesign.CONTROLLED_TRIAL: "Controlled trial (not randomised)",
    StudyDesign.COHORT: "Cohort study",
    StudyDesign.CROSS_SECTIONAL: "Cross-sectional study",
    StudyDesign.CASE_CONTROL: "Case-control study",
    StudyDesign.CASE_SERIES: "Case series",
    StudyDesign.LAB_STUDY: "Laboratory study",
    StudyDesign.REVIEW: "Review",
    StudyDesign.OTHER: "Study",
}

# child -> parent. The hierarchy deliberately stops at these parents: a cohort
# described only as "asian" is not a match for an Indian profile.
ANCESTRY_PARENTS: dict[str, str] = {
    "indian": "south_asian",
    "pakistani": "south_asian",
    "bangladeshi": "south_asian",
    "nepali": "south_asian",
    "sri_lankan": "south_asian",
    "african_american": "black",
    "african": "black",
    "afro_caribbean": "black",
}

ANCESTRY_KEYS: set[str] = (
    set(ANCESTRY_PARENTS)
    | set(ANCESTRY_PARENTS.values())
    | {"white_european", "hispanic", "east_asian", "asian_unspecified", "mixed", "other"}
)

MENOPAUSAL_KEYS = {"premenopausal", "perimenopausal", "postmenopausal"}
PREGNANCY_KEYS = {"pregnant", "not_pregnant"}


class CheckStatus(str, Enum):
    UNCHECKED = "unchecked"
    CHECKED = "checked"
    DISPUTED = "disputed"


# ── Models ────────────────────────────────────────────────────────────────


class Cohort(BaseModel):
    """Who was studied. Empty lists mean "not stated"."""

    description: str = Field(
        default="", description="Short plain-language cohort summary for display"
    )
    ancestry: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    menopausal_status: list[str] = Field(default_factory=list)
    pregnancy: list[str] = Field(default_factory=list)


class CheckInfo(BaseModel):
    status: CheckStatus = CheckStatus.UNCHECKED
    checked_by: Optional[str] = Field(
        default=None, description="Model name or person"
    )
    checked_on: Optional[date] = None
    notes: str = ""


class StudyRecord(BaseModel):
    """One paper in the corpus."""

    study_id: str = Field(description="Stable id, e.g. 'pmid-18803273'")
    pmid: Optional[str] = None
    pmcid: Optional[str] = Field(default=None, description="PubMed Central id, when the full text is there")
    open_access: bool = Field(default=False, description="Full text may be downloaded from Europe PMC")
    doi: Optional[str] = None
    url: str
    title: str
    authors: str = Field(description="Short form, e.g. 'Ravel et al.'")
    year: int
    journal: str = ""

    design: StudyDesign
    sample_size: Optional[int] = Field(default=None, ge=1)
    cohort: Cohort = Field(default_factory=Cohort)
    topics: list[str] = Field(default_factory=list)
    key_finding: str = Field(default="", description="One sentence, plain language")

    abstract: str
    licence: Optional[str] = None
    text_source: str = "abstract"
    check: CheckInfo = Field(default_factory=CheckInfo)

    @property
    def design_label(self) -> str:
        return DESIGN_LABELS[self.design]

    def vocabulary_errors(self) -> list[str]:
        """Return problems with controlled-vocabulary fields (empty if none)."""
        errors = []
        for a in self.cohort.ancestry:
            if a not in ANCESTRY_KEYS:
                errors.append(f"unknown ancestry '{a}'")
        for m in self.cohort.menopausal_status:
            if m not in MENOPAUSAL_KEYS:
                errors.append(f"unknown menopausal status '{m}'")
        for p in self.cohort.pregnancy:
            if p not in PREGNANCY_KEYS:
                errors.append(f"unknown pregnancy value '{p}'")
        return errors


class Passage(BaseModel):
    """A verbatim piece of a study's text that a claim can rest on."""

    passage_id: str
    study_id: str
    text: str
    section: str = Field(default="Abstract", description="Section heading the text sits under")
    source: str = Field(default="abstract", description="'abstract' or 'fulltext'")


# ── File handling ─────────────────────────────────────────────────────────


def load_record(path: Path) -> StudyRecord:
    return StudyRecord.model_validate(yaml.safe_load(path.read_text()))


def save_record(record: StudyRecord, directory: Path = STUDIES_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.study_id}.yaml"
    data = record.model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return path


def load_records(
    directory: Path = STUDIES_DIR, *, checked_only: bool = True
) -> dict[str, StudyRecord]:
    """Load all study records keyed by study_id.

    With ``checked_only`` (the default) records that have not passed the
    second check are left out, so they can never be indexed or cited.
    """
    records: dict[str, StudyRecord] = {}
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.yaml")):
        record = load_record(path)
        if checked_only and record.check.status is not CheckStatus.CHECKED:
            continue
        records[record.study_id] = record
    return records


# ── Passages ──────────────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_ABBREVIATION = re.compile(r"(?:\b(?:Fig|Figs|Tab|Eq|No|vs|ca|approx|resp|e\.g|i\.e|al|Dr|St)\.)$")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence in ``text``.

    Spans index into the original text, so a passage built from them is an
    exact substring of it, whatever kind of whitespace the paper uses
    between sentences. No split after "Fig.", "e.g.", "et al." and the like.
    """
    spans, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        if _ABBREVIATION.search(text[start:match.start()]):
            continue
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _windows(text: str, size: int) -> list[str]:
    """Consecutive groups of ``size`` sentences, each an exact substring of ``text``."""
    spans = sentence_spans(text)
    return [text[spans[i][0]:spans[min(i + size, len(spans)) - 1][1]] for i in range(0, len(spans), size)]


def split_passages(record: StudyRecord, sentences_per_passage: int = 2) -> list[Passage]:
    """Split a record's abstract into short verbatim passages."""
    passages = []
    for n, text in enumerate(_windows(record.abstract, sentences_per_passage), 1):
        passages.append(Passage(
            passage_id=f"{record.study_id}#p{n}",
            study_id=record.study_id,
            text=text,
        ))
    return passages


MIN_PASSAGE_WORDS = 8

# A sentence that cites other work ("[8]", "(Smith et al., 2010)") reports
# someone else's finding. Quoting it would credit this paper with it.
_CITES_OTHERS = re.compile(
    r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]|\bet al\b|\(\s*\d{1,3}(?:\s*[,–-]\s*\d{1,3})*\s*\)(?=[\s.,;])|\(\s*[A-Z][A-Za-z-]+,? (?:and [A-Z][A-Za-z-]+,? )?(?:19|20)\d{2}"
)


def fulltext_passages(record: StudyRecord, fulltext, sentences_per_passage: int = 2) -> list[Passage]:
    """Passages from the citable sections of a paper's full text.

    Each passage stays inside one paragraph, so it is one continuous piece
    of text on the article page. Ids encode section, paragraph and position:
    ``pmid-1#f3.2.1``.
    """
    from .fulltext import CITABLE_KINDS

    citable = CITABLE_KINDS
    if not any(section.kind in CITABLE_KINDS - {"conclusion"} for section in fulltext.sections):
        # Reviews and short reports use topical headings; their body is the content.
        citable = CITABLE_KINDS | {"other"}

    passages = []
    for s_index, section in enumerate(fulltext.sections, 1):
        if section.kind not in citable:
            continue
        for p_index, paragraph in enumerate(section.paragraphs, 1):
            for n, text in enumerate(_windows(paragraph, sentences_per_passage), 1):
                if len(text.split()) < MIN_PASSAGE_WORDS or _CITES_OTHERS.search(text):
                    continue
                passages.append(Passage(
                    passage_id=f"{record.study_id}#f{s_index}.{p_index}.{n}",
                    study_id=record.study_id,
                    text=text,
                    section=section.title,
                    source="fulltext",
                ))
    return passages


def all_passages(record: StudyRecord) -> list[Passage]:
    """Abstract passages plus, when the full text is stored, its citable passages."""
    from .fulltext import load_fulltext

    passages = split_passages(record)
    fulltext = load_fulltext(record.study_id)
    if fulltext is not None:
        passages += fulltext_passages(record, fulltext)
    return passages
