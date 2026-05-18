"""Drug interaction checking agent — OpenFDA screening of patient medications."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.models.state import HealthcareState
from src.prompts.drug_check import SYSTEM_PROMPT

from .base import HealthcareAgent

logger = logging.getLogger(__name__)


def _format_screening_results(results: list[Any]) -> dict[str, Any]:
    """Convert OpenFDA interaction results into DrugCheckAgent state fields."""
    interactions = []
    has_high_severity = False
    for result in results:
        result_dict = (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else dict(result)
        )
        severity = (
            "high"
            if (
                result_dict.get("label_a_mentions_b")
                or result_dict.get("label_b_mentions_a")
            )
            else "moderate"
        )

        interaction = {
            "drug_a": result_dict.get("drug_a", ""),
            "drug_b": result_dict.get("drug_b", ""),
            "label_a_mentions_b": result_dict.get("label_a_mentions_b", False),
            "label_b_mentions_a": result_dict.get("label_b_mentions_a", False),
            "interaction_text_a": result_dict.get("interaction_text_a"),
            "interaction_text_b": result_dict.get("interaction_text_b"),
            "severity": severity,
            "confidence_note": result_dict.get("confidence_note", ""),
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


def _mcp_tool_data(result: Any) -> list[Any]:
    """Return FastMCP tool payloads while isolating version-specific shape assumptions."""
    data = getattr(result, "data", None)
    if data is None:
        return []
    if isinstance(data, list):
        return data

    logger.warning(
        "Unexpected OpenFDA MCP result.data shape %s; ignoring payload",
        type(data).__name__,
    )
    return []


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

        return _format_screening_results(results)

    except Exception as e:
        logger.warning("Drug interaction screening failed: %s", e)
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": f"Screening unavailable: {e}",
        }


async def screen_patient_medications_via_mcp(
    patient: dict,
    user_input: str = "",
) -> dict[str, Any]:
    """Screen patient medications through the OpenFDA MCP server."""
    medications = patient.get("medications", [])
    if not medications:
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": "No medications to screen.",
        }

    active_medications = [
        med_dict for med_dict in medications if med_dict.get("status") == "active"
    ]
    if len(active_medications) < 2:
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": f"Only {len(active_medications)} active medication(s) — no pairs to screen.",
        }

    try:
        from fastmcp import Client

        mcp_url = os.getenv("OPENFDA_MCP_URL", "http://localhost:8001/mcp/")
        async with Client(mcp_url) as client:
            result = await client.call_tool(
                "screen_all_pairs",
                {"medications": active_medications},
            )
        # FastMCP exposes return values on result.data for the tested Streamable
        # HTTP client version; keep that assumption in one helper for upgrades.
        return _format_screening_results(_mcp_tool_data(result))
    except Exception as e:  # noqa: BLE001
        logger.warning("MCP drug interaction screening failed: %s", e)
        return {
            "drug_interactions": [],
            "safety_escalation": False,
            "summary": f"MCP screening unavailable: {e}",
        }


class DrugCheckAgent(HealthcareAgent):
    """Screens patient medications for drug-drug interactions via OpenFDA."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="drug_check", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        patient = state.get("patient", {})
        user_input = state.get("user_input", "")

        use_mcp = os.getenv("USE_MCP", "false").lower() in ("true", "1", "yes")
        if use_mcp:
            screening = await screen_patient_medications_via_mcp(patient, user_input)
        else:
            screening = screen_patient_medications(patient, user_input)

        return {
            "specialist_outputs": {self.name: screening["summary"]},
            "handoff_chain": [self.name],
            "safety_escalation": screening["safety_escalation"],
            "drug_interactions": screening["drug_interactions"],
        }
