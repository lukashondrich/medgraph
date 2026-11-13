"""Evaluation helpers: run real turns through the graph and judge the answers.

These tests make real model calls and use the real study store, so they need
an API key and must not run while the web app is running (the embedded
store allows one process at a time).

    pytest tests/eval/ -v
"""

from __future__ import annotations

import json
import re

import litellm
import pytest

from src.agents.writer import NEW_READING_INPUT
from src.config import load_config
from src.data.personas import load_persona
from src.data.profile import TestReading, UserProfile, build_profile_summary
from src.orchestrator import build_ph_graph

_cache: dict[tuple, dict] = {}


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.eval)


@pytest.fixture(scope="session", autouse=True)
def _config():
    return load_config()


async def run_turn(
    persona: str | UserProfile,
    ph: float = 4.8,
    confidence: float = 0.92,
    question: str | None = None,
    language: str = "en",
) -> dict:
    """Run one turn and return the final graph state. Identical turns are reused."""
    profile = load_persona(persona) if isinstance(persona, str) else persona
    key = (profile.id, profile.ancestry, ph, confidence, question, language)
    if key in _cache:
        return _cache[key]
    reading = TestReading(ph=ph, confidence=confidence, taken_at="2026-11-13T08:14:00")
    state = {
        "messages": [],
        "user_input": question or NEW_READING_INPUT,
        "language": language,
        "patient": profile.to_dict(),
        "patient_summary": build_profile_summary(profile, reading),
        "reading": reading.to_dict(),
        "turn_kind": "question" if question else "new_reading",
        "route": [], "queries": [], "route_reasoning": "",
        "sources": {}, "retrieval_trace": [], "evidence_gap": {},
        "safety_reasons": [], "safety_escalation": False,
        "final_response": "", "citations": [], "handoff_chain": [],
    }
    _cache[key] = await build_ph_graph().ainvoke(state)
    return _cache[key]


def cited_numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[(\d+)\]", text)}


async def judge(answer: str, statement: str) -> tuple[bool, str]:
    """Ask the model whether ``statement`` is true of ``answer``."""
    import os

    prompt = (
        "You are grading an assistant's answer to a woman about her at-home vaginal pH test.\n"
        "Decide whether the statement below is true of the answer. Be strict and literal.\n"
        'Reply with JSON: {"verdict": true or false, "reason": "one sentence"}\n\n'
        f"Statement: {statement}\n\nAnswer:\n{answer}"
    )
    response = await litellm.acompletion(
        model=os.environ["MEDGRAPH_MODEL"],
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return bool(data.get("verdict")), str(data.get("reason", ""))
