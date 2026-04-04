"""Patient data models for the Digital Twin Copilot.

These Pydantic v2 models define the canonical patient representation used
across all agents. FHIR R4 resources are parsed into these models once; agents
then work with clean, typed data rather than raw FHIR JSON.

Follows conventions from knowledge_pipeline/schemas.py: Field descriptions,
str Enums, docstrings.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field


# ── Component Models ─────────────────────────────────────────────────────


class Condition(BaseModel):
    """A single diagnosis from the patient's problem list."""

    snomed_code: str = Field(
        description="SNOMED-CT code from Synthea, e.g. '44054006'"
    )
    snomed_display: str = Field(
        description="Synthea's display text, e.g. 'Diabetes mellitus type 2'"
    )
    icd10_code: Optional[str] = Field(
        default=None,
        description="Mapped ICD-10 code, e.g. 'E11.9'"
    )
    abbreviation: str = Field(
        description="Clinician shorthand, e.g. 'T2DM'"
    )
    patient_friendly_name: str = Field(
        description="Plain-language name, e.g. 'Diabetes'"
    )
    clinical_status: str = Field(
        description="'active' or 'resolved'"
    )
    onset_date: Optional[date] = Field(
        default=None,
        description="Date of first diagnosis"
    )
    category: Optional[str] = Field(
        default=None,
        description="FHIR condition category, e.g. 'encounter-diagnosis'"
    )


class Medication(BaseModel):
    """A single prescription from the patient's medication list."""

    rxnorm_code: str = Field(
        description="RxNorm code from Synthea"
    )
    display: str = Field(
        description="Full display text, e.g. 'Hydrochlorothiazide 25 MG Oral Tablet'"
    )
    short_name: str = Field(
        description="Derived short form, e.g. 'Hydrochlorothiazide 25mg'"
    )
    dosage_text: Optional[str] = Field(
        default=None,
        description="Dosage instruction text"
    )
    frequency: Optional[str] = Field(
        default=None,
        description="Dosing frequency, e.g. 'BID', 'daily', 'PRN'"
    )
    status: str = Field(
        description="'active', 'stopped', or 'completed'"
    )
    start_date: Optional[date] = Field(
        default=None,
        description="When the prescription started"
    )
    end_date: Optional[date] = Field(
        default=None,
        description="When the prescription ended (if stopped/completed)"
    )
    reason_code: Optional[str] = Field(
        default=None,
        description="SNOMED code of the condition this medication treats"
    )
    reason_display: Optional[str] = Field(
        default=None,
        description="Display text of the condition this medication treats"
    )


class LabResult(BaseModel):
    """A single lab or vital sign observation."""

    loinc_code: str = Field(
        description="LOINC code, e.g. '4548-4' for HbA1c"
    )
    display: str = Field(
        description="Full display, e.g. 'Hemoglobin A1c/Hemoglobin.total in Blood'"
    )
    short_name: str = Field(
        description="Short label, e.g. 'HbA1c'"
    )
    value: float = Field(
        description="Numeric result value"
    )
    unit: str = Field(
        description="Unit of measurement, e.g. '%', 'mg/dL'"
    )
    observed_date: date = Field(
        description="Date the observation was recorded"
    )
    category: str = Field(
        description="'vital-signs' or 'laboratory'"
    )


class Allergy(BaseModel):
    """A single allergy or intolerance."""

    code: str = Field(
        description="SNOMED-CT or other code"
    )
    display: str = Field(
        description="Display text, e.g. 'Penicillin'"
    )
    category: Optional[str] = Field(
        default=None,
        description="'medication', 'food', or 'environment'"
    )
    criticality: Optional[str] = Field(
        default=None,
        description="'high' or 'low'"
    )


class BiometricSummary(BaseModel):
    """Synthetic Apple Health snapshot — summary stats, not time-series."""

    last_sync: datetime = Field(
        description="When Apple Health data was last synced"
    )
    resting_hr_bpm: int = Field(
        description="Resting heart rate in beats per minute"
    )
    mean_daily_steps: int = Field(
        description="Average daily step count"
    )
    step_trend_pct: float = Field(
        description="Step trend as percentage change, e.g. -22.0 for 'down 22%'"
    )
    sleep_hours: float = Field(
        description="Average hours of sleep per night"
    )
    sleep_efficiency_pct: float = Field(
        description="Sleep efficiency percentage (time asleep / time in bed)"
    )
    wake_events_per_night: float = Field(
        description="Average number of wake events per night"
    )
    hrv_ms: Optional[int] = Field(
        default=None,
        description="Heart rate variability (RMSSD) in milliseconds"
    )


# ── Top-Level Patient Model ─────────────────────────────────────────────


class PatientProfile(BaseModel):
    """Complete patient profile — the canonical model all agents work with.

    Built from FHIR R4 Bundle parsing. Contains structured data plus
    pre-computed summary strings for clinician and patient display modes.
    """

    id: str = Field(
        description="Patient UUID from Synthea"
    )
    name: str = Field(
        description="Formatted 'First Last'"
    )
    age: int = Field(
        description="Current age computed from birthDate"
    )
    sex: str = Field(
        description="'M' or 'F'"
    )
    birth_date: date = Field(
        description="Date of birth"
    )

    # Clinical data — active items only for primary display
    conditions: list[Condition] = Field(
        default_factory=list,
        description="Active conditions only"
    )
    medications: list[Medication] = Field(
        default_factory=list,
        description="Active medications only"
    )
    allergies: list[Allergy] = Field(
        default_factory=list,
        description="Known allergies and intolerances"
    )
    recent_labs: list[LabResult] = Field(
        default_factory=list,
        description="Most recent value per LOINC code"
    )

    # Apple Health data (synthetic for demo)
    biometrics: Optional[BiometricSummary] = Field(
        default=None,
        description="Synthetic Apple Health data"
    )

    # ── Computed summaries ───────────────────────────────────────────

    @computed_field
    @property
    def conditions_summary_clinician(self) -> str:
        """Clinician-mode summary, e.g. 'T2DM, HTN, OA (bilateral knees)'."""
        if not self.conditions:
            return "No active conditions"
        return ", ".join(c.abbreviation for c in self.conditions)

    @computed_field
    @property
    def conditions_summary_patient(self) -> str:
        """Patient-mode summary, e.g. 'Diabetes, High Blood Pressure'."""
        if not self.conditions:
            return "No active conditions"
        return ", ".join(c.patient_friendly_name for c in self.conditions)

    @computed_field
    @property
    def medications_summary_clinician(self) -> str:
        """Clinician-mode medication list, e.g. 'Metformin 1g BID · Lisinopril 20mg'."""
        if not self.medications:
            return "No active medications"
        parts = []
        for m in self.medications:
            label = m.short_name
            if m.frequency:
                label += f" {m.frequency}"
            parts.append(label)
        return " · ".join(parts)

    @computed_field
    @property
    def medications_summary_patient(self) -> str:
        """Patient-mode medication count, e.g. '4 medications'."""
        n = len(self.medications)
        if n == 0:
            return "No medications"
        if n == 1:
            return "1 medication"
        return f"{n} medications"

    def to_dict(self) -> dict:
        """Serialize to dict for JSON export. Includes computed fields."""
        return self.model_dump(mode="json")
