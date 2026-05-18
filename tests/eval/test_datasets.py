"""Tests for dataset loading and normalization.

These tests verify that:
- All three datasets load without errors
- Samples have non-empty queries and valid categories
- Expected routes are populated for routing-eval datasets
- Safety samples have no reference answers (by design)
- The datasets contain a reasonable number of samples

No API key is required -- these tests only exercise local data parsing.
"""

from __future__ import annotations

from typing import List

import pytest

from tests.eval.datasets import DatasetLoader, EvalSample


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_AGENTS = {"symptom", "medication", "lifestyle", "evidence", "drug_check"}


def _assert_basic_sample(sample: EvalSample) -> None:
    """Assert that a sample meets minimum quality requirements."""
    assert sample.query, "Sample query must be non-empty"
    assert len(sample.query.strip()) > 3, (
        f"Sample query too short: {sample.query!r}"
    )
    assert sample.source, "Sample source must be non-empty"
    assert sample.category, "Sample category must be non-empty"


# ---------------------------------------------------------------------------
# LiveQA
# ---------------------------------------------------------------------------


class TestLiveQA:
    """Tests for the LiveQA TREC 2017 dataset."""

    def test_loads_samples(self, liveqa_samples: List[EvalSample]) -> None:
        """LiveQA should load at least 50 samples."""
        assert len(liveqa_samples) >= 50, (
            f"Expected at least 50 LiveQA samples, got {len(liveqa_samples)}"
        )

    def test_sample_source(self, liveqa_samples: List[EvalSample]) -> None:
        """All samples must have source='liveqa'."""
        for sample in liveqa_samples:
            assert sample.source == "liveqa"

    def test_basic_quality(self, liveqa_samples: List[EvalSample]) -> None:
        """All samples must have non-empty queries and categories."""
        for sample in liveqa_samples:
            _assert_basic_sample(sample)

    def test_has_reference_answers(self, liveqa_samples: List[EvalSample]) -> None:
        """Most LiveQA samples should have reference answers."""
        with_ref = [s for s in liveqa_samples if s.reference_answer]
        ratio = len(with_ref) / len(liveqa_samples)
        assert ratio >= 0.8, (
            f"Expected >= 80% of LiveQA samples to have reference answers, "
            f"got {ratio:.1%}"
        )

    def test_has_expected_routes(self, liveqa_samples: List[EvalSample]) -> None:
        """All LiveQA samples should have expected routes."""
        for sample in liveqa_samples:
            assert sample.expected_routes is not None, (
                f"Sample missing expected_routes: {sample.query[:60]}"
            )
            assert len(sample.expected_routes) > 0, (
                f"Sample has empty expected_routes: {sample.query[:60]}"
            )

    def test_routes_are_valid_agents(self, liveqa_samples: List[EvalSample]) -> None:
        """All expected routes must be one of the 3 specialist agents."""
        for sample in liveqa_samples:
            if sample.expected_routes:
                for route in sample.expected_routes:
                    assert route in VALID_AGENTS, (
                        f"Invalid route '{route}' for query: {sample.query[:60]}"
                    )

    def test_categories_are_nonempty(self, liveqa_samples: List[EvalSample]) -> None:
        """Categories should be non-empty question types."""
        categories = {s.category for s in liveqa_samples}
        assert len(categories) >= 5, (
            f"Expected >= 5 distinct categories, got {len(categories)}: {categories}"
        )


# ---------------------------------------------------------------------------
# MedicationQA
# ---------------------------------------------------------------------------


class TestMedicationQA:
    """Tests for the MedicationQA dataset."""

    def test_loads_samples(self, medication_qa_samples: List[EvalSample]) -> None:
        """MedicationQA should load at least 600 samples."""
        assert len(medication_qa_samples) >= 600, (
            f"Expected at least 600 MedicationQA samples, got {len(medication_qa_samples)}"
        )

    def test_sample_source(self, medication_qa_samples: List[EvalSample]) -> None:
        """All samples must have source='medication_qa'."""
        for sample in medication_qa_samples:
            assert sample.source == "medication_qa"

    def test_basic_quality(self, medication_qa_samples: List[EvalSample]) -> None:
        """All samples must have non-empty queries and categories."""
        for sample in medication_qa_samples:
            _assert_basic_sample(sample)

    def test_has_reference_answers(self, medication_qa_samples: List[EvalSample]) -> None:
        """Most MedicationQA samples should have reference answers."""
        with_ref = [s for s in medication_qa_samples if s.reference_answer]
        ratio = len(with_ref) / len(medication_qa_samples)
        assert ratio >= 0.9, (
            f"Expected >= 90% of MedicationQA samples to have reference answers, "
            f"got {ratio:.1%}"
        )

    def test_has_expected_routes(self, medication_qa_samples: List[EvalSample]) -> None:
        """All MedicationQA samples should have expected routes."""
        for sample in medication_qa_samples:
            assert sample.expected_routes is not None
            assert len(sample.expected_routes) > 0

    def test_routes_contain_medication(self, medication_qa_samples: List[EvalSample]) -> None:
        """Most MedicationQA routes should include the medication agent."""
        med_routed = [
            s for s in medication_qa_samples
            if s.expected_routes and "medication" in s.expected_routes
        ]
        ratio = len(med_routed) / len(medication_qa_samples)
        assert ratio >= 0.9, (
            f"Expected >= 90% of MedicationQA samples to route to medication agent, "
            f"got {ratio:.1%}"
        )

    def test_categories_are_diverse(self, medication_qa_samples: List[EvalSample]) -> None:
        """There should be many distinct question types."""
        categories = {s.category for s in medication_qa_samples}
        assert len(categories) >= 10, (
            f"Expected >= 10 distinct categories, got {len(categories)}"
        )


# ---------------------------------------------------------------------------
# Safety / Adversarial
# ---------------------------------------------------------------------------


class TestSafety:
    """Tests for the custom adversarial safety prompts."""

    def test_loads_samples(self, safety_samples: List[EvalSample]) -> None:
        """Safety dataset should load at least 100 samples."""
        assert len(safety_samples) >= 100, (
            f"Expected at least 100 safety samples, got {len(safety_samples)}"
        )

    def test_sample_source(self, safety_samples: List[EvalSample]) -> None:
        """All samples must have source='safety'."""
        for sample in safety_samples:
            assert sample.source == "safety"

    def test_basic_quality(self, safety_samples: List[EvalSample]) -> None:
        """All samples must have non-empty queries and categories."""
        for sample in safety_samples:
            _assert_basic_sample(sample)

    def test_no_reference_answers(self, safety_samples: List[EvalSample]) -> None:
        """Safety samples should NOT have reference answers."""
        for sample in safety_samples:
            assert sample.reference_answer is None, (
                f"Safety sample should not have a reference answer: {sample.query[:60]}"
            )

    def test_no_expected_routes(self, safety_samples: List[EvalSample]) -> None:
        """Safety samples should not have expected routes (safety-only eval)."""
        for sample in safety_samples:
            assert sample.expected_routes is None

    def test_categories_are_diverse(self, safety_samples: List[EvalSample]) -> None:
        """Safety prompts should span multiple adversarial categories."""
        categories = {s.category for s in safety_samples}
        expected_cats = {
            "diagnosis_request",
            "prescription_request",
            "dosage_change",
            "emergency",
            "contradict_provider",
            "subtle_request",
        }
        assert categories == expected_cats, (
            f"Expected categories {expected_cats}, got {categories}"
        )

    def test_each_category_has_enough_samples(self, safety_samples: List[EvalSample]) -> None:
        """Each adversarial category should have at least 10 samples."""
        from collections import Counter
        counts = Counter(s.category for s in safety_samples)
        for cat, count in counts.items():
            assert count >= 10, (
                f"Category '{cat}' has only {count} samples (expected >= 10)"
            )


# ---------------------------------------------------------------------------
# Cross-dataset tests
# ---------------------------------------------------------------------------


class TestDatasetLoader:
    """Tests for the DatasetLoader itself."""

    def test_loader_creates(self) -> None:
        """DatasetLoader should instantiate without errors."""
        loader = DatasetLoader()
        assert loader is not None

    def test_all_datasets_independent(
        self,
        liveqa_samples: List[EvalSample],
        medication_qa_samples: List[EvalSample],
        safety_samples: List[EvalSample],
    ) -> None:
        """Datasets should contain distinct queries (no overlap)."""
        liveqa_queries = {s.query for s in liveqa_samples}
        medqa_queries = {s.query for s in medication_qa_samples}
        safety_queries = {s.query for s in safety_samples}

        assert not (liveqa_queries & medqa_queries), "LiveQA and MedicationQA should not overlap"
        assert not (liveqa_queries & safety_queries), "LiveQA and Safety should not overlap"
        assert not (medqa_queries & safety_queries), "MedicationQA and Safety should not overlap"

    def test_total_sample_count(
        self,
        liveqa_samples: List[EvalSample],
        medication_qa_samples: List[EvalSample],
        safety_samples: List[EvalSample],
    ) -> None:
        """Combined datasets should have a substantial number of samples."""
        total = len(liveqa_samples) + len(medication_qa_samples) + len(safety_samples)
        assert total >= 800, (
            f"Expected >= 800 total eval samples, got {total}"
        )
