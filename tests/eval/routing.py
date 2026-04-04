"""Routing evaluation: measures how accurately the router classifies queries.

The ``RoutingEvaluator`` runs labelled ``EvalSample`` instances through the
``RouterAgent`` and computes accuracy, per-category F1, and a confusion
matrix.

The ``RouterAdapter`` wraps the real ``RouterAgent`` to satisfy the generic
``RouterProtocol`` expected by the evaluator.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from tests.eval.datasets import EvalSample

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Router protocol -- what we need from the router agent
# ---------------------------------------------------------------------------


@runtime_checkable
class RouterProtocol(Protocol):
    """Minimal interface the router agent must satisfy for eval.

    Any object with an async ``route`` method that accepts a query string
    and returns a list of specialist names (e.g. ``["symptom", "medication"]``)
    is compatible.
    """

    async def route(self, query: str) -> List[str]:
        """Classify a patient query and return the target specialist name(s)."""
        ...


# ---------------------------------------------------------------------------
# Adapter: real RouterAgent -> RouterProtocol
# ---------------------------------------------------------------------------


class RouterAdapter:
    """Wraps the real ``RouterAgent`` to satisfy ``RouterProtocol``.

    The ``RouterAgent`` expects a full ``HealthcareState`` dict and returns
    a partial state update.  This adapter builds a minimal state from a
    plain query string and extracts the ``route`` list from the result.
    """

    def __init__(self, router_agent: Any) -> None:
        self._router = router_agent

    async def route(self, query: str) -> List[str]:
        """Route a query string through the real router agent."""
        state: dict[str, Any] = {
            "messages": [],
            "user_input": query,
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
        }
        result = await self._router(state)
        return result.get("route", [])


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------


class MisroutedSample(BaseModel):
    """A sample that the router misclassified."""

    query: str
    expected_routes: List[str]
    predicted_routes: List[str]
    category: str


class RoutingReport(BaseModel):
    """Full routing-evaluation results."""

    accuracy: float = Field(
        ...,
        description="Fraction of samples where predicted route(s) exactly match expected route(s)",
        ge=0.0,
        le=1.0,
    )
    f1_per_category: Dict[str, float] = Field(
        ...,
        description="Per-specialist-agent F1 score (micro-averaged across samples)",
    )
    confusion_matrix: Dict[str, Dict[str, int]] = Field(
        ...,
        description=(
            "Confusion counts: outer key = expected agent, "
            "inner key = predicted agent, value = count"
        ),
    )
    misrouted_samples: List[MisroutedSample] = Field(
        default_factory=list,
        description="Samples where the router made a mistake (for debugging)",
    )
    total_samples: int = Field(..., description="Total number of samples evaluated")
    correct_samples: int = Field(..., description="Number of exactly-correct predictions")


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class RoutingEvaluator:
    """Evaluates router accuracy against labelled test data.

    Usage
    -----
    Once the ``RouterAgent`` is available::

        from src.agents.router import RouterAgent
        evaluator = RoutingEvaluator()
        report = await evaluator.evaluate(samples, RouterAgent())
    """

    async def evaluate(
        self,
        samples: List[EvalSample],
        router: Any,
    ) -> RoutingReport:
        """Run all samples through the router and compute metrics.

        Parameters
        ----------
        samples : list[EvalSample]
            Labelled evaluation samples.  Each must have ``expected_routes``
            populated (samples without expected routes are skipped).
        router : RouterProtocol
            Any object satisfying the ``RouterProtocol`` (an async ``route``
            method).  Typically the ``RouterAgent`` from ``src/``.

        Returns
        -------
        RoutingReport
            Accuracy, F1 scores, confusion matrix, and misrouted samples.

        Raises
        ------
        NotImplementedError
            If the router does not satisfy ``RouterProtocol``.
        """
        # Validate router interface
        if not hasattr(router, "route") or not callable(getattr(router, "route")):
            raise NotImplementedError(
                "The provided router does not have a callable 'route' method. "
                "The RouterAgent from src/agents/router.py is required."
            )

        # Filter to samples with expected routes
        labelled = [s for s in samples if s.expected_routes]
        if not labelled:
            raise ValueError("No samples with expected_routes provided.")

        # Collect predictions
        all_agents = {"symptom", "medication", "lifestyle"}
        correct = 0
        misrouted: List[MisroutedSample] = []
        # Per-agent TP/FP/FN for F1
        tp: Dict[str, int] = defaultdict(int)
        fp: Dict[str, int] = defaultdict(int)
        fn: Dict[str, int] = defaultdict(int)
        # Confusion matrix
        confusion: Dict[str, Dict[str, int]] = {
            a: {b: 0 for b in all_agents} for a in all_agents
        }

        for sample in labelled:
            try:
                predicted = await router.route(sample.query)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Router failed for query: %s", sample.query[:80]
                )
                predicted = []

            predicted_set = set(predicted)
            expected_set = set(sample.expected_routes)  # type: ignore[arg-type]

            # Exact match accuracy
            if predicted_set == expected_set:
                correct += 1
            else:
                misrouted.append(
                    MisroutedSample(
                        query=sample.query,
                        expected_routes=sample.expected_routes,  # type: ignore[arg-type]
                        predicted_routes=predicted,
                        category=sample.category,
                    )
                )

            # Per-agent TP/FP/FN
            for agent in all_agents:
                if agent in expected_set and agent in predicted_set:
                    tp[agent] += 1
                elif agent not in expected_set and agent in predicted_set:
                    fp[agent] += 1
                elif agent in expected_set and agent not in predicted_set:
                    fn[agent] += 1

            # Confusion matrix (each expected -> each predicted)
            for exp in expected_set:
                for pred in predicted_set:
                    if exp in confusion and pred in confusion[exp]:
                        confusion[exp][pred] += 1

        total = len(labelled)
        accuracy = correct / total if total > 0 else 0.0

        # Compute F1 per agent
        f1_per_category: Dict[str, float] = {}
        for agent in sorted(all_agents):
            precision = tp[agent] / (tp[agent] + fp[agent]) if (tp[agent] + fp[agent]) > 0 else 0.0
            recall = tp[agent] / (tp[agent] + fn[agent]) if (tp[agent] + fn[agent]) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            f1_per_category[agent] = round(f1, 4)

        return RoutingReport(
            accuracy=round(accuracy, 4),
            f1_per_category=f1_per_category,
            confusion_matrix=confusion,
            misrouted_samples=misrouted,
            total_samples=total,
            correct_samples=correct,
        )
