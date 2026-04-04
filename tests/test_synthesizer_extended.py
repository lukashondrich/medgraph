"""Tests for extended synthesizer (Phase 4).

Covers build_prompt() extensions for evidence + citations sections,
backward compatibility with old signature.
"""

import pytest

from src.prompts.synthesizer import build_prompt


class TestBuildPromptBackwardCompat:
    def test_old_signature_still_works(self):
        """build_prompt(specialist_outputs, safety_escalation) still works."""
        prompt = build_prompt({"symptom": "headache info"}, safety_escalation=False)
        assert "Symptom Specialist" in prompt
        assert "headache info" in prompt

    def test_safety_escalation_block(self):
        prompt = build_prompt(
            {"symptom": "chest pain [SAFETY_ESCALATION]"},
            safety_escalation=True,
        )
        assert "SAFETY NOTICE" in prompt

    def test_no_specialist_outputs(self):
        prompt = build_prompt({})
        assert "No specialist outputs received" in prompt


class TestBuildPromptEvidence:
    def test_evidence_section_included(self):
        prompt = build_prompt(
            {"symptom": "knee pain info"},
            evidence_context={
                "ADA-SOC-2025": "ADA recommends caution with NSAIDs in CKD.",
            },
        )
        assert "Evidence" in prompt
        assert "ADA recommends caution" in prompt

    def test_citations_section_included(self):
        prompt = build_prompt(
            {"medication": "ibuprofen info"},
            citations=[
                {"source": "ADA-SOC-2025", "tier": "guideline", "text": "Avoid NSAIDs in CKD"},
                {"source": "NICE-NG28", "tier": "guideline", "text": "CKD management"},
            ],
        )
        assert "Citations" in prompt
        assert "ADA-SOC-2025" in prompt
        assert "NICE-NG28" in prompt

    def test_no_evidence_no_section(self):
        """When no evidence, don't add empty sections."""
        prompt = build_prompt({"symptom": "test"})
        assert "Retrieved Evidence" not in prompt

    def test_drug_interactions_section_included(self):
        prompt = build_prompt(
            {"medication": "info"},
            drug_interactions=[
                {"drug_a": "NAPROXEN", "drug_b": "LISINOPRIL", "severity": "high"},
            ],
        )
        assert "Drug Interaction" in prompt
        assert "NAPROXEN" in prompt

    def test_full_extended_prompt(self):
        """All sections present when all data provided."""
        prompt = build_prompt(
            specialist_outputs={"symptom": "knee pain", "medication": "ibuprofen info"},
            safety_escalation=True,
            evidence_context={"ADA-1": "Avoid NSAIDs"},
            citations=[{"source": "ADA-1", "tier": "guideline", "text": "..."}],
            drug_interactions=[{"drug_a": "A", "drug_b": "B", "severity": "high"}],
        )
        assert "Symptom Specialist" in prompt
        assert "Medication Specialist" in prompt
        assert "SAFETY NOTICE" in prompt
        assert "Evidence" in prompt
        assert "Citations" in prompt
        assert "Drug Interaction" in prompt
