from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


def _merge_dicts(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Reducer that merges specialist output dicts.

    When multiple specialists run in parallel via ``Send()``, each returns a
    dict with its own key.  This reducer merges them so no output is lost.
    A new dict is returned each time (the original dicts are not mutated).
    """
    merged = {**left, **right}
    return merged


def _or_reduce(left: bool, right: bool) -> bool:
    """Reducer for safety_escalation: True if ANY branch escalates."""
    return left or right


class MedGraphState(TypedDict):
    """LangGraph graph state. Central data contract for the entire system.

    Extends the original HealthcareState with patient context, evidence
    retrieval, drug interaction screening, and citation tracking.

    Reducer rules:
    - messages, handoff_chain, citations: append via operator.add
    - specialist_outputs, evidence_context: merge via _merge_dicts
    - safety_escalation: OR via _or_reduce
    - All other fields: replaced each turn
    """

    # ── Original fields (unchanged) ──────────────────────────────────

    # Conversation history (appended each turn)
    messages: Annotated[list[dict[str, str]], operator.add]

    # Current turn input
    user_input: str

    # Router outputs
    route: list[str]
    route_reasoning: str

    # Specialist outputs: {agent_name: raw_response}
    specialist_outputs: Annotated[dict[str, str], _merge_dicts]

    # Synthesizer output
    final_response: str

    # Tracking
    handoff_chain: Annotated[list[str], operator.add]
    safety_escalation: Annotated[bool, _or_reduce]

    # ── New medgraph fields ──────────────────────────────────────────

    # Serialized PatientProfile dict (or {} when no patient loaded)
    patient: dict

    # Pre-formatted patient context string for prompt injection
    patient_summary: str

    # Evidence retrieved from Qdrant: {source_id: text}
    evidence_context: Annotated[dict[str, str], _merge_dicts]

    # Drug interaction screening results from OpenFDA
    drug_interactions: list[dict]

    # Citations from evidence + drug check agents: [{source, tier, grade, text}]
    citations: Annotated[list[dict], operator.add]

    # Which model tier the router used: "local" or "cloud"
    router_model_source: str


# Backward compatibility alias
HealthcareState = MedGraphState
