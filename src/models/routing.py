from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Structured output from the router LLM call.

    Used with litellm's response_format to get typed JSON from the LLM.
    """

    agents: list[Literal["symptom", "medication", "lifestyle", "evidence", "drug_check"]] = Field(
        description="Specialist agents to consult for this query"
    )
    reasoning: str = Field(
        description="Why these agents were selected"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Router confidence in this classification"
    )
