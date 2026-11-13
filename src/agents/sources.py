"""Source nodes: graph steps that gather evidence without calling an LLM.

Each node reads the profile and reading from state and writes its evidence
into ``sources`` plus one entry into ``retrieval_trace`` so the interface
can show what was looked up.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.data.profile import TestReading, UserProfile
from src.models.state import MedGraphState
from src.sources.queries import question_queries, reading_queries
from src.sources.reference_ranges import lookup_reference_ranges
from src.sources.safety import evaluate_safety
from src.sources.study_library import StudyLibrary, get_study_library

logger = logging.getLogger(__name__)


def _profile(state: MedGraphState) -> Optional[UserProfile]:
    data = state.get("patient") or {}
    return UserProfile.model_validate(data) if data else None


def _reading(state: MedGraphState) -> Optional[TestReading]:
    data = state.get("reading") or {}
    return TestReading.model_validate(data) if data else None


class SafetySource:
    """Checks the safety rules against the profile and the reading."""

    name = "safety_rules"

    def __init__(self, library: Optional[StudyLibrary] = None) -> None:
        self._library = library

    async def __call__(self, state: MedGraphState) -> dict:
        profile = _profile(state)
        if profile is None:
            return {"handoff_chain": [self.name]}
        library = self._library or get_study_library()
        fired = evaluate_safety(profile, _reading(state), library.records)
        language = state.get("language", "en")
        return {
            "safety_reasons": [f.rule.text(language) for f in fired],
            "safety_escalation": bool(fired),
            "sources": {f.evidence.id: f.evidence.model_dump() for f in fired if f.evidence},
            "retrieval_trace": [{
                "source": self.name,
                "query": "",
                "counts": {"fired": len(fired)},
            }],
            "handoff_chain": [self.name],
        }


class GuidelineSource:
    """Finds guideline passages that speak to the question."""

    name = "guidelines"

    def __init__(self, library: Optional[StudyLibrary] = None) -> None:
        self._library = library

    async def __call__(self, state: MedGraphState) -> dict:
        queries = list(state.get("queries") or []) or question_queries(state.get("user_input", ""))
        library = self._library or get_study_library()
        try:
            items = await asyncio.to_thread(library.retrieve_guidelines, queries)
        except Exception:  # noqa: BLE001 - the answer degrades, the turn survives
            logger.exception("Guideline search failed")
            return {
                "retrieval_trace": [{"source": self.name, "query": "", "counts": {"found": 0}, "error": True}],
                "handoff_chain": [self.name],
            }
        return {
            "sources": {item.id: item.model_dump() for item in items},
            "retrieval_trace": [{
                "source": self.name,
                "query": queries[0] if queries else "",
                "counts": {"found": len(items)},
            }],
            "handoff_chain": [self.name],
        }


class ReferenceRangeSource:
    """Looks up the expected pH statements for this profile."""

    name = "reference_ranges"

    def __init__(self, library: Optional[StudyLibrary] = None) -> None:
        self._library = library

    async def __call__(self, state: MedGraphState) -> dict:
        profile = _profile(state)
        if profile is None:
            return {"handoff_chain": [self.name]}
        library = self._library or get_study_library()
        items = lookup_reference_ranges(profile, library.records)
        pregnancy = "pregnant" if profile.pregnancy.is_pregnant else "not pregnant"
        return {
            "sources": {item.id: item.model_dump() for item in items},
            "retrieval_trace": [{
                "source": self.name,
                "query": f"{profile.menopausal_status.value}, {pregnancy}",
                "counts": {"found": len(items)},
            }],
            "handoff_chain": [self.name],
        }


class StudyLibrarySource:
    """Searches the study corpus and splits results into the two lanes."""

    name = "study_library"

    def __init__(self, library: Optional[StudyLibrary] = None) -> None:
        self._library = library

    async def __call__(self, state: MedGraphState) -> dict:
        profile = _profile(state)
        if profile is None:
            return {"handoff_chain": [self.name]}

        queries = list(state.get("queries") or [])
        if not queries:
            reading = _reading(state)
            if state.get("turn_kind") == "new_reading" and reading is not None:
                queries = reading_queries(profile, reading)
            else:
                queries = question_queries(state.get("user_input", ""))

        library = self._library or get_study_library()
        try:
            lanes = await asyncio.to_thread(library.retrieve, queries, profile)
        except Exception:  # noqa: BLE001 - the answer degrades, the turn survives
            logger.exception("Study library search failed")
            return {
                "retrieval_trace": [{
                    "source": self.name, "query": queries[0] if queries else "",
                    "counts": {"found": 0, "matched": 0}, "error": True,
                }],
                "handoff_chain": [self.name],
            }

        return {
            "sources": {item.id: item.model_dump() for item in lanes.items},
            "evidence_gap": {
                "no_matched_evidence": lanes.no_matched_evidence,
                "unmatched_attributes": lanes.unmatched_attributes,
            },
            "retrieval_trace": [{
                "source": self.name,
                "query": queries[0] if queries else "",
                "queries": queries,
                "counts": {
                    "found": lanes.studies_found,
                    "used": len(lanes.items),
                    "matched": len(lanes.matched),
                },
            }],
            "handoff_chain": [self.name],
        }
