"""LangGraph StateGraph construction for the medgraph multiagent system.

Graph flow:
    START -> router -> conditional_edges -> specialist(s) -> synthesizer -> END

The router node classifies the user query and selects 1-5 specialist agents.
A pure routing function reads ``state["route"]`` and dispatches to the selected
specialists in parallel via LangGraph ``Send()``.  All specialist branches
converge at the synthesizer, which merges their outputs into the final response.

When the router returns an empty route (off-topic / inappropriate query), the
graph skips specialists and goes directly to the synthesizer for a fallback
response.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

logger = logging.getLogger(__name__)

from src.agents.drug_check import DrugCheckAgent
from src.agents.evidence import EvidenceAgent
from src.agents.lifestyle import LifestyleAgent
from src.agents.medication import MedicationAgent
from src.agents.router import RouterAgent
from src.agents.symptom import SymptomAgent
from src.agents.synthesizer import SynthesizerAgent
from src.models.state import MedGraphState

# ---------------------------------------------------------------------------
# Map from route labels (as produced by the router) to graph node names
# ---------------------------------------------------------------------------
AGENT_NODE_MAP: dict[str, str] = {
    "symptom": "symptom_agent",
    "medication": "medication_agent",
    "lifestyle": "lifestyle_agent",
    "evidence": "evidence_agent",
    "drug_check": "drug_check_agent",
}


def route_to_specialists(state: MedGraphState) -> list[Send]:
    """Pure routing function -- reads ``state["route"]`` and returns ``Send`` objects.

    This function contains **no** LLM calls.  It is deterministic given the
    current state.

    Returns:
        A list of ``Send`` objects, one per selected specialist.  If the route
        list is empty (fallback case), a single ``Send`` to the synthesizer is
        returned so the graph can produce a polite fallback response.
    """
    route = state.get("route", [])
    logger.info("Routing decision: %s", route if route else "(none — fallback)")

    if not route:
        # Fallback: no specialists selected -- go straight to synthesizer
        return [Send("synthesizer", state)]

    sends: list[Send] = []
    for agent_label in route:
        node_name = AGENT_NODE_MAP.get(agent_label)
        if node_name is not None:
            sends.append(Send(node_name, state))

    # Safety net: if all labels were unrecognised, fall back to synthesizer
    if not sends:
        return [Send("synthesizer", state)]

    return sends


def build_graph() -> CompiledStateGraph:
    """Build and compile the medgraph orchestration graph.

    Returns a ``CompiledStateGraph`` ready for ``await graph.ainvoke(state)``.
    The graph is stateless -- all conversation context must be supplied in the
    initial state dict passed to ``ainvoke``.
    """
    # Instantiate agent callables ------------------------------------------------
    router_agent = RouterAgent()
    symptom_agent = SymptomAgent()
    medication_agent = MedicationAgent()
    lifestyle_agent = LifestyleAgent()
    evidence_agent = EvidenceAgent()
    drug_check_agent = DrugCheckAgent()
    synthesizer_agent = SynthesizerAgent()

    # Build the graph ------------------------------------------------------------
    builder = StateGraph(MedGraphState)

    # -- Nodes -------------------------------------------------------------------
    builder.add_node("router", router_agent)
    builder.add_node("symptom_agent", symptom_agent)
    builder.add_node("medication_agent", medication_agent)
    builder.add_node("lifestyle_agent", lifestyle_agent)
    builder.add_node("evidence_agent", evidence_agent)
    builder.add_node("drug_check_agent", drug_check_agent)
    builder.add_node("synthesizer", synthesizer_agent)

    # -- Edges -------------------------------------------------------------------
    # START -> router (always the first node)
    builder.add_edge(START, "router")

    # Router -> conditional fan-out to specialists (or directly to synthesizer)
    builder.add_conditional_edges("router", route_to_specialists)

    # Each specialist -> synthesizer
    builder.add_edge("symptom_agent", "synthesizer")
    builder.add_edge("medication_agent", "synthesizer")
    builder.add_edge("lifestyle_agent", "synthesizer")
    builder.add_edge("evidence_agent", "synthesizer")
    builder.add_edge("drug_check_agent", "synthesizer")

    # Synthesizer -> END
    builder.add_edge("synthesizer", END)

    # Compile and return ---------------------------------------------------------
    return builder.compile()
