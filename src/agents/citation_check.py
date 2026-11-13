"""Citation check: make sure every citation points at retrieved evidence.

Deterministic, no LLM. The writer marks claims with keys such as ``[S2]``;
this module validates those keys against what was gathered this turn,
removes any that do not exist, renumbers the rest in reading order and
builds the citation records sent to the browser.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from src.models.evidence import Citation, SourceItem

logger = logging.getLogger(__name__)

_MARKER = re.compile(r"\[\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*\]")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,;:!?])")


class CheckedAnswer(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    removed: list[str] = Field(
        default_factory=list, description="Marker keys that pointed at nothing"
    )


def check_citations(text: str, marker_map: dict[str, SourceItem]) -> CheckedAnswer:
    """Validate and renumber the citation markers in ``text``.

    Args:
        text: Writer output containing markers like ``[S1]`` or ``[S1, S3]``.
        marker_map: Marker key -> the evidence it stands for, for this turn.

    Returns:
        The text with markers rewritten as ``[1]``, ``[2]`` in order of first
        appearance, the matching citation records, and the removed keys.
        A study gets one number even when several pieces of its evidence are
        cited; the citation then carries each cited passage.
    """
    by_study: dict[str, Citation] = {}
    seen_keys: set[str] = set()
    removed: list[str] = []

    def rewrite(match: re.Match) -> str:
        out = []
        for key in re.split(r"\s*[,;]\s*", match.group(1)):
            item = marker_map.get(key)
            if item is None:
                removed.append(key)
                continue
            citation = by_study.get(item.study_id)
            if citation is None:
                citation = Citation.from_source(len(by_study) + 1, item)
                by_study[item.study_id] = citation
            elif key not in seen_keys:
                citation.absorb(item)
            seen_keys.add(key)
            token = f"[{citation.number}]"
            if token not in out:
                out.append(token)
        return "".join(out)

    checked = _MARKER.sub(rewrite, text)
    checked = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", checked)

    if removed:
        logger.warning("Removed citation markers with no source: %s", removed)

    citations = sorted(by_study.values(), key=lambda c: c.number)
    return CheckedAnswer(text=checked.strip(), citations=citations, removed=removed)
