"""LangGraph StateGraph for pH Companion: plan, gather evidence, then write.

    START -> planner -> [safety_rules + chosen sources, in parallel] -> writer -> END

The planner decides which sources to consult and what to search for. Source
nodes gather evidence without calling a language model. The writer composes
the answer from that evidence only and validates its citations.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from src.agents.planner import PlannerAgent
from src.agents.sources import (
    GuidelineSource,
    ReferenceRangeSource,
    SafetySource,
    StudyLibrarySource,
)
from src.agents.writer import WriterAgent
from src.models.state import MedGraphState

# Runs on every on-topic turn, whatever the planner chooses.
PH_ALWAYS_NODES: list[str] = ["safety_rules"]
# Sources the planner can choose from, in display order.
PH_OPTIONAL_NODES: list[str] = ["reference_ranges", "study_library", "guidelines"]
PH_SOURCE_NODES: list[str] = PH_ALWAYS_NODES + PH_OPTIONAL_NODES


def planned_sources(route: list[str]) -> list[str]:
    """Source nodes that will run for a planner route, in display order.

    An empty route means the question is off-topic: nothing is looked up.
    """
    chosen = [node for node in PH_OPTIONAL_NODES if node in route]
    return PH_ALWAYS_NODES + chosen if chosen else []


def route_to_sources(state: MedGraphState) -> list[Send]:
    """Fan out to the planned sources, or go straight to the writer."""
    nodes = planned_sources(state.get("route", []))
    if not nodes:
        return [Send("writer", state)]
    return [Send(node, state) for node in nodes]


def build_ph_graph(
    planner=None,
    safety_rules=None,
    reference_ranges=None,
    study_library=None,
    guidelines=None,
    writer=None,
) -> CompiledStateGraph:
    """Build the pH Companion graph.

    Flow:
        START -> planner -> [safety_rules + chosen sources, in parallel] -> writer -> END

    The planner picks sources and search queries (a fixed plan for a new
    reading, a model call for a follow-up question). All sources finish
    before the writer starts, so the writer composes its answer from gathered
    evidence only. The writer also runs the citation check. Node instances
    can be injected for tests.
    """
    builder = StateGraph(MedGraphState)

    builder.add_node("planner", planner or PlannerAgent())
    builder.add_node("safety_rules", safety_rules or SafetySource())
    builder.add_node("reference_ranges", reference_ranges or ReferenceRangeSource())
    builder.add_node("study_library", study_library or StudyLibrarySource())
    builder.add_node("guidelines", guidelines or GuidelineSource())
    builder.add_node("writer", writer or WriterAgent())

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", route_to_sources, PH_SOURCE_NODES + ["writer"])
    for node in PH_SOURCE_NODES:
        builder.add_edge(node, "writer")
    builder.add_edge("writer", END)

    return builder.compile()
