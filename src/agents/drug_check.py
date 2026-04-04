"""Drug interaction checking agent — OpenFDA screening of patient medications."""

from __future__ import annotations

import logging
from typing import Any

from src.models.state import HealthcareState
from src.prompts.drug_check import SYSTEM_PROMPT

from .base import HealthcareAgent

logger = logging.getLogger(__name__)


def screen_patient_medications(patient: dict, user_input: str = "") -> dict[str, Any]:
    """Screen a patient's medications for drug-drug interactions.

    Args:
        patient: Serialized PatientProfile dict.
        user_input: The user's question (for context).

    Returns:
        Dict with drug_interactions, safety_escalation, and summary.
    """
    medications = patient.get("medications", [])
    if not medications:
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": "No medications to screen.",
        }

    try:
        from src.data.openfda import OpenFDAClient, screen_all_pairs
        from src.data.schemas import Medication

        # Convert dict medications to Medication models
        med_models = []
        for med_dict in medications:
            if med_dict.get("status") == "active":
                med_models.append(Medication.model_validate(med_dict))

        if len(med_models) < 2:
            return {
                "drug_interactions": [],
                "safety_escalation": False,
                "summary": f"Only {len(med_models)} active medication(s) — no pairs to screen.",
            }

        with OpenFDAClient() as client:
            results = screen_all_pairs(client, med_models)

        interactions = []
        has_high_severity = False
        for result in results:
            severity = "high" if (result.label_a_mentions_b or result.label_b_mentions_a) else "moderate"
            if result.label_a_mentions_b and result.label_b_mentions_a:
                severity = "high"

            interaction = {
                "drug_a": result.drug_a,
                "drug_b": result.drug_b,
                "label_a_mentions_b": result.label_a_mentions_b,
                "label_b_mentions_a": result.label_b_mentions_a,
                "interaction_text_a": result.interaction_text_a,
                "interaction_text_b": result.interaction_text_b,
                "severity": severity,
                "confidence_note": result.confidence_note,
            }
            interactions.append(interaction)
            if severity == "high":
                has_high_severity = True

        summary_parts = []
        if interactions:
            summary_parts.append(f"Found {len(interactions)} interaction(s).")
            high = [i for i in interactions if i["severity"] == "high"]
            if high:
                pairs = [f"{i['drug_a']} + {i['drug_b']}" for i in high]
                summary_parts.append(f"High-severity: {', '.join(pairs)}")
        else:
            summary_parts.append("No significant interactions detected.")

        return {
            "drug_interactions": interactions,
            "safety_escalation": has_high_severity,
            "summary": " ".join(summary_parts),
        }

    except Exception as e:
        logger.warning("Drug interaction screening failed: %s", e)
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": f"Screening unavailable: {e}",
        }


class DrugCheckAgent(HealthcareAgent):
    """Screens patient medications for drug-drug interactions via OpenFDA."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="drug_check", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        patient = state.get("patient", {})
        user_input = state.get("user_input", "")

        screening = screen_patient_medications(patient, user_input)

        return {
            "specialist_outputs": {self.name: screening["summary"]},
            "handoff_chain": [self.name],
            "safety_escalation": screening["safety_escalation"],
            "drug_interactions": screening["drug_interactions"],
        }
