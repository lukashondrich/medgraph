"""Specialist response quality evaluation using grouped LLM judge calls.

Runs a small subset of queries through the full orchestration graph, then
scores each response using three judge groups: clinical quality (vs reference),
communication, and questioning.

Requires an API key (makes real LLM calls for both the system and the judge).
"""

from __future__ import annotations

from typing import List

import pytest

from tests.eval.conftest import requires_api_key
from tests.eval.datasets import EvalSample
from tests.eval.judge import GroupResult

# How many samples to evaluate (each needs 4 LLM round-trips:
# one for the system, three for the judge groups)
_QUALITY_SAMPLE_SIZE = 20

# Minimum acceptable average pass rate across all groups
_MIN_AVG_PASS_RATE = 0.5


def _samples_with_reference(
    liveqa: List[EvalSample],
    medqa: List[EvalSample],
    n: int,
) -> List[EvalSample]:
    """Select up to n samples that have reference answers."""
    pool = [s for s in liveqa + medqa if s.reference_answer]
    return pool[:n]


def _build_initial_state(query: str) -> dict:
    """Build a minimal HealthcareState dict for graph.ainvoke()."""
    return {
        "messages": [],
        "user_input": query,
        "route": [],
        "route_reasoning": "",
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
    }


def _aggregate_pass_rate(*groups: GroupResult) -> float:
    """Compute combined pass rate across multiple GroupResults."""
    total_applicable = sum(g.applicable_count for g in groups)
    if total_applicable == 0:
        return 1.0
    total_passed = sum(
        sum(1 for s in g.scores.values() if s.score == 1)
        for g in groups
    )
    return total_passed / total_applicable


@pytest.mark.eval
@requires_api_key
class TestResponseQuality:
    """Evaluate response quality via grouped LLM judge calls."""

    @pytest.mark.asyncio
    async def test_quality_scores(
        self,
        graph,
        judge,
        liveqa_samples: List[EvalSample],
        medication_qa_samples: List[EvalSample],
    ) -> None:
        """Average pass rate across all groups should meet threshold."""
        samples = _samples_with_reference(
            liveqa_samples, medication_qa_samples, _QUALITY_SAMPLE_SIZE
        )
        assert len(samples) > 0, "No samples with reference answers found"

        pass_rates: list[float] = []
        details: list[dict] = []

        for sample in samples:
            state = _build_initial_state(sample.query)
            result = await graph.ainvoke(state)
            response = result.get("final_response", "")

            if not response:
                pass_rates.append(0.0)
                details.append({
                    "query": sample.query[:80],
                    "pass_rate": 0.0,
                    "note": "empty response",
                })
                continue

            # Run all three judge groups
            clinical = await judge.evaluate_clinical_quality(
                query=sample.query,
                agent_response=response,
                reference_answer=sample.reference_answer,
            )
            communication = await judge.evaluate_communication(
                query=sample.query,
                agent_response=response,
            )
            questioning = await judge.evaluate_questioning(
                query=sample.query,
                agent_response=response,
            )

            combined = _aggregate_pass_rate(clinical, communication, questioning)
            pass_rates.append(combined)

            details.append({
                "query": sample.query[:80],
                "pass_rate": combined,
                "clinical": clinical.pass_rate,
                "communication": communication.pass_rate,
                "questioning": questioning.pass_rate,
                "clinical_applicable": clinical.applicable_count,
                "questioning_applicable": questioning.applicable_count,
            })

        avg_pass_rate = sum(pass_rates) / len(pass_rates) if pass_rates else 0.0

        # Print report
        print(f"\n{'='*60}")
        print(f"Quality Report ({len(samples)} samples)")
        print(f"{'='*60}")
        print(f"Average pass rate: {avg_pass_rate:.3f}")
        print(f"Min: {min(pass_rates):.3f}  Max: {max(pass_rates):.3f}")

        # Per-group averages
        clinical_rates = [d["clinical"] for d in details if "clinical" in d]
        comm_rates = [d["communication"] for d in details if "communication" in d]
        quest_rates = [d["questioning"] for d in details if "questioning" in d]
        if clinical_rates:
            print(f"\nGroup averages:")
            print(f"  Clinical Quality: {sum(clinical_rates)/len(clinical_rates):.3f}")
            print(f"  Communication:    {sum(comm_rates)/len(comm_rates):.3f}")
            print(f"  Questioning:      {sum(quest_rates)/len(quest_rates):.3f}")

        print(f"\nPer-sample scores:")
        for d in details:
            if "note" in d:
                print(f"  [{d['pass_rate']:.2f}] {d['query']}... ({d['note']})")
            else:
                print(
                    f"  [{d['pass_rate']:.2f}] {d['query']}... "
                    f"(clin={d['clinical']:.2f} comm={d['communication']:.2f} "
                    f"quest={d['questioning']:.2f})"
                )

        assert avg_pass_rate >= _MIN_AVG_PASS_RATE, (
            f"Average pass rate {avg_pass_rate:.3f} below threshold "
            f"{_MIN_AVG_PASS_RATE}"
        )
