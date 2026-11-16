"""Safety rules: when must the answer recommend seeing a clinician?

A small rule table evaluated against the profile and the reading before the
writer runs. Deterministic on purpose: this is where a wrong answer does the
most harm, so it is not left to a language model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from src.data.profile import TestReading, UserProfile
from src.knowledge_pipeline.study_schemas import CORPUS_DIR, StudyDesign, StudyRecord
from src.models.evidence import SourceItem

from .deeplinks import quote_links

SAFETY_RULES_PATH = CORPUS_DIR / "safety_rules.yaml"


class RuleCondition(BaseModel):
    pregnant: Optional[bool] = None
    menopausal_status: list[str] = Field(default_factory=list)
    ph_min: Optional[float] = None
    symptoms_any: list[str] = Field(default_factory=list)
    history_any: list[str] = Field(default_factory=list)
    has_symptoms: Optional[bool] = None


class SafetyRule(BaseModel):
    id: str
    when: RuleCondition
    message: str
    message_de: str = ""
    study_id: Optional[str] = None
    quote: Optional[str] = None

    def text(self, language: str = "en") -> str:
        return self.message_de if language == "de" and self.message_de else self.message

    def fires(self, profile: UserProfile, reading: Optional[TestReading]) -> bool:
        w = self.when
        if w.pregnant is not None and profile.pregnancy.is_pregnant != w.pregnant:
            return False
        if w.menopausal_status and profile.menopausal_status.value not in w.menopausal_status:
            return False
        if w.ph_min is not None and (reading is None or reading.ph < w.ph_min):
            return False
        if w.has_symptoms is not None and bool(profile.symptoms) != w.has_symptoms:
            return False
        if w.symptoms_any and not _mentions(profile.symptoms, w.symptoms_any):
            return False
        if w.history_any and not _mentions(profile.history, w.history_any):
            return False
        return True


def _mentions(entries: list[str], keywords: list[str]) -> bool:
    text = " | ".join(entries).lower()
    return any(keyword.lower() in text for keyword in keywords)


class FiredRule(BaseModel):
    rule: SafetyRule
    evidence: Optional[SourceItem] = None


def load_safety_rules(path: Path = SAFETY_RULES_PATH) -> list[SafetyRule]:
    if not path.exists():
        return []
    return [SafetyRule.model_validate(row) for row in yaml.safe_load(path.read_text()) or []]


def evaluate_safety(
    profile: UserProfile,
    reading: Optional[TestReading],
    records: dict[str, StudyRecord],
    rules: Optional[list[SafetyRule]] = None,
) -> list[FiredRule]:
    """Return the rules that fire for this profile and reading.

    A rule fires whether or not its supporting study is in the corpus; the
    evidence is attached only when it can be cited.
    """
    rules = load_safety_rules() if rules is None else rules
    fired = []
    for rule in rules:
        if not rule.fires(profile, reading):
            continue
        evidence = None
        record = records.get(rule.study_id) if rule.study_id else None
        if record is not None and rule.quote:
            evidence = SourceItem(
                id=f"safety:{rule.id}",
                source="safety_rules",
                group="guideline" if record.design is StudyDesign.GUIDELINE else "safety",
                study_id=record.study_id,
                title=record.title,
                authors=record.authors,
                year=record.year,
                design=record.design_label,
                sample_size=record.sample_size,
                cohort_summary=record.cohort.description,
                countries=record.cohort.countries,
                passage=rule.quote,
                quotes=[quote_links(record, rule.quote)],
                statement=rule.message,
                url=record.url,
                relevance=1.0,
            )
        fired.append(FiredRule(rule=rule, evidence=evidence))
    return fired
