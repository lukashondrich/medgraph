# Data Architecture

## Profiles and readings

| File | Purpose |
|---|---|
| `profile.py` | `UserProfile`, `TestReading`, `build_profile_summary()` |
| `personas.py` | `list_personas()`, `load_persona()`, `list_readings()` |
| `personas/*.json` | Three demo personas; `_readings.json` holds preset readings |

`UserProfile` fields: age, ancestry (a key from the ancestry hierarchy), country of residence, menopausal status, pregnancy, cycle, hormonal contraception, hormone therapy, recent antibiotics, symptoms, history.

`build_profile_summary()` formats profile and reading as the context block that the base agent appends to every system prompt.

Persona ids are validated before use as file names.

## OpenFDA (`openfda/`, `schemas.py`)

The drug label client from the earlier project. It is not used by pH Companion and is kept for a possible "medication labels" source (design decision D4).
