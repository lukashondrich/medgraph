# Data Layer Architecture

## Overview

Patient data loading, parsing, context building, and drug interaction screening tools. Two sub-systems:

1. **FHIR patient data** — Parse Synthea bundles into typed Pydantic models, build prompt-ready context strings, manage the demo patient gallery.
2. **OpenFDA integration** — Screen patient medications for drug-drug interactions via FDA label and FAERS APIs.

This module is a pure data layer — it has no dependency on agents, orchestrator, or knowledge_pipeline.

**Related docs:** [Agents](../agents/ARCHITECTURE.md) (DrugCheck agent consumes OpenFDA) · [Models](../models/ARCHITECTURE.md) (patient fields in state)

## Directory Structure

```
src/data/
  __init__.py
  schemas.py             # Pydantic models: PatientProfile, Condition, Medication, LabResult, Allergy, BiometricSummary
  fhir_parser.py         # Synthea FHIR R4 Bundle → PatientProfile
  condition_maps.py      # SNOMED-CT + LOINC → abbreviations / friendly names / ICD-10
  patient_context.py     # build_patient_summary() → formatted string for prompt injection
  gallery.py             # list_patients(), load_patient() from pre-parsed JSON
  gallery.json           # Index of 5 curated patient cards
  patients/              # Pre-parsed patient profile JSONs (5 files)
  openfda/               # Drug interaction screening sub-package (6 files)
    __init__.py
    client.py            # HTTP client with rate limiting + caching
    drug_resolver.py     # Synthea names → FDA generic names
    drug_labels.py       # FDA label fetching + safety section extraction
    adverse_events.py    # FAERS adverse event queries
    tools.py             # Agent-facing API: screen_all_pairs()
    schemas.py           # Pydantic output models
```

## Patient Schemas (`schemas.py`)

Six Pydantic models define the canonical patient representation:

| Model | Key Fields | Notes |
|-------|-----------|-------|
| `Condition` | snomed_code, abbreviation, patient_friendly_name, clinical_status, onset_date | SNOMED-CT coded |
| `Medication` | rxnorm_code, short_name, dosage_text, frequency, reason_display | RxNorm coded |
| `LabResult` | loinc_code, short_name, value, unit, observed_date, category | LOINC coded |
| `Allergy` | code, display, category, criticality | |
| `BiometricSummary` | resting_hr_bpm, mean_daily_steps, sleep_hours, hrv_ms | Synthetic Apple Health data |
| `PatientProfile` | id, name, age, sex, conditions, medications, allergies, recent_labs | Top-level model |

`PatientProfile` has four computed fields:
- `conditions_summary_clinician` — e.g. "T2DM, HTN, CKD"
- `conditions_summary_patient` — e.g. "Diabetes, High Blood Pressure, Kidney Disease"
- `medications_summary_clinician` — e.g. "Metformin 1g BID · Lisinopril 20mg"
- `medications_summary_patient` — e.g. "4 medications"

## FHIR Parsing (`fhir_parser.py`)

Converts Synthea FHIR R4 Bundle JSON into a `PatientProfile`.

- **Raw dict access** — no `fhir.resources` dependency. Synthea's output is predictable enough that raw parsing is reliable.
- **Extracts:** Patient demographics, active conditions, active medications, observations (labs + vitals), allergies.
- **Handles:** Component-based observations (blood pressure → systolic + diastolic), medication dosage/frequency parsing, LOINC grouping (keeps most recent value per code).
- **Medication name shortening:** `_shorten_medication_name()` transforms Synthea's verbose names (e.g. "Hydrochlorothiazide 25 MG Oral Tablet") into concise forms ("Hydrochlorothiazide 25mg"). Removes salt suffixes (hydrochloride, sodium, etc.), detects extended release, falls back to first 3 words.
- **`parse_directory()`** — batch-parses all bundles in a directory, skipping hospital/practitioner files.

## Condition Maps (`condition_maps.py`)

Static lookup tables:
- ~70 SNOMED-CT → (clinical abbreviation, patient-friendly name, ICD-10) mappings
- ~40 LOINC → lab short name mappings
- **Fallback:** Unknown codes use Synthea's display text as-is

## Patient Context (`patient_context.py`)

`build_patient_summary(profile) -> str` — formats a `PatientProfile` into a prompt-ready text block. This is the string that gets injected into every agent's system prompt via the base class.

Sections: demographics, active conditions (with onset dates), medications (with frequency and reason), allergies (with criticality), recent labs (up to 10).

Bounded by `--- PATIENT CONTEXT ---` / `--- END PATIENT CONTEXT ---` markers.

## Gallery (`gallery.py` + `gallery.json`)

- `list_patients()` → 5 curated patient cards from `gallery.json`
- `load_patient(patient_id)` → full `PatientProfile` from pre-parsed JSON in `patients/`
- Patients selected for diversity: ages 66-85, both sexes, varied condition profiles, different interaction risk levels

### Demo Patients

| Patient | Age/Sex | Key Conditions | Meds | Clinical Interest |
|---------|---------|---------------|------|-------------------|
| Nelia Rolfson | 73F | T2DM, HTN, CKD, Anemia | 6 | NSAID + ARB renal risk |
| Jeff Heathcote | 66M | CAD, T2DM, HTN | 7 | Antiplatelet + statin CYP interaction |
| Sanda Wolff | 68F | COPD, T2DM, HTN, CKD | 5 | Respiratory + metabolic comorbidity |
| Derek Brakus | 74M | CHF, T2DM, Obesity | 5 | Heart failure + diuretic therapy |
| David Guillen | 85M | AFib, CAD, Epilepsy, T2DM | 11 | Extreme polypharmacy, Warfarin + Clopidogrel |

## OpenFDA Sub-Package (`openfda/`)

Six files providing drug-drug interaction screening:

### `client.py` — HTTP Client
- Token bucket rate limiting (4 req/sec, 10 burst)
- Exponential backoff retries on 429/5xx
- LRU TTL cache (labels: 1h, FAERS: 4h, not-found: 10min)

### `drug_resolver.py` — Name Resolution
- Bridges Synthea medication names → FDA generic names
- Static map of ~50 drugs, text extraction fallback, combo product splitting

### `drug_labels.py` — Label Fetching
- 3-tier fallback strategy: warnings_and_cautions → adverse_reactions → generic_name
- Extracts 7 safety sections from FDA labels, cleans HTML

### `adverse_events.py` — FAERS Queries
- Single-drug and drug-pair co-reported adverse event lookups

### `tools.py` — Agent-Facing API
- `screen_all_pairs()` — resolves all patient medications, generates unique pairs, screens each
- Cross-mention detection uses ~40 drug class aliases (NSAIDs, ACE-I, ARBs, statins, etc.)
- Severity classification: "high" if label cross-mentions, "moderate" otherwise

### `schemas.py` — Output Models
- `DrugIdentity`, `DrugLabelResult`, `InteractionScreenResult`, `AdverseEventResult`

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Raw FHIR parsing | Dict access, no fhir.resources | Synthea output is predictable; avoids heavyweight dependency |
| SNOMED/LOINC maps | Static dicts with display fallback | Immediate, no external service; covers common conditions |
| Patient context as text | Formatted string, not structured data | Injected directly into LLM prompts; structured data not needed |
| OpenFDA rate limiting | Token bucket in client | Respects FDA API limits without external dependencies |
| Drug class aliases | Static alias map (~40 classes) | Cross-mention detection needs class-level matching, not just exact names |

## Testing

- `tests/test_patient_data.py` — 27 tests: schemas, condition maps, patient context building, gallery loading
- `tests/test_patient_aware_agents.py` — 11 tests: evidence + drug_check agent integration with patient data
