"""Unit tests for router classification.

Tests the RouterAgent with various mocked LLM responses to verify
correct parsing, fallback behaviour, and classification logic.
No real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.router import RouterAgent


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


def _route_json(agents: list[str], reasoning: str, confidence: float) -> str:
    """Build a valid RouteDecision JSON string."""
    return json.dumps({
        "agents": agents,
        "reasoning": reasoning,
        "confidence": confidence,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def router():
    return RouterAgent()


@pytest.fixture
def base_state():
    return {
        "messages": [],
        "user_input": "",
        "route": [],
        "route_reasoning": "",
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
    }


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestRouterClassification:
    """Test that the router correctly parses structured output."""

    @pytest.mark.asyncio
    async def test_single_specialist_symptom(self, router, base_state):
        base_state["user_input"] = "I have a terrible headache."
        mock_response = _mock_llm_response(
            _route_json(["symptom"], "User describes a physical symptom.", 0.95)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert result["route"] == ["symptom"]
        assert "symptom" in result["route_reasoning"].lower()
        assert result["handoff_chain"] == ["router"]

    @pytest.mark.asyncio
    async def test_single_specialist_medication(self, router, base_state):
        base_state["user_input"] = "What are the side effects of metformin?"
        mock_response = _mock_llm_response(
            _route_json(["medication"], "User asks about medication side effects.", 0.9)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert result["route"] == ["medication"]

    @pytest.mark.asyncio
    async def test_single_specialist_lifestyle(self, router, base_state):
        base_state["user_input"] = "How can I improve my sleep?"
        mock_response = _mock_llm_response(
            _route_json(["lifestyle"], "User asks about sleep improvement.", 0.85)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert result["route"] == ["lifestyle"]

    @pytest.mark.asyncio
    async def test_multi_specialist_routing(self, router, base_state):
        base_state["user_input"] = "My medication gives me stomach cramps."
        mock_response = _mock_llm_response(
            _route_json(
                ["symptom", "medication"],
                "User describes medication side effects causing physical symptoms.",
                0.92,
            )
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert set(result["route"]) == {"symptom", "medication"}

    @pytest.mark.asyncio
    async def test_three_specialist_routing(self, router, base_state):
        base_state["user_input"] = (
            "I take blood pressure medication, have headaches, "
            "and want diet advice for hypertension."
        )
        mock_response = _mock_llm_response(
            _route_json(
                ["symptom", "medication", "lifestyle"],
                "Query spans symptoms, medication, and lifestyle domains.",
                0.88,
            )
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert set(result["route"]) == {"symptom", "medication", "lifestyle"}

    @pytest.mark.asyncio
    async def test_off_topic_returns_empty_route(self, router, base_state):
        base_state["user_input"] = "What is the capital of France?"
        mock_response = _mock_llm_response(
            _route_json([], "Query is not healthcare-related.", 0.98)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert result["route"] == []


# ---------------------------------------------------------------------------
# Fallback / error handling tests
# ---------------------------------------------------------------------------

class TestRouterFallback:
    """Test that the router handles malformed output and LLM failures."""

    @pytest.mark.asyncio
    async def test_malformed_json_triggers_retry_then_fallback(self, router, base_state):
        """If both attempts produce invalid JSON, router falls back to symptom."""
        base_state["user_input"] = "I feel sick."

        mock_acompletion = AsyncMock(
            return_value=_mock_llm_response("This is not JSON at all.")
        )

        with patch("litellm.acompletion", mock_acompletion):
            result = await router(base_state)

        # Should fall back to ["symptom"] with 0.0 confidence reasoning
        assert result["route"] == ["symptom"]
        assert "failed" in result["route_reasoning"].lower() or "defaulting" in result["route_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_invalid_agent_name_triggers_fallback(self, router, base_state):
        """If the LLM returns an agent name not in the allowed set, validation fails."""
        base_state["user_input"] = "Help me."
        mock_response = _mock_llm_response(
            json.dumps({
                "agents": ["cardiology"],  # not a valid specialist
                "reasoning": "Needs heart specialist.",
                "confidence": 0.8,
            })
        )

        mock_acompletion = AsyncMock(return_value=mock_response)

        with patch("litellm.acompletion", mock_acompletion):
            result = await router(base_state)

        # Pydantic validation should reject "cardiology", triggering fallback
        assert result["route"] == ["symptom"]

    @pytest.mark.asyncio
    async def test_llm_exception_triggers_fallback(self, router, base_state):
        """If litellm raises an exception, router falls back gracefully."""
        base_state["user_input"] = "I need help."

        mock_acompletion = AsyncMock(
            side_effect=Exception("API unavailable")
        )

        with patch("litellm.acompletion", mock_acompletion):
            result = await router(base_state)

        assert result["route"] == ["symptom"]
        assert result["handoff_chain"] == ["router"]

    @pytest.mark.asyncio
    async def test_first_attempt_fails_second_succeeds(self, router, base_state):
        """Router retries once; if the second attempt succeeds, use it."""
        base_state["user_input"] = "I have a rash."

        bad_response = _mock_llm_response("not json")
        good_response = _mock_llm_response(
            _route_json(["symptom"], "User describes a skin symptom.", 0.9)
        )

        mock_acompletion = AsyncMock(side_effect=[bad_response, good_response])

        with patch("litellm.acompletion", mock_acompletion):
            result = await router(base_state)

        assert result["route"] == ["symptom"]


# ---------------------------------------------------------------------------
# State contract tests
# ---------------------------------------------------------------------------

class TestRouterStateContract:
    """Verify the router returns the correct state keys."""

    @pytest.mark.asyncio
    async def test_returns_route_and_reasoning_keys(self, router, base_state):
        base_state["user_input"] = "My knee hurts."
        mock_response = _mock_llm_response(
            _route_json(["symptom"], "Physical symptom described.", 0.9)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        assert "route" in result
        assert "route_reasoning" in result
        assert "handoff_chain" in result
        assert "router_model_source" in result
        assert isinstance(result["route"], list)
        assert isinstance(result["route_reasoning"], str)
        assert isinstance(result["handoff_chain"], list)
        assert result["router_model_source"] in ("local", "cloud")

    @pytest.mark.asyncio
    async def test_does_not_return_unexpected_keys(self, router, base_state):
        base_state["user_input"] = "Tell me about vitamins."
        mock_response = _mock_llm_response(
            _route_json(["lifestyle"], "Nutrition-related query.", 0.85)
        )

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await router(base_state)

        allowed_keys = {"route", "route_reasoning", "handoff_chain", "router_model_source"}
        assert set(result.keys()) == allowed_keys


# ---------------------------------------------------------------------------
# Local model (Ollama) fallback tests
# ---------------------------------------------------------------------------

class TestRouterLocalModel:
    """Test local Ollama model usage and fallback to cloud."""

    @pytest.mark.asyncio
    async def test_ollama_available_and_succeeds(self, router, base_state):
        """When Ollama is healthy and returns valid JSON, use local model."""
        base_state["user_input"] = "I have a headache."
        mock_response = _mock_llm_response(
            _route_json(["symptom"], "Physical symptom.", 0.9)
        )

        with patch("src.agents.base.ollama_health") as mock_health, \
             patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            mock_health.check = AsyncMock(return_value=True)
            result = await router(base_state)

        assert result["route"] == ["symptom"]
        assert result["router_model_source"] == "local"

    @pytest.mark.asyncio
    async def test_ollama_unavailable_uses_cloud(self, router, base_state):
        """When Ollama is down, skip local and go straight to cloud."""
        base_state["user_input"] = "I have a headache."
        mock_response = _mock_llm_response(
            _route_json(["symptom"], "Physical symptom.", 0.9)
        )

        with patch("src.agents.base.ollama_health") as mock_health, \
             patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            mock_health.check = AsyncMock(return_value=False)
            result = await router(base_state)

        assert result["route"] == ["symptom"]
        assert result["router_model_source"] == "cloud"

    @pytest.mark.asyncio
    async def test_ollama_available_but_call_fails_falls_back(self, router, base_state):
        """When Ollama is healthy but the LLM call fails, fall back to cloud."""
        base_state["user_input"] = "I have a headache."

        good_response = _mock_llm_response(
            _route_json(["symptom"], "Physical symptom.", 0.9)
        )

        call_count = 0

        async def acompletion_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            model = kwargs.get("model") or (args[0] if args else "")
            # First call is local (ollama_chat/...) — fail it
            if "ollama" in str(model):
                raise Exception("Ollama model error")
            return good_response

        with patch("src.agents.base.ollama_health") as mock_health, \
             patch("litellm.acompletion", new_callable=AsyncMock, side_effect=acompletion_side_effect):
            mock_health.check = AsyncMock(return_value=True)
            result = await router(base_state)

        assert result["route"] == ["symptom"]
        assert result["router_model_source"] == "cloud"
