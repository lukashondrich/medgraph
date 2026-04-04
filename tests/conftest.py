"""Shared fixtures for the test suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def base_state() -> dict:
    """Return a minimal valid HealthcareState dict for testing.

    Uses a plain dict because HealthcareState is a TypedDict (structural typing).
    """
    return {
        "messages": [],
        "user_input": "I have a headache and feel dizzy.",
        "route": [],
        "route_reasoning": "",
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
    }


@pytest.fixture
def state_with_specialist_outputs(base_state: dict) -> dict:
    """State with pre-filled specialist outputs for synthesizer tests."""
    base_state["specialist_outputs"] = {
        "symptom": "Headaches with dizziness can have many causes. Please monitor onset and severity.",
        "lifestyle": "Staying hydrated and getting adequate rest can help with headaches.",
    }
    base_state["route"] = ["symptom", "lifestyle"]
    return base_state
