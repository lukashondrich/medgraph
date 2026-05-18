"""Router agent — classifies user intent and selects specialist(s).

Uses litellm's structured output support and parses the result into a
``RouteDecision`` Pydantic model. The router is local-first when
``LOCAL_ROUTER_MODEL`` + ``LOCAL_LLM_API_BASE`` are configured, with legacy
Ollama router support retained as a fallback path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.models.routing import RouteDecision
from src.models.state import HealthcareState
from src.prompts.router import SYSTEM_PROMPT

from .base import HealthcareAgent

logger = logging.getLogger(__name__)

# If structured output parsing fails after retry, fall back to this single
# specialist so the system can still produce a response.
_FALLBACK_ROUTE = ["symptom"]
_FALLBACK_REASONING = "Routing failed; defaulting to symptom specialist."


class RouterAgent(HealthcareAgent):
    """Classifies user queries and selects 1-5 specialist agents."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            name="router",
            system_prompt=SYSTEM_PROMPT,
            model=model,
            local_first=True,
            local_model_env="LOCAL_ROUTER_MODEL",
            local_api_base_env="LOCAL_ROUTER_API_BASE",
            legacy_ollama_router=True,
        )

    async def process(self, state: HealthcareState) -> dict:
        """Route the user's message to the appropriate specialist(s)."""
        messages = self._build_messages(state)

        decision, model_source = await self._get_route_decision(messages)

        return {
            "route": decision.agents,
            "route_reasoning": decision.reasoning,
            "handoff_chain": ["router"],
            "router_model_source": model_source,
        }

    # ------------------------------------------------------------------
    # Structured output helpers
    # ------------------------------------------------------------------

    async def _get_route_decision(
        self, messages: list[dict[str, str]]
    ) -> tuple[RouteDecision, str]:
        """Attempt to get a valid RouteDecision from the LLM.

        Strategy: try once with provider-aware response_format; if parsing
        fails, retry once. If both attempts fail, return a fallback decision.
        """
        model_source = "cloud"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = await self._call_llm(
                    messages,
                    response_format_factory=self._route_response_format_for_model,
                )
                model_source = self.last_llm_metrics.get("model_source", "cloud")
                data = json.loads(raw)
                return RouteDecision.model_validate(data), model_source
            except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Router structured-output attempt %d failed: %s",
                    attempt + 1,
                    exc,
                )

        logger.error("Router structured output failed after retry: %s", last_error)
        return RouteDecision(
            agents=_FALLBACK_ROUTE,
            reasoning=_FALLBACK_REASONING,
            confidence=0.0,
        ), model_source

    @staticmethod
    def _route_response_format_for_model(model: str) -> dict[str, Any]:
        """Return a response_format compatible with the target provider."""
        if model.startswith("gemini/") or model.startswith("ollama_chat/"):
            return {"type": "json_object"}

        schema = RouteDecision.model_json_schema()
        schema["additionalProperties"] = False
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "RouteDecision",
                "schema": schema,
                "strict": True,
            },
        }
