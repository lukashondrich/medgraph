"""Tests for state model backward compatibility (Phase 2).

Ensures the MedGraphState extension doesn't break existing code
that uses HealthcareState or the original 8 fields.
"""

from typing import get_type_hints

import pytest

from src.models.state import MedGraphState, HealthcareState, _merge_dicts, _or_reduce


class TestBackwardCompatibility:
    """All 8 original fields exist with same types."""

    def test_healthcare_state_alias_exists(self):
        """HealthcareState is still importable and is the same as MedGraphState."""
        assert HealthcareState is MedGraphState

    def test_original_fields_present(self):
        hints = get_type_hints(MedGraphState, include_extras=True)
        original_fields = [
            "messages", "user_input", "route", "route_reasoning",
            "specialist_outputs", "final_response", "handoff_chain",
            "safety_escalation",
        ]
        for field in original_fields:
            assert field in hints, f"Original field '{field}' missing from MedGraphState"

    def test_old_initial_state_works(self):
        """A dict with only the old fields is a valid state."""
        old_state: MedGraphState = {
            "messages": [],
            "user_input": "test",
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
        }
        assert old_state["user_input"] == "test"
        assert old_state["safety_escalation"] is False

    def test_merge_dicts_reducer_unchanged(self):
        left = {"symptom": "headache info"}
        right = {"medication": "aspirin info"}
        merged = _merge_dicts(left, right)
        assert merged == {"symptom": "headache info", "medication": "aspirin info"}
        # Originals not mutated
        assert "medication" not in left

    def test_or_reduce_unchanged(self):
        assert _or_reduce(False, False) is False
        assert _or_reduce(False, True) is True
        assert _or_reduce(True, False) is True


class TestNewFields:
    """New medgraph fields are present and default-friendly."""

    def test_new_fields_present(self):
        hints = get_type_hints(MedGraphState, include_extras=True)
        new_fields = [
            "patient", "patient_summary", "evidence_context",
            "drug_interactions", "citations",
        ]
        for field in new_fields:
            assert field in hints, f"New field '{field}' missing from MedGraphState"

    def test_state_with_new_fields(self):
        """A state dict can include the new fields."""
        state: MedGraphState = {
            "messages": [],
            "user_input": "test",
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
            "patient": {"id": "test-123", "name": "Jane Doe"},
            "patient_summary": "72F, T2DM, HTN",
            "evidence_context": {},
            "drug_interactions": [],
            "citations": [],
        }
        assert state["patient"]["name"] == "Jane Doe"
        assert state["patient_summary"] == "72F, T2DM, HTN"

    def test_evidence_context_merge_reducer(self):
        """evidence_context uses _merge_dicts to combine from multiple agents."""
        left = {"guideline-1": "ADA recommends..."}
        right = {"guideline-2": "NICE says..."}
        merged = _merge_dicts(left, right)
        assert len(merged) == 2

    def test_citations_append_reducer(self):
        """citations use operator.add to append from multiple agents."""
        import operator
        left = [{"source": "ADA", "text": "..."}]
        right = [{"source": "NICE", "text": "..."}]
        result = operator.add(left, right)
        assert len(result) == 2
