"""Reference ranges: a curated lookup table, not a search.

Each row states what pH is expected for a group of women and quotes the
corpus study it comes from. The lookup is deterministic so it can be unit
tested and reviewed line by line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from src.data.profile import UserProfile
from src.knowledge_pipeline.study_schemas import CORPUS_DIR, StudyRecord
from src.models.evidence import SourceItem

from .deeplinks import quote_links

REFERENCE_RANGES_PATH = CORPUS_DIR / "reference_ranges.yaml"


class AppliesTo(BaseModel):
    menopausal_status: list[str] = Field(default_factory=list)
    pregnancy: list[str] = Field(default_factory=list)


class ReferenceRange(BaseModel):
    id: str
    label: str
    applies_to: AppliesTo = Field(default_factory=AppliesTo)
    statement: str
    study_id: str
    quote: str

    def applies(self, profile: UserProfile) -> bool:
        a = self.applies_to
        if a.menopausal_status and profile.menopausal_status.value not in a.menopausal_status:
            return False
        pregnancy = "pregnant" if profile.pregnancy.is_pregnant else "not_pregnant"
        if a.pregnancy and pregnancy not in a.pregnancy:
            return False
        return True


def load_reference_ranges(path: Path = REFERENCE_RANGES_PATH) -> list[ReferenceRange]:
    if not path.exists():
        return []
    return [ReferenceRange.model_validate(row) for row in yaml.safe_load(path.read_text()) or []]


def lookup_reference_ranges(
    profile: UserProfile,
    records: dict[str, StudyRecord],
    rows: Optional[list[ReferenceRange]] = None,
) -> list[SourceItem]:
    """Return the reference statements that apply to this profile.

    Rows whose study has no checked record are dropped: a range that cannot
    be cited is not shown.
    """
    rows = load_reference_ranges() if rows is None else rows
    items = []
    for row in rows:
        record = records.get(row.study_id)
        if record is None or not row.applies(profile):
            continue
        items.append(SourceItem(
            id=f"range:{row.id}",
            source="reference_ranges",
            group="reference_range",
            study_id=record.study_id,
            title=record.title,
            authors=record.authors,
            year=record.year,
            design=record.design_label,
            sample_size=record.sample_size,
            cohort_summary=record.cohort.description,
            countries=record.cohort.countries,
            passage=row.quote,
            quotes=[quote_links(record, row.quote)],
            statement=row.statement,
            url=record.url,
            relevance=1.0,
        ))
    return items
