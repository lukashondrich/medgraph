"""Evaluation dataset models and loaders.

Loads and normalizes LiveQA TREC 2017, MedicationQA, and custom adversarial
safety datasets into a common EvalSample format for evaluation.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Project root is three levels up from this file:
#   tests/eval/datasets.py -> project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data" / "eval"


# ---------------------------------------------------------------------------
# Route-mapping helpers
# ---------------------------------------------------------------------------

# LiveQA question types -> specialist agent(s)
_LIVEQA_TYPE_ROUTES: dict[str, list[str]] = {
    # Symptom agent: symptom descriptions, diagnosis-seeking, triage
    "SYMPTOM": ["symptom"],
    "DIAGNOSIS": ["symptom"],
    "SUSCEPTIBILITY": ["symptom"],
    "PROGNOSIS": ["symptom"],
    "COMPLICATION": ["symptom"],
    "CAUSE": ["symptom"],
    # Medication agent: drug info, side effects, interactions, dosage
    "DOSAGE": ["medication"],
    "SIDE_EFFECT": ["medication"],
    "INTERACTION": ["medication"],
    "INGREDIENT": ["medication"],
    "CONTRAINDICATION": ["medication"],
    "TAPERING": ["medication"],
    "STORAGE_DISPOSAL": ["medication"],
    "ACTION": ["medication"],
    "INDICATION": ["medication"],
    "USAGE": ["medication"],
    # Lifestyle agent: diet, exercise, prevention, wellness
    "LIFESTYLE_DIET": ["lifestyle"],
    "PREVENTION": ["lifestyle"],
    # Multi-agent or ambiguous
    "TREATMENT": ["symptom", "medication"],
    "EFFECT": ["symptom", "medication"],
    "ALTERNATIVE": ["medication", "lifestyle"],
    "COMPARISON": ["medication"],
    "INFORMATION": ["symptom"],
    "INHERITANCE": ["symptom"],
    "PERSON_ORGANIZATION": ["symptom"],
    "OTHER_QUESTION": ["symptom"],
}

# MedicationQA question types -> specialist agent(s)
_MEDQA_TYPE_ROUTES: dict[str, list[str]] = {
    "Information": ["medication"],
    "Dose": ["medication"],
    "Usage": ["medication"],
    "Side effects": ["medication"],
    "Indication": ["medication"],
    "Interaction": ["medication"],
    "Appearance": ["medication"],
    "Action": ["medication"],
    "Usage/time": ["medication"],
    "Stopping/tapering": ["medication"],
    "Ingredient": ["medication"],
    "Action/time": ["medication"],
    "Storage and disposal": ["medication"],
    "Comparison": ["medication"],
    "Contraindication": ["medication"],
    "Overdose": ["medication"],
    "Alternatives": ["medication", "lifestyle"],
    "Usage/duration": ["medication"],
    "not_drug_question": ["symptom"],
    "Time/duration": ["medication"],
    "Pronounce name": ["medication"],
    "Brand names": ["medication"],
    "Action/effectiveness": ["medication"],
    "Combination": ["medication"],
    "Dose/time": ["medication"],
    "Manufacturer": ["medication"],
    "Stopping/side effects": ["medication"],
    "Side effects/time": ["medication"],
    "Availability": ["medication"],
    "Time/side effects": ["medication"],
    "Dose/Potency": ["medication"],
    "other_drug_question": ["medication"],
    "Forget a dose": ["medication"],
    "unanswerable": ["medication"],
    "Usage/special populations": ["medication"],
    "Time/effectiveness": ["medication"],
    "Long term consequences": ["medication", "symptom"],
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class EvalSample(BaseModel):
    """A single evaluation sample from a dataset."""

    query: str = Field(..., description="Patient question")
    reference_answer: Optional[str] = Field(
        default=None,
        description="Gold-standard answer (None for safety-only samples)",
    )
    expected_routes: Optional[List[str]] = Field(
        default=None,
        description="Expected specialist agent(s) for routing evaluation",
    )
    source: str = Field(..., description="Dataset name (liveqa / medication_qa / safety)")
    category: str = Field(..., description="Question type or category")


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------


class DatasetLoader:
    """Loads and normalizes evaluation datasets from data/eval/."""

    LIVEQA_DIR: ClassVar[Path] = _DATA_DIR / "liveqa"
    MEDQA_DIR: ClassVar[Path] = _DATA_DIR / "medication_qa"
    SAFETY_DIR: ClassVar[Path] = _DATA_DIR / "safety"

    # ------------------------------------------------------------------
    # LiveQA TREC 2017
    # ------------------------------------------------------------------

    def load_liveqa(self) -> list[EvalSample]:
        """Load LiveQA TREC 2017 test questions with reference answers.

        Parses the XML test-questions-with-summaries file that contains 104
        questions, each with one or more reference answers, focus annotations,
        and question-type annotations.

        Returns:
            List of EvalSample with query, reference_answer, expected_routes,
            source='liveqa', and category set to the question type(s).
        """
        xml_path = self.LIVEQA_DIR / "TREC-2017-LiveQA-Medical-Test-Questions-w-summaries.xml"
        if not xml_path.exists():
            raise FileNotFoundError(
                f"LiveQA data not found at {xml_path}. "
                "Run the dataset download step first."
            )

        tree = ET.parse(xml_path)  # noqa: S314
        root = tree.getroot()
        samples: list[EvalSample] = []

        for question_el in root.findall(".//NLM-QUESTION"):
            # --- Extract query ---
            # Prefer the NLM summary (cleaner), fall back to original message
            summary_el = question_el.find("NLM-Summary")
            orig_q = question_el.find("Original-Question")
            if summary_el is not None and summary_el.text and summary_el.text.strip():
                query = summary_el.text.strip()
            elif orig_q is not None:
                msg_el = orig_q.find("MESSAGE")
                subj_el = orig_q.find("SUBJECT")
                message = msg_el.text.strip() if msg_el is not None and msg_el.text else ""
                subject = subj_el.text.strip() if subj_el is not None and subj_el.text else ""
                query = f"{subject}: {message}" if subject and message else (message or subject)
            else:
                continue  # skip malformed entries

            if not query:
                continue

            # --- Extract reference answer (combine all reference answers) ---
            ref_answers: list[str] = []
            for ref in question_el.findall(".//RefAnswer/ANSWER"):
                if ref.text and ref.text.strip():
                    ref_answers.append(ref.text.strip())
            # Also check ReferenceAnswer elements
            for ref in question_el.findall(".//ReferenceAnswer/ANSWER"):
                if ref.text and ref.text.strip():
                    ref_answers.append(ref.text.strip())

            reference_answer = "\n\n---\n\n".join(ref_answers) if ref_answers else None

            # --- Extract question types ---
            q_types: list[str] = []
            for type_el in question_el.findall(".//ANNOTATIONS/TYPE"):
                # The type text is stored as element text content
                type_text = type_el.text.strip() if type_el.text else ""
                if not type_text:
                    # Some entries use the tid attribute pattern like "T1"
                    # but type names are in the element text
                    continue
                q_types.append(type_text)

            # Use the first type as category, or "UNKNOWN"
            category = q_types[0] if q_types else "UNKNOWN"

            # --- Determine expected routes ---
            routes: set[str] = set()
            for qt in q_types:
                qt_upper = qt.upper()
                if qt_upper in _LIVEQA_TYPE_ROUTES:
                    routes.update(_LIVEQA_TYPE_ROUTES[qt_upper])
            expected_routes = sorted(routes) if routes else ["symptom"]

            samples.append(
                EvalSample(
                    query=query,
                    reference_answer=reference_answer,
                    expected_routes=expected_routes,
                    source="liveqa",
                    category=category,
                )
            )

        return samples

    # ------------------------------------------------------------------
    # MedicationQA
    # ------------------------------------------------------------------

    def load_medication_qa(self) -> list[EvalSample]:
        """Load MedicationQA dataset from the Excel file.

        Parses the MedInfo2019-QA-Medications.xlsx file containing ~690
        medication-related QA pairs with question type annotations.

        Returns:
            List of EvalSample with query, reference_answer, expected_routes,
            source='medication_qa', and category set to the question type.
        """
        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to load MedicationQA. "
                "Install it with: pip install openpyxl"
            ) from exc

        xlsx_path = self.MEDQA_DIR / "MedInfo2019-QA-Medications.xlsx"
        if not xlsx_path.exists():
            raise FileNotFoundError(
                f"MedicationQA data not found at {xlsx_path}. "
                "Run the dataset download step first."
            )

        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        samples: list[EvalSample] = []

        # Expected columns: Question, Focus (Drug), Question Type, Answer,
        #                    Section Title, URL
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            question = str(row[0]).strip() if row[0] else ""
            question_type = str(row[2]).strip() if row[2] else "Information"
            answer = str(row[3]).strip() if row[3] else None

            if not question:
                continue

            # Clean up answer
            if answer and answer.lower() in ("none", "na", "n/a", ""):
                answer = None

            # Determine expected routes
            routes = _MEDQA_TYPE_ROUTES.get(question_type, ["medication"])

            samples.append(
                EvalSample(
                    query=question,
                    reference_answer=answer,
                    expected_routes=routes,
                    source="medication_qa",
                    category=question_type,
                )
            )

        wb.close()
        return samples

    # ------------------------------------------------------------------
    # Safety / Adversarial prompts
    # ------------------------------------------------------------------

    def load_safety(self) -> list[EvalSample]:
        """Load custom adversarial safety prompts.

        Parses data/eval/safety/adversarial_prompts.json, which contains
        hand-crafted prompts designed to test whether agents refuse to
        diagnose, prescribe, or give harmful advice.

        Returns:
            List of EvalSample with query, reference_answer=None,
            expected_routes=None, source='safety', and category from the
            prompt's category field.
        """
        json_path = self.SAFETY_DIR / "adversarial_prompts.json"
        if not json_path.exists():
            raise FileNotFoundError(
                f"Safety prompts not found at {json_path}. "
                "Create the adversarial prompts file first."
            )

        with open(json_path, encoding="utf-8") as f:
            prompts = json.load(f)

        samples: list[EvalSample] = []
        for prompt in prompts:
            query = prompt.get("query", "").strip()
            if not query:
                continue

            samples.append(
                EvalSample(
                    query=query,
                    reference_answer=None,
                    expected_routes=None,
                    source="safety",
                    category=prompt.get("category", "unknown"),
                )
            )

        return samples

    # ------------------------------------------------------------------
    # Convenience: load all
    # ------------------------------------------------------------------

    def load_all(self) -> dict[str, list[EvalSample]]:
        """Load all available datasets.

        Returns:
            Dictionary mapping dataset name to list of EvalSample.
        """
        return {
            "liveqa": self.load_liveqa(),
            "medication_qa": self.load_medication_qa(),
            "safety": self.load_safety(),
        }
