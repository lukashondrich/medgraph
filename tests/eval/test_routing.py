"""Routing accuracy evaluation against the real RouterAgent.

Runs labelled LiveQA + MedicationQA samples through the router and measures
exact-match accuracy, per-agent F1, and produces a confusion matrix.

Requires an API key (makes real LLM calls).
"""

from __future__ import annotations

from typing import List

import pytest

from tests.eval.conftest import requires_api_key
from tests.eval.datasets import EvalSample
from tests.eval.routing import RoutingEvaluator

# Subsample sizes -- keep eval fast while still meaningful
_LIVEQA_SAMPLE_SIZE = 30
_MEDQA_SAMPLE_SIZE = 30

# Minimum acceptable accuracy (intentionally low for a first pass --
# our route labels are best-guess mappings from question types)
_MIN_ACCURACY = 0.3


def _subsample(samples: List[EvalSample], n: int) -> List[EvalSample]:
    """Take the first n samples with expected_routes."""
    labelled = [s for s in samples if s.expected_routes]
    return labelled[:n]


@pytest.mark.eval
@requires_api_key
class TestRoutingAccuracy:
    """Evaluate routing accuracy against real LLM router."""

    @pytest.mark.asyncio
    async def test_liveqa_routing(
        self,
        router,
        liveqa_samples: List[EvalSample],
    ) -> None:
        """Routing accuracy on LiveQA subset."""
        subset = _subsample(liveqa_samples, _LIVEQA_SAMPLE_SIZE)
        assert len(subset) > 0, "No LiveQA samples with expected_routes"

        evaluator = RoutingEvaluator()
        report = await evaluator.evaluate(subset, router)

        # Print report for inspection
        print(f"\n{'='*60}")
        print(f"LiveQA Routing Report ({report.total_samples} samples)")
        print(f"{'='*60}")
        print(f"Accuracy: {report.accuracy:.2%} ({report.correct_samples}/{report.total_samples})")
        print(f"F1 per agent: {report.f1_per_category}")
        print(f"Confusion matrix: {report.confusion_matrix}")
        if report.misrouted_samples:
            print(f"\nMisrouted ({len(report.misrouted_samples)}):")
            for m in report.misrouted_samples[:5]:
                print(f"  Q: {m.query[:80]}...")
                print(f"    expected={m.expected_routes}, predicted={m.predicted_routes}")

        assert report.accuracy >= _MIN_ACCURACY, (
            f"LiveQA routing accuracy {report.accuracy:.2%} below threshold {_MIN_ACCURACY:.0%}"
        )

    @pytest.mark.asyncio
    async def test_medication_qa_routing(
        self,
        router,
        medication_qa_samples: List[EvalSample],
    ) -> None:
        """Routing accuracy on MedicationQA subset."""
        subset = _subsample(medication_qa_samples, _MEDQA_SAMPLE_SIZE)
        assert len(subset) > 0, "No MedicationQA samples with expected_routes"

        evaluator = RoutingEvaluator()
        report = await evaluator.evaluate(subset, router)

        print(f"\n{'='*60}")
        print(f"MedicationQA Routing Report ({report.total_samples} samples)")
        print(f"{'='*60}")
        print(f"Accuracy: {report.accuracy:.2%} ({report.correct_samples}/{report.total_samples})")
        print(f"F1 per agent: {report.f1_per_category}")
        if report.misrouted_samples:
            print(f"\nMisrouted ({len(report.misrouted_samples)}):")
            for m in report.misrouted_samples[:5]:
                print(f"  Q: {m.query[:80]}...")
                print(f"    expected={m.expected_routes}, predicted={m.predicted_routes}")

        assert report.accuracy >= _MIN_ACCURACY, (
            f"MedicationQA routing accuracy {report.accuracy:.2%} below threshold {_MIN_ACCURACY:.0%}"
        )

    @pytest.mark.asyncio
    async def test_combined_routing(
        self,
        router,
        liveqa_samples: List[EvalSample],
        medication_qa_samples: List[EvalSample],
    ) -> None:
        """Combined routing accuracy across both datasets."""
        subset = (
            _subsample(liveqa_samples, _LIVEQA_SAMPLE_SIZE)
            + _subsample(medication_qa_samples, _MEDQA_SAMPLE_SIZE)
        )
        assert len(subset) > 0, "No samples with expected_routes"

        evaluator = RoutingEvaluator()
        report = await evaluator.evaluate(subset, router)

        print(f"\n{'='*60}")
        print(f"Combined Routing Report ({report.total_samples} samples)")
        print(f"{'='*60}")
        print(f"Accuracy: {report.accuracy:.2%} ({report.correct_samples}/{report.total_samples})")
        print(f"F1 per agent: {report.f1_per_category}")

        assert report.accuracy >= _MIN_ACCURACY, (
            f"Combined routing accuracy {report.accuracy:.2%} below threshold {_MIN_ACCURACY:.0%}"
        )
