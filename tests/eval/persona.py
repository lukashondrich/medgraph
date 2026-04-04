"""Multi-turn persona simulation for evaluation.

Defines Persona and Transcript models plus a PersonaSimulator that drives
multi-turn conversations through the orchestration graph by role-playing
patient personas via LLM.
"""

from __future__ import annotations

import logging
from typing import List

import litellm
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Persona(BaseModel):
    """A simulated patient persona for multi-turn evaluation."""

    name: str = Field(..., description="Unique persona identifier")
    description: str = Field(
        ..., description="Background: age, symptoms, medications, speaking style"
    )
    starting_message: str = Field(
        ..., description="The first message the persona sends"
    )
    goal: str = Field(
        ..., description="What the persona wants to learn or achieve"
    )
    max_turns: int = Field(
        default=4, description="Maximum conversation turns (user-assistant pairs)"
    )
    eval_groups: List[str] = Field(
        ...,
        description=(
            "Which judge groups to apply: 'clinical', 'communication', "
            "'questioning', 'conversation'"
        ),
    )


class Transcript(BaseModel):
    """A completed multi-turn conversation."""

    persona_name: str = Field(..., description="Name of the persona used")
    turns: List[dict] = Field(
        ...,
        description=(
            "Conversation turns as list of "
            "{'role': 'user'|'assistant', 'content': '...'} dicts"
        ),
    )
    turn_count: int = Field(
        ..., description="Number of user-assistant exchange pairs"
    )


# ---------------------------------------------------------------------------
# Patient role-play prompt
# ---------------------------------------------------------------------------

_PATIENT_SYSTEM_PROMPT = """\
You are role-playing as a patient in a conversation with a healthcare
assistant.  Stay fully in character based on the persona description below.

PERSONA
-------
{persona_description}

GOAL: {goal}

RULES
- Answer questions based on your background.  Only reveal information when
  asked -- do not volunteer everything at once.
- Match your persona's natural speaking style and register.
- Keep your responses short (1-3 sentences), like a real patient texting.
- If the assistant has adequately addressed your goal, say "thank you" to
  end the conversation.
- Never break character or acknowledge that you are an AI.
"""


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class PersonaSimulator:
    """Drives multi-turn conversations through the graph using persona LLM.

    Parameters
    ----------
    model : str
        litellm model identifier for generating patient replies.
    graph
        Compiled LangGraph graph (must support ``ainvoke``).
    """

    def __init__(self, model: str, graph) -> None:
        self.model = model
        self.graph = graph

    async def run(self, persona: Persona) -> Transcript:
        """Simulate a full conversation for the given persona.

        Returns a Transcript with interleaved user/assistant messages.
        """
        history: List[dict] = []
        user_message = persona.starting_message
        turn_count = 0

        for _ in range(persona.max_turns):
            # Record user message
            history.append({"role": "user", "content": user_message})

            # Send through the orchestration graph
            state = self._build_state(user_message, history)
            result = await self.graph.ainvoke(state)
            assistant_response = result.get("final_response", "")

            # Record assistant message
            history.append({"role": "assistant", "content": assistant_response})
            turn_count += 1

            # Check if conversation should end
            if not assistant_response:
                break

            # Generate patient reply
            user_message = await self._generate_patient_reply(persona, history)

            # End if patient says thank you (goal satisfied)
            if "thank you" in user_message.lower():
                history.append({"role": "user", "content": user_message})
                break

        return Transcript(
            persona_name=persona.name,
            turns=history,
            turn_count=turn_count,
        )

    async def _generate_patient_reply(
        self, persona: Persona, history: List[dict]
    ) -> str:
        """Use LLM to generate the next patient message in character."""
        system_prompt = _PATIENT_SYSTEM_PROMPT.format(
            persona_description=persona.description,
            goal=persona.goal,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
        ]

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=256,
            )
            return response.choices[0].message.content  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("Patient reply generation failed: %s", exc)
            return "thank you"

    @staticmethod
    def _build_state(user_input: str, history: List[dict]) -> dict:
        """Build a HealthcareState dict for graph.ainvoke()."""
        return {
            "messages": history[:-1],  # prior messages (exclude current user input)
            "user_input": user_input,
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
        }
