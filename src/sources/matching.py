"""Cohort matching: how closely does a study's cohort resemble a user profile?

Pure functions over structured data. Ancestry matches wherever the study was
run; country of residence only adds a small bonus and is never required.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.data.profile import MenopausalStatus, UserProfile, ancestry_label
from src.knowledge_pipeline.study_schemas import ANCESTRY_PARENTS, StudyRecord

W_ANCESTRY_EXACT = 3.0
W_ANCESTRY_BROADER = 1.5
W_PREGNANT = 2.0
W_MENOPAUSAL = 1.0
W_NOT_PREGNANT = 0.5
W_AGE = 0.5
W_COUNTRY = 0.25

# Groups that most studies in this literature already include. Matching on
# them is shown and scored, but does not make a study "about women like
# you", for the same reason that being premenopausal does not.
NON_DISTINGUISHING_ANCESTRY = {"white_european"}


class CohortMatch(BaseModel):
    """Result of comparing one study cohort with one profile."""

    score: float = 0.0
    qualifying_score: float = Field(
        default=0.0,
        description="Score from distinguishing attributes only; ranks the matched lane",
    )
    qualifies: bool = Field(
        default=False,
        description="True when the study belongs in the 'women like you' lane",
    )
    matched_attributes: list[str] = Field(
        default_factory=list, description="Display strings, most important first"
    )
    ancestry_match: str = Field(
        default="none", description="'exact', 'broader' or 'none'"
    )


def _ancestry_match(profile_ancestry: str, cohort_ancestry: list[str]) -> str:
    if profile_ancestry in cohort_ancestry:
        return "exact"
    # A cohort that is a subgroup of the profile's group (profile: black,
    # cohort: african_american) counts as an exact match.
    if any(ANCESTRY_PARENTS.get(a) == profile_ancestry for a in cohort_ancestry):
        return "exact"
    parent = ANCESTRY_PARENTS.get(profile_ancestry)
    if parent and parent in cohort_ancestry:
        return "broader"
    return "none"


def match_cohort(profile: UserProfile, record: StudyRecord) -> CohortMatch:
    """Score a study's cohort against a profile."""
    cohort = record.cohort
    match = CohortMatch()
    qualifies = False

    match.ancestry_match = _ancestry_match(profile.ancestry, cohort.ancestry)
    if match.ancestry_match == "exact":
        match.score += W_ANCESTRY_EXACT
        match.matched_attributes.append(f"{ancestry_label(profile.ancestry)} ancestry")
        if profile.ancestry not in NON_DISTINGUISHING_ANCESTRY:
            match.qualifying_score += W_ANCESTRY_EXACT
            qualifies = True
    elif match.ancestry_match == "broader":
        parent = ANCESTRY_PARENTS[profile.ancestry]
        match.score += W_ANCESTRY_BROADER
        match.qualifying_score += W_ANCESTRY_BROADER
        match.matched_attributes.append(
            f"{ancestry_label(parent)} ancestry (broader group)"
        )
        qualifies = True

    if profile.pregnancy.is_pregnant and "pregnant" in cohort.pregnancy:
        match.score += W_PREGNANT
        match.qualifying_score += W_PREGNANT
        match.matched_attributes.append("pregnant")
        qualifies = True
    elif not profile.pregnancy.is_pregnant and "not_pregnant" in cohort.pregnancy:
        match.score += W_NOT_PREGNANT

    if profile.menopausal_status.value in cohort.menopausal_status:
        match.score += W_MENOPAUSAL
        match.matched_attributes.append(profile.menopausal_status.value)
        # Being premenopausal describes most study cohorts, so it does not
        # make a study "about women like you" by itself.
        if profile.menopausal_status is MenopausalStatus.POSTMENOPAUSAL:
            match.qualifying_score += W_MENOPAUSAL
            qualifies = True

    if (
        cohort.age_min is not None
        and cohort.age_max is not None
        and cohort.age_min <= profile.age <= cohort.age_max
    ):
        match.score += W_AGE
        match.matched_attributes.append("your age group")

    if profile.country_of_residence in cohort.countries:
        match.score += W_COUNTRY
        match.matched_attributes.append(f"lives in {profile.country_of_residence}")

    match.qualifies = qualifies
    return match


def distinguishing_attributes(profile: UserProfile) -> list[str]:
    """Attributes on which a matched study would be expected for this profile."""
    attributes = []
    if profile.ancestry not in NON_DISTINGUISHING_ANCESTRY:
        attributes.append(f"{ancestry_label(profile.ancestry)} ancestry")
    if profile.pregnancy.is_pregnant:
        attributes.append("pregnancy")
    if profile.menopausal_status is MenopausalStatus.POSTMENOPAUSAL:
        attributes.append("postmenopausal status")
    return attributes
