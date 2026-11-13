"""Search queries for the study library.

Queries are short and topical. The profile is deliberately not pasted into
them: it is applied through structured cohort matching instead.
"""

from __future__ import annotations

from src.data.profile import MenopausalStatus, TestReading, UserProfile

ELEVATED_ABOVE = 4.5


def reading_queries(profile: UserProfile, reading: TestReading) -> list[str]:
    """Fixed query set for the automatic interpretation of a new reading."""
    if profile.menopausal_status is MenopausalStatus.POSTMENOPAUSAL:
        queries = ["vaginal pH after menopause"]
    elif profile.pregnancy.is_pregnant:
        queries = [
            "vaginal pH during pregnancy",
            "vaginal pH self-testing in pregnancy and preterm birth",
        ]
    else:
        queries = ["normal vaginal pH in healthy women of reproductive age"]

    if reading.ph > ELEVATED_ABOVE:
        queries.append("causes of elevated vaginal pH")
        queries.append("vaginal pH as a sign of bacterial vaginosis")
    else:
        queries.append("low vaginal pH and lactobacilli")
    queries.append("vaginal lactobacilli in healthy women")
    return queries


def question_queries(question: str) -> list[str]:
    """Queries for a follow-up question (a router refines this later)."""
    question = " ".join(question.split())
    return [question] if question else []
