# Agents Architecture

Graph nodes for pH Companion. Each is an async callable that receives `MedGraphState` and returns a partial state update.

| File | Node | Model call | Reads | Writes |
|---|---|---|---|---|
| `planner.py` | `PlannerAgent` | Questions only | `turn_kind`, `user_input`, `messages`, `patient`, `reading` | `route`, `queries`, `route_reasoning` |
| `sources.py` | `SafetySource` | No | `patient`, `reading`, `language` | `safety_reasons`, `safety_escalation`, `sources`, `retrieval_trace` |
| `sources.py` | `ReferenceRangeSource` | No | `patient` | `sources`, `retrieval_trace` |
| `sources.py` | `StudyLibrarySource` | No | `patient`, `queries` | `sources`, `evidence_gap`, `retrieval_trace` |
| `sources.py` | `GuidelineSource` | No | `queries` | `sources`, `retrieval_trace` |
| `writer.py` | `WriterAgent` | Yes | everything gathered | `final_response`, `citations`, `messages`, `safety_escalation` |
| `citation_check.py` | (functions) | No | — | — |
| `base.py` | `HealthcareAgent` | — | — | Shared message building, model call with fallback |

## Planner

A new reading gets a fixed plan (all sources, queries from `src/sources/queries.py`) with no model call. A question goes to the model, which returns `{on_topic, sources, queries, reasoning}`. Unusable output is retried once, then falls back to all sources with the question as the query. Off-topic gives an empty route and the graph goes straight to the writer.

## Writer and citation check

The writer receives each gathered item under a short key (`S1`, `S2`, ...) with a one-line description (design, size, cohort, lane) and the verbatim text. It must mark every claim with a key.

`check_citations` then:

1. removes keys that were not gathered this turn,
2. renumbers the rest in reading order, one number per study,
3. builds `Citation` records carrying every cited passage,
4. collapses a number repeated back to back.

The writer retries once when evidence was available but nothing valid was cited, or when a whole paragraph of statements has no citation (`uncited_paragraphs`). This guard is coarse; sentence-level coverage is measured in `tests/eval`.

## Error handling

- Model failure in the writer: a safe fallback message, no citations.
- Search failure in a source: the step reports an error in its trace and the turn continues without that evidence.
- A profile or reading that does not validate is rejected by the API before the graph runs.

## Tests

`tests/test_ph_companion.py`: `TestPlanner`, `TestSourceNodes`, `TestWriterPrompt`, `TestWriterAgent`, `TestCitationCheck`, `TestGraph`.
