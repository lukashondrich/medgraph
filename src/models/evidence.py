"""Evidence models shared by sources, the writer and the API.

``SourceItem`` is what a source hands to the writer: one citable piece of
evidence with everything needed to describe it honestly. ``Citation`` is
what the browser receives for each marker that survives the citation check.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EvidenceGroup = Literal["overall", "matched", "reference_range", "guideline", "safety"]


class SourceItem(BaseModel):
    """One citable piece of evidence gathered for the current turn."""

    id: str = Field(description="Stable id, unique across sources, e.g. 'study:pmid-123'")
    source: str = Field(description="Which source produced it, e.g. 'study_library'")
    group: EvidenceGroup
    study_id: str
    title: str
    authors: str
    year: int
    design: str = Field(description="Display label, e.g. 'Cross-sectional study'")
    sample_size: Optional[int] = None
    cohort_summary: str = ""
    countries: list[str] = Field(default_factory=list)
    matched_attributes: list[str] = Field(default_factory=list)
    passage: str = Field(description="Verbatim text from the study")
    statement: str = Field(
        default="", description="Curated plain-language statement (reference ranges only)"
    )
    url: str
    relevance: float = 0.0

    def describe(self) -> str:
        """One line for the writer prompt: what kind of evidence this is."""
        size = f"{self.sample_size:,} participants" if self.sample_size else "size not stated"
        parts = [f"{self.authors} {self.year}", self.design, size]
        if self.cohort_summary:
            parts.append(self.cohort_summary)
        if self.countries:
            parts.append("run in " + ", ".join(self.countries))
        return " · ".join(parts)


class Citation(BaseModel):
    """A validated citation as sent to the browser."""

    number: int
    group: EvidenceGroup
    study_id: str
    title: str
    authors: str
    year: int
    design: str
    sample_size: Optional[int] = None
    cohort_summary: str = ""
    countries: list[str] = Field(default_factory=list)
    matched_attributes: list[str] = Field(default_factory=list)
    passages: list[str] = Field(
        default_factory=list, description="Verbatim texts the cited claims rest on"
    )
    url: str

    @classmethod
    def from_source(cls, number: int, item: SourceItem) -> "Citation":
        fields = set(cls.model_fields) - {"number", "passages"}
        return cls(number=number, passages=[item.passage], **item.model_dump(include=fields))

    def absorb(self, item: SourceItem) -> None:
        """Fold another piece of evidence from the same study into this citation."""
        if item.passage not in self.passages:
            self.passages.append(item.passage)
        if _GROUP_PRIORITY[item.group] < _GROUP_PRIORITY[self.group]:
            self.group = item.group
        for attribute in item.matched_attributes:
            if attribute not in self.matched_attributes:
                self.matched_attributes.append(attribute)


# When one study is cited as several kinds of evidence, show it under the
# most specific group.
_GROUP_PRIORITY = {"safety": 0, "matched": 1, "reference_range": 2, "guideline": 3, "overall": 4}
