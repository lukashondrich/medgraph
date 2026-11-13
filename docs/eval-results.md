# Evaluation Results — pH Companion

**Date:** 2026-11-13 · **Model:** gpt-5.2 (planner, writer and judge) · **Corpus:** 63 checked records, 335 passages

## Acceptance scenarios

Two full runs of `pytest tests/eval/` after the last change:

| Scenario | Run 1 | Run 2 |
|---|---|---|
| A1 Matched Indian study for the Indian persona | pass | pass |
| A2 Postmenopausal reference range | pass | pass |
| A3 Pregnant persona sent to a clinician | pass | pass |
| A4 Missing matched evidence is stated | pass | pass |
| A5 Citations resolve; claims are cited | pass | pass |
| A6 Uncertain reading flagged | pass | pass |
| A7 Off-topic declined | pass | pass |
| A8 Disagreement named | **fail** | pass |

**A8 is not stable.** Retrieval now returns both German pregnancy studies every time, but in one of two runs the writer left the contrary report out of its answer.

Earlier runs during the work also showed A5 and A7 failing once each. A5 was a real gap (an opening sentence without a citation) and led to the paragraph-level retry in the writer. A7 and part of A5 were the judge reading a statement too literally; those statements were reworded. The judge is the same model as the writer, which is a weakness of this setup.

## Unit tests

91 passing (`pytest tests/ --ignore=tests/eval`), no network.

## Response time

Measured through the running web app, first interpretation of a reading: 5 to 6 seconds, 13 seconds on the first request after start (model loading). Follow-up questions add one planner call: about 6 seconds.

## Accessibility

axe-core, WCAG 2.0–2.2 A/AA, phone-sized viewport, answer and sources expanded: no violations in light, dark and high-contrast themes, with the citation card open and closed.

## Not evaluated

- Clinical correctness of the answers. No clinician has reviewed them.
- Correctness of the study records beyond the two model passes.
- Screen reader behaviour with a real screen reader.
