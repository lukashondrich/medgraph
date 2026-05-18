"""Base healthcare agent callable for LangGraph nodes.

Shared logic:
- Building message lists (system prompt + conversation history + current input)
- Calling litellm.acompletion()
- Local-first inference routing when configured
- Error handling with cloud fallback then graceful fallback
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import litellm

from src.models.state import HealthcareState
from src.ollama_health import ollama_health

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


@dataclass(frozen=True)
class LLMCallResult:
    """LLM response content plus the serving metadata we log for proof."""

    content: str
    model: str
    model_source: str
    metrics: dict[str, Any]


class HealthcareAgent:
    """Base callable for LangGraph nodes.

    Subclasses override ``process(state)`` to customize behavior. The base
    class handles message construction, LLM invocation, local/cloud routing,
    retry/fallback, and structured inference metrics.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str | None = None,
        *,
        local_first: bool = False,
        local_model_env: str | None = None,
        local_api_base_env: str | None = None,
        cache_prompt_local: bool = False,
        cloud_only: bool = False,
        legacy_ollama_router: bool = False,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.model = model or _get_default_model()
        self.fallback_model = _get_fallback_model()
        self.local_first = local_first
        self.local_model_env = local_model_env
        self.local_api_base_env = local_api_base_env
        self.cache_prompt_local = cache_prompt_local
        self.cloud_only = cloud_only
        self.legacy_ollama_router = legacy_ollama_router
        self.last_llm_metrics: dict[str, Any] = {}

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
        1. System prompt, optionally prefixed with patient context
        2. Conversation history (state["messages"])
        3. Current user input as the final user message when not already present
        """
        prompt = system_prompt_override or self.system_prompt

        # Put patient context first so repeated local specialist calls can reuse
        # the longest shared prefix when the serving backend supports caching.
        patient_summary = state.get("patient_summary", "")
        if patient_summary:
            prompt = patient_summary + "\n\n" + prompt

        messages: list[dict[str, str]] = [{"role": "system", "content": prompt}]

        history = state.get("messages") or []
        messages.extend(history)

        user_input = state.get("user_input", "")
        if user_input and not self._history_already_has_current_user(history, user_input):
            messages.append({"role": "user", "content": user_input})

        return messages

    @staticmethod
    def _history_already_has_current_user(
        history: list[dict[str, str]],
        user_input: str,
    ) -> bool:
        """Return True when the latest user message already equals user_input."""
        for message in reversed(history):
            if message.get("role") == "user":
                return message.get("content") == user_input
        return False

    # ------------------------------------------------------------------
    # LLM invocation with retry
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Call litellm.acompletion and return response content.

        Strategy: try the configured local model first when this agent's role
        allows local inference, then try the primary cloud model and configured
        cloud fallback. Returns ``FALLBACK_MESSAGE`` if all attempts fail.
        """
        result = await self._call_llm_result(messages, **kwargs)
        return result.content

    async def _call_llm_result(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMCallResult:
        """Call litellm.acompletion and return content plus serving metadata."""
        response_format_factory = kwargs.pop("response_format_factory", None)
        attempts = await self._build_llm_attempts()

        last_error: Exception | None = None
        for attempt in attempts:
            model = attempt["model"]
            model_source = attempt["model_source"]
            try:
                t0 = time.perf_counter()
                call_kwargs = self._kwargs_for_attempt(
                    base_kwargs=kwargs,
                    attempt=attempt,
                    response_format_factory=response_format_factory,
                )
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    **call_kwargs,
                )
                elapsed = time.perf_counter() - t0
                content = response.choices[0].message.content or ""
                metrics = self._build_metrics(
                    response=response,
                    model=model,
                    model_source=model_source,
                    elapsed=elapsed,
                )
                self.last_llm_metrics = metrics
                logger.info("llm_call_metrics %s", json.dumps(metrics, sort_keys=True))
                if model_source == "local":
                    logger.info("%s used local model %s", self.name, model)
                elif model != self.model:
                    logger.info("%s succeeded with fallback model %s", self.name, model)
                return LLMCallResult(
                    content=content,
                    model=model,
                    model_source=model_source,
                    metrics=metrics,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "%s LLM call failed with model %s (%s): %s",
                    self.name,
                    model,
                    model_source,
                    exc,
                )

        logger.error("%s LLM call failed after all attempts: %s", self.name, last_error)
        fallback_metrics = {
            "agent": self.name,
            "model": "",
            "model_source": "fallback",
            "latency_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "tokens_per_sec": None,
        }
        self.last_llm_metrics = fallback_metrics
        return LLMCallResult(
            content=FALLBACK_MESSAGE,
            model="",
            model_source="fallback",
            metrics=fallback_metrics,
        )

    async def _build_llm_attempts(self) -> list[dict[str, Any]]:
        """Build the ordered list of local/cloud attempts for this agent."""
        attempts: list[dict[str, Any]] = []

        local_attempt = await self._build_local_attempt()
        if local_attempt:
            attempts.append(local_attempt)

        attempts.append({"model": self.model, "model_source": "cloud"})
        if self.fallback_model:
            attempts.append({"model": self.fallback_model, "model_source": "cloud"})

        return attempts

    async def _build_local_attempt(self) -> dict[str, Any] | None:
        """Return local model attempt config, including legacy Ollama fallback."""
        if not self.local_first or self.cloud_only:
            return None

        local_enabled = os.environ.get("LOCAL_LLM_ENABLED", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        local_model = os.environ.get(self.local_model_env or "")
        local_api_base = os.environ.get(self.local_api_base_env or "") or os.environ.get(
            "LOCAL_LLM_API_BASE",
            "",
        )

        if local_enabled and local_model and local_api_base:
            return {
                "model": local_model,
                "model_source": "local",
                "api_base": local_api_base,
                "api_key": os.environ.get("LOCAL_LLM_API_KEY", "local"),
                "cache_prompt": self.cache_prompt_local,
            }

        if self.legacy_ollama_router:
            ollama_enabled = os.environ.get("OLLAMA_ENABLED", "true").lower() in (
                "true",
                "1",
                "yes",
            )
            if not ollama_enabled or not await ollama_health.check():
                return None

            auth_token = os.environ.get("OLLAMA_AUTH_TOKEN", "")
            return {
                "model": os.environ.get(
                    "OLLAMA_ROUTER_MODEL",
                    "ollama_chat/gemma4:26b-a4b-it-q8_0",
                ),
                "model_source": "local",
                "api_base": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                "extra_headers": (
                    {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
                ),
                "cache_prompt": False,
            }

        return None

    def _kwargs_for_attempt(
        self,
        *,
        base_kwargs: dict[str, Any],
        attempt: dict[str, Any],
        response_format_factory: Callable[[str], dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Merge caller kwargs with attempt-specific local serving options."""
        call_kwargs = dict(base_kwargs)
        model = attempt["model"]

        if response_format_factory is not None:
            call_kwargs["response_format"] = response_format_factory(model)

        if attempt.get("api_base"):
            call_kwargs["api_base"] = attempt["api_base"]
        if attempt.get("api_key"):
            call_kwargs["api_key"] = attempt["api_key"]
        if attempt.get("extra_headers"):
            headers = dict(call_kwargs.get("extra_headers") or {})
            headers.update(attempt["extra_headers"])
            call_kwargs["extra_headers"] = headers

        if attempt.get("model_source") == "local":
            extra_body = dict(call_kwargs.get("extra_body") or {})
            # Qwen3+ models default to thinking mode; disable it for
            # deterministic, low-latency output on local inference.
            extra_body.setdefault(
                "chat_template_kwargs", {"enable_thinking": False}
            )
            if attempt.get("cache_prompt"):
                extra_body.setdefault("cache_prompt", True)
            call_kwargs["extra_body"] = extra_body

        return call_kwargs

    def _build_metrics(
        self,
        *,
        response: Any,
        model: str,
        model_source: str,
        elapsed: float,
    ) -> dict[str, Any]:
        """Build structured latency/token metrics from a litellm response."""
        prompt_tokens = self._usage_value(response, "prompt_tokens")
        completion_tokens = self._usage_value(response, "completion_tokens")
        tokens_per_sec = (
            round(completion_tokens / elapsed, 2)
            if completion_tokens is not None and elapsed > 0
            else None
        )

        return {
            "agent": self.name,
            "model": model,
            "model_source": model_source,
            "latency_ms": round(elapsed * 1000, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tokens_per_sec": tokens_per_sec,
        }

    @staticmethod
    def _usage_value(response: Any, key: str) -> int | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if isinstance(usage, dict):
            value = usage.get(key)
        else:
            value = getattr(usage, key, None)
        if isinstance(value, (int, float)):
            return int(value)
        return None

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
        """LangGraph node entry-point. Delegates to ``process``."""
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
