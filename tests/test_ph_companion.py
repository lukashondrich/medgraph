"""Tests for the pH Companion thin slice (M1).

Covers the deterministic parts: models, cohort matching, lane selection,
reference ranges, the corpus, the citation check, and the graph and API with
the LLM and the embedding search replaced by fakes.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agents.citation_check import check_citations, uncited_paragraphs
from src.agents.planner import ALL_SOURCES, PlannerAgent
from src.agents.sources import (
    GuidelineSource,
    ReferenceRangeSource,
    SafetySource,
    StudyLibrarySource,
)
from src.agents.writer import WriterAgent
from src.data.personas import list_personas, list_readings, load_persona
from src.data.profile import (
    MenopausalStatus,
    PregnancyStatus,
    TestReading,
    UserProfile,
    build_profile_summary,
)
from src.knowledge_pipeline import corpus
from src.knowledge_pipeline.study_schemas import (
    CheckInfo,
    CheckStatus,
    Cohort,
    StudyDesign,
    StudyRecord,
    load_records,
    save_record,
    split_passages,
)
from src.models.evidence import SourceItem
from src.orchestrator import build_ph_graph
from src.orchestrator.graph import planned_sources
from src.prompts.writer import assign_markers, build_prompt
from src.sources.matching import match_cohort
from src.sources.queries import reading_queries
from src.sources.reference_ranges import load_reference_ranges, lookup_reference_ranges
from src.sources.safety import evaluate_safety, load_safety_rules
from src.sources.study_library import (
    LaneResult,
    ScoredPassage,
    evidence_weight,
    select_guidelines,
    select_lanes,
)


# ── Builders ──────────────────────────────────────────────────────────────


def make_profile(**overrides) -> UserProfile:
    data = {
        "id": "test", "name": "Test", "age": 29, "ancestry": "indian",
        "country_of_residence": "Germany", "menopausal_status": "premenopausal",
    }
    return UserProfile.model_validate({**data, **overrides})


def make_record(study_id: str, *, checked: bool = True, **overrides) -> StudyRecord:
    cohort = overrides.pop("cohort", {})
    data = {
        "study_id": study_id, "url": f"https://example.org/{study_id}",
        "title": f"Title of {study_id}", "authors": "Author et al.", "year": 2020,
        "design": StudyDesign.CROSS_SECTIONAL, "sample_size": 100,
        "abstract": "First sentence about pH. Second sentence about bacteria. Third one.",
        "cohort": Cohort(**cohort),
        "check": CheckInfo(status=CheckStatus.CHECKED if checked else CheckStatus.UNCHECKED),
    }
    return StudyRecord.model_validate({**data, **overrides})


def passage(study_id: str, relevance: float, n: int = 1) -> ScoredPassage:
    return ScoredPassage(
        passage_id=f"{study_id}#p{n}", study_id=study_id,
        text=f"Passage {n} of {study_id}.", relevance=relevance,
    )


def make_item(item_id: str, study_id: str, group: str = "overall", text: str = "Quoted.") -> SourceItem:
    return SourceItem(
        id=item_id, source="study_library", group=group, study_id=study_id,
        title="T", authors="A et al.", year=2020, design="Cross-sectional study",
        passage=text, url="https://example.org",
    )


# ── Models and personas ───────────────────────────────────────────────────


class TestModels:
    def test_persona_loads(self):
        priya = load_persona("priya")
        assert priya.ancestry == "indian"
        assert priya.country_of_residence == "Germany"
        assert priya.menopausal_status is MenopausalStatus.PREMENOPAUSAL
        assert not priya.pregnancy.is_pregnant

    def test_unknown_or_unsafe_persona_id(self):
        assert load_persona("nobody") is None
        assert load_persona("../priya") is None
        assert load_persona("_readings") is None

    def test_gallery_and_readings(self):
        assert any(p["persona_id"] == "priya" for p in list_personas())
        readings = list_readings()
        assert readings and all({"id", "ph", "confidence", "taken_at"} <= set(r) for r in readings)

    def test_reading_validation(self):
        with pytest.raises(ValidationError):
            TestReading(ph=12.0, confidence=0.9, taken_at="2026-11-13T08:00:00")
        with pytest.raises(ValidationError):
            TestReading(ph=4.5, confidence=1.4, taken_at="2026-11-13T08:00:00")

    def test_profile_summary_includes_reading(self):
        reading = TestReading(ph=4.8, confidence=0.92, taken_at="2026-11-13T08:14:00")
        summary = build_profile_summary(make_profile(), reading)
        assert "Indian" in summary and "Germany" in summary
        assert "Vaginal pH: 4.8" in summary and "92%" in summary


# ── Cohort matching (task 1.8) ────────────────────────────────────────────


class TestCohortMatch:
    def test_exact_ancestry_qualifies_wherever_the_study_ran(self):
        for country in ("India", "United States", "Germany"):
            record = make_record("s", cohort={"ancestry": ["indian"], "countries": [country]})
            match = match_cohort(make_profile(), record)
            assert match.qualifies and match.ancestry_match == "exact"
            assert "Indian ancestry" in match.matched_attributes

    def test_broader_ancestry_qualifies_with_lower_score_and_label(self):
        exact = match_cohort(make_profile(), make_record("a", cohort={"ancestry": ["indian"]}))
        broader = match_cohort(make_profile(), make_record("b", cohort={"ancestry": ["south_asian"]}))
        assert broader.qualifies and broader.ancestry_match == "broader"
        assert broader.qualifying_score < exact.qualifying_score
        assert "South Asian ancestry (broader group)" in broader.matched_attributes

    def test_unspecified_asian_cohort_is_not_a_match(self):
        record = make_record("s", cohort={"ancestry": ["asian_unspecified", "white_european"]})
        match = match_cohort(make_profile(), record)
        assert not match.qualifies and match.ancestry_match == "none"

    def test_premenopausal_alone_does_not_qualify(self):
        record = make_record("s", cohort={"menopausal_status": ["premenopausal"]})
        match = match_cohort(make_profile(), record)
        assert not match.qualifies
        assert "premenopausal" in match.matched_attributes  # still shown, still scored
        assert match.score > 0 and match.qualifying_score == 0

    def test_postmenopausal_match_qualifies(self):
        profile = make_profile(age=56, ancestry="white_european", menopausal_status="postmenopausal")
        record = make_record("s", cohort={"menopausal_status": ["postmenopausal"]})
        assert match_cohort(profile, record).qualifies

    def test_pregnancy_match_qualifies_only_for_pregnant_profile(self):
        record = make_record("s", cohort={"pregnancy": ["pregnant"]})
        pregnant = make_profile(ancestry="black", pregnancy=PregnancyStatus.SECOND_TRIMESTER)
        assert match_cohort(pregnant, record).qualifies
        assert not match_cohort(make_profile(ancestry="black"), record).qualifies

    def test_majority_ancestry_is_shown_but_does_not_qualify(self):
        anna = make_profile(age=56, ancestry="white_european", menopausal_status="postmenopausal")
        general = make_record("s", cohort={"ancestry": ["white_european", "black"]})
        match = match_cohort(anna, general)
        assert not match.qualifies and "White European ancestry" in match.matched_attributes
        after_menopause = make_record("t", cohort={"menopausal_status": ["postmenopausal"]})
        assert match_cohort(anna, after_menopause).qualifies

    def test_subgroup_cohort_matches_parent_profile(self):
        record = make_record("s", cohort={"ancestry": ["african_american"]})
        assert match_cohort(make_profile(ancestry="black"), record).ancestry_match == "exact"

    def test_age_and_country_add_score_but_do_not_qualify(self):
        record = make_record("s", cohort={"age_min": 18, "age_max": 45, "countries": ["Germany"]})
        match = match_cohort(make_profile(), record)
        assert not match.qualifies
        assert "your age group" in match.matched_attributes
        assert "lives in Germany" in match.matched_attributes


# ── Lane selection (task 1.9) ─────────────────────────────────────────────


class TestLanes:
    def records(self):
        return {
            "small-indian": make_record("small-indian", sample_size=15, cohort={"ancestry": ["indian"]}),
            "big-general": make_record("big-general", sample_size=9000, design=StudyDesign.COHORT),
            "mid-general": make_record("mid-general", sample_size=400),
            "offtopic-indian": make_record("offtopic-indian", cohort={"ancestry": ["indian"]}),
        }

    def test_small_matched_study_is_surfaced(self):
        candidates = [passage("small-indian", 0.55), passage("big-general", 0.9), passage("mid-general", 0.8)]
        lanes = select_lanes(candidates, self.records(), make_profile())
        assert [i.study_id for i in lanes.matched] == ["small-indian"]
        assert lanes.matched[0].sample_size == 15
        assert lanes.matched[0].group == "matched"
        assert not lanes.no_matched_evidence

    def test_small_study_would_lose_on_quality_alone(self):
        records = self.records()
        assert evidence_weight(records["small-indian"]) < evidence_weight(records["big-general"])

    def test_unrelated_matched_study_is_not_surfaced(self):
        candidates = [passage("offtopic-indian", 0.1), passage("big-general", 0.9)]
        lanes = select_lanes(candidates, self.records(), make_profile(), min_relevance=0.3)
        assert lanes.matched == []
        assert lanes.no_matched_evidence
        assert lanes.unmatched_attributes == ["Indian ancestry"]

    def test_unrelated_question_uses_no_studies_and_reports_no_gap(self):
        candidates = [passage(sid, 0.15) for sid in self.records()]
        lanes = select_lanes(candidates, self.records(), make_profile(), min_relevance=0.3)
        assert lanes.items == [] and lanes.studies_found == 0
        assert not lanes.no_matched_evidence

    def test_study_appears_in_one_lane_only(self):
        candidates = [passage("small-indian", 0.9), passage("big-general", 0.8)]
        lanes = select_lanes(candidates, self.records(), make_profile())
        ids = [i.study_id for i in lanes.items]
        assert ids.count("small-indian") == 1
        assert "small-indian" not in [i.study_id for i in lanes.overall]

    def test_overall_lane_ranks_by_relevance_and_quality(self):
        candidates = [passage("mid-general", 0.80), passage("big-general", 0.80)]
        lanes = select_lanes(candidates, self.records(), make_profile())
        assert [i.study_id for i in lanes.overall] == ["big-general", "mid-general"]

    def test_matched_lane_weighs_match_strength_and_relevance(self):
        records = {
            "exact": make_record("exact", cohort={"ancestry": ["indian"]}),
            "broader": make_record("broader", cohort={"ancestry": ["south_asian"]}),
            "exact-weak": make_record("exact-weak", cohort={"ancestry": ["indian"]}),
        }
        # Equal relevance: the closer match comes first.
        lanes = select_lanes([passage("broader", 0.8), passage("exact", 0.8)], records, make_profile())
        assert [i.study_id for i in lanes.matched] == ["exact", "broader"]
        # A broader match that answers the question beats a close match that barely does.
        lanes = select_lanes([passage("exact-weak", 0.4), passage("broader", 0.9)], records, make_profile())
        assert [i.study_id for i in lanes.matched] == ["broader", "exact-weak"]

    def test_lane_sizes_are_capped(self):
        records = {f"m{i}": make_record(f"m{i}", cohort={"ancestry": ["indian"]}) for i in range(6)}
        records |= {f"g{i}": make_record(f"g{i}") for i in range(8)}
        candidates = [passage(sid, 0.7) for sid in records]
        lanes = select_lanes(candidates, records, make_profile(), max_matched=3, max_overall=4)
        assert len(lanes.matched) == 3 and len(lanes.overall) == 4
        assert lanes.studies_found == 14

    def test_passages_without_a_checked_record_are_ignored(self):
        lanes = select_lanes([passage("ghost", 0.99)], self.records(), make_profile())
        assert lanes.items == [] and lanes.studies_found == 0

    def test_best_passages_are_quoted_in_abstract_order(self):
        candidates = [passage("big-general", 0.6, n=3), passage("big-general", 0.9, n=1)]
        lanes = select_lanes(candidates, self.records(), make_profile())
        assert lanes.overall[0].passage == "Passage 1 of big-general. … Passage 3 of big-general."
        assert lanes.overall[0].relevance == 0.9


# ── Corpus (tasks 1.2, 1.5) ───────────────────────────────────────────────


class TestCorpus:
    def test_unchecked_and_disputed_records_are_never_indexed(self, tmp_path):
        save_record(make_record("ok"), tmp_path)
        save_record(make_record("draft", checked=False), tmp_path)
        disputed = make_record("argued")
        disputed.check.status = CheckStatus.DISPUTED
        save_record(disputed, tmp_path)

        assert set(load_records(tmp_path)) == {"ok"}
        assert set(load_records(tmp_path, checked_only=False)) == {"ok", "draft", "argued"}
        assert {record.study_id for record, _ in corpus.collect_passages(tmp_path)} == {"ok"}

    def test_record_round_trips_through_yaml(self, tmp_path):
        record = make_record("rt", cohort={"ancestry": ["indian"], "age_min": 18, "age_max": 45})
        record.check.checked_on = date(2026, 11, 13)
        save_record(record, tmp_path)
        assert load_records(tmp_path)["rt"] == record

    def test_split_passages_are_verbatim_and_complete(self):
        record = make_record("s")
        passages = split_passages(record, sentences_per_passage=2)
        assert [p.passage_id for p in passages] == ["s#p1", "s#p2"]
        assert all(p.text in record.abstract for p in passages)
        assert " ".join(p.text for p in passages) == record.abstract

    def test_clean_abstract_keeps_section_headings_apart(self):
        raw = "<h4>Background</h4>Lactobacilli matter.<h4>Methods</h4>We sampled <i>40</i> women &amp; more."
        assert corpus.clean_abstract(raw) == (
            "Background: Lactobacilli matter. Methods: We sampled 40 women & more."
        )

    def test_short_authors(self):
        assert corpus.short_authors("Ravel J, Gajer P, Abdo Z.") == "Ravel et al."
        assert corpus.short_authors("Fiscella K, Klebanoff MA.") == "Fiscella and Klebanoff"
        assert corpus.short_authors("Das Purkayastha S.") == "Das Purkayastha"

    def test_vocabulary_errors_are_reported(self):
        record = make_record("s", cohort={"ancestry": ["martian"], "pregnancy": ["maybe"]})
        assert len(record.vocabulary_errors()) == 2

    def test_shipped_corpus_is_checked_and_citable(self):
        everything = load_records(checked_only=False)
        checked = load_records()
        assert len(checked) >= 8
        assert set(everything) == set(checked), "every shipped record must have passed the check"
        for record in checked.values():
            assert record.pmid or record.doi
            assert record.url.startswith("https://")
            assert record.abstract and record.check.checked_by
            assert record.vocabulary_errors() == []

    @pytest.mark.parametrize("persona_id", ["priya", "anna", "amara"])
    def test_shipped_corpus_covers_each_persona(self, persona_id):
        persona = load_persona(persona_id)
        matched = [r for r in load_records().values() if match_cohort(persona, r).qualifies]
        assert len(matched) >= 2


# ── Reference ranges (task 1.7) ───────────────────────────────────────────


class TestReferenceRanges:
    def test_every_quote_is_verbatim_from_a_checked_study(self):
        records = load_records()
        rows = load_reference_ranges()
        assert rows
        for row in rows:
            assert row.study_id in records, f"{row.id}: study not in checked corpus"
            assert row.quote in records[row.study_id].abstract, f"{row.id}: quote not found in study text"

    def test_lookup_for_premenopausal_profile(self):
        items = lookup_reference_ranges(load_persona("priya"), load_records())
        ids = {i.id for i in items}
        assert "range:premenopausal-typical" in ids
        assert "range:postmenopausal-typical" not in ids
        assert all(i.group == "reference_range" and i.passage and i.statement for i in items)

    def test_lookup_for_postmenopausal_profile(self):
        profile = make_profile(age=56, ancestry="white_european", menopausal_status="postmenopausal")
        ids = {i.id for i in lookup_reference_ranges(profile, load_records())}
        assert ids == {"range:postmenopausal-typical", "range:postmenopausal-average"}

    def test_lookup_for_pregnant_profile(self):
        ids = {i.id for i in lookup_reference_ranges(load_persona("amara"), load_records())}
        assert {"range:pregnant-threshold", "range:pregnant-by-race"} <= ids
        assert "range:premenopausal-typical" not in ids

    def test_range_without_a_checked_study_is_dropped(self):
        assert lookup_reference_ranges(load_persona("priya"), records={}) == []


class TestQueries:
    def test_profile_is_not_pasted_into_queries(self):
        reading = TestReading(ph=4.8, confidence=0.9, taken_at="2026-11-13T08:00:00")
        queries = reading_queries(make_profile(), reading)
        assert queries and not any("indian" in q.lower() or "germany" in q.lower() for q in queries)
        assert any("elevated" in q for q in queries)

    def test_queries_follow_menopausal_status(self):
        reading = TestReading(ph=6.0, confidence=0.9, taken_at="2026-11-13T08:00:00")
        profile = make_profile(menopausal_status="postmenopausal", age=56)
        assert "menopause" in reading_queries(profile, reading)[0]


# ── Citation check (task 1.13) ────────────────────────────────────────────


class TestCitationCheck:
    def marker_map(self):
        return {
            "S1": make_item("a", "study-1", "overall", "Passage A."),
            "S2": make_item("b", "study-2", "matched", "Passage B."),
            "S3": make_item("c", "study-1", "reference_range", "Passage C."),
        }

    def test_unknown_markers_are_removed(self):
        result = check_citations("Fine [S1]. Invented [S9]. Mixed [S2, S8].", self.marker_map())
        assert result.text == "Fine [1]. Invented. Mixed [2]."
        assert result.removed == ["S9", "S8"]
        assert [c.number for c in result.citations] == [1, 2]

    def test_numbers_follow_first_appearance(self):
        result = check_citations("Later source first [S2]. Then [S1]. Again [S2].", self.marker_map())
        assert result.text == "Later source first [1]. Then [2]. Again [1]."
        assert [(c.number, c.study_id) for c in result.citations] == [(1, "study-2"), (2, "study-1")]

    def test_one_number_per_study_with_all_cited_passages(self):
        result = check_citations("Range [S3]. Detail [S1].", self.marker_map())
        assert result.text == "Range [1]. Detail [1]."
        assert len(result.citations) == 1
        assert result.citations[0].passages == ["Passage C.", "Passage A."]
        assert result.citations[0].group == "reference_range"

    def test_citation_carries_honest_framing_fields(self):
        item = make_item("m", "s", "matched")
        item.sample_size, item.cohort_summary = 15, "Women in Delhi"
        item.matched_attributes, item.countries = ["Indian ancestry"], ["India"]
        citation = check_citations("Claim [S1].", {"S1": item}).citations[0]
        assert (citation.sample_size, citation.design) == (15, "Cross-sectional study")
        assert citation.matched_attributes == ["Indian ancestry"]
        assert citation.countries == ["India"] and citation.url

    def test_same_study_cited_twice_in_a_row_shows_one_number(self):
        result = check_citations("Range and detail [S3][S1]. Again [S1] [S3].", self.marker_map())
        assert result.text == "Range and detail [1]. Again [1]."

    def test_grouped_and_adjacent_markers(self):
        result = check_citations("Both [S1][S2] and [S2; S1].", self.marker_map())
        assert result.text == "Both [1][2] and [2][1]."

    def test_uncited_paragraphs_guard(self):
        long_bare = "This paragraph states several things about ranges and causes without giving any source at all."
        text = f"{long_bare}\n\nCited claim about the range [1].\n\nShort note.\n\n**Next step:** retest in a few days and watch for any new symptoms that appear."
        assert uncited_paragraphs(text) == [long_bare]
        assert uncited_paragraphs("All good here with a source for the statement being made [2].") == []

    def test_text_without_markers_has_no_citations(self):
        result = check_citations("No claims here [SAFETY_ESCALATION]", self.marker_map())
        assert result.citations == [] and "[SAFETY_ESCALATION]" in result.text


# ── Writer (task 1.12) ────────────────────────────────────────────────────


def llm_reply(text: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


def ph_state(**overrides) -> dict:
    profile = load_persona("priya")
    reading = TestReading(ph=4.8, confidence=0.92, taken_at="2026-11-13T08:14:00")
    state = {
        "messages": [], "user_input": "explain", "route": [], "route_reasoning": "",
        "final_response": "", "handoff_chain": [],
        "safety_escalation": False, "patient": profile.to_dict(),
        "patient_summary": build_profile_summary(profile, reading),
        "citations": [], "language": "en", "reading": reading.to_dict(),
        "turn_kind": "new_reading", "queries": [], "sources": {}, "retrieval_trace": [],
        "evidence_gap": {}, "safety_reasons": [],
    }
    return {**state, **overrides}


class TestWriterPrompt:
    def sources(self):
        matched = make_item("study:m", "m", "matched", "Matched text.")
        matched.matched_attributes, matched.sample_size = ["Indian ancestry"], 15
        ref = make_item("range:r", "r", "reference_range", "Range text.")
        ref.statement = "About 4.5."
        overall = make_item("study:o", "o", "overall", "Overall text.")
        return {i.id: i.model_dump() for i in (overall, matched, ref)}

    def test_markers_are_stable_and_ordered_by_group(self):
        marker_map = assign_markers(self.sources())
        assert [(k, v.group) for k, v in marker_map.items()] == [
            ("S1", "reference_range"), ("S2", "matched"), ("S3", "overall"),
        ]

    def test_prompt_describes_each_source(self):
        prompt = build_prompt(assign_markers(self.sources()), turn_kind="new_reading")
        assert "[S2] (women like you)" in prompt and "15 participants" in prompt
        assert "Matches her on: Indian ancestry" in prompt
        assert 'Text: "Matched text."' in prompt and "Summary: About 4.5." in prompt
        assert "first interpretation" in prompt

    def test_gap_low_confidence_and_language_notes(self):
        prompt = build_prompt(
            {}, evidence_gap={"no_matched_evidence": True, "unmatched_attributes": ["Indian ancestry"]},
            reading_confidence=0.55, language="de",
        )
        assert "were done in women matching her on: Indian ancestry" in prompt
        assert "this question only" in prompt and "'Sie'" in prompt
        assert "uncertain (confidence 55%)" in prompt and "retesting" in prompt
        assert "German" in prompt and "do not make medical claims" in prompt

    def test_safety_reason_leads_the_notes(self):
        prompt = build_prompt({}, safety_reasons=["Please show it to your midwife."])
        assert 'A safety rule applies: "Please show it to your midwife."' in prompt
        assert "Open your reply with this recommendation" in prompt

    def test_no_notes_when_nothing_to_flag(self):
        prompt = build_prompt(assign_markers(self.sources()), reading_confidence=0.95)
        assert "Evidence notes" not in prompt


class TestWriterAgent:
    def sources(self):
        return TestWriterPrompt().sources()

    async def test_only_gathered_sources_are_cited(self):
        reply = "Your value is a little high [S1]. A small study agrees [S2]. Also [S7]."
        with patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply(reply))):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert out["final_response"] == "Your value is a little high [1]. A small study agrees [2]. Also."
        assert [c["study_id"] for c in out["citations"]] == ["r", "m"]
        assert out["messages"][-1] == {"role": "assistant", "content": out["final_response"]}

    async def test_retries_once_when_nothing_valid_is_cited(self):
        mock = AsyncMock(side_effect=[llm_reply("No markers at all."), llm_reply("Now cited [S3].")])
        with patch("litellm.acompletion", new=mock):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert mock.await_count == 2
        assert out["final_response"] == "Now cited [1]."
        assert "Correction" in mock.await_args_list[1].kwargs["messages"][0]["content"]

    async def test_retries_once_when_a_paragraph_of_claims_is_uncited(self):
        bare = "Your value sits a little above what is usually seen in women without any symptoms at all."
        first = f"{bare}\n\nStudies agree [S1].\n\n**Next step:** retest in a few days and see whether it settles down again."
        second = f"Your value sits a little above the usual range [S1].\n\nStudies agree [S2].\n\n**Next step:** retest."
        mock = AsyncMock(side_effect=[llm_reply(first), llm_reply(second)])
        with patch("litellm.acompletion", new=mock):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert mock.await_count == 2
        assert out["final_response"].startswith("Your value sits a little above the usual range [1].")
        assert bare[:40] in mock.await_args_list[1].kwargs["messages"][0]["content"]

    async def test_keeps_first_answer_when_retry_is_no_better(self):
        bare = "Your value sits a little above what is usually seen in women without any symptoms at all."
        first = f"{bare}\n\nStudies agree [S1]."
        mock = AsyncMock(side_effect=[llm_reply(first), llm_reply(first)])
        with patch("litellm.acompletion", new=mock):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert mock.await_count == 2 and out["final_response"] == f"{bare}\n\nStudies agree [1]."

    async def test_no_retry_without_sources(self):
        mock = AsyncMock(return_value=llm_reply("I can only help with your test result."))
        with patch("litellm.acompletion", new=mock):
            out = await WriterAgent(model="test")(ph_state(sources={}))
        assert mock.await_count == 1 and out["citations"] == []

    async def test_safety_marker_sets_flag_and_is_hidden(self):
        reply = "Please see a clinician soon [S1]. [SAFETY_ESCALATION]"
        with patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply(reply))):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert out["safety_escalation"] is True
        assert "SAFETY_ESCALATION" not in out["final_response"]

    async def test_llm_failure_gives_fallback_without_citations(self):
        with patch("litellm.acompletion", new=AsyncMock(side_effect=RuntimeError("down"))):
            out = await WriterAgent(model="test")(ph_state(sources=self.sources()))
        assert "trouble processing" in out["final_response"] and out["citations"] == []


# ── Sources and graph (tasks 1.11, 1.14) ──────────────────────────────────


class FakeLibrary:
    """Stands in for the embedding search; cohort logic still runs for real."""

    def __init__(self, candidates=None, records=None):
        self.records = records if records is not None else load_records()
        self.candidates = candidates
        self.queries: list[str] = []

    def _candidates(self):
        if self.candidates is not None:
            return self.candidates
        return [passage(sid, 0.7) for sid in self.records]

    def _kind(self, guidelines: bool):
        return {
            sid: r for sid, r in self.records.items()
            if (r.design is StudyDesign.GUIDELINE) == guidelines
        }

    def retrieve(self, queries, profile) -> LaneResult:
        self.queries = queries
        return select_lanes(self._candidates(), self._kind(False), profile)

    def retrieve_guidelines(self, queries):
        self.guideline_queries = queries
        return select_guidelines(self._candidates(), self._kind(True))


class TestSourceNodes:
    async def test_reference_range_node(self):
        out = await ReferenceRangeSource(FakeLibrary())(ph_state())
        assert any(k.startswith("range:") for k in out["sources"])
        trace = out["retrieval_trace"][0]
        assert trace["source"] == "reference_ranges"
        assert trace["query"] == "premenopausal, not pregnant"
        assert trace["counts"]["found"] == len(out["sources"])

    async def test_study_library_node_uses_reading_queries(self):
        library = FakeLibrary()
        out = await StudyLibrarySource(library)(ph_state())
        assert len(library.queries) >= 3 and "queries" not in out
        counts = out["retrieval_trace"][0]["counts"]
        assert counts["matched"] >= 2 and counts["found"] == len(library._kind(False))
        assert out["evidence_gap"] == {"no_matched_evidence": False, "unmatched_attributes": []}
        groups = {s["group"] for s in out["sources"].values()}
        assert groups == {"matched", "overall"}

    async def test_study_library_node_prefers_planned_queries(self):
        library = FakeLibrary()
        await StudyLibrarySource(library)(ph_state(queries=["vaginal pH after sex"]))
        assert library.queries == ["vaginal pH after sex"]

    async def test_study_library_node_uses_question_on_follow_up(self):
        library = FakeLibrary()
        state = ph_state(turn_kind="question", user_input="Could my period affect this?")
        await StudyLibrarySource(library)(state)
        assert library.queries == ["Could my period affect this?"]

    async def test_study_library_node_reports_gap(self):
        library = FakeLibrary(records={"g": make_record("g")})
        out = await StudyLibrarySource(library)(ph_state())
        assert out["evidence_gap"]["no_matched_evidence"] is True
        assert out["evidence_gap"]["unmatched_attributes"] == ["Indian ancestry"]

    async def test_search_failure_does_not_break_the_turn(self):
        library = FakeLibrary()
        library.retrieve = MagicMock(side_effect=RuntimeError("store locked"))
        out = await StudyLibrarySource(library)(ph_state())
        assert out["retrieval_trace"][0]["error"] is True and "sources" not in out


def fake_graph(library):
    """The real graph with the embedding search replaced by a fake library."""
    return build_ph_graph(
        planner=PlannerAgent(model="test"),
        safety_rules=SafetySource(library),
        reference_ranges=ReferenceRangeSource(library),
        study_library=StudyLibrarySource(library),
        guidelines=GuidelineSource(library),
        writer=WriterAgent(model="test"),
    )


class TestPlanner:
    async def test_new_reading_needs_no_model_call(self):
        mock = AsyncMock()
        with patch("litellm.acompletion", new=mock):
            out = await PlannerAgent(model="test")(ph_state())
        assert mock.await_count == 0
        assert out["route"] == ALL_SOURCES and len(out["queries"]) >= 3

    async def test_question_plan_is_parsed(self):
        plan = '{"on_topic": true, "sources": ["guidelines"], "queries": [" vaginal discharge advice ", ""], "reasoning": "r"}'
        with patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply(plan))):
            out = await PlannerAgent(model="test")(ph_state(turn_kind="question", user_input="What do doctors advise?"))
        assert out["route"] == ["guidelines"] and out["queries"] == ["vaginal discharge advice"]

    async def test_off_topic_gives_empty_route(self):
        plan = '{"on_topic": false, "sources": ["study_library"], "queries": ["x"], "reasoning": "r"}'
        with patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply(plan))):
            out = await PlannerAgent(model="test")(ph_state(turn_kind="question", user_input="laptops?"))
        assert out["route"] == [] and out["queries"] == []

    async def test_unusable_output_falls_back_to_all_sources(self):
        bad = AsyncMock(side_effect=[llm_reply("not json"), llm_reply('{"sources": ["astrology"]}')])
        with patch("litellm.acompletion", new=bad):
            out = await PlannerAgent(model="test")(ph_state(turn_kind="question", user_input="Is 4.8 fine?"))
        assert bad.await_count == 2
        assert out["route"] == ALL_SOURCES and out["queries"] == ["Is 4.8 fine?"]

    async def test_at_most_three_queries(self):
        plan = '{"on_topic": true, "sources": ["study_library"], "queries": ["a b c", "d e f", "g h i", "j k l"], "reasoning": ""}'
        with patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply(plan))):
            out = await PlannerAgent(model="test")(ph_state(turn_kind="question", user_input="q"))
        assert len(out["queries"]) == 3

    def test_planned_sources_always_include_the_safety_check(self):
        assert planned_sources(["study_library"]) == ["safety_rules", "study_library"]
        assert planned_sources(["guidelines", "reference_ranges"]) == [
            "safety_rules", "reference_ranges", "guidelines",
        ]
        assert planned_sources([]) == [] and planned_sources(["nonsense"]) == []


class TestSafety:
    def reading(self, ph):
        return TestReading(ph=ph, confidence=0.9, taken_at="2026-11-13T08:14:00")

    def fired(self, profile, ph=4.8):
        return [f.rule.id for f in evaluate_safety(profile, self.reading(ph), load_records())]

    def test_pregnant_with_elevated_reading(self):
        amara = load_persona("amara")
        assert self.fired(amara, 5.0) == ["pregnant-elevated"]
        assert self.fired(amara, 4.5) == ["pregnant-elevated"]
        assert self.fired(amara, 4.1) == []

    def test_not_pregnant_elevated_reading_does_not_fire(self):
        assert self.fired(load_persona("priya"), 5.5) == []
        assert self.fired(load_persona("anna"), 6.5) == []

    def test_bleeding_after_menopause(self):
        anna = load_persona("anna").model_copy(update={"symptoms": ["light bleeding last week"]})
        assert self.fired(anna, 6.0) == ["postmenopausal-bleeding"]
        priya = load_persona("priya").model_copy(update={"symptoms": ["bleeding"]})
        assert self.fired(priya) == []

    def test_fever_or_pelvic_pain(self):
        priya = load_persona("priya").model_copy(update={"symptoms": ["Fever since yesterday"]})
        assert self.fired(priya) == ["fever-or-pelvic-pain"]

    def test_recurrent_symptoms_need_current_symptoms(self):
        history = {"history": ["recurrent bacterial vaginosis"]}
        assert self.fired(load_persona("priya").model_copy(update=history)) == []
        with_symptoms = load_persona("priya").model_copy(update={**history, "symptoms": ["odour"]})
        assert self.fired(with_symptoms) == ["recurrent-symptoms"]

    def test_pregnancy_rule_without_a_reading_does_not_fire(self):
        assert evaluate_safety(load_persona("amara"), None, load_records()) == []

    def test_rule_texts_and_quotes(self):
        records = load_records()
        for rule in load_safety_rules():
            assert rule.message and rule.message_de and rule.text("de") == rule.message_de
            if rule.study_id:
                assert rule.quote and rule.quote in records[rule.study_id].abstract, rule.id

    async def test_safety_node(self):
        amara = load_persona("amara")
        state = ph_state(patient=amara.to_dict(), reading=self.reading(5.2).to_dict(), language="de")
        out = await SafetySource(FakeLibrary())(state)
        assert out["safety_escalation"] is True
        assert out["safety_reasons"][0].startswith("Sie sind schwanger")
        assert out["retrieval_trace"][0]["counts"] == {"fired": 1}

        calm = await SafetySource(FakeLibrary())(ph_state())
        assert calm["safety_escalation"] is False and calm["safety_reasons"] == []


class TestGuidelines:
    def records(self):
        return {
            "g1": make_record("g1", design=StudyDesign.GUIDELINE),
            "g2": make_record("g2", design=StudyDesign.GUIDELINE),
            "g3": make_record("g3", design=StudyDesign.GUIDELINE),
            "study": make_record("study"),
        }

    def test_only_relevant_guidelines_best_first(self):
        candidates = [passage("g1", 0.5), passage("g2", 0.9), passage("g3", 0.1), passage("study", 0.95)]
        guidelines = {k: v for k, v in self.records().items() if k != "study"}
        items = select_guidelines(candidates, guidelines)
        assert [i.study_id for i in items] == ["g2", "g1"]
        assert all(i.group == "guideline" and i.source == "guidelines" for i in items)
        assert items[0].id == "guideline:g2"

    async def test_guidelines_are_kept_out_of_the_study_lanes(self):
        library = FakeLibrary(records=self.records())
        studies = await StudyLibrarySource(library)(ph_state())
        guides = await GuidelineSource(library)(ph_state(queries=["vaginal discharge"]))
        assert {s["study_id"] for s in studies["sources"].values()} == {"study"}
        assert {s["study_id"] for s in guides["sources"].values()} <= {"g1", "g2", "g3"}
        assert guides["retrieval_trace"][0]["counts"]["found"] == 2


class TestGraph:
    async def test_reading_in_answer_with_citations_out(self):
        library = FakeLibrary()
        captured = {}

        async def fake_llm(**kwargs):
            captured["system"] = kwargs["messages"][0]["content"]
            return llm_reply("A bit above the usual range [S1]. Seen in Indian women too [S5].")

        graph = fake_graph(library)
        with patch("litellm.acompletion", new=fake_llm):
            out = await graph.ainvoke(ph_state())

        # Plan first, every source next, the writer last, with the evidence in its prompt.
        assert out["handoff_chain"][0] == "planner" and out["handoff_chain"][-1] == "writer"
        assert set(out["handoff_chain"][1:-1]) == {
            "safety_rules", "reference_ranges", "study_library", "guidelines",
        }
        assert out["queries"] == library.queries == library.guideline_queries
        assert "(reference range)" in captured["system"] and "(women like you)" in captured["system"]
        assert "Vaginal pH: 4.8" in captured["system"]
        assert out["final_response"] == "A bit above the usual range [1]. Seen in Indian women too [2]."
        assert [c["number"] for c in out["citations"]] == [1, 2]
        assert out["citations"][1]["group"] == "matched"
        assert {t["source"] for t in out["retrieval_trace"]} == {
            "safety_rules", "reference_ranges", "study_library", "guidelines",
        }

    async def test_off_topic_question_skips_all_sources(self):
        library = FakeLibrary()
        plan = '{"on_topic": false, "sources": [], "queries": [], "reasoning": "not about the test"}'
        replies = AsyncMock(side_effect=[llm_reply(plan), llm_reply("I can only help with your test.")])
        state = ph_state(turn_kind="question", user_input="Which laptop should I buy?")
        with patch("litellm.acompletion", new=replies):
            out = await fake_graph(library).ainvoke(state)
        assert out["handoff_chain"] == ["planner", "writer"]
        assert out["sources"] == {} and out["citations"] == [] and library.queries == []

    async def test_follow_up_consults_only_planned_sources(self):
        library = FakeLibrary()
        plan = '{"on_topic": true, "sources": ["study_library"], "queries": ["vaginal pH after intercourse"], "reasoning": "r"}'
        replies = AsyncMock(side_effect=[llm_reply(plan), llm_reply("Sex can shift it [S1].")])
        state = ph_state(turn_kind="question", user_input="Could sex have changed it?")
        with patch("litellm.acompletion", new=replies):
            out = await fake_graph(library).ainvoke(state)
        assert set(out["handoff_chain"][1:-1]) == {"safety_rules", "study_library"}
        assert library.queries == ["vaginal pH after intercourse"]
        assert all(s["source"] == "study_library" for s in out["sources"].values())

    async def test_safety_rule_reaches_the_writer(self):
        library = FakeLibrary()
        captured = {}

        async def fake_llm(**kwargs):
            captured["system"] = kwargs["messages"][0]["content"]
            return llm_reply("Please show this to your midwife [S1].")

        amara = load_persona("amara")
        reading = TestReading(ph=5.0, confidence=0.9, taken_at="2026-11-13T08:14:00")
        state = ph_state(
            patient=amara.to_dict(), reading=reading.to_dict(),
            patient_summary=build_profile_summary(amara, reading),
        )
        with patch("litellm.acompletion", new=fake_llm):
            out = await fake_graph(library).ainvoke(state)
        assert out["safety_escalation"] is True
        assert len(out["safety_reasons"]) == 1 and "pregnant" in out["safety_reasons"][0]
        assert "A safety rule applies" in captured["system"]


# ── API (task 1.15) ───────────────────────────────────────────────────────


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class TestApi:
    @pytest.fixture
    def client(self):
        from src.api import app
        return TestClient(app)

    def test_persona_endpoints(self, client):
        gallery = client.get("/api/personas").json()
        assert [p["persona_id"] for p in gallery] == ["priya", "anna", "amara"]
        assert client.get("/api/personas/priya").json()["ancestry"] == "indian"
        assert client.get("/api/personas/nobody").status_code == 404
        assert len(client.get("/api/readings").json()) >= 2

    def test_new_reading_stream(self, client):
        library = FakeLibrary()

        reading = client.get("/api/readings").json()[0]
        reply = llm_reply("Slightly high [S1]. Indian studies exist [S5].")
        with patch("src.orchestrator.graph.build_ph_graph", new=lambda: fake_graph(library)), \
             patch("litellm.acompletion", new=AsyncMock(return_value=reply)):
            resp = client.post("/api/chat", json={
                "message": "", "persona_id": "priya", "reading": reading, "turn_kind": "new_reading",
            })
        assert resp.status_code == 200
        events = parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names[0] == "routing" and names[-1] == "done"
        assert names.index("synthesizing") < names.index("response")

        assert events[0][1] == {"status": "processing"}
        routing = next(d for n, d in events if n == "routing" and "agents" in d)
        assert routing["agents"] == ["safety_rules", "reference_ranges", "study_library", "guidelines"]
        assert len(routing["queries"]) >= 3
        done = {d["agent"]: d["detail"] for n, d in events if n == "specialist" and d["status"] == "done"}
        assert set(done) == set(routing["agents"])
        assert done["safety_rules"]["counts"] == {"fired": 0}
        assert done["study_library"]["counts"]["matched"] >= 2

        response = next(d for n, d in events if n == "response")
        assert response["content"] == "Slightly high [1]. Indian studies exist [2]."
        assert [c["number"] for c in response["citations"]] == [1, 2]
        assert response["citations"][1]["matched_attributes"]
        assert response["safety_escalation"] is False and response["safety_reasons"] == []

    def test_pregnant_persona_gets_the_safety_notice(self, client):
        library = FakeLibrary()
        reading = {"ph": 5.0, "confidence": 0.9, "taken_at": "2026-11-13T08:14:00"}
        with patch("src.orchestrator.graph.build_ph_graph", new=lambda: fake_graph(library)), \
             patch("litellm.acompletion", new=AsyncMock(return_value=llm_reply("Please see your midwife [S1]."))):
            resp = client.post("/api/chat", json={
                "message": "", "persona_id": "amara", "reading": reading, "turn_kind": "new_reading",
            })
        response = next(d for n, d in parse_sse(resp.text) if n == "response")
        assert response["safety_escalation"] is True
        assert len(response["safety_reasons"]) == 1

    def test_unknown_persona_and_bad_reading(self, client):
        assert client.post("/api/chat", json={"message": "hi", "persona_id": "nobody"}).status_code == 404
        bad = client.post("/api/chat", json={
            "message": "", "persona_id": "priya", "reading": {"ph": 40}, "turn_kind": "new_reading",
        })
        assert bad.status_code == 422


# ── Full text, sentence links and the reader page ─────────────────────────

from src.data.profile import askable_topics  # noqa: E402
from src.knowledge_pipeline.fulltext import FullText, Section, load_fulltext, parse_jats  # noqa: E402
from src.knowledge_pipeline.study_schemas import all_passages, fulltext_passages  # noqa: E402
from src.reader import render_paper  # noqa: E402
from src.sources.deeplinks import document_text, make_anchors, pmc_url, pubmed_url, quote_links  # noqa: E402

JATS = """<article><front/><body>
<p>A loose opening paragraph without any section heading at all.</p>
<sec><title>Introduction</title><p>Earlier work by others found many things [<xref>1</xref>].</p></sec>
<sec><title>Materials and Methods</title><p>We sampled women. <table-wrap><table><tr><td>cell</td></tr></table></table-wrap></p></sec>
<sec><title>Results</title><p>Overall findings were clear.</p>
  <sec><title>Vaginal pH</title><p>The mean pH was <italic>4.2</italic> in the first group. It was 5.0 in the second group of women.</p></sec>
</sec>
<sec><title>Funding Statement</title><p>Paid for by a grant.</p></sec>
<sec sec-type="ref-list"><title>References</title><sec><p>1. Someone.</p></sec></sec>
</body></article>"""


class TestFullText:
    def test_sections_are_parsed_and_classified(self):
        ft = parse_jats(JATS, "s", "PMC1")
        assert [(s.title, s.kind) for s in ft.sections] == [
            ("Text", "results"), ("Introduction", "introduction"),
            ("Materials and Methods", "methods"), ("Results", "results"), ("Vaginal pH", "results"),
        ]
        assert ft.sections[-1].paragraphs == [
            "The mean pH was 4.2 in the first group. It was 5.0 in the second group of women."
        ]
        assert ft.sections[2].paragraphs == ["We sampled women."]  # the table is left out

    def test_only_findings_sections_become_passages(self):
        record = make_record("s")
        passages = fulltext_passages(record, parse_jats(JATS, "s", "PMC1"))
        assert {p.section for p in passages} == {"Text", "Vaginal pH"}  # short "Results" paragraph dropped
        assert all(p.source == "fulltext" and p.passage_id.startswith("s#f") for p in passages)
        assert not any("Earlier work" in p.text or "sampled" in p.text for p in passages)

    def test_sentences_that_cite_other_work_are_not_citable(self):
        ft = FullText(study_id="s", pmcid="PMC1", sections=[Section(title="Discussion", kind="discussion", paragraphs=[
            "A low vaginal pH is maintained by lactobacilli in healthy women of reproductive age [8]. Others agree.",
            "Earlier reports found the same pattern in a much larger group (Smith et al., 2010). So did we.",
            "In our study the mean pH was clearly higher in the second group of women. This held after adjustment.",
        ])])
        passages = fulltext_passages(make_record("s"), ft)
        assert [p.text for p in passages] == [
            "In our study the mean pH was clearly higher in the second group of women. This held after adjustment."
        ]

    def test_passages_are_exact_substrings_even_with_unusual_spaces(self):
        paragraph = ("In fact, as Fig.\u00a01 shows, most measurements stabilized within minutes. "
                     "The second sentence follows after it.\u2009A third and longer sentence ends the paragraph right here.")
        ft = FullText(study_id="s", pmcid="PMC1", sections=[Section(title="Results", kind="results", paragraphs=[paragraph])])
        passages = fulltext_passages(make_record("s"), ft)
        assert len(passages) == 2 and all(p.text in paragraph for p in passages)
        assert passages[0].text.startswith("In fact, as Fig.\u00a01 shows")  # no split after "Fig."

    def test_reviews_without_results_sections_use_their_body(self):
        ft = FullText(study_id="s", pmcid="PMC1", sections=[
            Section(title="pH and the vaginal ecosystem", kind="other",
                    paragraphs=["This review section says several useful things about vaginal pH values."]),
        ])
        assert len(fulltext_passages(make_record("s"), ft)) == 1

    def test_shipped_full_texts_belong_to_open_access_records(self):
        records = load_records()
        with_text = [r for r in records.values() if load_fulltext(r.study_id)]
        official = [r for r in with_text if load_fulltext(r.study_id).source == "europepmc"]
        assert len(official) >= 20
        assert all(r.pmcid and r.open_access for r in official)
        r = with_text[0]
        ids = [p.passage_id for p in all_passages(r)]
        assert len(ids) == len(set(ids)) and any("#f" in i for i in ids) and any("#p" in i for i in ids)


class TestSentenceLinks:
    DOC = ("Title of the paper. Methods: We sampled forty women in two clinics. Results: The mean vaginal pH "
           "was 4.2 ± 0.3 in the first group. The mean vaginal pH was 5.0 in the second group (n = 20). "
           "Conclusion: Group differences were large.")

    def test_anchors_are_unique_whole_words(self):
        start, end = make_anchors("The mean vaginal pH was 5.0 in the second group (n = 20).", self.DOC)
        assert self.DOC.count(start) == 1 and start.startswith("The mean vaginal pH was 5.0")
        assert end[0].isalnum() and end[-1].isalnum() and end.endswith("20")

    def test_abstract_heading_is_never_part_of_an_anchor(self):
        start, end = make_anchors(
            "Methods: We sampled forty women in two clinics. Results: The mean vaginal pH was 4.2 ± 0.3 in the first group.",
            self.DOC,
        )
        assert start.startswith("We sampled forty women") and "Results" not in end and "Methods" not in start

    def test_symbols_are_avoided_when_a_plain_anchor_exists(self):
        start, end = make_anchors("Results: The mean vaginal pH was 4.2 ± 0.3 in the first group.", self.DOC)
        assert end.isascii() and end.endswith("first group")

    def test_text_that_is_not_in_the_document_gets_no_anchor(self):
        assert make_anchors("This sentence does not occur anywhere in the paper.", self.DOC) is None
        assert make_anchors("Too short.", self.DOC) is None

    def test_pmc_link_only_for_papers_on_pmc(self):
        text = "First sentence about pH. Second sentence about bacteria."
        on_pmc = make_record("a", pmcid="PMC42")
        url = pmc_url(on_pmc, text)
        assert url.startswith("https://pmc.ncbi.nlm.nih.gov/articles/PMC42/#:~:text=First%20sentence")
        assert "-" not in url.split("#:~:text=")[1]  # dashes are syntax and must be escaped
        assert pmc_url(make_record("b"), text) is None

    def test_every_quote_can_be_opened_somewhere(self):
        record = make_record("c")
        links = quote_links(record, "Second sentence about bacteria. Third one.")
        assert links["pmc_url"] is None and links["pubmed_url"] is None  # no PubMed id either
        assert links["reader_url"].startswith("/paper/c?hl=Second%20sentence")

    def test_abstract_quotes_open_on_pubmed_when_the_paper_is_not_on_pmc(self):
        record = make_record("d", pmid="12345")
        links = quote_links(record, "First sentence about pH. Second sentence about bacteria.")
        assert links["pmc_url"] is None
        assert links["pubmed_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/12345/#:~:text=First%20sentence")
        assert quote_links(record, "A sentence from the full text only.")["pubmed_url"] is None

    def test_every_shipped_abstract_passage_has_an_outside_link(self):
        missing = [
            p.passage_id
            for r in load_records().values() for p in split_passages(r)
            if not (pubmed_url(r, p.text) or pmc_url(r, p.text, load_fulltext(r.study_id)))
        ]
        assert len(missing) <= 5, missing

    def test_most_shipped_passages_on_pmc_get_a_link(self):
        records = load_records()
        total = linked = 0
        for record in records.values():
            if not record.pmcid:
                continue
            fulltext = load_fulltext(record.study_id)
            document = document_text(record, fulltext)
            from_pdf = fulltext is not None and fulltext.source == "pdf"
            for p in all_passages(record):
                if from_pdf and p.source == "fulltext":
                    continue  # body text taken from a PDF opens in the PDF viewer instead
                total += 1
                linked += make_anchors(p.text, document) is not None
        assert total > 800 and linked / total > 0.9

    def test_lane_items_carry_quotes_with_links(self):
        records = {"s": make_record("s", pmcid="PMC7", cohort={"ancestry": ["indian"]})}
        candidate = ScoredPassage(passage_id="s#p1", study_id="s", relevance=0.8, section="Abstract",
                                  text="First sentence about pH. Second sentence about bacteria.")
        item = select_lanes([candidate], records, make_profile()).matched[0]
        assert item.quotes[0]["text"] == candidate.text
        assert item.quotes[0]["pmc_url"].startswith("https://pmc.ncbi.nlm.nih.gov/articles/PMC7/")
        citation = check_citations("Claim [S1].", {"S1": item}).citations[0]
        assert citation.quotes == item.quotes


class TestReader:
    def test_highlights_the_passage_in_the_abstract(self):
        page = render_paper(make_record("s"), None, "Second sentence about bacteria.")
        assert '<mark id="cited">Second sentence about bacteria.</mark>' in page
        assert "the abstract of this paper" in page and "could not be located" not in page

    def test_highlights_a_passage_in_the_full_text_once(self):
        ft = parse_jats(JATS, "s", "PMC1")
        page = render_paper(make_record("s", pmcid="PMC1"), ft, "It was 5.0 in the second group of women.")
        assert page.count('<mark id="cited">') == 1
        assert "<h2>Vaginal pH</h2>" in page and "<h2>Materials and Methods</h2>" in page
        assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/" in page

    def test_unknown_passage_is_reported_and_text_is_escaped(self):
        record = make_record("s", title="pH <script>alert(1)</script>")
        page = render_paper(record, None, "Not in the text at all.")
        assert "could not be located" in page and "<mark" not in page
        assert "<script>alert(1)</script>" not in page

    def test_reader_endpoint(self):
        from src.api import app
        client = TestClient(app)
        record = next(iter(load_records().values()))
        first = split_passages(record)[0].text
        ok = client.get(f"/paper/{record.study_id}", params={"hl": first})
        assert ok.status_code == 200 and '<mark id="cited">' in ok.text
        assert client.get("/paper/pmid-0").status_code == 404


class TestLinkCheckPage:
    def test_lists_sample_links_for_every_paper_on_pmc(self):
        from src.api import app
        from src.sources.deeplinks import sample_links

        page = TestClient(app).get("/check")
        assert page.status_code == 200
        records = list(load_records().values())
        assert all(r.pmcid in page.text for r in records if r.pmcid)
        assert all(f"PubMed {r.pmid}" in page.text for r in records if not r.pmcid)
        assert page.text.count('class="check-row"') == sum(len(sample_links(r)) for r in records)

    def test_samples_are_spread_through_the_paper(self):
        from src.sources.deeplinks import sample_links

        record = next(r for r in load_records().values() if load_fulltext(r.study_id))
        links = sample_links(record)
        assert len(links) == 3 and len({l["passage_id"] for l in links}) == 3
        assert links[0]["section"] == "Abstract" and links[-1]["section"] != "Abstract"
        assert all(l["url"].startswith("https://pmc.ncbi.nlm.nih.gov/") and l["where"] == "PubMed Central" for l in links)


class TestPdfViewer:
    def test_pdf_link_only_when_a_pdf_is_stored(self, tmp_path, monkeypatch):
        from src.sources import deeplinks

        monkeypatch.setattr(deeplinks, "PDF_DIR", tmp_path)
        record = make_record("with-pdf")
        assert deeplinks.pdf_url(record, "Some passage.") is None
        (tmp_path / "with-pdf.pdf").write_bytes(b"%PDF-1.4")
        assert deeplinks.pdf_url(record, "Some  passage.") == "/pdf/with-pdf?hl=Some%20passage."
        assert deeplinks.quote_links(record, "Second sentence about bacteria.")["pdf_url"].startswith("/pdf/with-pdf")

    def test_viewer_and_file_endpoints(self, tmp_path, monkeypatch):
        from src.api import app
        from src.sources import deeplinks

        monkeypatch.setattr(deeplinks, "PDF_DIR", tmp_path)
        client = TestClient(app)
        study_id = next(iter(load_records()))
        assert client.get(f"/pdf/{study_id}").status_code == 404
        assert client.get(f"/pdf-file/{study_id}").status_code == 404
        (tmp_path / f"{study_id}.pdf").write_bytes(b"%PDF-1.4 test")
        page = client.get(f"/pdf/{study_id}", params={"hl": 'A "quoted" </script> passage'})
        assert page.status_code == 200 and "pdfviewer.js" in page.text
        assert "</script> passage" not in page.text  # the passage cannot break out of the script
        served = client.get(f"/pdf-file/{study_id}")
        assert served.status_code == 200 and served.headers["content-type"] == "application/pdf"
        assert client.get("/pdf-file/..%2F..%2Fsecret").status_code == 404


class TestAskableTopics:
    def test_no_period_question_for_pregnant_or_postmenopausal_women(self):
        assert any("period" in t for t in askable_topics(load_persona("priya")))
        assert not any("period" in t for t in askable_topics(load_persona("amara")))
        assert not any("period" in t for t in askable_topics(load_persona("anna")))

    def test_symptoms_are_not_asked_about_when_already_known(self):
        priya = load_persona("priya").model_copy(update={"symptoms": ["itching"]})
        assert not any("symptoms" in t for t in askable_topics(priya))

    def test_topics_reach_the_writer_prompt(self):
        prompt = build_prompt({}, askable=askable_topics(load_persona("amara")))
        assert "You may ask about: sex in the last day or two" in prompt and "period" not in prompt.split("You may ask about")[1]


# ── Text extracted from PDFs ──────────────────────────────────────────────

from src.knowledge_pipeline.pdftext import build_sections, drop_page_furniture, looks_like_prose, to_lines  # noqa: E402


def pdf_line(text, y, x=50, size=10.0, font="body", eol=True):
    return {"s": text, "x": x, "y": y, "h": size, "w": len(text) * 5.0, "eol": eol, "f": "", "n": font}


def pdf_page(*items):
    return {"width": 600, "height": 800, "items": list(items)}


class TestPdfText:
    def body(self):
        return [
            pdf_line("Journal of Things 2016", 780, size=8.0),
            pdf_line("Introduction", 700, size=12.0, font="bold"),
            pdf_line("Earlier studies looked at vaginal pH in many different groups of", 680),
            pdf_line("women and reported values that varied quite a lot between them.", 668),
            pdf_line("Results", 620, size=12.0, font="bold"),
            pdf_line("The mean vaginal pH was 4.2 in the first group and it was clearly", 600),
            pdf_line("higher in the second group of women who took part in the study.", 588),
            pdf_line("Figure 1. Distribution of pH values in both groups of women.", 540),
            pdf_line("Open circles show the first group and squares the second one.", 528),
            pdf_line("In the multi-", 480, x=60),
            pdf_line("variable model the difference between the two groups remained.", 468),
            pdf_line("References", 420, size=12.0, font="bold"),
            pdf_line("1. Smith AB, Jones C. A paper about something else entirely. J Things 2001; 12(3):45-50.", 400),
        ]

    def sections(self):
        pages = [pdf_page(*self.body()), pdf_page(pdf_line("Journal of Things 2016", 780, size=8.0)),
                 pdf_page(pdf_line("Journal of Things 2016", 780, size=8.0))]
        return build_sections(drop_page_furniture(to_lines(pages), pages))

    def test_sections_headings_and_paragraphs(self):
        sections = self.sections()
        assert [(s.title, s.kind) for s in sections] == [("Introduction", "introduction"), ("Results", "results")]
        assert sections[1].paragraphs[0].startswith("The mean vaginal pH was 4.2 in the first group")

    def test_running_headers_captions_and_references_are_left_out(self):
        text = " ".join(p for s in self.sections() for p in s.paragraphs)
        assert "Journal of Things" not in text
        assert "Figure 1" not in text and "Open circles" not in text
        assert "Smith AB" not in text

    def test_words_split_at_line_ends_are_rejoined(self):
        assert "In the multivariable model the difference" in self.sections()[1].paragraphs[1]

    def test_fragments_on_one_line_are_joined(self):
        page = pdf_page(pdf_line("The mean ", 600, eol=False), pdf_line("pH was 4.2.", 600, x=95))
        assert [l.text for l in to_lines([page])] == ["The mean pH was 4.2."]

    def test_prose_filter(self):
        assert looks_like_prose("The mean vaginal pH was clearly higher in the second group of women.")
        assert not looks_like_prose("BV 12 (3.4) 45 (12.9) 0.01 TV 3 (0.9) 9 (2.6) 0.08 CT 4 (1.1) 7 (2.0)")
        assert not looks_like_prose("Smith AB, Jones C, Brown DE, Miller FG, Davis HI, Wilson JK, Moore LM")
        assert not looks_like_prose("Too short to count.")

    def test_pdf_text_is_not_used_for_links_into_web_pages(self):
        record = make_record("s", pmcid="PMC9")
        ft = FullText(study_id="s", source="pdf", sections=[Section(title="Results", kind="results", paragraphs=[
            "In our study the mean pH was clearly higher in the second group of women than in the first."])])
        text = ft.sections[0].paragraphs[0]
        assert pmc_url(record, text, ft) is None  # may differ from the page; the PDF viewer shows it instead
        assert pmc_url(record, "First sentence about pH. Second sentence about bacteria.", ft) is not None
        assert '<mark id="cited">' in render_paper(record, ft, text) and "extracted from the PDF" in render_paper(record, ft, text)
