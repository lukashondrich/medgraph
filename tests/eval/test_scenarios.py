"""Acceptance scenarios A1-A8 from docs/specs/ph-companion/01-requirements.md.

Each test runs a real turn. Structural expectations are checked directly;
expectations about wording are checked by a model acting as judge.
"""

from __future__ import annotations

from src.data.personas import load_persona
from src.knowledge_pipeline.fulltext import load_fulltext
from src.knowledge_pipeline.study_schemas import load_records
from src.sources.deeplinks import document_text, normalize

from .conftest import cited_numbers, judge, run_turn


def matched(state: dict) -> list[dict]:
    return [c for c in state["citations"] if c["group"] == "matched"]


async def test_a1_indian_persona_gets_a_matched_indian_study():
    state = await run_turn("priya", ph=4.8)
    indian = [c for c in matched(state) if "Indian ancestry" in c["matched_attributes"]]
    assert indian, "no study in Indian women was cited in the matched group"
    for c in indian:
        assert c["design"] and c["passages"] and c["url"].startswith("https://")
    ok, why = await judge(
        state["final_response"],
        "The answer explicitly mentions findings from studies in Indian women or women of Indian ancestry.",
    )
    assert ok, why


async def test_a2_postmenopausal_persona_gets_her_own_reference_range():
    state = await run_turn("anna", ph=4.8)
    ranges = [s for s in state["sources"].values() if s["group"] == "reference_range"]
    assert ranges and all(s["id"].startswith("range:postmenopausal") for s in ranges)
    assert not any("Indian ancestry" in c["matched_attributes"] for c in state["citations"])
    assert all("postmenopausal" in c["matched_attributes"] for c in matched(state))
    ok, why = await judge(
        state["final_response"],
        "The answer interprets the reading against values expected after menopause, not against the range for women before menopause.",
    )
    assert ok, why


async def test_a3_pregnant_persona_is_sent_to_a_clinician():
    state = await run_turn("amara", ph=5.0)
    assert state["safety_escalation"] is True and state["safety_reasons"]
    ok, why = await judge(
        state["final_response"],
        "The answer tells her, at or near the start, to show the result to a midwife, doctor or other clinician.",
    )
    assert ok, why
    ok, why = await judge(
        state["final_response"],
        "The answer does NOT state as an established fact that she has an infection or any specific condition.",
    )
    assert ok, why


async def test_a4_missing_matched_evidence_is_stated():
    # No study in the corpus was run in women of this ancestry.
    profile = load_persona("priya").model_copy(update={"id": "gap", "ancestry": "pacific_islander"})
    state = await run_turn(profile, ph=4.8)
    assert state["evidence_gap"]["no_matched_evidence"] is True
    assert matched(state) == []
    ok, why = await judge(
        state["final_response"],
        "The answer tells her that the library it draws on has no studies in women of her ancestry.",
    )
    assert ok, why


async def test_a5_every_citation_resolves_and_claims_are_cited():
    records = load_records()
    for persona in ("priya", "anna", "amara"):
        state = await run_turn(persona, ph=4.8 if persona != "amara" else 5.0)
        numbers = {c["number"] for c in state["citations"]}
        assert numbers and cited_numbers(state["final_response"]) == numbers
        gathered = {s["study_id"] for s in state["sources"].values()}
        for c in state["citations"]:
            assert c["study_id"] in records and c["study_id"] in gathered
            held = document_text(records[c["study_id"]], load_fulltext(c["study_id"]))
            assert c["quotes"], "citation has no quotes"
            for quote in c["quotes"]:
                assert normalize(quote["text"]) in held, "quoted passage is not verbatim"
                assert quote["reader_url"].startswith(f"/paper/{c['study_id']}?hl=")
                if quote["pmc_url"]:
                    assert records[c["study_id"]].pmcid in quote["pmc_url"]
        ok, why = await judge(
            state["final_response"],
            "Ignoring mentions of her own reading and ignoring the final next-step paragraph: every "
            "paragraph that states a pH range, a threshold or a study finding contains at least one "
            "citation number in square brackets.",
        )
        assert ok, f"{persona}: {why}"


async def test_a6_uncertain_reading_is_flagged():
    state = await run_turn("priya", ph=5.3, confidence=0.55)
    ok, why = await judge(
        state["final_response"],
        "The answer says the strip reading was uncertain or unclear and suggests testing again.",
    )
    assert ok, why


async def test_a7_off_topic_question_is_declined():
    state = await run_turn("priya", ph=4.8, question="Which laptop should I buy for programming?")
    assert state["route"] == [] and state["sources"] == {} and state["citations"] == []
    ok, why = await judge(
        state["final_response"],
        "The answer gives no laptop or shopping advice and makes clear that it only helps with "
        "vaginal health or her test.",
    )
    assert ok, why


async def test_a8_disagreeing_evidence_is_shown_as_disagreement():
    question = "Does testing my vaginal pH at home during pregnancy actually help prevent preterm birth?"
    state = await run_turn("amara", ph=4.1, question=question)
    gathered = {s["study_id"] for s in state["sources"].values()}
    cited = {c["study_id"] for c in state["citations"]}
    # A German programme report says screening prevented preterm births; a
    # later, much larger German controlled trial did not show a benefit.
    assert {"pmid-21373274", "pmid-21051849"} <= gathered, "retrieval missed one side of the disagreement"
    assert {"pmid-21373274", "pmid-21051849"} <= cited, "one side of the disagreement was left out of the answer"
    ok, why = await judge(
        state["final_response"],
        "The answer reports one finding of a benefit from pH screening or self-testing and another "
        "finding of no demonstrated benefit, and makes clear that these point in different directions.",
    )
    assert ok, why
