"""Patient gallery — load pre-parsed patient profiles for the demo.

Provides a simple API for the web app and CLI to list and load patients.
Patients are pre-parsed FHIR bundles stored as JSON in src/data/patients/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .schemas import PatientProfile

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent
_GALLERY_PATH = _DATA_DIR / "gallery.json"
_PATIENTS_DIR = _DATA_DIR / "patients"


def list_patients() -> list[dict]:
    """Return the gallery index (list of patient summary cards).

    Each dict contains: patient_id, name, age, sex, headline,
    condition_tags, medication_count, interest_hook.
    """
    if not _GALLERY_PATH.exists():
        logger.warning("Gallery file not found at %s", _GALLERY_PATH)
        return []
    with open(_GALLERY_PATH) as f:
        return json.load(f)


def load_patient(patient_id: str) -> Optional[PatientProfile]:
    """Load a full PatientProfile by ID from the pre-parsed JSON files.

    Args:
        patient_id: Patient UUID (matches filename without .json extension).

    Returns:
        PatientProfile or None if not found.
    """
    path = _PATIENTS_DIR / f"{patient_id}.json"
    if not path.exists():
        logger.warning("Patient file not found: %s", path)
        return None

    with open(path) as f:
        data = json.load(f)

    return PatientProfile.model_validate(data)
