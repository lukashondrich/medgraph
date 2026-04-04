"""Agent-facing tool functions for drug interaction screening.

These are the public tools the Drug Interaction Agent calls. Each tool
handles the full pipeline internally: resolve name → query API → parse →
return typed model. The agent never sees httpx, rate limits, or retry logic.

Usage:
    from data.openfda.client import OpenFDAClient
    from data.openfda.tools import screen_drug_pair, screen_all_pairs

    with OpenFDAClient() as client:
        result = screen_drug_pair(client, "WARFARIN", "NAPROXEN")
        results = screen_all_pairs(client, patient.medications)
"""

import itertools
import logging
from typing import Optional

from ..schemas import Medication
from .adverse_events import get_pair_adverse_events
from .client import OpenFDAClient
from .drug_labels import fetch_drug_label
from .drug_resolver import resolve_medication
from .schemas import (
    AdverseEventResult,
    DrugLabelResult,
    InteractionScreenResult,
)

logger = logging.getLogger(__name__)


# ── Drug Class Aliases ───────────────────────────────────────────────────
# FDA labels often reference drug classes ("NSAIDs") rather than specific drugs.
# When checking if warfarin's label mentions naproxen, we also search for "NSAID".

_CLASS_ALIASES: dict[str, list[str]] = {
    # NSAIDs
    "NAPROXEN": ["nsaid", "nonsteroidal anti-inflammatory", "non-steroidal"],
    "IBUPROFEN": ["nsaid", "nonsteroidal anti-inflammatory", "non-steroidal"],
    "DICLOFENAC": ["nsaid", "nonsteroidal anti-inflammatory", "non-steroidal"],
    "MELOXICAM": ["nsaid", "nonsteroidal anti-inflammatory", "non-steroidal"],
    "CELECOXIB": ["nsaid", "nonsteroidal anti-inflammatory", "non-steroidal", "cox-2"],
    "ASPIRIN": ["nsaid", "nonsteroidal anti-inflammatory", "salicylate", "antiplatelet"],
    # ACE inhibitors
    "LISINOPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    "ENALAPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    "RAMIPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    "CAPTOPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    "BENAZEPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    "FOSINOPRIL": ["ace inhibitor", "angiotensin-converting enzyme", "acei"],
    # ARBs
    "LOSARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    "VALSARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    "OLMESARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    "CANDESARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    "IRBESARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    "TELMISARTAN": ["angiotensin receptor blocker", "angiotensin ii receptor", "arb"],
    # Anticoagulants
    "WARFARIN": ["anticoagulant", "coumarin", "vitamin k antagonist"],
    "APIXABAN": ["anticoagulant", "factor xa inhibitor"],
    "RIVAROXABAN": ["anticoagulant", "factor xa inhibitor"],
    "DABIGATRAN": ["anticoagulant", "thrombin inhibitor"],
    # Antiplatelets
    "CLOPIDOGREL": ["antiplatelet", "p2y12 inhibitor", "thienopyridine"],
    "PRASUGREL": ["antiplatelet", "p2y12 inhibitor", "thienopyridine"],
    "TICAGRELOR": ["antiplatelet", "p2y12 inhibitor"],
    # SSRIs
    "SERTRALINE": ["ssri", "selective serotonin reuptake inhibitor", "serotonergic"],
    "FLUOXETINE": ["ssri", "selective serotonin reuptake inhibitor", "serotonergic"],
    "PAROXETINE": ["ssri", "selective serotonin reuptake inhibitor", "serotonergic"],
    "CITALOPRAM": ["ssri", "selective serotonin reuptake inhibitor", "serotonergic"],
    "ESCITALOPRAM": ["ssri", "selective serotonin reuptake inhibitor", "serotonergic"],
    # Statins
    "SIMVASTATIN": ["statin", "hmg-coa reductase inhibitor"],
    "ATORVASTATIN": ["statin", "hmg-coa reductase inhibitor"],
    "ROSUVASTATIN": ["statin", "hmg-coa reductase inhibitor"],
    "PRAVASTATIN": ["statin", "hmg-coa reductase inhibitor"],
    "LOVASTATIN": ["statin", "hmg-coa reductase inhibitor"],
    # Beta blockers
    "METOPROLOL": ["beta-blocker", "beta blocker", "beta-adrenergic blocker"],
    "ATENOLOL": ["beta-blocker", "beta blocker", "beta-adrenergic blocker"],
    "PROPRANOLOL": ["beta-blocker", "beta blocker", "beta-adrenergic blocker"],
    "CARVEDILOL": ["beta-blocker", "beta blocker", "alpha/beta-blocker"],
    "BISOPROLOL": ["beta-blocker", "beta blocker", "beta-adrenergic blocker"],
    # Diuretics
    "HYDROCHLOROTHIAZIDE": ["diuretic", "thiazide"],
    "FUROSEMIDE": ["diuretic", "loop diuretic"],
    "SPIRONOLACTONE": ["diuretic", "aldosterone antagonist", "potassium-sparing"],
    "CHLORTHALIDONE": ["diuretic", "thiazide-like"],
    # Insulin
    "INSULIN": ["hypoglycemic", "antidiabetic"],
    # Metformin
    "METFORMIN": ["biguanide", "antidiabetic", "hypoglycemic"],
}


# ── Cross-Mention Detection ─────────────────────────────────────────────


def _get_search_terms(drug_name: str) -> list[str]:
    """Get all search terms for a drug: its name + class aliases.

    Returns lowercased terms for case-insensitive matching.
    """
    terms = [drug_name.lower()]
    aliases = _CLASS_ALIASES.get(drug_name.upper(), [])
    terms.extend(aliases)
    return terms


def _check_label_mentions(
    label: DrugLabelResult,
    target_drug: str,
) -> tuple[bool, Optional[str]]:
    """Check if a label mentions another drug (by name or class).

    Searches drug_interactions, warnings_and_cautions, contraindications,
    and drug_interactions_otc sections.

    Returns:
        (found, excerpt) — whether mentioned and a relevant text excerpt.
    """
    search_terms = _get_search_terms(target_drug)

    # Sections to search (in priority order)
    search_sections = [
        "drug_interactions",
        "drug_interactions_otc",
        "warnings_and_cautions",
        "contraindications",
        "boxed_warning",
    ]

    for section_key in search_sections:
        section = label.sections.get(section_key)
        if not section:
            continue

        text_lower = section.raw_text.lower()

        for term in search_terms:
            pos = text_lower.find(term)
            if pos != -1:
                # Extract surrounding context (~300 chars centered on match)
                start = max(0, pos - 150)
                end = min(len(section.raw_text), pos + len(term) + 150)

                # Try to start at a sentence boundary
                if start > 0:
                    sentence_start = section.raw_text.rfind(".", start - 1, pos)
                    if sentence_start != -1:
                        start = sentence_start + 1

                # Try to end at a sentence boundary
                sentence_end = section.raw_text.find(".", end - 1, end + 100)
                if sentence_end != -1:
                    end = sentence_end + 1

                excerpt = section.raw_text[start:end].strip()
                return True, excerpt

    return False, None


# ── Public Tool Functions ────────────────────────────────────────────────


def get_drug_label(
    client: OpenFDAClient,
    drug_name: str,
) -> Optional[DrugLabelResult]:
    """Fetch the FDA label for a drug by generic name.

    Args:
        client: OpenFDA HTTP client.
        drug_name: Generic drug name (case-insensitive).

    Returns:
        DrugLabelResult with parsed sections, or None if not found.
    """
    return fetch_drug_label(client, drug_name.upper())


def get_drug_label_for_medication(
    client: OpenFDAClient,
    medication: Medication,
) -> list[DrugLabelResult]:
    """Fetch FDA labels for a patient medication.

    Handles combo products — returns one label per component.

    Args:
        client: OpenFDA HTTP client.
        medication: A Medication model from the patient profile.

    Returns:
        List of DrugLabelResult (one per resolved component). May be empty.
    """
    generic_names = resolve_medication(medication)
    results = []

    for name in generic_names:
        label = fetch_drug_label(client, name)
        if label:
            results.append(label)

    return results


def get_adverse_events(
    client: OpenFDAClient,
    drug_name: str,
) -> Optional[AdverseEventResult]:
    """Get top FAERS serious adverse events for a single drug.

    Args:
        client: OpenFDA HTTP client.
        drug_name: Generic drug name (case-insensitive).

    Returns:
        AdverseEventResult with top reactions, or None if no data.
    """
    from .adverse_events import get_top_adverse_events
    return get_top_adverse_events(client, drug_name.upper())


def screen_drug_pair(
    client: OpenFDAClient,
    drug_a: str,
    drug_b: str,
) -> Optional[InteractionScreenResult]:
    """Screen a drug pair for interactions using FDA labels and FAERS data.

    The primary tool. Fetches both labels, checks if each mentions the other
    (using drug name + class aliases), queries FAERS co-reporting, and returns
    a structured result with confidence notes.

    Args:
        client: OpenFDA HTTP client.
        drug_a: First drug generic name (case-insensitive).
        drug_b: Second drug generic name (case-insensitive).

    Returns:
        InteractionScreenResult, or None if neither drug has label data.
    """
    a_upper = drug_a.upper()
    b_upper = drug_b.upper()

    # Fetch labels
    label_a = fetch_drug_label(client, a_upper)
    label_b = fetch_drug_label(client, b_upper)

    if not label_a and not label_b:
        logger.debug("No labels found for %s or %s", a_upper, b_upper)
        return None

    # Check cross-mentions
    a_mentions_b = False
    text_a = None
    if label_a:
        a_mentions_b, text_a = _check_label_mentions(label_a, b_upper)

    b_mentions_a = False
    text_b = None
    if label_b:
        b_mentions_a, text_b = _check_label_mentions(label_b, a_upper)

    # FAERS co-reporting
    faers = get_pair_adverse_events(client, a_upper, b_upper)

    # Build confidence note
    confidence_parts = []
    if label_a:
        confidence_parts.append(f"{a_upper} label: found")
        if label_a.has_interactions:
            confidence_parts.append("interactions section present")
    else:
        confidence_parts.append(f"{a_upper} label: not found")

    if label_b:
        confidence_parts.append(f"{b_upper} label: found")
        if label_b.has_interactions:
            confidence_parts.append("interactions section present")
    else:
        confidence_parts.append(f"{b_upper} label: not found")

    if faers:
        confidence_parts.append(
            f"FAERS co-reports: {faers.total_reports or 'available'}"
        )
    else:
        confidence_parts.append("FAERS co-reports: no data")

    return InteractionScreenResult(
        drug_a=a_upper,
        drug_b=b_upper,
        label_a_mentions_b=a_mentions_b,
        label_b_mentions_a=b_mentions_a,
        interaction_text_a=text_a,
        interaction_text_b=text_b,
        faers_coreported=faers,
        confidence_note="; ".join(confidence_parts),
    )


def screen_all_pairs(
    client: OpenFDAClient,
    medications: list[Medication],
) -> list[InteractionScreenResult]:
    """Screen all medication pairs for interactions.

    Batch tool for proactive research. Resolves all medications, generates
    all unique pairs, screens each, returns only pairs with findings.

    Args:
        client: OpenFDA HTTP client.
        medications: List of active Medication models from patient profile.

    Returns:
        List of InteractionScreenResult for pairs with any signal.
    """
    # Resolve all medications to generic names
    drug_names: list[str] = []
    seen: set[str] = set()

    for med in medications:
        names = resolve_medication(med)
        for name in names:
            if name not in seen:
                drug_names.append(name)
                seen.add(name)

    logger.info(
        "Screening %d drugs (%d unique pairs) for interactions",
        len(drug_names),
        len(drug_names) * (len(drug_names) - 1) // 2,
    )

    # Pre-fetch all labels (cache will make pair screening fast)
    for name in drug_names:
        fetch_drug_label(client, name)

    # Screen all unique pairs
    results: list[InteractionScreenResult] = []

    for a, b in itertools.combinations(drug_names, 2):
        result = screen_drug_pair(client, a, b)
        if result is None:
            continue

        # Only include pairs with actual findings
        has_signal = (
            result.label_a_mentions_b
            or result.label_b_mentions_a
            or (result.faers_coreported and result.faers_coreported.top_reactions)
        )

        if has_signal:
            results.append(result)

    logger.info("Found %d interaction signals out of %d pairs screened",
                len(results), len(drug_names) * (len(drug_names) - 1) // 2)

    return results
