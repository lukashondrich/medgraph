from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer that merges dicts written by parallel source nodes.

    Each source writes its own keys; this keeps all of them. A new dict is
    returned each time (the inputs are not mutated).
    """
    return {**left, **right}


def _or_reduce(left: bool, right: bool) -> bool:
    """Reducer for safety_escalation: True if ANY node escalates."""
    return left or right


class MedGraphState(TypedDict):
    """LangGraph graph state. Central data contract for pH Companion.

    Reducer rules:
    - messages, handoff_chain, citations, retrieval_trace, safety_reasons:
      append via operator.add
    - sources: merge via _merge_dicts
    - safety_escalation: OR via _or_reduce
    - All other fields: replaced each turn
    """

    # Conversation history (appended each turn)
    messages: Annotated[list[dict[str, str]], operator.add]

    # Current turn input
    user_input: str

    # Response language code, e.g. "en" or "de"
    language: str

    # Serialized UserProfile, and the profile + reading context block that
    # the base agent appends to every system prompt
    patient: dict
    patient_summary: str

    # Serialized TestReading (or {} when no reading is selected)
    reading: dict

    # "new_reading" (automatic first interpretation) or "question"
    turn_kind: str

    # Planner outputs: chosen sources, search queries, and why
    route: list[str]
    queries: list[str]
    route_reasoning: str

    # Evidence gathered this turn: {source_item_id: serialized SourceItem}
    sources: Annotated[dict[str, dict], _merge_dicts]

    # What each source looked up: [{source, query, counts}]
    retrieval_trace: Annotated[list[dict], operator.add]

    # Set by the study library: {no_matched_evidence, unmatched_attributes}
    evidence_gap: dict

    # Safety rules that fired this turn, and whether any node escalated
    safety_reasons: Annotated[list[str], operator.add]
    safety_escalation: Annotated[bool, _or_reduce]

    # Writer outputs: the answer and its validated citations
    final_response: str
    citations: Annotated[list[dict], operator.add]

    # Tracking: node names in execution order
    handoff_chain: Annotated[list[str], operator.add]


# Backward compatibility alias
HealthcareState = MedGraphState
