"""Unit tests for agent contracts.

Every agent must return a valid partial-state dict with the correct keys.
All LLM calls are mocked — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.lifestyle import LifestyleAgent
from src.agents.medication import MedicationAgent
from src.agents.router import RouterAgent
from src.agents.symptom import SymptomAgent
from src.agents.synthesizer import SynthesizerAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock litellm response object."""
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Specialist agents: symptom, medication, lifestyle
# ---------------------------------------------------------------------------

class TestSymptomAgent:
    """SymptomAgent returns specialist_outputs, handoff_chain, safety_escalation."""

    @pytest.mark.asyncio
    async def test_returns_correct_keys(self, base_state):
        agent = SymptomAgent()
        mock_response = _mock_llm_response(
            "You may be experiencing tension headaches. Please see a doctor if they persist."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert "specialist_outputs" in result
        assert "handoff_chain" in result
        assert "safety_escalation" in result

    @pytest.mark.asyncio
    async def test_writes_own_key_in_specialist_outputs(self, base_state):
        agent = SymptomAgent()
        mock_response = _mock_llm_response("Some symptom information.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert "symptom" in result["specialist_outputs"]
        assert result["specialist_outputs"]["symptom"] == "Some symptom information."

    @pytest.mark.asyncio
    async def test_handoff_chain_contains_agent_name(self, base_state):
        agent = SymptomAgent()
        mock_response = _mock_llm_response("Info.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert result["handoff_chain"] == ["symptom"]

    @pytest.mark.asyncio
    async def test_safety_escalation_detected(self, base_state):
        agent = SymptomAgent()
        mock_response = _mock_llm_response(
            "This sounds serious. [SAFETY_ESCALATION] Please call emergency services."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert result["safety_escalation"] is True

    @pytest.mark.asyncio
    async def test_no_safety_escalation_when_absent(self, base_state):
        agent = SymptomAgent()
        mock_response = _mock_llm_response("Mild headaches are common.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert result["safety_escalation"] is False


class TestMedicationAgent:
    """MedicationAgent returns specialist_outputs, handoff_chain, safety_escalation."""

    @pytest.mark.asyncio
    async def test_returns_correct_keys(self, base_state):
        agent = MedicationAgent()
        mock_response = _mock_llm_response("Ibuprofen is commonly used for pain relief.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert "specialist_outputs" in result
        assert "medication" in result["specialist_outputs"]
        assert result["handoff_chain"] == ["medication"]

    @pytest.mark.asyncio
    async def test_safety_escalation_on_interaction(self, base_state):
        agent = MedicationAgent()
        base_state["user_input"] = "I take warfarin and aspirin together."
        mock_response = _mock_llm_response(
            "Combining these medications [SAFETY_ESCALATION] may increase bleeding risk."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert result["safety_escalation"] is True


class TestLifestyleAgent:
    """LifestyleAgent returns specialist_outputs, handoff_chain, safety_escalation."""

    @pytest.mark.asyncio
    async def test_returns_correct_keys(self, base_state):
        agent = LifestyleAgent()
        mock_response = _mock_llm_response("Regular exercise can improve energy levels.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(base_state)

        assert "specialist_outputs" in result
        assert "lifestyle" in result["specialist_outputs"]
        assert result["handoff_chain"] == ["lifestyle"]
        assert isinstance(result["safety_escalation"], bool)


# ---------------------------------------------------------------------------
# Synthesizer agent
# ---------------------------------------------------------------------------

class TestSynthesizerAgent:
    """SynthesizerAgent returns final_response and messages."""

    @pytest.mark.asyncio
    async def test_returns_correct_keys(self, state_with_specialist_outputs):
        agent = SynthesizerAgent()
        mock_response = _mock_llm_response(
            "Based on the information gathered, here is what we know about your headaches..."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(state_with_specialist_outputs)

        assert "final_response" in result
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_messages_contain_user_and_assistant(self, state_with_specialist_outputs):
        agent = SynthesizerAgent()
        mock_response = _mock_llm_response("Here is your combined answer.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(state_with_specialist_outputs)

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == state_with_specialist_outputs["user_input"]
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["content"] == result["final_response"]

    @pytest.mark.asyncio
    async def test_safety_marker_stripped_from_final_response(
        self, state_with_specialist_outputs
    ):
        agent = SynthesizerAgent()
        state_with_specialist_outputs["safety_escalation"] = True
        mock_response = _mock_llm_response(
            "Please seek help immediately. [SAFETY_ESCALATION] This is important."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(state_with_specialist_outputs)

        assert "[SAFETY_ESCALATION]" not in result["final_response"]
        assert "Please seek help immediately." in result["final_response"]

    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self, state_with_specialist_outputs):
        agent = SynthesizerAgent()
        mock_response = _mock_llm_response("")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await agent(state_with_specialist_outputs)

        # Should return fallback message, not empty string
        assert result["final_response"] != ""


# ---------------------------------------------------------------------------
# Base agent: retry / fallback
# ---------------------------------------------------------------------------

class TestBaseAgentRetry:
    """The base agent retries once on failure, then returns fallback."""

    @pytest.mark.asyncio
    async def test_retry_on_llm_failure(self, base_state):
        agent = SymptomAgent()
        agent.fallback_model = "fallback-model"

        success_response = _mock_llm_response("Recovery response.")
        mock_acompletion = AsyncMock(
            side_effect=[Exception("API error"), success_response]
        )

        with patch("litellm.acompletion", mock_acompletion):
            result = await agent(base_state)

        assert mock_acompletion.call_count == 2
        assert result["specialist_outputs"]["symptom"] == "Recovery response."

    @pytest.mark.asyncio
    async def test_fallback_after_all_retries_fail(self, base_state):
        agent = SymptomAgent()
        agent.fallback_model = "fallback-model"

        mock_acompletion = AsyncMock(
            side_effect=[Exception("Error 1"), Exception("Error 2")]
        )

        with patch("litellm.acompletion", mock_acompletion):
            result = await agent(base_state)

        assert mock_acompletion.call_count == 2
        # Should contain the fallback message
        assert "sorry" in result["specialist_outputs"]["symptom"].lower()
