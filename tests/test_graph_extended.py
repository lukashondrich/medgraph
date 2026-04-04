"""Tests for extended graph integration (Phase 4).

Covers: new agents run in parallel, all outputs reach synthesizer,
without patient behaves as before.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.graph import build_graph, route_to_specialists


class TestRouteToSpecialistsExtended:
    """Extended routing function handles new agent names."""

    def test_evidence_agent_routed(self):
        sends = route_to_specialists({"route": ["evidence"]})
        assert len(sends) == 1
        assert sends[0].node == "evidence_agent"

    def test_drug_check_agent_routed(self):
        sends = route_to_specialists({"route": ["drug_check"]})
        assert len(sends) == 1
        assert sends[0].node == "drug_check_agent"

    def test_mixed_old_and_new_agents(self):
        sends = route_to_specialists({"route": ["symptom", "evidence", "drug_check"]})
        assert len(sends) == 3
        node_names = {s.node for s in sends}
        assert node_names == {"symptom_agent", "evidence_agent", "drug_check_agent"}

    def test_all_five_agents(self):
        sends = route_to_specialists(
            {"route": ["symptom", "medication", "lifestyle", "evidence", "drug_check"]}
        )
        assert len(sends) == 5

    def test_old_routes_still_work(self):
        """Original 3 specialists still route correctly."""
        sends = route_to_specialists({"route": ["symptom", "medication"]})
        assert len(sends) == 2
        node_names = {s.node for s in sends}
        assert node_names == {"symptom_agent", "medication_agent"}


class TestGraphBuild:
    """Graph builds with all 7 nodes (router + 5 specialists + synthesizer)."""

    def test_graph_has_new_nodes(self):
        graph = build_graph()
        node_names = set(graph.get_graph().nodes)
        assert "evidence_agent" in node_names
        assert "drug_check_agent" in node_names

    def test_graph_has_original_nodes(self):
        graph = build_graph()
        node_names = set(graph.get_graph().nodes)
        assert "router" in node_names
        assert "symptom_agent" in node_names
        assert "medication_agent" in node_names
        assert "lifestyle_agent" in node_names
        assert "synthesizer" in node_names


class TestGraphIntegrationWithNewAgents:
    """Full flow tests with new agents mocked."""

    @pytest.fixture(autouse=True)
    def _patch_llm(self):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
            self.mock_llm = mock
            yield

    def _setup_router_response(self, agents: list[str]):
        """Configure mock to return router JSON, then specialist responses."""
        import json
        router_json = json.dumps({
            "agents": agents,
            "reasoning": "test routing",
            "confidence": 0.9,
        })
        responses = [self._make_response(router_json)]
        for agent in agents:
            responses.append(self._make_response(f"{agent} response"))
        # Synthesizer response
        responses.append(self._make_response("Final synthesized response"))
        self.mock_llm.side_effect = responses

    def _make_response(self, content: str):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = content
        return mock_resp

    @pytest.mark.asyncio
    async def test_full_flow_with_evidence(self):
        """Evidence agent runs and output reaches synthesizer."""
        self._setup_router_response(["symptom", "evidence"])

        with patch("src.agents.evidence.retrieve_evidence") as mock_ret:
            mock_ret.return_value = {
                "evidence_context": {"ADA-1": "Test evidence"},
                "citations": [{"source": "ADA-1", "tier": "guideline", "text": "..."}],
            }
            graph = build_graph()
            result = await graph.ainvoke({
                "messages": [],
                "user_input": "Should I take ibuprofen?",
                "route": [],
                "route_reasoning": "",
                "specialist_outputs": {},
                "final_response": "",
                "handoff_chain": [],
                "safety_escalation": False,
                "patient": {},
                "patient_summary": "",
                "evidence_context": {},
                "drug_interactions": [],
                "citations": [],
            })

        assert "final_response" in result
        assert result["final_response"] != ""
        assert "evidence" in result["handoff_chain"]

    @pytest.mark.asyncio
    async def test_full_flow_with_drug_check(self):
        """DrugCheck agent runs and output reaches synthesizer."""
        self._setup_router_response(["medication", "drug_check"])

        with patch("src.agents.drug_check.screen_patient_medications") as mock_scr:
            mock_scr.return_value = {
                "drug_interactions": [],
                "safety_escalation": False,
                "summary": "No interactions found.",
            }
            graph = build_graph()
            result = await graph.ainvoke({
                "messages": [],
                "user_input": "Is my medication safe?",
                "route": [],
                "route_reasoning": "",
                "specialist_outputs": {},
                "final_response": "",
                "handoff_chain": [],
                "safety_escalation": False,
                "patient": {},
                "patient_summary": "",
                "evidence_context": {},
                "drug_interactions": [],
                "citations": [],
            })

        assert "final_response" in result
        assert "drug_check" in result["handoff_chain"]

    @pytest.mark.asyncio
    async def test_without_patient_behaves_as_before(self):
        """Without patient context, old behavior is preserved."""
        self._setup_router_response(["symptom"])

        graph = build_graph()
        result = await graph.ainvoke({
            "messages": [],
            "user_input": "I have a headache",
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
            "patient": {},
            "patient_summary": "",
            "evidence_context": {},
            "drug_interactions": [],
            "citations": [],
        })

        assert "final_response" in result
        assert result["final_response"] != ""
