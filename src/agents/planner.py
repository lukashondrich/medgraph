"""Planner: decides which sources to consult and what to search for."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from src.data.profile import TestReading, UserProfile
from src.models.state import MedGraphState
from src.prompts.planner import SYSTEM_PROMPT
from src.sources.queries import question_queries, reading_queries

from .base import FALLBACK_MESSAGE, HealthcareAgent

logger = logging.getLogger(__name__)

SourceName = Literal["reference_ranges", "study_library", "guidelines"]
ALL_SOURCES: list[str] = ["reference_ranges", "study_library", "guidelines"]
MAX_QUERIES = 3


class LookupPlan(BaseModel):
    """Structured planner output."""

    on_topic: bool = True
    sources: list[SourceName] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PlannerAgent(HealthcareAgent):
    """Plans the lookups for one turn. Never produces user-facing text."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="planner", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: MedGraphState) -> dict:
        if state.get("turn_kind") == "new_reading" and state.get("reading"):
            # Fixed lookups for a new reading: no model call needed.
            profile = UserProfile.model_validate(state["patient"])
            reading = TestReading.model_validate(state["reading"])
            plan = LookupPlan(sources=ALL_SOURCES, queries=reading_queries(profile, reading))
        else:
            plan = await self._plan_question(state)

        return {
            "route": list(plan.sources) if plan.on_topic else [],
            "queries": plan.queries if plan.on_topic else [],
            "route_reasoning": plan.reasoning,
            "handoff_chain": [self.name],
        }

    async def _plan_question(self, state: MedGraphState) -> LookupPlan:
        question = state.get("user_input", "")
        messages = self._build_messages(state)
        for attempt in range(2):
            raw = await self._call_llm(messages, response_format={"type": "json_object"})
            if raw == FALLBACK_MESSAGE:
                break
            try:
                plan = LookupPlan.model_validate(json.loads(raw))
            except Exception as exc:  # noqa: BLE001 - bad JSON or wrong shape
                logger.warning("Planner output attempt %d unusable: %s", attempt + 1, exc)
                continue
            if plan.on_topic:
                queries = [q.strip() for q in plan.queries if q.strip()][:MAX_QUERIES]
                plan.queries = queries or question_queries(question)
                plan.sources = plan.sources or ["study_library"]
            return plan

        # Planning failed: look everywhere with the question as the query.
        logger.error("Planner failed; consulting all sources")
        return LookupPlan(
            sources=ALL_SOURCES,
            queries=question_queries(question),
            reasoning="Planning failed; all sources consulted.",
        )
