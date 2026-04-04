"""Tests for the patient data layer (Phase 1).

Covers FHIR parsing, condition maps, patient context building,
gallery loading, and schema validation.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from src.data.schemas import (
    Allergy,
    Condition,
    LabResult,
    Medication,
    PatientProfile,
)
from src.data.condition_maps import (
    CONDITION_MAP,
    LAB_SHORT_NAMES,
    lookup_condition,
    lookup_lab_short_name,
)
from src.data.patient_context import build_patient_summary
from src.data.gallery import list_patients, load_patient


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def sample_profile() -> PatientProfile:
    """Minimal PatientProfile for unit testing."""
    return PatientProfile(
        id="test-123",
        name="Jane Doe",
        age=72,
        sex="F",
        birth_date=date(1954, 3, 15),
        conditions=[
            Condition(
                snomed_code="44054006",
                snomed_display="Diabetes mellitus type 2",
                icd10_code="E11.9",
                abbreviation="T2DM",
                patient_friendly_name="Type 2 Diabetes",
                clinical_status="active",
                onset_date=date(2010, 6, 1),
            ),
            Condition(
                snomed_code="59621000",
                snomed_display="Essential hypertension",
                abbreviation="HTN",
                patient_friendly_name="High Blood Pressure",
                clinical_status="active",
                icd10_code="I10",
            ),
        ],
        medications=[
            Medication(
                rxnorm_code="860975",
                display="Metformin hydrochloride 500 MG Oral Tablet",
                short_name="Metformin 500mg",
                status="active",
                frequency="BID",
                reason_display="Diabetes mellitus type 2",
            ),
            Medication(
                rxnorm_code="314076",
                display="Lisinopril 20 MG Oral Tablet",
                short_name="Lisinopril 20mg",
                status="active",
                frequency="daily",
            ),
        ],
        allergies=[
            Allergy(code="7980", display="Penicillin", category="medication", criticality="high"),
        ],
        recent_labs=[
            LabResult(
                loinc_code="4548-4",
                display="Hemoglobin A1c",
                short_name="HbA1c",
                value=7.2,
                unit="%",
                observed_date=date(2025, 12, 1),
                category="laboratory",
            ),
        ],
    )


# ── Schema Tests ─────────────────────────────────────────────────────────


class TestPatientProfile:
    def test_creates_with_required_fields(self, sample_profile: PatientProfile):
        assert sample_profile.id == "test-123"
        assert sample_profile.name == "Jane Doe"
        assert sample_profile.age == 72
        assert sample_profile.sex == "F"

    def test_conditions_summary_clinician(self, sample_profile: PatientProfile):
        assert sample_profile.conditions_summary_clinician == "T2DM, HTN"

    def test_conditions_summary_patient(self, sample_profile: PatientProfile):
        assert sample_profile.conditions_summary_patient == "Type 2 Diabetes, High Blood Pressure"

    def test_medications_summary_clinician(self, sample_profile: PatientProfile):
        summary = sample_profile.medications_summary_clinician
        assert "Metformin 500mg BID" in summary
        assert "Lisinopril 20mg daily" in summary

    def test_medications_summary_patient(self, sample_profile: PatientProfile):
        assert sample_profile.medications_summary_patient == "2 medications"

    def test_empty_conditions_summary(self):
        profile = PatientProfile(
            id="empty", name="Empty", age=30, sex="M", birth_date=date(1996, 1, 1),
        )
        assert profile.conditions_summary_clinician == "No active conditions"
        assert profile.conditions_summary_patient == "No active conditions"

    def test_empty_medications_summary(self):
        profile = PatientProfile(
            id="empty", name="Empty", age=30, sex="M", birth_date=date(1996, 1, 1),
        )
        assert profile.medications_summary_clinician == "No active medications"
        assert profile.medications_summary_patient == "No medications"

    def test_to_dict_includes_computed_fields(self, sample_profile: PatientProfile):
        d = sample_profile.to_dict()
        assert "conditions_summary_clinician" in d
        assert "conditions_summary_patient" in d
        assert d["conditions_summary_clinician"] == "T2DM, HTN"

    def test_single_medication_summary(self):
        profile = PatientProfile(
            id="one", name="One Med", age=50, sex="F", birth_date=date(1976, 1, 1),
            medications=[
                Medication(rxnorm_code="1", display="Test", short_name="Test", status="active"),
            ],
        )
        assert profile.medications_summary_patient == "1 medication"


# ── Condition Map Tests ──────────────────────────────────────────────────


class TestConditionMaps:
    def test_known_snomed_code_maps_correctly(self):
        result = lookup_condition("44054006", "Diabetes mellitus type 2")
        assert result["abbreviation"] == "T2DM"
        assert result["patient_name"] == "Type 2 Diabetes"
        assert result["icd10"] == "E11.9"

    def test_unknown_snomed_falls_back_to_display(self):
        result = lookup_condition("99999999", "Some Rare Condition")
        assert result["abbreviation"] == "Some Rare Condition"
        assert result["patient_name"] == "Some Rare Condition"
        assert result["icd10"] is None

    def test_lab_short_name_known_loinc(self):
        assert lookup_lab_short_name("4548-4", "Hemoglobin A1c") == "HbA1c"
        assert lookup_lab_short_name("2160-0", "Creatinine") == "Creatinine"

    def test_lab_short_name_unknown_falls_back(self):
        assert lookup_lab_short_name("99999-9", "Unknown Lab") == "Unknown Lab"

    def test_condition_map_has_common_conditions(self):
        # Verify key conditions are present
        assert "44054006" in CONDITION_MAP  # T2DM
        assert "59621000" in CONDITION_MAP  # HTN
        assert "431855005" in CONDITION_MAP  # CKD
        assert "13645005" in CONDITION_MAP  # COPD

    def test_lab_short_names_has_common_labs(self):
        assert "4548-4" in LAB_SHORT_NAMES  # HbA1c
        assert "2160-0" in LAB_SHORT_NAMES  # Creatinine
        assert "8480-6" in LAB_SHORT_NAMES  # Systolic BP


# ── Patient Context Tests ────────────────────────────────────────────────


class TestBuildPatientSummary:
    def test_includes_demographics(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert "Jane Doe" in summary
        assert "72F" in summary

    def test_includes_conditions(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert "T2DM" in summary
        assert "Type 2 Diabetes" in summary
        assert "HTN" in summary

    def test_includes_medications(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert "Metformin 500mg" in summary
        assert "Lisinopril 20mg" in summary

    def test_includes_allergies(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert "Penicillin" in summary

    def test_includes_labs(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert "HbA1c" in summary
        assert "7.2" in summary

    def test_empty_profile_graceful(self):
        profile = PatientProfile(
            id="empty", name="Empty", age=30, sex="M", birth_date=date(1996, 1, 1),
        )
        summary = build_patient_summary(profile)
        assert "Empty" in summary
        assert "30M" in summary
        assert "None recorded" in summary

    def test_has_boundary_markers(self, sample_profile: PatientProfile):
        summary = build_patient_summary(sample_profile)
        assert summary.startswith("--- PATIENT CONTEXT ---")
        assert summary.endswith("--- END PATIENT CONTEXT ---")


# ── Gallery Tests ────────────────────────────────────────────────────────


class TestGallery:
    def test_list_patients_returns_5(self):
        patients = list_patients()
        assert len(patients) == 5

    def test_list_patients_has_required_fields(self):
        patients = list_patients()
        for p in patients:
            assert "patient_id" in p
            assert "name" in p
            assert "age" in p
            assert "sex" in p
            assert "headline" in p

    def test_load_patient_returns_profile(self):
        patients = list_patients()
        patient_id = patients[0]["patient_id"]
        profile = load_patient(patient_id)
        assert profile is not None
        assert isinstance(profile, PatientProfile)
        assert profile.id == patient_id

    def test_load_patient_has_conditions_and_meds(self):
        patients = list_patients()
        patient_id = patients[0]["patient_id"]
        profile = load_patient(patient_id)
        assert len(profile.conditions) > 0
        assert len(profile.medications) > 0

    def test_load_nonexistent_patient_returns_none(self):
        result = load_patient("nonexistent-uuid")
        assert result is None
