"""Persona gallery and preset readings for the pH Companion demo."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .profile import TestReading, UserProfile, ancestry_label

logger = logging.getLogger(__name__)

_PERSONAS_DIR = Path(__file__).parent / "personas"
_READINGS_PATH = _PERSONAS_DIR / "_readings.json"
_QUESTIONS_PATH = _PERSONAS_DIR / "_questions.json"
_ORDER = ["priya", "anna", "amara"]


def suggested_questions(persona_id: str) -> list[dict]:
    """Questions offered as shortcuts for a persona: [{"en": ..., "de": ...}]."""
    if not _QUESTIONS_PATH.exists():
        return []
    return json.loads(_QUESTIONS_PATH.read_text()).get(persona_id, [])


def load_persona(persona_id: str) -> Optional[UserProfile]:
    """Load one persona by id, or None when it does not exist."""
    if not persona_id or "/" in persona_id or persona_id.startswith((".", "_")):
        return None
    path = _PERSONAS_DIR / f"{persona_id}.json"
    if not path.exists():
        logger.warning("Persona file not found: %s", path)
        return None
    return UserProfile.model_validate(json.loads(path.read_text()))


def list_personas() -> list[dict]:
    """Return gallery cards for all personas, sorted by file name."""
    cards = []
    paths = [p for p in _PERSONAS_DIR.glob("*.json") if not p.name.startswith("_")]
    # Demo order first, anything else alphabetically after it.
    paths.sort(key=lambda p: (_ORDER.index(p.stem) if p.stem in _ORDER else len(_ORDER), p.stem))
    for path in paths:
        profile = UserProfile.model_validate(json.loads(path.read_text()))
        cards.append({
            "persona_id": profile.id,
            "name": profile.name,
            "age": profile.age,
            "ancestry": ancestry_label(profile.ancestry),
            "menopausal_status": profile.menopausal_status.value,
            "pregnancy": profile.pregnancy.value,
            "headline": profile.headline,
            "questions": suggested_questions(profile.id),
        })
    return cards


def list_readings() -> list[dict]:
    """Return the preset strip readings selectable in the demo."""
    if not _READINGS_PATH.exists():
        return []
    raw = json.loads(_READINGS_PATH.read_text())
    return [TestReading.model_validate(r).to_dict() | {"id": r["id"], "label": r.get("label", "")} for r in raw]
