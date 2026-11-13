"""Writer agent: composes the answer from gathered evidence only."""

from __future__ import annotations

import logging

from src.models.state import MedGraphState
from src.prompts.writer import SYSTEM_PROMPT, assign_markers, build_prompt

from .base import FALLBACK_MESSAGE, HealthcareAgent
from .citation_check import CheckedAnswer, check_citations

logger = logging.getLogger(__name__)

NEW_READING_INPUT = "I just took a test. Please explain my result."

_RETRY_NOTE = (
    "\n\n## Correction\n\nYour previous reply contained no valid evidence keys. "
    "Rewrite it so that every claim about pH ranges, causes or risks is "
    "followed by the key of the evidence it rests on, for example [S1]."
)


class WriterAgent(HealthcareAgent):
    """Writes the user-facing answer and validates its citations."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="writer", system_prompt=SYSTEM_PROMPT, model=model)

    async def _write(self, state: MedGraphState, prompt: str, marker_map) -> CheckedAnswer | None:
        messages = self._build_messages(state, system_prompt_override=prompt)
        response = await self._call_llm(messages)
        if not response or response == FALLBACK_MESSAGE:
            return None
        return check_citations(response, marker_map)

    async def process(self, state: MedGraphState) -> dict:
        marker_map = assign_markers(state.get("sources") or {})
        reading = state.get("reading") or {}
        turn_kind = state.get("turn_kind") or "question"
        prompt = build_prompt(
            marker_map,
            turn_kind=turn_kind,
            evidence_gap=state.get("evidence_gap"),
            reading_confidence=reading.get("confidence"),
            safety_reasons=state.get("safety_reasons"),
            language=state.get("language", "en"),
        )

        answer = await self._write(state, prompt, marker_map)
        # Evidence was available but nothing valid was cited: one retry.
        if answer is not None and marker_map and not answer.citations:
            logger.warning("Writer produced no valid citations; retrying once")
            retry = await self._write(state, prompt + _RETRY_NOTE, marker_map)
            if retry is not None and retry.citations:
                answer = retry

        if answer is None:
            text, citations = FALLBACK_MESSAGE, []
            safety = False
        else:
            safety = self._detect_safety_escalation(answer.text)
            text = answer.text.replace("[SAFETY_ESCALATION]", "").strip() or FALLBACK_MESSAGE
            citations = [c.model_dump() for c in answer.citations]

        return {
            "final_response": text,
            "citations": citations,
            "safety_escalation": safety,
            "messages": [
                {"role": "user", "content": state.get("user_input", "")},
                {"role": "assistant", "content": text},
            ],
            "handoff_chain": [self.name],
        }
