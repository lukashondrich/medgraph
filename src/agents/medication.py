"""Medication information specialist agent."""

from __future__ import annotations

from src.models.state import HealthcareState
from src.prompts.medication import SYSTEM_PROMPT

from .base import HealthcareAgent


class MedicationAgent(HealthcareAgent):
    """Provides medication information, side effects, and interaction guidance."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            name="medication",
            system_prompt=SYSTEM_PROMPT,
            model=model,
            local_first=True,
            local_model_env="LOCAL_SPECIALIST_MODEL",
            local_api_base_env="LOCAL_SPECIALIST_API_BASE",
            cache_prompt_local=True,
        )

    async def process(self, state: HealthcareState) -> dict:
        messages = self._build_messages(state)
        response = await self._call_llm(messages)

        return {
            "specialist_outputs": {self.name: response},
            "handoff_chain": [self.name],
            "safety_escalation": self._detect_safety_escalation(response),
        }
