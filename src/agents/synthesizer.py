"""Synthesizer agent — merges specialist outputs into a cohesive response."""

from __future__ import annotations

from src.models.state import HealthcareState
from src.prompts.synthesizer import SYSTEM_PROMPT, build_prompt

from .base import FALLBACK_MESSAGE, HealthcareAgent


class SynthesizerAgent(HealthcareAgent):
    """Reads all specialist outputs and produces the final patient-facing response."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="synthesizer", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        specialist_outputs = state.get("specialist_outputs") or {}
        safety_escalation = state.get("safety_escalation", False)
        evidence_context = state.get("evidence_context") or {}
        citations = state.get("citations") or []
        drug_interactions = state.get("drug_interactions") or []

        language = state.get("language", "en")

        # Build a dynamic system prompt that includes the specialist outputs.
        dynamic_prompt = build_prompt(
            specialist_outputs,
            safety_escalation,
            evidence_context=evidence_context or None,
            citations=citations or None,
            drug_interactions=drug_interactions or None,
            language=language,
        )

        messages = self._build_messages(state, system_prompt_override=dynamic_prompt)
        response = await self._call_llm(messages)

        # Strip the safety marker from the final user-facing text if present.
        final_text = response.replace("[SAFETY_ESCALATION]", "").strip()

        if not final_text:
            final_text = FALLBACK_MESSAGE

        return {
            "final_response": final_text,
            "messages": [
                {"role": "user", "content": state.get("user_input", "")},
                {"role": "assistant", "content": final_text},
            ],
        }
