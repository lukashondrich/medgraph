"""Corpus build for pH Companion: fetch, draft, check, index.

    python -m src.knowledge_pipeline.corpus draft 18803273 20534435 ...
    python -m src.knowledge_pipeline.corpus check
    python -m src.knowledge_pipeline.corpus build

``draft`` fetches title, abstract and identifiers from Europe PMC and lets an
LLM draft the structured study record. ``check`` runs a second, independent
LLM pass that verifies each field against the abstract. ``build`` indexes
the passages of checked records into the Qdrant study store. Records that
have not passed the check are never indexed.

The check is done by a model, not by a clinical expert.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import os
import re
import shutil
from datetime import date
from pathlib import Path

import httpx
import litellm

from .study_schemas import (
    ANCESTRY_KEYS,
    STUDIES_DIR,
    CheckInfo,
    CheckStatus,
    Cohort,
    Passage,
    StudyDesign,
    StudyRecord,
    load_record,
    load_records,
    all_passages,
    save_record,
)

logger = logging.getLogger(__name__)

EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
STUDY_COLLECTION = "womens_health_studies"
STUDY_STORE_PATH = Path(__file__).parent / "study_store"


# ── Fetch ─────────────────────────────────────────────────────────────────


def clean_abstract(raw: str) -> str:
    """Turn Europe PMC abstract markup into plain text.

    Structured-abstract headings (``<h4>Methods</h4>``) become "Methods: " so
    they do not run into the following sentence.
    """
    text = re.sub(r"<h4>\s*(.*?)\s*</h4>", lambda m: f" {m.group(1).rstrip(':.')}: ", raw or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def short_authors(author_string: str) -> str:
    """'Ravel J, Gajer P, Abdo Z.' -> 'Ravel et al.'"""
    authors = [a.strip() for a in (author_string or "").rstrip(".").split(",") if a.strip()]
    if not authors:
        return "Unknown authors"
    surname = authors[0].rsplit(" ", 1)[0]
    if len(authors) == 1:
        return surname
    if len(authors) == 2:
        return f"{surname} and {authors[1].rsplit(' ', 1)[0]}"
    return f"{surname} et al."


def fetch_paper(pmid: str) -> dict:
    """Fetch one paper's core record from Europe PMC by PubMed ID."""
    response = httpx.get(
        EUROPE_PMC_SEARCH,
        params={"query": f"EXT_ID:{pmid} AND SRC:MED", "format": "json", "resultType": "core"},
        headers={"User-Agent": "corpus-builder/0.1"},
        timeout=40,
    )
    response.raise_for_status()
    results = response.json().get("resultList", {}).get("result", [])
    if not results:
        raise LookupError(f"No Europe PMC record for PubMed ID {pmid}")
    r = results[0]
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("isoabbreviation") or ""
    affiliation = r.get("affiliation") or ""
    if not affiliation:
        for author in ((r.get("authorList") or {}).get("author") or [])[:1]:
            details = (author.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []
            if details:
                affiliation = details[0].get("affiliation", "")
    return {
        "pmid": str(r.get("pmid") or pmid),
        "doi": r.get("doi"),
        "title": html.unescape(re.sub(r"<[^>]+>", "", r.get("title", ""))).rstrip("."),
        "authors": short_authors(r.get("authorString", "")),
        "year": int(r.get("pubYear")),
        "journal": journal,
        "abstract": clean_abstract(r.get("abstractText", "")),
        "licence": r.get("license"),
        "affiliation": affiliation,
        "pub_types": ((r.get("pubTypeList") or {}).get("pubType") or []),
    }


# ── LLM helpers ───────────────────────────────────────────────────────────

_VOCAB = f"""Allowed values
- design: {", ".join(d.value for d in StudyDesign)}
- cohort.ancestry (list): {", ".join(sorted(ANCESTRY_KEYS))}
- cohort.menopausal_status (list): premenopausal, perimenopausal, postmenopausal
- cohort.pregnancy (list): pregnant, not_pregnant

Rules
- Use only the title, abstract, publication types and affiliation given. Never use outside knowledge about the paper.
- sample_size is the number of human participants analysed. Use null when it is not stated.
- cohort.countries: where participants were recruited. The affiliation may be used when the abstract names no place.
- cohort.ancestry: only what the text states. One exception: when participants were recruited locally in a single country and no other groups are mentioned, use that country's group (India -> indian, Pakistan -> pakistani, Nepal -> nepali). Never infer ancestry for studies in multi-ethnic countries such as the USA, UK, Canada, Netherlands or Brazil unless groups are named. A group called only "Asian" is asian_unspecified.
- Leave a list empty and a number null when the text does not say. Do not guess.
- age_min / age_max: only when an age range is stated.
"""

_DRAFT_PROMPT = """You extract structured study details from a paper abstract for a medical evidence library.

{vocab}
Return one JSON object with exactly these keys:
{{
  "design": "...",
  "sample_size": 123 or null,
  "cohort": {{
    "description": "short plain-language summary of who was studied, max 12 words",
    "ancestry": [], "countries": [], "age_min": null, "age_max": null,
    "menopausal_status": [], "pregnancy": []
  }},
  "topics": ["3 to 6 short topic keywords"],
  "key_finding": "one plain-language sentence stating the main finding, using only the abstract"
}}

Title: {title}
Journal: {journal} ({year})
Publication types: {pub_types}
Affiliation: {affiliation}
Abstract: {abstract}
"""

_CHECK_PROMPT = """You are checking a structured record that someone else extracted from a paper abstract. Be strict: your job is to catch errors.

{vocab}
For each field decide:
- "supported": the claimed value is backed by the text (or it is empty/null and the text indeed does not state it)
- "unsupported": the claimed value is wrong, not backed by the text, or it is empty although the text clearly states a value

Return one JSON object:
{{
  "fields": {{
    "design": {{"verdict": "...", "correct_value": null, "reason": ""}},
    "sample_size": {{...}},
    "cohort.ancestry": {{...}},
    "cohort.countries": {{...}},
    "cohort.age_range": {{...}},
    "cohort.menopausal_status": {{...}},
    "cohort.pregnancy": {{...}},
    "cohort.description": {{...}},
    "key_finding": {{...}}
  }}
}}
Give "correct_value" and a short "reason" only for unsupported fields.

Title: {title}
Journal: {journal} ({year})
Publication types: {pub_types}
Affiliation: {affiliation}
Abstract: {abstract}

Claimed record:
{claimed}
"""


async def _llm_json(prompt: str, model: str, attempts: int = 3) -> dict:
    """One JSON-mode LLM call with a timeout, retried on failure."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                ),
                timeout=90,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001 - timeout, provider or JSON error
            last_error = exc
    raise RuntimeError(f"LLM call failed after {attempts} attempts: {last_error!r}")


def _draft_model() -> str:
    return os.environ["MEDGRAPH_MODEL"]


def _check_model() -> str:
    """Model for the second pass.

    Set ``CORPUS_CHECK_MODEL`` to a different model than the drafting one so
    the two passes are independent. Without it the drafting model is reused
    and independence rests on the different, error-hunting prompt only.
    """
    return os.environ.get("CORPUS_CHECK_MODEL") or os.environ["MEDGRAPH_MODEL"]


# ── Draft ─────────────────────────────────────────────────────────────────


async def draft_record(pmid: str) -> StudyRecord:
    """Fetch a paper and draft its (unchecked) study record."""
    paper = fetch_paper(pmid)
    if not paper["abstract"]:
        raise ValueError(f"PubMed ID {pmid} has no abstract; cannot draft a record")
    extracted = await _llm_json(
        _DRAFT_PROMPT.format(vocab=_VOCAB, **{**paper, "pub_types": ", ".join(paper["pub_types"])}),
        _draft_model(),
    )
    record = StudyRecord(
        study_id=f"pmid-{paper['pmid']}",
        pmid=paper["pmid"],
        doi=paper["doi"],
        url=f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/",
        title=paper["title"],
        authors=paper["authors"],
        year=paper["year"],
        journal=paper["journal"],
        design=extracted["design"],
        sample_size=extracted.get("sample_size"),
        cohort=Cohort.model_validate(extracted.get("cohort") or {}),
        topics=extracted.get("topics") or [],
        key_finding=extracted.get("key_finding") or "",
        abstract=paper["abstract"],
        licence=paper["licence"],
        check=CheckInfo(status=CheckStatus.UNCHECKED, notes=f"affiliation: {paper['affiliation']}"),
    )
    errors = record.vocabulary_errors()
    if errors:
        raise ValueError(f"{record.study_id}: {'; '.join(errors)}")
    return record


# ── Check ─────────────────────────────────────────────────────────────────


def _claimed_fields(record: StudyRecord) -> dict:
    c = record.cohort
    return {
        "design": record.design.value,
        "sample_size": record.sample_size,
        "cohort.ancestry": c.ancestry,
        "cohort.countries": c.countries,
        "cohort.age_range": [c.age_min, c.age_max],
        "cohort.menopausal_status": c.menopausal_status,
        "cohort.pregnancy": c.pregnancy,
        "cohort.description": c.description,
        "key_finding": record.key_finding,
    }


def _affiliation_from_notes(notes: str) -> str:
    for line in notes.splitlines():
        if line.startswith("affiliation:"):
            return line.split(":", 1)[1].strip()
    return ""


async def check_record(record: StudyRecord) -> StudyRecord:
    """Run the second pass over one record and set its check status."""
    affiliation = _affiliation_from_notes(record.check.notes)
    model = _check_model()
    result = await _llm_json(
        _CHECK_PROMPT.format(
            vocab=_VOCAB,
            title=record.title,
            journal=record.journal,
            year=record.year,
            pub_types="",
            affiliation=affiliation,
            abstract=record.abstract,
            claimed=json.dumps(_claimed_fields(record), indent=2),
        ),
        model,
    )
    disputes = [
        f"{name}: should be {verdict.get('correct_value')!r} ({verdict.get('reason', '')})"
        for name, verdict in (result.get("fields") or {}).items()
        if verdict.get("verdict") != "supported"
    ]
    notes = [f"affiliation: {affiliation}"] + disputes
    record.check = CheckInfo(
        status=CheckStatus.DISPUTED if disputes else CheckStatus.CHECKED,
        checked_by=f"LLM second pass ({model})",
        checked_on=date.today(),
        notes="\n".join(notes),
    )
    return record


# ── Build ─────────────────────────────────────────────────────────────────


def collect_passages(studies_dir: Path = STUDIES_DIR) -> list[tuple[StudyRecord, Passage]]:
    """Passages of every checked record. Unchecked and disputed records are left out."""
    return [
        (record, passage)
        for record in load_records(studies_dir, checked_only=True).values()
        for passage in all_passages(record)
    ]


def build_index(
    studies_dir: Path = STUDIES_DIR,
    store_path: Path | str = STUDY_STORE_PATH,
) -> int:
    """Index passages of all checked records. Returns the passage count.

    The store is rebuilt from scratch each time. Records that are unchecked
    or disputed are skipped by ``load_records``.
    """
    from haystack import Document
    from haystack.components.embedders import SentenceTransformersDocumentEmbedder

    from .pipeline import DEFAULT_EMBEDDING_MODEL, get_document_store

    documents = [
        Document(
            id=passage.passage_id,
            content=passage.text,
            meta={
                "passage_id": passage.passage_id,
                "study_id": record.study_id,
                "title": record.title,
                "section": passage.section,
            },
        )
        for record, passage in collect_passages(studies_dir)
    ]

    location = str(store_path)
    if location != ":memory:" and Path(location).exists():
        shutil.rmtree(location)
    store = get_document_store(location=location, collection_name=STUDY_COLLECTION, recreate=True)
    if documents:
        embedder = SentenceTransformersDocumentEmbedder(
            model=DEFAULT_EMBEDDING_MODEL, meta_fields_to_embed=["title"]
        )
        embedder.warm_up()
        store.write_documents(embedder.run(documents=documents)["documents"])
    return len(documents)


# ── CLI ───────────────────────────────────────────────────────────────────


def _cmd_enrich() -> None:
    """Record which papers are in PubMed Central and download open-access full texts."""
    from .fulltext import FULLTEXT_DIR, fetch_fulltext, save_fulltext

    records = load_records(checked_only=False)
    pmids = [r.pmid for r in records.values() if r.pmid]
    found: dict[str, dict] = {}
    for i in range(0, len(pmids), 30):
        query = "SRC:MED AND EXT_ID:(" + " OR ".join(pmids[i:i + 30]) + ")"
        response = httpx.get(
            EUROPE_PMC_SEARCH,
            params={"query": query, "format": "json", "resultType": "lite", "pageSize": 100},
            headers={"User-Agent": "corpus-builder/0.1"},
            timeout=40,
        )
        response.raise_for_status()
        for hit in response.json()["resultList"]["result"]:
            found[hit.get("pmid", "")] = hit

    in_pmc = fetched = 0
    for record in records.values():
        hit = found.get(record.pmid or "", {})
        record.pmcid = hit.get("pmcid") or None
        record.open_access = bool(record.pmcid) and hit.get("isOpenAccess") == "Y"
        save_record(record)
        in_pmc += bool(record.pmcid)
        if record.open_access and not (FULLTEXT_DIR / f"{record.study_id}.json").exists():
            fulltext = fetch_fulltext(record.study_id, record.pmcid)
            if fulltext is None:
                print(f"no full text returned for {record.study_id} ({record.pmcid})")
                continue
            save_fulltext(fulltext)
            fetched += 1
            kinds = ", ".join(f"{s.kind}:{len(s.paragraphs)}" for s in fulltext.sections)
            print(f"full text {record.study_id} ({record.pmcid}): {kinds[:110]}")
    stored = len(list(FULLTEXT_DIR.glob("*.json"))) if FULLTEXT_DIR.exists() else 0
    print(f"{len(records)} records | {in_pmc} in PubMed Central | {stored} full texts stored ({fetched} new)")


async def _cmd_draft(pmids: list[str], force: bool) -> None:
    for pmid in pmids:
        path = STUDIES_DIR / f"pmid-{pmid}.yaml"
        if path.exists() and not force:
            print(f"skip  pmid-{pmid} (exists; use --force to redraft)")
            continue
        try:
            record = await draft_record(pmid)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  pmid-{pmid}: {exc}")
            continue
        save_record(record)
        print(f"draft {record.study_id}: {record.design.value}, n={record.sample_size}, {record.cohort.description}")


async def _cmd_check(recheck: bool) -> None:
    for path in sorted(STUDIES_DIR.glob("*.yaml")):
        record = load_record(path)
        if record.check.status is CheckStatus.CHECKED and not recheck:
            continue
        record = await check_record(record)
        save_record(record)
        print(f"{record.check.status.value:9} {record.study_id}")
        if record.check.status is CheckStatus.DISPUTED:
            for line in record.check.notes.splitlines()[1:]:
                print(f"          - {line}")


def main() -> None:
    from src.config import load_config

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_draft = sub.add_parser("draft", help="fetch papers and draft records")
    p_draft.add_argument("pmids", nargs="+")
    p_draft.add_argument("--force", action="store_true")
    p_check = sub.add_parser("check", help="second-pass check of unchecked records")
    p_check.add_argument("--recheck", action="store_true", help="also re-run checked records")
    sub.add_parser("build", help="index checked records into the study store")
    sub.add_parser("enrich", help="look up PubMed Central ids and download open-access full texts")
    args = parser.parse_args()

    if args.command == "enrich":
        _cmd_enrich()
        return

    if args.command == "build":
        count = build_index()
        total = len(list(STUDIES_DIR.glob("*.yaml")))
        indexed = len(load_records(checked_only=True))
        print(f"indexed {count} passages from {indexed} checked records ({total - indexed} skipped)")
        return

    load_config()
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    if args.command == "draft":
        asyncio.run(_cmd_draft(args.pmids, args.force))
    else:
        asyncio.run(_cmd_check(args.recheck))


if __name__ == "__main__":
    main()
