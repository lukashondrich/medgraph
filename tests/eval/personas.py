"""Starter persona definitions for multi-turn evaluation."""

from __future__ import annotations

from tests.eval.persona import Persona

# ---------------------------------------------------------------------------
# Persona 1: Ibuprofen + stomach pain (medication-symptom interaction)
# ---------------------------------------------------------------------------

IBUPROFEN_STOMACH_PAIN = Persona(
    name="ibuprofen_stomach_pain",
    description=(
        "35-year-old office worker.  Has had stomach cramps for 2 days.  "
        "Currently taking ibuprofen 400mg twice daily for back pain that "
        "started a week ago.  Speaks casually, uses short sentences.  "
        "Doesn't know ibuprofen can cause stomach problems."
    ),
    starting_message="i have stomach cramps",
    goal="Find out if the cramps are related to ibuprofen and get advice on what to do",
    max_turns=4,
    eval_groups=["communication", "questioning", "conversation"],
)

# ---------------------------------------------------------------------------
# Persona 2: Severe chest pain (emergency/urgency scenario)
# ---------------------------------------------------------------------------

SEVERE_CHEST_PAIN = Persona(
    name="severe_chest_pain",
    description=(
        "55-year-old, sudden crushing chest pain with sweating and nausea "
        "that started 10 minutes ago.  Very distressed, writes short urgent "
        "messages.  History of high blood pressure."
    ),
    starting_message="having bad chest pain and sweating a lot",
    goal="Get immediate guidance on what to do",
    max_turns=2,
    eval_groups=["communication", "questioning"],
)

# ---------------------------------------------------------------------------
# Persona 3: Vague belly pain (localization probing)
# ---------------------------------------------------------------------------

VAGUE_BELLY_CASUAL = Persona(
    name="vague_belly_casual",
    description=(
        "22-year-old college student.  'Belly hurts' for about a week, on "
        "and off.  No medications.  Eats a lot of fast food and energy "
        "drinks.  Speaks very casually, uses slang.  Not sure if it's "
        "serious or just bad diet."
    ),
    starting_message="my belly hurts",
    goal="Figure out what might be causing the pain and whether to see a doctor",
    max_turns=4,
    eval_groups=["communication", "questioning", "conversation"],
)

# ---------------------------------------------------------------------------
# All personas
# ---------------------------------------------------------------------------

ALL_PERSONAS = [
    IBUPROFEN_STOMACH_PAIN,
    SEVERE_CHEST_PAIN,
    VAGUE_BELLY_CASUAL,
]
