"""Drug name resolver — bridges Synthea medication display text to OpenFDA generic names.

Resolution strategy (priority order):
1. Static map (~50 drugs): zero-API-call resolution for known gallery drugs
2. Text extraction: strip prefixes/suffixes, extract drug name
3. Combo product splitting: " / " separator → resolve each component

Usage:
    from data.openfda.drug_resolver import resolve_medication, extract_generic_name

    names = resolve_medication(medication)  # ["METFORMIN"]
    name = extract_generic_name("24 HR Metformin hydrochloride 500 MG")  # "METFORMIN"
"""

import re
from typing import Optional

from ..schemas import Medication


# ── Static Map ───────────────────────────────────────────────────────────
# Maps lowercase keywords from Synthea display text → uppercase FDA generic names.
# Covers all drugs in gallery.py's _INTERACTION_DRUGS + the 29 unique medications
# from the 12 gallery patients.

_STATIC_MAP: dict[str, str] = {
    # ── Gallery patient medications ────────────────────────────────────
    "amlodipine": "AMLODIPINE",
    "hydrochlorothiazide": "HYDROCHLOROTHIAZIDE",
    "olmesartan": "OLMESARTAN",
    "metformin": "METFORMIN",
    "naproxen": "NAPROXEN",
    "insulin": "INSULIN",
    "warfarin": "WARFARIN",
    "verapamil": "VERAPAMIL",
    "digoxin": "DIGOXIN",
    "galantamine": "GALANTAMINE",
    "simvastatin": "SIMVASTATIN",
    "simvistatin": "SIMVASTATIN",  # Synthea typo
    "hydrocortisone": "HYDROCORTISONE",
    "chlorpheniramine": "CHLORPHENIRAMINE",
    "ferrous sulfate": "FERROUS SULFATE",
    "clopidogrel": "CLOPIDOGREL",
    "nitroglycerin": "NITROGLYCERIN",
    "fluticasone": "FLUTICASONE",
    "salmeterol": "SALMETEROL",
    "atenolol": "ATENOLOL",
    "chlorthalidone": "CHLORTHALIDONE",
    "donepezil": "DONEPEZIL",
    "metoprolol": "METOPROLOL",
    "furosemide": "FUROSEMIDE",
    "tacrine": "TACRINE",
    "carbamazepine": "CARBAMAZEPINE",
    "leucovorin": "LEUCOVORIN",
    "oxaliplatin": "OXALIPLATIN",

    # ── Brand name → generic ──────────────────────────────────────────
    "lasix": "FUROSEMIDE",
    "toprol": "METOPROLOL",
    "humulin": "INSULIN",
    "aricept": "DONEPEZIL",
    "tegretol": "CARBAMAZEPINE",

    # ── Additional interaction drugs from gallery.py ──────────────────
    "ibuprofen": "IBUPROFEN",
    "diclofenac": "DICLOFENAC",
    "meloxicam": "MELOXICAM",
    "celecoxib": "CELECOXIB",
    "aspirin": "ASPIRIN",
    "lisinopril": "LISINOPRIL",
    "enalapril": "ENALAPRIL",
    "ramipril": "RAMIPRIL",
    "captopril": "CAPTOPRIL",
    "benazepril": "BENAZEPRIL",
    "fosinopril": "FOSINOPRIL",
    "losartan": "LOSARTAN",
    "valsartan": "VALSARTAN",
    "candesartan": "CANDESARTAN",
    "irbesartan": "IRBESARTAN",
    "telmisartan": "TELMISARTAN",
    "apixaban": "APIXABAN",
    "rivaroxaban": "RIVAROXABAN",
    "dabigatran": "DABIGATRAN",
    "enoxaparin": "ENOXAPARIN",
    "heparin": "HEPARIN",
    "prasugrel": "PRASUGREL",
    "ticagrelor": "TICAGRELOR",
    "sertraline": "SERTRALINE",
    "fluoxetine": "FLUOXETINE",
    "paroxetine": "PAROXETINE",
    "citalopram": "CITALOPRAM",
    "escitalopram": "ESCITALOPRAM",
    "atorvastatin": "ATORVASTATIN",
    "rosuvastatin": "ROSUVASTATIN",
    "pravastatin": "PRAVASTATIN",
    "lovastatin": "LOVASTATIN",
    "propranolol": "PROPRANOLOL",
    "carvedilol": "CARVEDILOL",
    "bisoprolol": "BISOPROLOL",
    "spironolactone": "SPIRONOLACTONE",
}

# Salt suffixes to strip during text extraction
_SALT_SUFFIXES = [
    "hydrochloride", "sodium", "potassium", "calcium", "mesylate",
    "besylate", "maleate", "tartrate", "succinate", "fumarate",
    "acetate", "propionate", "medoxomil", "sulfate",
]

# ── Public API ───────────────────────────────────────────────────────────


def resolve_medication(medication: Medication) -> list[str]:
    """Resolve a patient Medication to one or more OpenFDA generic names.

    Handles combo products (returns multiple names) and single drugs.

    Args:
        medication: A Medication model from the patient profile.

    Returns:
        List of uppercase FDA generic names. May be empty if unresolvable.
    """
    display = medication.display

    # Check for combo product (" / " separator in Synthea)
    if " / " in display:
        return _resolve_combo(display)

    name = extract_generic_name(display)
    return [name] if name else []


def extract_generic_name(display: str) -> Optional[str]:
    """Extract a single generic drug name from a display string.

    Resolution order:
    1. Static map lookup (keyword match)
    2. Text extraction (strip prefixes, suffixes, dosages)

    Args:
        display: Synthea medication display text.

    Returns:
        Uppercase FDA generic name, or None if unresolvable.
    """
    # Step 1: Try static map (longest match first for multi-word entries)
    display_lower = display.lower()

    # Check brand names in brackets first: "Carbamazepine[Tegretol]"
    bracket_match = re.search(r"\[([^\]]+)\]", display)
    if bracket_match:
        brand = bracket_match.group(1).lower()
        if brand in _STATIC_MAP:
            return _STATIC_MAP[brand]

    # Check static map — try longest keys first to prefer "ferrous sulfate" over "sulfate"
    for keyword in sorted(_STATIC_MAP, key=len, reverse=True):
        if keyword in display_lower:
            return _STATIC_MAP[keyword]

    # Step 2: Text extraction
    return _extract_from_text(display)


def _resolve_combo(display: str) -> list[str]:
    """Resolve a combination product into component generic names.

    Synthea uses " / " as separator:
    "Amlodipine 5 MG / HCTZ 12.5 MG / Olmesartan medoxomil 20 MG"
    → ["AMLODIPINE", "HYDROCHLOROTHIAZIDE", "OLMESARTAN"]
    """
    components = display.split(" / ")
    names: list[str] = []
    seen: set[str] = set()

    for component in components:
        name = extract_generic_name(component.strip())
        if name and name not in seen:
            names.append(name)
            seen.add(name)

    return names


def _extract_from_text(display: str) -> Optional[str]:
    """Extract drug name from display text by stripping noise.

    Handles:
    - "XX HR " prefix (extended release)
    - "XXX ACTUAT " prefix (inhalers)
    - "XX ML " prefix (injections)
    - Salt suffixes (hydrochloride, sodium, etc.)
    - Dosage numbers and form text
    """
    cleaned = display

    # Remove leading volume/count prefixes
    cleaned = re.sub(r"^\d+\s+HR\s+", "", cleaned)
    cleaned = re.sub(r"^\d+\s+ACTUAT\s+", "", cleaned)
    cleaned = re.sub(r"^\d+\s+ML\s+", "", cleaned)

    # Remove bracketed brand names
    cleaned = re.sub(r"\[.*?\]", "", cleaned)

    # Try to extract the name before the first number
    match = re.match(
        r"^([A-Za-z][A-Za-z\s,'-]+?)\s+\d",
        cleaned,
    )
    if match:
        name = match.group(1).strip()

        # Strip salt suffixes
        for suffix in _SALT_SUFFIXES:
            name = re.sub(rf"\s+{suffix}$", "", name, flags=re.IGNORECASE)

        # Strip trailing commas and whitespace
        name = name.strip().rstrip(",").strip()

        if name:
            return name.upper()

    # Fallback: first word if alphanumeric
    first_word = cleaned.split()[0] if cleaned.split() else None
    if first_word and first_word[0].isalpha():
        return first_word.upper()

    return None
