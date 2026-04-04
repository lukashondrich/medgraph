"""Router agent — classifies user intent and selects specialist(s).

Uses litellm's ``response_format`` for structured JSON output parsed
into a ``RouteDecision`` Pydantic model.

Supports local Ollama model (e.g. Gemma 4) with automatic fallback
to cloud APIs when the local model is unavailable or fails.
"""

from __future__ import annotations

import json
import logging
import os

import litellm

from src.models.routing import RouteDecision
from src.models.state import HealthcareState
from src.ollama_health import ollama_health
from src.prompts.router import SYSTEM_PROMPT

from .base import HealthcareAgent, _get_default_model

logger = logging.getLogger(__name__)

# If structured output parsing fails after retry, fall back to this single
# specialist so the system can still produce a response.
_FALLBACK_ROUTE = ["symptom"]
_FALLBACK_REASONING = "Routing failed; defaulting to symptom specialist."


class RouterAgent(HealthcareAgent):
    """Classifies user queries and selects 1-3 specialist agents."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="router", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        """Route the user's message to the appropriate specialist(s).

        Returns a partial state update with ``route``, ``route_reasoning``,
        and ``router_model_source``.
        """
        messages = self._build_messages(state)

        decision, model_source = await self._get_route_decision(messages)

        return {
            "route": decision.agents,
            "route_reasoning": decision.reasoning,
            "handoff_chain": ["router"],
            "router_model_source": model_source,
        }

    # ------------------------------------------------------------------
    # Local model support
    # ------------------------------------------------------------------

    async def _call_llm_with_local(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> tuple[str, str]:
        """Try local Ollama first, then fall back to cloud.

        Returns:
            Tuple of (content, model_source) where model_source is
            ``"local"`` or ``"cloud"``.
        """
        ollama_model = os.environ.get("OLLAMA_ROUTER_MODEL", "ollama_chat/gemma4:26b-a4b-it-q8_0")
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_auth_token = os.environ.get("OLLAMA_AUTH_TOKEN", "")

        if await ollama_health.check():
            try:
                extra_headers = (
                    {"Authorization": f"Bearer {ollama_auth_token}"}
                    if ollama_auth_token else {}
                )
                response = await litellm.acompletion(
                    model=ollama_model,
                    messages=messages,
                    api_base=ollama_base_url,
                    extra_headers=extra_headers,
                    **kwargs,
                )
                content = response.choices[0].message.content or ""
                logger.info("Router used local model %s", ollama_model)
                return content, "local"
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Router local model call failed, falling back to cloud: %s", exc
                )

        # Fall through to cloud
        content = await self._call_llm(messages, **kwargs)
        return content, "cloud"

    # ------------------------------------------------------------------
    # Structured output helpers
    # ------------------------------------------------------------------

    async def _get_route_decision(
        self, messages: list[dict[str, str]]
    ) -> tuple[RouteDecision, str]:
        """Attempt to get a valid RouteDecision from the LLM.

        Strategy: try once with response_format; if parsing fails, retry
        once.  If both fail, return a fallback decision.

        Returns:
            Tuple of (RouteDecision, model_source).
        """
        model_source = "cloud"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw, model_source = await self._call_llm_with_local(
                    messages,
                    response_format={"type": "json_object"},
                )
                data = json.loads(raw)
                return RouteDecision.model_validate(data), model_source
            except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Router structured-output attempt %d failed: %s",
                    attempt + 1,
                    exc,
                )

        logger.error(
            "Router structured output failed after retry: %s", last_error
        )
        return RouteDecision(
            agents=_FALLBACK_ROUTE,
            reasoning=_FALLBACK_REASONING,
            confidence=0.0,
        ), model_source
