"""User profile and test reading models for pH Companion.

``UserProfile`` holds the personal attributes that matter for interpreting a
vaginal pH reading. ``TestReading`` is the structured output of the (stubbed)
strip-reading step. Both are plain Pydantic models loaded from JSON files in
``src/data/personas/``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MenopausalStatus(str, Enum):
    PREMENOPAUSAL = "premenopausal"
    PERIMENOPAUSAL = "perimenopausal"
    POSTMENOPAUSAL = "postmenopausal"


class PregnancyStatus(str, Enum):
    NOT_PREGNANT = "not_pregnant"
    FIRST_TRIMESTER = "first_trimester"
    SECOND_TRIMESTER = "second_trimester"
    THIRD_TRIMESTER = "third_trimester"

    @property
    def is_pregnant(self) -> bool:
        return self is not PregnancyStatus.NOT_PREGNANT


class UserProfile(BaseModel):
    """Personal attributes used to personalise the interpretation."""

    id: str = Field(description="Stable persona id, also the file name")
    name: str = Field(description="Display name")
    age: int = Field(ge=12, le=110)
    ancestry: str = Field(
        description="Key from the ancestry hierarchy, e.g. 'indian'"
    )
    country_of_residence: str = Field(description="Country name, e.g. 'Germany'")
    menopausal_status: MenopausalStatus
    pregnancy: PregnancyStatus = PregnancyStatus.NOT_PREGNANT
    cycle_regular: Optional[bool] = Field(
        default=None, description="None when not applicable or unknown"
    )
    cycle_day: Optional[int] = Field(default=None, ge=1, le=60)
    hormonal_contraception: Optional[str] = Field(
        default=None, description="Type, or None when not used"
    )
    hrt: Optional[str] = Field(
        default=None, description="Hormone therapy type, or None when not used"
    )
    recent_antibiotics: bool = False
    symptoms: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    headline: str = Field(default="", description="One-line summary for the gallery")

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class TestReading(BaseModel):
    """One strip reading as produced by the strip-reading step."""

    __test__ = False  # not a pytest test class

    ph: float = Field(ge=3.0, le=9.0)
    confidence: float = Field(ge=0.0, le=1.0, description="Reading confidence")
    taken_at: datetime

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


_ANCESTRY_LABELS = {
    "indian": "Indian",
    "south_asian": "South Asian",
    "black": "Black",
    "white_european": "White European",
}


def ancestry_label(key: str) -> str:
    """Human-readable label for an ancestry key."""
    return _ANCESTRY_LABELS.get(key, key.replace("_", " ").title())


def build_profile_summary(profile: UserProfile, reading: TestReading | None = None) -> str:
    """Format the profile (and reading) as a context block for prompts."""
    lines = [
        "--- USER PROFILE ---",
        f"Name: {profile.name} | Age: {profile.age}",
        f"Ancestry: {ancestry_label(profile.ancestry)} | Lives in: {profile.country_of_residence}",
        f"Menopausal status: {profile.menopausal_status.value}",
        f"Pregnancy: {profile.pregnancy.value.replace('_', ' ')}",
    ]
    if profile.cycle_regular is not None:
        cycle = "regular" if profile.cycle_regular else "irregular"
        if profile.cycle_day:
            cycle += f", day {profile.cycle_day}"
        lines.append(f"Cycle: {cycle}")
    lines.append(f"Hormonal contraception: {profile.hormonal_contraception or 'none'}")
    lines.append(f"Hormone therapy: {profile.hrt or 'none'}")
    lines.append(f"Antibiotics recently: {'yes' if profile.recent_antibiotics else 'no'}")
    lines.append(f"Current symptoms: {', '.join(profile.symptoms) or 'none reported'}")
    lines.append(f"Relevant history: {', '.join(profile.history) or 'none reported'}")
    lines.append("--- END USER PROFILE ---")
    if reading is not None:
        lines += [
            "",
            "--- TEST READING ---",
            f"Vaginal pH: {reading.ph:.1f}",
            f"Reading confidence: {round(reading.confidence * 100)}%",
            f"Taken at: {reading.taken_at.isoformat(timespec='minutes')}",
            "--- END TEST READING ---",
        ]
    return "\n".join(lines)
