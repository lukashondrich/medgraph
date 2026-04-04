"""SNOMED-CT → clinician abbreviation / patient-friendly name / ICD-10 mappings.

Covers the ~35 most common conditions Synthea generates. If a SNOMED code
isn't in this map, the parser uses Synthea's display text as fallback for
both abbreviation and patient-friendly name.

Sources:
- SNOMED codes: Synthea FHIR R4 output
- ICD-10 codes: approximate mappings for demo purposes (not clinical-grade crosswalk)
- Abbreviations: standard clinical shorthand
"""

CONDITION_MAP: dict[str, dict[str, str]] = {
    # ── Metabolic / Endocrine ────────────────────────────────────────
    "44054006": {
        "abbreviation": "T2DM",
        "patient_name": "Type 2 Diabetes",
        "icd10": "E11.9",
    },
    "15777000": {
        "abbreviation": "T2DM (pre)",
        "patient_name": "Prediabetes",
        "icd10": "R73.03",
    },
    "46635009": {
        "abbreviation": "T1DM",
        "patient_name": "Type 1 Diabetes",
        "icd10": "E10.9",
    },
    "190905008": {
        "abbreviation": "Hyperlipidemia",
        "patient_name": "High Cholesterol",
        "icd10": "E78.5",
    },
    "267432004": {
        "abbreviation": "Overweight",
        "patient_name": "Overweight",
        "icd10": "E66.3",
    },
    "162864005": {
        "abbreviation": "Obesity",
        "patient_name": "Obesity",
        "icd10": "E66.9",
    },
    "40930008": {
        "abbreviation": "Hypothyroidism",
        "patient_name": "Underactive Thyroid",
        "icd10": "E03.9",
    },

    # ── Cardiovascular ───────────────────────────────────────────────
    "59621000": {
        "abbreviation": "HTN",
        "patient_name": "High Blood Pressure",
        "icd10": "I10",
    },
    "53741008": {
        "abbreviation": "CAD",
        "patient_name": "Coronary Artery Disease",
        "icd10": "I25.10",
    },
    "22298006": {
        "abbreviation": "MI",
        "patient_name": "Heart Attack",
        "icd10": "I21.9",
    },
    "88805009": {
        "abbreviation": "CHF",
        "patient_name": "Heart Failure",
        "icd10": "I50.9",
    },
    "49436004": {
        "abbreviation": "AFib",
        "patient_name": "Irregular Heartbeat",
        "icd10": "I48.91",
    },
    "230690007": {
        "abbreviation": "CVA",
        "patient_name": "Stroke",
        "icd10": "I63.9",
    },

    # ── Respiratory ──────────────────────────────────────────────────
    "195967001": {
        "abbreviation": "Asthma",
        "patient_name": "Asthma",
        "icd10": "J45.909",
    },
    "13645005": {
        "abbreviation": "COPD",
        "patient_name": "Chronic Lung Disease",
        "icd10": "J44.9",
    },
    "233604007": {
        "abbreviation": "Pneumonia",
        "patient_name": "Pneumonia",
        "icd10": "J18.9",
    },

    # ── Musculoskeletal ──────────────────────────────────────────────
    "239873007": {
        "abbreviation": "OA",
        "patient_name": "Arthritis",
        "icd10": "M19.90",
    },
    "69896004": {
        "abbreviation": "RA",
        "patient_name": "Rheumatoid Arthritis",
        "icd10": "M06.9",
    },
    "64859006": {
        "abbreviation": "Osteoporosis",
        "patient_name": "Weak Bones",
        "icd10": "M81.0",
    },
    "82423001": {
        "abbreviation": "LBP",
        "patient_name": "Chronic Back Pain",
        "icd10": "M54.5",
    },

    # ── Renal ────────────────────────────────────────────────────────
    "431855005": {
        "abbreviation": "CKD",
        "patient_name": "Chronic Kidney Disease",
        "icd10": "N18.9",
    },
    "127013003": {
        "abbreviation": "DKD",
        "patient_name": "Diabetic Kidney Disease",
        "icd10": "E11.22",
    },
    "431856006": {
        "abbreviation": "CKD stage 2",
        "patient_name": "Early Kidney Disease",
        "icd10": "N18.2",
    },
    "90781000119102": {
        "abbreviation": "Microalbuminuria (T2DM)",
        "patient_name": "Early Kidney Changes from Diabetes",
        "icd10": "E11.21",
    },

    # ── Neurological / Mental Health ─────────────────────────────────
    "36971009": {
        "abbreviation": "Depression",
        "patient_name": "Depression",
        "icd10": "F32.9",
    },
    "87512008": {
        "abbreviation": "MDD",
        "patient_name": "Depression",
        "icd10": "F33.0",
    },
    "197480006": {
        "abbreviation": "Anxiety",
        "patient_name": "Anxiety",
        "icd10": "F41.9",
    },
    "386806002": {
        "abbreviation": "PTSD",
        "patient_name": "PTSD",
        "icd10": "F43.10",
    },
    "26929004": {
        "abbreviation": "Alzheimer's",
        "patient_name": "Alzheimer's Disease",
        "icd10": "G30.9",
    },

    # ── GI ───────────────────────────────────────────────────────────
    "235595009": {
        "abbreviation": "GERD",
        "patient_name": "Acid Reflux",
        "icd10": "K21.0",
    },

    # ── Ophthalmologic ───────────────────────────────────────────────
    "4855003": {
        "abbreviation": "DR",
        "patient_name": "Diabetic Eye Disease",
        "icd10": "E11.319",
    },
    "422034002": {
        "abbreviation": "Diabetic retinopathy",
        "patient_name": "Diabetic Eye Disease",
        "icd10": "E11.319",
    },
    "368581000119106": {
        "abbreviation": "Neuropathy",
        "patient_name": "Diabetic Nerve Damage",
        "icd10": "E11.40",
    },
    "1501000119109": {
        "abbreviation": "PDR (T2DM)",
        "patient_name": "Advanced Diabetic Eye Disease",
        "icd10": "E11.359",
    },
    "97331000119101": {
        "abbreviation": "DME + DR",
        "patient_name": "Diabetic Eye Swelling",
        "icd10": "E11.311",
    },
    "60951000119105": {
        "abbreviation": "Blindness (T2DM)",
        "patient_name": "Vision Loss from Diabetes",
        "icd10": "E11.3",
    },

    # ── Respiratory (additional) ────────────────────────────────────
    "185086009": {
        "abbreviation": "COPD (bronchitis)",
        "patient_name": "Chronic Lung Disease",
        "icd10": "J44.1",
    },

    # ── Ophthalmologic (additional) ──────────────────────────────────
    "1551000119108": {
        "abbreviation": "NPDR (T2DM)",
        "patient_name": "Diabetic Eye Disease",
        "icd10": "E11.329",
    },

    # ── Surgical / trauma (additional) ───────────────────────────────
    "47693006": {
        "abbreviation": "Ruptured appendix",
        "patient_name": "Ruptured Appendix",
        "icd10": "K35.20",
    },

    # ── Rheumatologic ────────────────────────────────────────────────
    "95417003": {
        "abbreviation": "Fibromyalgia",
        "patient_name": "Fibromyalgia",
        "icd10": "M79.7",
    },

    # ── ENT / Respiratory (additional) ──────────────────────────────
    "40055000": {
        "abbreviation": "Chronic sinusitis",
        "patient_name": "Chronic Sinus Problems",
        "icd10": "J32.9",
    },
    "446096008": {
        "abbreviation": "Allergic rhinitis",
        "patient_name": "Allergies (Nasal)",
        "icd10": "J30.89",
    },

    # ── Metabolic (additional) ───────────────────────────────────────
    "302870006": {
        "abbreviation": "Hypertriglyceridemia",
        "patient_name": "High Triglycerides",
        "icd10": "E78.1",
    },
    "237602007": {
        "abbreviation": "MetS",
        "patient_name": "Metabolic Syndrome",
        "icd10": "E88.81",
    },
    "80394007": {
        "abbreviation": "Hyperglycemia",
        "patient_name": "High Blood Sugar",
        "icd10": "R73.9",
    },

    # ── Neurological (additional) ────────────────────────────────────
    "124171000119105": {
        "abbreviation": "Migraine",
        "patient_name": "Chronic Migraine",
        "icd10": "G43.709",
    },
    "128613002": {
        "abbreviation": "Seizure disorder",
        "patient_name": "Seizure Disorder",
        "icd10": "G40.909",
    },
    "703151001": {
        "abbreviation": "Hx seizure",
        "patient_name": "Previous Seizure",
        "icd10": "R56.9",
    },
    "84757009": {
        "abbreviation": "Epilepsy",
        "patient_name": "Epilepsy",
        "icd10": "G40.909",
    },

    # ── Surgical history ─────────────────────────────────────────────
    "74400008": {
        "abbreviation": "Appendicitis",
        "patient_name": "Appendicitis",
        "icd10": "K37",
    },
    "428251008": {
        "abbreviation": "Hx appendectomy",
        "patient_name": "Previous Appendix Surgery",
        "icd10": "Z87.09",
    },
    "410429000": {
        "abbreviation": "Cardiac arrest",
        "patient_name": "Cardiac Arrest",
        "icd10": "I46.9",
    },
    "429007001": {
        "abbreviation": "Hx cardiac arrest",
        "patient_name": "History of Cardiac Arrest",
        "icd10": "Z86.74",
    },
    "429280009": {
        "abbreviation": "Hx foot amputation",
        "patient_name": "Previous Foot Amputation",
        "icd10": "Z89.43",
    },
    "55680006": {
        "abbreviation": "Drug overdose",
        "patient_name": "Drug Overdose",
        "icd10": "T50.901A",
    },

    # ── GI (additional) ──────────────────────────────────────────────
    "68496003": {
        "abbreviation": "Colon polyp",
        "patient_name": "Colon Polyp",
        "icd10": "K63.5",
    },
    "713197008": {
        "abbreviation": "Rectal polyp (recurrent)",
        "patient_name": "Recurrent Rectal Polyp",
        "icd10": "K62.1",
    },
    "75498004": {
        "abbreviation": "Acute sinusitis",
        "patient_name": "Sinus Infection",
        "icd10": "J01.90",
    },

    # ── Oncology ─────────────────────────────────────────────────────
    "254837009": {
        "abbreviation": "Breast Ca",
        "patient_name": "Breast Cancer",
        "icd10": "C50.919",
    },
    "126906006": {
        "abbreviation": "Prostate neoplasm",
        "patient_name": "Prostate Growth",
        "icd10": "D29.1",
    },
    "92691004": {
        "abbreviation": "Prostate CIS",
        "patient_name": "Early Prostate Changes",
        "icd10": "D07.5",
    },

    # ── Musculoskeletal (additional) ─────────────────────────────────
    "201834006": {
        "abbreviation": "Hand OA",
        "patient_name": "Hand Arthritis",
        "icd10": "M19.049",
    },
    "239872002": {
        "abbreviation": "Hip OA",
        "patient_name": "Hip Arthritis",
        "icd10": "M16.9",
    },

    # ── Reproductive ─────────────────────────────────────────────────
    "19169002": {
        "abbreviation": "Miscarriage (Hx)",
        "patient_name": "Previous Miscarriage",
        "icd10": "O03.9",
    },

    # ── Dental ───────────────────────────────────────────────────────
    "196416002": {
        "abbreviation": "Impacted molars",
        "patient_name": "Impacted Wisdom Teeth",
        "icd10": "K01.1",
    },

    # ── Other common Synthea conditions ──────────────────────────────
    "271737000": {
        "abbreviation": "Anemia",
        "patient_name": "Anemia",
        "icd10": "D64.9",
    },
    "55822004": {
        "abbreviation": "Hyperlipidemia",
        "patient_name": "High Cholesterol",
        "icd10": "E78.5",
    },
    "38341003": {
        "abbreviation": "HTN",
        "patient_name": "High Blood Pressure",
        "icd10": "I10",
    },
    "399211009": {
        "abbreviation": "MI (Hx)",
        "patient_name": "History of Heart Attack",
        "icd10": "I25.2",
    },
    "73211009": {
        "abbreviation": "DM",
        "patient_name": "Diabetes",
        "icd10": "E11.9",
    },
    "72892002": {
        "abbreviation": "OSA",
        "patient_name": "Sleep Apnea",
        "icd10": "G47.33",
    },
}


# ── Lab short names ──────────────────────────────────────────────────────

LAB_SHORT_NAMES: dict[str, str] = {
    "4548-4": "HbA1c",
    "2339-0": "Glucose",
    "2345-7": "Glucose (serum)",
    "6299-2": "BUN",
    "2160-0": "Creatinine",
    "33914-3": "eGFR",
    "2571-8": "Triglycerides",
    "2093-3": "Total Cholesterol",
    "2085-9": "HDL",
    "13457-7": "LDL (calc)",
    "18262-6": "LDL",
    "2823-3": "Potassium",
    "2951-2": "Sodium",
    "17861-6": "Calcium",
    "718-7": "Hemoglobin",
    "4544-3": "Hematocrit",
    "789-8": "RBC",
    "6690-2": "WBC",
    "785-6": "MCH",
    "786-4": "MCHC",
    "787-2": "MCV",
    "788-0": "RDW",
    "777-3": "Platelets",
    "32623-1": "Platelet Mean Volume",
    "6768-6": "ALP",
    "1742-6": "ALT",
    "1920-8": "AST",
    "1975-2": "Bilirubin",
    "2157-6": "CK",
    "49765-1": "Calcium (corrected)",
    "14959-1": "Microalbumin/Creatinine",
    "14682-9": "Creatinine (urine)",
    "1751-7": "Albumin (serum)",
    "2947-0": "Chloride",
    "1988-5": "CRP",
    "30385-9": "hsCRP",
    # Vitals
    "8302-2": "Height",
    "29463-7": "Weight",
    "39156-5": "BMI",
    "8310-5": "Temperature",
    "8867-4": "Heart Rate",
    "8480-6": "Systolic BP",
    "8462-4": "Diastolic BP",
    "9279-1": "Respiratory Rate",
    "59408-5": "SpO2",
    "72166-2": "Smoking Status",
}


def lookup_condition(snomed_code: str, synthea_display: str) -> dict[str, str]:
    """Look up a SNOMED code, falling back to Synthea's display text.

    Returns dict with keys: abbreviation, patient_name, icd10 (may be None).
    """
    if snomed_code in CONDITION_MAP:
        entry = CONDITION_MAP[snomed_code]
        return {
            "abbreviation": entry["abbreviation"],
            "patient_name": entry["patient_name"],
            "icd10": entry.get("icd10"),
        }
    # Fallback: use Synthea's display as both abbreviation and patient name
    return {
        "abbreviation": synthea_display,
        "patient_name": synthea_display,
        "icd10": None,
    }


def lookup_lab_short_name(loinc_code: str, display: str) -> str:
    """Get a short lab name for a LOINC code, falling back to display text."""
    return LAB_SHORT_NAMES.get(loinc_code, display)
