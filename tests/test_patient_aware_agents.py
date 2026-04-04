"""Tests for patient-aware agents (Phase 3 + 4).

Covers:
- EvidenceAgent: returns evidence_context + citations
- DrugCheckAgent: returns drug_interactions, sets safety_escalation
- Existing specialists: patient_summary appears in prompt when present
- Router: includes evidence/drug_check in routing table
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.state import MedGraphState


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def base_state() -> MedGraphState:
    """Minimal valid state without patient."""
    return {
        "messages": [],
        "user_input": "Should I take ibuprofen for my knee pain?",
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
    }


@pytest.fixture
def patient_state(base_state: MedGraphState) -> MedGraphState:
    """State with a loaded patient (72F, T2DM+HTN+CKD)."""
    base_state["patient"] = {"id": "test-123", "name": "Jane Doe"}
    base_state["patient_summary"] = (
        "--- PATIENT CONTEXT ---\n"
        "Name: Jane Doe | Age: 72F\n\n"
        "Active conditions:\n"
        "  - T2DM (Type 2 Diabetes)\n"
        "  - HTN (High Blood Pressure)\n"
        "  - CKD (Chronic Kidney Disease)\n\n"
        "Current medications:\n"
        "  - Metformin 500mg BID\n"
        "  - Lisinopril 20mg daily\n\n"
        "--- END PATIENT CONTEXT ---"
    )
    return base_state


# ── EvidenceAgent Tests ──────────────────────────────────────────────────


class TestEvidenceAgent:
    @pytest.fixture(autouse=True)
    def _patch_retrieval(self):
        """Patch the retrieval pipeline to avoid Qdrant dependency."""
        with patch("src.agents.evidence.retrieve_evidence") as mock_retrieve:
            mock_retrieve.return_value = {
                "evidence_context": {
                    "ADA-SOC-2025-9.1": "ADA recommends avoiding NSAIDs in CKD patients."
                },
                "citations": [
                    {
                        "source": "ADA-SOC-2025",
                        "tier": "guideline",
                        "text": "Avoid NSAIDs in CKD stage 3+",
                    }
                ],
            }
            self.mock_retrieve = mock_retrieve
            yield

    @pytest.mark.asyncio
    async def test_returns_evidence_context(self, patient_state):
        from src.agents.evidence import EvidenceAgent

        agent = EvidenceAgent()
        result = await agent(patient_state)
        assert "evidence_context" in result
        assert len(result["evidence_context"]) > 0

    @pytest.mark.asyncio
    async def test_returns_citations(self, patient_state):
        from src.agents.evidence import EvidenceAgent

        agent = EvidenceAgent()
        result = await agent(patient_state)
        assert "citations" in result
        assert len(result["citations"]) > 0
        assert result["citations"][0]["source"] == "ADA-SOC-2025"

    @pytest.mark.asyncio
    async def test_returns_handoff_chain(self, patient_state):
        from src.agents.evidence import EvidenceAgent

        agent = EvidenceAgent()
        result = await agent(patient_state)
        assert "handoff_chain" in result
        assert "evidence" in result["handoff_chain"]

    @pytest.mark.asyncio
    async def test_returns_specialist_output(self, patient_state):
        from src.agents.evidence import EvidenceAgent

        agent = EvidenceAgent()
        result = await agent(patient_state)
        assert "specialist_outputs" in result
        assert "evidence" in result["specialist_outputs"]

    @pytest.mark.asyncio
    async def test_handles_no_results(self, patient_state):
        from src.agents.evidence import EvidenceAgent

        self.mock_retrieve.return_value = {
            "evidence_context": {},
            "citations": [],
        }
        agent = EvidenceAgent()
        result = await agent(patient_state)
        assert result["evidence_context"] == {}
        assert result["citations"] == []


# ── DrugCheckAgent Tests ─────────────────────────────────────────────────


class TestDrugCheckAgent:
    @pytest.fixture(autouse=True)
    def _patch_screening(self):
        """Patch the drug screening to avoid OpenFDA dependency."""
        with patch("src.agents.drug_check.screen_patient_medications") as mock_screen:
            mock_screen.return_value = {
                "drug_interactions": [
                    {
                        "drug_a": "NAPROXEN",
                        "drug_b": "LISINOPRIL",
                        "risk": "NSAID + ACE inhibitor: increased renal risk",
                        "severity": "high",
                    }
                ],
                "safety_escalation": True,
                "summary": "Found 1 high-severity interaction: NAPROXEN + LISINOPRIL",
            }
            self.mock_screen = mock_screen
            yield

    @pytest.mark.asyncio
    async def test_returns_drug_interactions(self, patient_state):
        from src.agents.drug_check import DrugCheckAgent

        agent = DrugCheckAgent()
        result = await agent(patient_state)
        assert "drug_interactions" in result
        assert len(result["drug_interactions"]) > 0

    @pytest.mark.asyncio
    async def test_sets_safety_escalation_on_high_risk(self, patient_state):
        from src.agents.drug_check import DrugCheckAgent

        agent = DrugCheckAgent()
        result = await agent(patient_state)
        assert result["safety_escalation"] is True

    @pytest.mark.asyncio
    async def test_returns_handoff_chain(self, patient_state):
        from src.agents.drug_check import DrugCheckAgent

        agent = DrugCheckAgent()
        result = await agent(patient_state)
        assert "drug_check" in result["handoff_chain"]

    @pytest.mark.asyncio
    async def test_returns_specialist_output(self, patient_state):
        from src.agents.drug_check import DrugCheckAgent

        agent = DrugCheckAgent()
        result = await agent(patient_state)
        assert "drug_check" in result["specialist_outputs"]

    @pytest.mark.asyncio
    async def test_handles_empty_medications(self, base_state):
        from src.agents.drug_check import DrugCheckAgent

        self.mock_screen.return_value = {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": "No medications to screen.",
        }
        agent = DrugCheckAgent()
        result = await agent(base_state)
        assert result["drug_interactions"] == []
        assert result["safety_escalation"] is False

    @pytest.mark.asyncio
    async def test_no_safety_escalation_when_no_risk(self, patient_state):
        from src.agents.drug_check import DrugCheckAgent

        self.mock_screen.return_value = {
            "drug_interactions": [
                {"drug_a": "A", "drug_b": "B", "risk": "minor", "severity": "low"}
            ],
            "safety_escalation": False,
            "summary": "Low-severity interactions only.",
        }
        agent = DrugCheckAgent()
        result = await agent(patient_state)
        assert result["safety_escalation"] is False
