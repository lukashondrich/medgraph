"""FHIR R4 Bundle parser — converts Synthea JSON bundles to PatientProfile.

Parses raw FHIR JSON using dict access (no fhir.resources dependency).
Synthea's output is predictable, so raw parsing is reliable and shows
FHIR understanding.

Usage:
    from data.fhir_parser import parse_bundle, parse_directory

    profile = parse_bundle(Path("data/synthea/Aaron_Abernathy.json"))
    all_profiles = parse_directory(Path("data/synthea/"))
"""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from .condition_maps import lookup_condition, lookup_lab_short_name
from .schemas import (
    Allergy,
    Condition,
    LabResult,
    Medication,
    PatientProfile,
)

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_date(date_str: str | None) -> date | None:
    """Parse a FHIR date or dateTime string to a Python date."""
    if not date_str:
        return None
    try:
        # FHIR dates: "2020-01-15" or "2020-01-15T10:30:00-05:00"
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _compute_age(birth_date: date) -> int:
    """Compute current age from a birth date."""
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _shorten_medication_name(display: str) -> str:
    """Derive a short medication name from Synthea's full display text.

    'Hydrochlorothiazide 25 MG Oral Tablet' → 'Hydrochlorothiazide 25mg'
    'Metformin hydrochloride 500 MG Oral Tablet' → 'Metformin 500mg'
    '12 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet'
      → 'Metformin ER 500mg'
    """
    # Remove leading "XX HR " prefix (extended release indicator)
    cleaned = re.sub(r"^\d+\s+HR\s+", "", display)
    # Remove leading "XXX ACTUAT " prefix (inhaler actuations)
    cleaned = re.sub(r"^\d+\s+ACTUAT\s+", "", cleaned)

    # Try to extract drug name and dose (MG or MG/ACTUAT etc.)
    match = re.match(
        r"^(.+?)\s+(\d+(?:\.\d+)?)\s*MG(?:/[A-Z]+)?",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip()
        dose = match.group(2)

        # Clean up common suffixes from name
        for suffix in ["hydrochloride", "sodium", "potassium", "calcium",
                       "mesylate", "besylate", "maleate", "tartrate",
                       "succinate", "fumarate", "acetate", "propionate"]:
            name = re.sub(rf"\s+{suffix}$", "", name, flags=re.IGNORECASE)

        # Check for extended release
        er = " ER" if "extended release" in display.lower() else ""

        return f"{name}{er} {dose}mg"

    # Fallback: first 3 words
    words = display.split()
    return " ".join(words[:3]) if len(words) > 3 else display


def _parse_frequency(dosage: dict | None) -> str | None:
    """Extract frequency from a FHIR dosageInstruction entry."""
    if not dosage:
        return None

    # Try timing.repeat first
    timing = dosage.get("timing", {})
    repeat = timing.get("repeat", {})
    freq = repeat.get("frequency")
    period = repeat.get("period")
    period_unit = repeat.get("periodUnit")

    if freq and period and period_unit:
        if period_unit == "d" and period == 1:
            freq_map = {1: "daily", 2: "BID", 3: "TID", 4: "QID"}
            return freq_map.get(freq, f"{freq}x/day")
        if period_unit == "wk":
            return f"{freq}x/week"

    # Try asNeededBoolean
    if dosage.get("asNeededBoolean"):
        return "PRN"

    # Try text
    text = dosage.get("text", "")
    if text:
        text_lower = text.lower()
        if "twice" in text_lower or "bid" in text_lower:
            return "BID"
        if "once" in text_lower or "daily" in text_lower:
            return "daily"
        if "three" in text_lower or "tid" in text_lower:
            return "TID"

    return None


def _parse_dosage_text(dosage: dict | None) -> str | None:
    """Extract dosage text from a FHIR dosageInstruction entry."""
    if not dosage:
        return None

    # Use the text field if available
    text = dosage.get("text")
    if text:
        return text

    # Build from structured fields
    parts = []
    dose_qty = dosage.get("doseAndRate", [{}])[0].get("doseQuantity", {}) if dosage.get("doseAndRate") else {}
    if dose_qty:
        value = dose_qty.get("value")
        unit = dose_qty.get("unit", "")
        if value is not None:
            parts.append(f"{value} {unit}".strip())

    route = dosage.get("route", {}).get("text")
    if route:
        parts.append(route)

    return " ".join(parts) if parts else None


# ── Main Parser ──────────────────────────────────────────────────────────


def parse_bundle(path: Path) -> PatientProfile:
    """Parse a Synthea FHIR R4 Bundle JSON into a PatientProfile.

    Args:
        path: Path to a Synthea-generated FHIR Bundle JSON file.

    Returns:
        A fully populated PatientProfile with active conditions,
        active medications, allergies, and most recent lab values.

    Raises:
        ValueError: If no Patient resource is found in the bundle.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with open(path) as f:
        bundle = json.load(f)

    entries = bundle.get("entry", [])

    # Build reference map: fullUrl → resource
    ref_map: dict[str, dict] = {}
    for entry in entries:
        full_url = entry.get("fullUrl", "")
        resource = entry.get("resource", {})
        if full_url:
            ref_map[full_url] = resource

    # Collect resources by type
    patient_resource = None
    conditions_raw: list[dict] = []
    med_requests_raw: list[dict] = []
    observations_raw: list[dict] = []
    allergies_raw: list[dict] = []

    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")

        if rtype == "Patient":
            patient_resource = resource
        elif rtype == "Condition":
            conditions_raw.append(resource)
        elif rtype == "MedicationRequest":
            med_requests_raw.append(resource)
        elif rtype == "Observation":
            observations_raw.append(resource)
        elif rtype == "AllergyIntolerance":
            allergies_raw.append(resource)

    if patient_resource is None:
        raise ValueError(f"No Patient resource found in {path}")

    # ── Parse Patient ────────────────────────────────────────────────

    names = patient_resource.get("name", [{}])
    name_entry = names[0] if names else {}
    given = " ".join(name_entry.get("given", [""]))
    family = name_entry.get("family", "")
    name = f"{given} {family}".strip()

    birth_date_str = patient_resource.get("birthDate", "")
    birth_date = _parse_date(birth_date_str) or date(1970, 1, 1)
    age = _compute_age(birth_date)

    gender = patient_resource.get("gender", "unknown")
    sex = "M" if gender == "male" else "F" if gender == "female" else gender

    patient_id = patient_resource.get("id", "")

    # ── Parse Conditions ─────────────────────────────────────────────

    conditions: list[Condition] = []
    for cond in conditions_raw:
        clinical_status = (
            cond.get("clinicalStatus", {})
            .get("coding", [{}])[0]
            .get("code", "unknown")
        )

        # Only include active conditions
        if clinical_status != "active":
            continue

        code_entry = cond.get("code", {}).get("coding", [{}])[0]
        snomed_code = code_entry.get("code", "")
        snomed_display = code_entry.get("display", "Unknown condition")

        # Look up mapping
        mapped = lookup_condition(snomed_code, snomed_display)

        # Onset date
        onset = _parse_date(cond.get("onsetDateTime"))
        if not onset:
            # Fallback: try encounter reference date (not always available)
            onset = _parse_date(cond.get("recordedDate"))

        # Category
        category = None
        cat_list = cond.get("category", [])
        if cat_list:
            cat_coding = cat_list[0].get("coding", [{}])
            if cat_coding:
                category = cat_coding[0].get("code")

        conditions.append(Condition(
            snomed_code=snomed_code,
            snomed_display=snomed_display,
            icd10_code=mapped["icd10"],
            abbreviation=mapped["abbreviation"],
            patient_friendly_name=mapped["patient_name"],
            clinical_status=clinical_status,
            onset_date=onset,
            category=category,
        ))

    # ── Parse Medications ────────────────────────────────────────────

    medications: list[Medication] = []
    for med in med_requests_raw:
        status = med.get("status", "unknown")
        if status != "active":
            continue

        code_entry = (
            med.get("medicationCodeableConcept", {})
            .get("coding", [{}])[0]
        )
        rxnorm_code = code_entry.get("code", "")
        display = code_entry.get("display", "Unknown medication")

        # Dosage
        dosage_instructions = med.get("dosageInstruction", [])
        dosage = dosage_instructions[0] if dosage_instructions else None

        # Reason reference
        reason_code = None
        reason_display = None
        reason_refs = med.get("reasonReference", [])
        if reason_refs:
            ref_url = reason_refs[0].get("reference", "")
            # Try to resolve via ref_map
            # Synthea uses "urn:uuid:..." format
            ref_resource = ref_map.get(ref_url, {})
            if ref_resource:
                reason_coding = ref_resource.get("code", {}).get("coding", [{}])[0]
                reason_code = reason_coding.get("code")
                reason_display = reason_coding.get("display")

        # Dates
        start_date = _parse_date(med.get("authoredOn"))

        medications.append(Medication(
            rxnorm_code=rxnorm_code,
            display=display,
            short_name=_shorten_medication_name(display),
            dosage_text=_parse_dosage_text(dosage),
            frequency=_parse_frequency(dosage),
            status=status,
            start_date=start_date,
            end_date=None,  # Active meds don't have end dates
            reason_code=reason_code,
            reason_display=reason_display,
        ))

    # ── Parse Observations (Labs + Vitals) ───────────────────────────

    # Group by LOINC code, keep most recent per code
    obs_by_loinc: dict[str, dict] = {}
    for obs in observations_raw:
        code_entry = obs.get("code", {}).get("coding", [{}])[0]
        loinc = code_entry.get("code", "")
        if not loinc:
            continue

        obs_date = _parse_date(obs.get("effectiveDateTime"))
        if not obs_date:
            continue

        # Handle valueQuantity
        value_qty = obs.get("valueQuantity")
        if value_qty and "value" in value_qty:
            existing = obs_by_loinc.get(loinc)
            existing_date = _parse_date(existing.get("effectiveDateTime")) if existing else None
            if not existing or (existing_date and obs_date > existing_date):
                obs_by_loinc[loinc] = obs
            continue

        # Handle component-based observations (e.g., blood pressure)
        components = obs.get("component", [])
        for comp in components:
            comp_code = comp.get("code", {}).get("coding", [{}])[0]
            comp_loinc = comp_code.get("code", "")
            comp_value = comp.get("valueQuantity")
            if comp_loinc and comp_value and "value" in comp_value:
                # Create a synthetic observation dict for the component
                synth_obs = {
                    "code": comp.get("code"),
                    "valueQuantity": comp_value,
                    "effectiveDateTime": obs.get("effectiveDateTime"),
                    "category": obs.get("category"),
                }
                existing = obs_by_loinc.get(comp_loinc)
                existing_date = _parse_date(existing.get("effectiveDateTime")) if existing else None
                if not existing or (existing_date and obs_date > existing_date):
                    obs_by_loinc[comp_loinc] = synth_obs

    recent_labs: list[LabResult] = []
    for loinc, obs in obs_by_loinc.items():
        code_entry = obs.get("code", {}).get("coding", [{}])[0]
        display = code_entry.get("display", "")
        value_qty = obs.get("valueQuantity", {})

        value = value_qty.get("value")
        if value is None:
            continue

        unit = value_qty.get("unit", value_qty.get("code", ""))
        obs_date = _parse_date(obs.get("effectiveDateTime"))

        # Determine category
        category = "laboratory"
        cat_list = obs.get("category", [])
        for cat in cat_list:
            for coding in cat.get("coding", []):
                if coding.get("code") == "vital-signs":
                    category = "vital-signs"
                    break

        recent_labs.append(LabResult(
            loinc_code=loinc,
            display=display,
            short_name=lookup_lab_short_name(loinc, display),
            value=float(value),
            unit=unit,
            observed_date=obs_date or date.today(),
            category=category,
        ))

    # Sort labs: vitals first, then labs, by display name
    recent_labs.sort(key=lambda x: (0 if x.category == "vital-signs" else 1, x.display))

    # ── Parse Allergies ──────────────────────────────────────────────

    allergies: list[Allergy] = []
    for allergy in allergies_raw:
        code_entry = allergy.get("code", {}).get("coding", [{}])[0]

        al_category = None
        cat_list = allergy.get("category", [])
        if cat_list:
            al_category = cat_list[0] if isinstance(cat_list[0], str) else None

        allergies.append(Allergy(
            code=code_entry.get("code", ""),
            display=code_entry.get("display", "Unknown allergen"),
            category=al_category,
            criticality=allergy.get("criticality"),
        ))

    # ── Build Profile ────────────────────────────────────────────────

    return PatientProfile(
        id=patient_id,
        name=name,
        age=age,
        sex=sex,
        birth_date=birth_date,
        conditions=conditions,
        medications=medications,
        allergies=allergies,
        recent_labs=recent_labs,
    )


def parse_directory(dir_path: Path) -> list[PatientProfile]:
    """Parse all Synthea FHIR Bundle JSONs in a directory.

    Skips hospitalInformation and practitionerInformation files.
    Logs warnings for files that fail to parse.

    Args:
        dir_path: Directory containing Synthea FHIR JSON files.

    Returns:
        List of successfully parsed PatientProfile objects.
    """
    profiles: list[PatientProfile] = []
    skip_prefixes = ("hospitalInformation", "practitionerInformation")

    json_files = sorted(dir_path.glob("*.json"))
    logger.info("Found %d JSON files in %s", len(json_files), dir_path)

    for path in json_files:
        if path.name.startswith(skip_prefixes):
            continue
        try:
            profile = parse_bundle(path)
            profiles.append(profile)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", path.name, e)

    logger.info("Successfully parsed %d patient bundles", len(profiles))
    return profiles
