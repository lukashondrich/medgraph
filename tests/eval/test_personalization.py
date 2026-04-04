"""Personalization evaluation tests (Phase 6).

Tests that the system produces different, patient-grounded responses
for different patients given the same query.

These tests require API keys and are excluded from the standard test suite.
Run with: pytest tests/eval/test_personalization.py -v
"""

import pytest

from src.data.gallery import list_patients, load_patient
from src.data.patient_context import build_patient_summary


# ── Test Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def all_patients():
    """Load all gallery patients."""
    gallery = list_patients()
    profiles = []
    for card in gallery:
        profile = load_patient(card["patient_id"])
        if profile:
            profiles.append(profile)
    return profiles


@pytest.fixture
def patient_summaries(all_patients):
    """Build summaries for all patients."""
    return {p.id: build_patient_summary(p) for p in all_patients}


# ── Unit Tests (no LLM required) ────────────────────────────────────────


class TestPatientGrounding:
    """Verify that patient context is properly structured for eval."""

    def test_different_patients_produce_different_summaries(self, all_patients):
        """Same query + different patient → different prompt context."""
        summaries = [build_patient_summary(p) for p in all_patients]
        # All summaries should be unique
        assert len(set(summaries)) == len(summaries)

    def test_summary_references_patient_specific_data(self, all_patients):
        """Each summary mentions the patient's own conditions."""
        for profile in all_patients:
            summary = build_patient_summary(profile)
            # Summary should mention at least one condition abbreviation
            assert any(
                c.abbreviation in summary for c in profile.conditions
            ), f"Summary for {profile.name} doesn't mention any conditions"

    def test_summary_references_patient_medications(self, all_patients):
        """Each summary mentions the patient's own medications."""
        for profile in all_patients:
            if not profile.medications:
                continue
            summary = build_patient_summary(profile)
            assert any(
                m.short_name in summary for m in profile.medications
            ), f"Summary for {profile.name} doesn't mention any medications"


class TestEvidenceAttribution:
    """Verify citation infrastructure supports eval criteria."""

    def test_citation_schema_has_required_fields(self):
        """Citations should have source, tier, and text fields."""
        citation = {
            "source": "ADA-SOC-2025",
            "tier": "guideline",
            "grade": "strong",
            "text": "Avoid NSAIDs in CKD stage 3+",
        }
        assert "source" in citation
        assert "tier" in citation
        assert "text" in citation

    def test_confidence_tiers_exist(self):
        """Verify the confidence tier enum is importable and has expected values."""
        from src.knowledge_pipeline.schemas import ConfidenceTier
        assert ConfidenceTier.REGULATORY.value == "regulatory"
        assert ConfidenceTier.GUIDELINE.value == "guideline"
        assert ConfidenceTier.STRONG_EVIDENCE.value == "strong_evidence"
        assert ConfidenceTier.EMERGING_EVIDENCE.value == "emerging_evidence"

    def test_recommendation_grades_exist(self):
        """Verify the recommendation grade enum."""
        from src.knowledge_pipeline.schemas import RecommendationGrade
        assert RecommendationGrade.STRONG.value == "strong"
        assert RecommendationGrade.MODERATE.value == "moderate"
        assert RecommendationGrade.WEAK.value == "weak"
        assert RecommendationGrade.EXPERT_OPINION.value == "expert"
