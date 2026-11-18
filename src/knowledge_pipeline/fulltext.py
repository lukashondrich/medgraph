"""Full text of open-access papers, fetched from Europe PMC as JATS XML.

Stored as one JSON file per paper under ``data/corpus/fulltext/``. Only
running text is kept: paragraphs grouped by section. Tables, figures,
captions and reference lists are left out.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from .study_schemas import CORPUS_DIR

FULLTEXT_DIR = CORPUS_DIR / "fulltext"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

# Sections whose sentences may be cited as what the study found. Background
# and methods are shown in the reader but never offered to the writer: an
# introduction mostly reports other people's findings.
CITABLE_KINDS = {"results", "discussion", "conclusion", "review"}

_KIND_PATTERNS = [
    ("results", r"result|finding"),
    ("discussion", r"discussion|interpretation|comment"),
    ("conclusion", r"conclusion|summary|implication"),
    ("methods", r"method|material|participant|patients and|study design|statistic|procedure"),
    ("introduction", r"introduction|background|rationale"),
]
_SKIP_SECTION = re.compile(
    r"fund|acknowledg|conflict|competing|author|contribut|supplement|abbreviation|ethic|"
    r"data availab|disclosure|reference|supporting information|consent|publisher|"
    r"sources of support|pre-publication|financial",
    re.I,
)
_SKIP_TAGS = {"table-wrap", "fig", "table", "caption", "disp-formula", "supplementary-material", "ref-list"}


class Section(BaseModel):
    title: str
    kind: str = "other"
    paragraphs: list[str] = Field(default_factory=list)


class FullText(BaseModel):
    study_id: str
    pmcid: str = ""
    source: str = Field(default="europepmc", description="'europepmc' (official full text) or 'pdf' (extracted)")
    sections: list[Section] = Field(default_factory=list)

    @property
    def paragraph_count(self) -> int:
        return sum(len(s.paragraphs) for s in self.sections)


def classify_section(title: str) -> str:
    for kind, pattern in _KIND_PATTERNS:
        if re.search(pattern, title, re.I):
            return kind
    return "other"


def _text(element: ET.Element) -> str:
    """Running text of an element, without tables, figures and formulas."""
    parts = [element.text or ""]
    for child in element:
        if child.tag not in _SKIP_TAGS:
            parts.append(_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _clean(text: str) -> str:
    return re.sub(r"[ \t\r\n]+", " ", text).strip()


def _collect(sec: ET.Element, title: str, kind: str, out: list[Section]) -> None:
    """Add this section's own paragraphs, then walk its subsections.

    A subsection inherits the kind of its parent when its own title says
    nothing (for example "Vaginal pH" inside "Results").
    """
    paragraphs = [_clean(_text(p)) for p in sec.findall("p")]
    paragraphs = [p for p in paragraphs if p]
    if paragraphs:
        out.append(Section(title=title, kind=kind, paragraphs=paragraphs))
    for sub in sec.findall("sec"):
        sub_title = _clean(sub.findtext("title") or "") or title
        if _SKIP_SECTION.search(sub_title) or sub.get("sec-type") in {"ref-list", "supplementary-material"}:
            continue
        sub_kind = classify_section(sub_title)
        _collect(sub, sub_title, kind if sub_kind == "other" else sub_kind, out)


def parse_jats(xml_text: str, study_id: str, pmcid: str) -> FullText:
    """Turn a JATS article into sections of plain paragraphs."""
    root = ET.fromstring(xml_text)
    for element in root.iter():  # drop namespaces so tags can be matched by name
        if "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    sections: list[Section] = []
    body = root.find("body")
    if body is None:
        return FullText(study_id=study_id, pmcid=pmcid)
    loose = [_clean(_text(p)) for p in body.findall("p")]
    loose = [p for p in loose if p]
    if loose:  # short papers and letters have no section headings
        sections.append(Section(title="Text", kind="results", paragraphs=loose))
    for sec in body.findall("sec"):
        title = _clean(sec.findtext("title") or "") or "Text"
        if _SKIP_SECTION.search(title) or sec.get("sec-type") in {"ref-list", "supplementary-material"}:
            continue
        _collect(sec, title, classify_section(title), sections)
    return FullText(study_id=study_id, pmcid=pmcid, sections=sections)


def fetch_fulltext(study_id: str, pmcid: str) -> Optional[FullText]:
    """Download and parse the full text, or None when Europe PMC has none."""
    response = httpx.get(
        EUROPE_PMC_FULLTEXT.format(pmcid=pmcid),
        headers={"User-Agent": "corpus-builder/0.1"},
        timeout=60,
        follow_redirects=True,
    )
    if response.status_code != 200 or "<body" not in response.text:
        return None
    fulltext = parse_jats(response.text, study_id, pmcid)
    return fulltext if fulltext.paragraph_count else None


def save_fulltext(fulltext: FullText, directory: Path = FULLTEXT_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{fulltext.study_id}.json"
    path.write_text(json.dumps(fulltext.model_dump(), ensure_ascii=False, indent=1))
    return path


def load_fulltext(study_id: str, directory: Path = FULLTEXT_DIR) -> Optional[FullText]:
    path = directory / f"{study_id}.json"
    if not path.exists():
        return None
    return FullText.model_validate(json.loads(path.read_text()))
