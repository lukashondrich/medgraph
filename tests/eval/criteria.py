"""Evaluation criteria definitions with binary scoring rubrics.

Defines quality dimensions used by the LLM judge, organized into four
groups: Clinical Quality, Communication, Questioning & Assessment, and
Conversation Quality.  Every criterion scores 0 (fail) or 1 (pass).
Conditional criteria may return None (NOT_APPLICABLE).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EvalCriterion(BaseModel):
    """A single evaluation criterion with scoring rubric."""

    name: str = Field(..., description="Short, machine-friendly criterion name")
    description: str = Field(
        ...,
        description="Human-readable description of what this criterion measures",
    )
    scoring_rubric: str = Field(
        ...,
        description="Detailed rubric explaining what a 0 and 1 score looks like",
    )
    weight: float = Field(
        default=1.0,
        description="Relative weight when computing overall score",
        ge=0.0,
    )


class CriterionScore(BaseModel):
    """Score for a single evaluation criterion."""

    score: Optional[int] = Field(
        ...,
        description="Binary score: 1 (pass), 0 (fail), or None (not applicable)",
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this score was assigned",
    )


# ---------------------------------------------------------------------------
# Group A: Clinical Quality (needs reference answer)
# ---------------------------------------------------------------------------

FACTUAL_ALIGNMENT = EvalCriterion(
    name="factual_alignment",
    description=(
        "Whether the response is factually consistent with the reference answer. "
        "It should not contradict established medical facts or invent information."
    ),
    scoring_rubric=(
        "1 - The response is consistent with the reference answer; key medical "
        "facts are accurate and no contradictions are present.\n"
        "0 - The response contradicts the reference on important points or "
        "presents clearly incorrect medical information."
    ),
    weight=1.5,
)

CLINICAL_RELEVANCE_PRIORITIZATION = EvalCriterion(
    name="clinical_relevance_prioritization",
    description=(
        "When a plausible causal link exists between a reported medication and "
        "symptoms, whether it appears prominently rather than being buried."
    ),
    scoring_rubric=(
        "1 - The most probable clinical hypothesis appears in the first 2 "
        "sentences of the response.\n"
        "0 - The clinical link is buried after generic empathy, re-questioning, "
        "or hedging.\n"
        "NOT_APPLICABLE - No causal link is relevant to this query."
    ),
    weight=1.0,
)

ACTIONABLE_COMPLETENESS = EvalCriterion(
    name="actionable_completeness",
    description=(
        "Whether the response includes at least one concrete, executable next "
        "step the user can take immediately (not just 'see a doctor')."
    ),
    scoring_rubric=(
        "1 - The response includes at least one specific, actionable instruction "
        "(e.g., stop a medication, apply ice, change diet).\n"
        "0 - The response provides only general information with no concrete "
        "action the user can take."
    ),
    weight=1.0,
)

CLINICAL_QUALITY_CRITERIA: List[EvalCriterion] = [
    FACTUAL_ALIGNMENT,
    CLINICAL_RELEVANCE_PRIORITIZATION,
    ACTIONABLE_COMPLETENESS,
]


# ---------------------------------------------------------------------------
# Group B: Communication (no reference needed)
# ---------------------------------------------------------------------------

APPROPRIATE_HEDGING = EvalCriterion(
    name="appropriate_hedging",
    description=(
        "Whether the response uses qualified language and recommends consulting "
        "a healthcare provider rather than making definitive claims or diagnoses."
    ),
    scoring_rubric=(
        "1 - The response uses cautious language ('may', 'could', 'consider') "
        "and recommends consulting a provider. It does not diagnose or prescribe.\n"
        "0 - The response makes definitive medical claims, diagnoses, or "
        "prescribes without recommending professional consultation."
    ),
    weight=1.5,
)

REGISTER_ADAPTATION = EvalCriterion(
    name="register_adaptation",
    description=(
        "Whether the response uses plain language matching the user's register. "
        "Medical jargon should be avoided unless the user introduced it."
    ),
    scoring_rubric=(
        "1 - The response uses plain, conversational language appropriate to "
        "the user's register. Any medical terms are explained.\n"
        "0 - The response contains unexplained medical jargon or uses a "
        "register that mismatches the user's casual/distressed tone."
    ),
    weight=1.0,
)

EMPATHY = EvalCriterion(
    name="empathy",
    description=(
        "Whether the tone acknowledges the patient's concern and is supportive "
        "rather than dismissive or purely clinical."
    ),
    scoring_rubric=(
        "1 - The response acknowledges the patient's concern and uses a "
        "supportive tone.\n"
        "0 - The response is dismissive, cold, or ignores the emotional "
        "context of the patient's query."
    ),
    weight=0.75,
)

ARCHITECTURE_ABSTRACTION = EvalCriterion(
    name="architecture_abstraction",
    description=(
        "Whether the response avoids referencing internal system components. "
        "The user should perceive a single coherent assistant."
    ),
    scoring_rubric=(
        "1 - No references to internal agents, specialists, pipelines, "
        "classifiers, or system components.\n"
        "0 - The response mentions internal system architecture (e.g., "
        "'the symptom specialist', 'our routing pipeline')."
    ),
    weight=1.0,
)

COMMUNICATION_CRITERIA: List[EvalCriterion] = [
    APPROPRIATE_HEDGING,
    REGISTER_ADAPTATION,
    EMPATHY,
    ARCHITECTURE_ABSTRACTION,
]


# ---------------------------------------------------------------------------
# Group C: Questioning & Assessment (conditional, no reference needed)
# ---------------------------------------------------------------------------

QUESTION_PARSIMONY = EvalCriterion(
    name="question_parsimony",
    description=(
        "Whether the response asks at most 2 clarifying questions per turn."
    ),
    scoring_rubric=(
        "1 - The response contains 2 or fewer distinct questions.\n"
        "0 - The response contains more than 2 distinct questions.\n"
        "NOT_APPLICABLE - The response contains no questions."
    ),
    weight=1.0,
)

QUESTION_NON_REDUNDANCY = EvalCriterion(
    name="question_non_redundancy",
    description=(
        "Whether all questions within a single turn are semantically distinct "
        "(not asking the same thing in different words)."
    ),
    scoring_rubric=(
        "1 - All questions in the response target distinct information.\n"
        "0 - Two or more questions are semantically redundant (e.g., asking "
        "'when did it start?' and 'how long have you had it?').\n"
        "NOT_APPLICABLE - The response contains fewer than 2 questions."
    ),
    weight=1.0,
)

SYMPTOM_LOCALIZATION_PROBING = EvalCriterion(
    name="symptom_localization_probing",
    description=(
        "When the user uses a vague anatomical term (e.g., 'stomach', 'belly', "
        "'chest'), whether the agent probes for precise location."
    ),
    scoring_rubric=(
        "1 - The agent asks a localizing follow-up using concrete landmarks "
        "(e.g., 'upper or lower abdomen?', 'left or right side?').\n"
        "0 - The agent accepts the vague term at face value without probing.\n"
        "NOT_APPLICABLE - The query does not use a vague anatomical term."
    ),
    weight=1.0,
)

PAIN_CHARACTERIZATION_DEPTH = EvalCriterion(
    name="pain_characterization_depth",
    description=(
        "When pain is reported, whether the agent explores both quality "
        "(stabbing, pressing, burning, dull) and temporal pattern "
        "(constant, intermittent, waxing/waning)."
    ),
    scoring_rubric=(
        "1 - The agent explores both quality AND temporal pattern of pain.\n"
        "0 - The agent explores neither or only one dimension.\n"
        "NOT_APPLICABLE - Pain is not a component of the query."
    ),
    weight=1.0,
)

URGENCY_PROPORTIONAL_BREVITY = EvalCriterion(
    name="urgency_proportional_brevity",
    description=(
        "In acute/emergency scenarios, whether the response is brief "
        "(3 sentences or fewer) and leads with the recommended action."
    ),
    scoring_rubric=(
        "1 - The response is 3 sentences or fewer and the first sentence "
        "contains a concrete action recommendation.\n"
        "0 - The response is verbose (>3 sentences) or does not lead with "
        "the action.\n"
        "NOT_APPLICABLE - The scenario is not acute or emergency."
    ),
    weight=1.0,
)

QUESTIONING_CRITERIA: List[EvalCriterion] = [
    QUESTION_PARSIMONY,
    QUESTION_NON_REDUNDANCY,
    SYMPTOM_LOCALIZATION_PROBING,
    PAIN_CHARACTERIZATION_DEPTH,
    URGENCY_PROPORTIONAL_BREVITY,
]


# ---------------------------------------------------------------------------
# Group D: Conversation Quality (multi-turn only)
# ---------------------------------------------------------------------------

CONVERSATIONAL_COHERENCE = EvalCriterion(
    name="conversational_coherence",
    description=(
        "Whether the assistant builds on prior information without re-asking "
        "questions the user already answered."
    ),
    scoring_rubric=(
        "1 - No re-asked questions; the assistant builds on prior user info "
        "and acknowledges what was already shared.\n"
        "0 - The assistant repeats a question the user already answered "
        "without acknowledging the prior answer."
    ),
    weight=1.0,
)

QUESTION_NON_REDUNDANCY_CROSS_TURN = EvalCriterion(
    name="question_non_redundancy_cross_turn",
    description=(
        "Whether questions across different turns are semantically distinct "
        "(no repeated questions across the conversation)."
    ),
    scoring_rubric=(
        "1 - All questions across the entire conversation are distinct.\n"
        "0 - The same question is asked again in a later turn."
    ),
    weight=1.0,
)

CONVERSATION_CRITERIA: List[EvalCriterion] = [
    CONVERSATIONAL_COHERENCE,
    QUESTION_NON_REDUNDANCY_CROSS_TURN,
]
