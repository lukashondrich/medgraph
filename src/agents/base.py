"""Base healthcare agent callable for LangGraph nodes.

Shared logic:
- Building message lists (system prompt + conversation history + current input)
- Calling litellm.acompletion()
- Error handling with one retry then graceful fallback
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import litellm

from src.models.state import HealthcareState

logger = logging.getLogger(__name__)

# Default model for all agents; individual agents can override at __init__ time.
DEFAULT_MODEL = "gemini/gemini-2.0-flash"


def _get_default_model() -> str:
    """Return the model from env (set by load_config) or the hardcoded default."""
    return os.environ.get("MEDGRAPH_MODEL", DEFAULT_MODEL)


def _get_fallback_model() -> str | None:
    """Return the fallback model from env, or None if not configured."""
    return os.environ.get("MEDGRAPH_FALLBACK_MODEL")


# Fallback message returned when the LLM call fails after retry.
FALLBACK_MESSAGE = (
    "I'm sorry, I'm having trouble processing your request right now. "
    "Please try again in a moment, or consult a healthcare professional "
    "if your concern is urgent."
)


class HealthcareAgent:
    """Base callable for LangGraph nodes.

    Subclasses override ``process(state)`` to customize behavior.  The base
    class handles message construction, LLM invocation, and retry/fallback.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.model = model or _get_default_model()
        self.fallback_model = _get_fallback_model()

    # ------------------------------------------------------------------
    # Message construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        state: HealthcareState,
        *,
        system_prompt_override: str | None = None,
    ) -> list[dict[str, str]]:
        """Build an OpenAI-format message list.

        Structure:
        1. System prompt
        2. Conversation history (state["messages"])
        3. Current user input as the final user message
        """
        prompt = system_prompt_override or self.system_prompt

        # Inject patient context when available (makes all agents patient-aware)
        patient_summary = state.get("patient_summary", "")
        if patient_summary:
            prompt = prompt + "\n\n" + patient_summary

        messages: list[dict[str, str]] = [{"role": "system", "content": prompt}]

        # Append prior conversation history if available.
        history = state.get("messages") or []
        messages.extend(history)

        # Append the current turn's user input.
        user_input = state.get("user_input", "")
        if user_input:
            messages.append({"role": "user", "content": user_input})

        return messages

    # ------------------------------------------------------------------
    # LLM invocation with retry
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Call litellm.acompletion with retry and optional model fallback.

        Strategy: try with the primary model first.  If it fails and a
        fallback model is configured, retry with the fallback model.
        Returns the assistant message content string, or ``FALLBACK_MESSAGE``
        if all attempts fail.
        """
        models_to_try = [self.model]
        if self.fallback_model:
            models_to_try.append(self.fallback_model)

        last_error: Exception | None = None
        for model in models_to_try:
            try:
                t0 = time.perf_counter()
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
                elapsed = time.perf_counter() - t0
                content = response.choices[0].message.content
                logger.info(
                    "%s LLM call completed in %.3fs (model=%s)",
                    self.name, elapsed, model,
                )
                if model != self.model:
                    logger.info(
                        "%s succeeded with fallback model %s", self.name, model
                    )
                return content or ""
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "%s LLM call failed with model %s: %s",
                    self.name,
                    model,
                    exc,
                )

        logger.error(
            "%s LLM call failed after all attempts: %s", self.name, last_error
        )
        return FALLBACK_MESSAGE

    # ------------------------------------------------------------------
    # Detect safety escalation in LLM response
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_safety_escalation(text: str) -> bool:
        """Return True if the LLM response contains the safety marker."""
        return "[SAFETY_ESCALATION]" in text

    # ------------------------------------------------------------------
    # Node interface (subclasses override ``process``)
    # ------------------------------------------------------------------

    async def __call__(self, state: HealthcareState) -> dict:
        """LangGraph node entry-point.  Delegates to ``process``."""
        logger.info("%s node started", self.name)
        t0 = time.perf_counter()
        result = await self.process(state)
        elapsed = time.perf_counter() - t0
        logger.info("%s node completed in %.3fs", self.name, elapsed)
        return result

    async def process(self, state: HealthcareState) -> dict:
        """Override in subclasses to implement agent-specific logic.

        Must return a partial state update dict.
        """
        raise NotImplementedError
