"""Medication information specialist agent."""

from __future__ import annotations

from src.models.state import HealthcareState
from src.prompts.medication import SYSTEM_PROMPT

from .base import HealthcareAgent


class MedicationAgent(HealthcareAgent):
    """Provides medication information, side effects, and interaction guidance."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="medication", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        messages = self._build_messages(state)
        response = await self._call_llm(messages)

        return {
            "specialist_outputs": {self.name: response},
            "handoff_chain": [self.name],
            "safety_escalation": self._detect_safety_escalation(response),
        }
