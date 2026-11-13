# pH Companion — Tasks

**Status:** Draft for review
**Created:** 2026-11-13
**Depends on:** [01-requirements.md](01-requirements.md), [02-design.md](02-design.md)

---

## Approach

Three milestones. The first builds a thin slice through every layer with one persona and a handful of studies, so the riskiest parts (real studies, claim-linked citations, phone layout) are proven before the corpus is filled out.

| Milestone | Outcome |
|---|---|
| **M0 — Corpus check** | We know real studies exist for each persona. Personas confirmed or adjusted. |
| **M1 — Thin slice** | One persona, about 8 verified studies, one reading: automatic interpretation with tappable citations, on a phone. |
| **M2 — Full demo** | Three personas, full corpus, follow-up questions, safety path, persona switch shows different evidence. |
| **M3 — Polish and proof** | Evaluation scenarios pass, German checked, docs updated, demo script rehearsed. |

Tasks marked **(you)** need your judgement or review; the rest I can do.

---

## M0 — Corpus check

| # | Task | Done when |
|---|---|---|
| 0.1 | Search for candidate papers per persona and topic (pH, bacterial vaginosis, microbiome, menopause, pregnancy) | A candidate list exists with identifier, design, sample size and cohort for each paper |
| 0.2 | Check coverage per persona | Each persona has at least two candidate matched studies, or the gap is written down |
| 0.3 | **(you)** Revisit the personas with the coverage in hand. A persona with little literature is kept and its gap is shown | Personas are final |
| 0.4 | Pick the guideline texts to include (no licence review, decided 2026-11-13) | A short list of guidelines with links |

M0 produces a list, not code. If a cohort turns out thin, this is where we find out, and that is a valid result for the demo.

## M1 — Thin slice

### Data and corpus

| # | Task | Done when |
|---|---|---|
| 1.1 | Add `UserProfile`, `TestReading`, `StudyRecord`, `Citation` models | Models exist with unit tests for validation |
| 1.2 | Define the study record file format and the ancestry hierarchy | One example record validates against `StudyRecord` |
| 1.3 | Write the corpus draft script: fetch title, abstract and identifiers; LLM drafts the record | Running it on an identifier produces an unverified record file |
| 1.4 | Second LLM pass checks about 8 drafted records for the first persona against their abstracts | 8 records marked checked; disagreements resolved or dropped |
| 1.5 | Write the index build: checked records → Qdrant collection with cohort and design metadata | Build is repeatable; unchecked records are refused; test covers both |
| 1.6 | Create the first persona file and two preset readings | Loadable through the data layer |
| 1.7 | Create the reference range table (rows needed for the first persona) | Lookup returns a range and its source passage; unit tested |

### Sources and graph

| # | Task | Done when |
|---|---|---|
| 1.8 | Cohort match scoring | Unit tests cover exact ancestry, broader ancestry, menopausal, pregnancy, age, and "premenopausal only does not qualify" |
| 1.9 | Two-lane study retrieval with the guards from design 4.1 | Tests: matched small study is returned; unrelated matched study is not; duplicate appears once; empty lane sets the gap flag |
| 1.10 | Update `MedGraphState` per design 5.5 | State tests updated and passing |
| 1.11 | Source nodes for reference ranges and study library, each writing `sources` and `retrieval_trace` | Node tests pass with a test store |
| 1.12 | Writer agent and prompt | Given fixed sources, output contains markers for those sources only (mocked LLM test plus one live check) |
| 1.13 | Citation check | Tests: unknown marker removed; renumbering by first appearance; records built; retry on zero valid markers |
| 1.14 | New graph for the automatic first turn (fixed route) | Graph test: reading in → answer with citation records out |

### API and interface

| # | Task | Done when |
|---|---|---|
| 1.15 | Persona and reading endpoints; chat request accepts `reading` and `turn_kind`; `response` event carries citations | API tests pass |
| 1.16 | Phone-first layout: header, persona chips, profile card, result card | Usable at 360px with no sideways page scroll; wide screen keeps the current look |
| 1.17 | Pipeline card shows source lines with query and counts; collapses when done | Visible in the browser on the first-turn flow |
| 1.18 | Inline citation numbers, tap card (bottom sheet on phone, popover on wide), "Sources (n)" list | Tapping a number shows study, design, size, match, passage and link |
| 1.19 | Run the slice end to end on a phone-sized screen and on desktop | **(you)** look at it and say what feels wrong |

### M1 status (2026-11-13)

Built and working end to end for the Indian persona: 13 checked studies (69 passages), automatic interpretation, follow-up questions, tappable citations, phone and desktop layouts. 186 unit tests pass (61 new).

How the build differs from the design:

| Design said | Built | Why |
|---|---|---|
| Citation check is its own graph step | A function the writer calls | The writer needs the result to retry once when nothing valid was cited |
| Each citation carries one passage | One number per study, with every cited passage | The same study can be cited as a reference range and as a study; two numbers for one paper read badly |
| Popover on wide screens | Centred card on wide screens, bottom sheet on a phone | Same component, no positioning logic |
| Lanes selected with Qdrant filters | Qdrant returns scored passages; lanes are chosen in Python from the study records | Simple and fully unit-tested at this corpus size |
| Second check by a different model | Same model with a separate error-hunting prompt | The Gemini key has no quota for a suitable model; `CORPUS_CHECK_MODEL` switches it when one is available |
| Matched group needs relevance | Both groups need relevance | Otherwise an unrelated question still pulled in studies |

Not done in M1, by plan: router for follow-up questions (2.6), safety rules (2.4), guidelines (2.2), removing the old agents (2.9), architecture docs (3.5), accessibility pass (3.3).

## M2 — Full demo

| # | Task | Done when |
|---|---|---|
| 2.1 | Draft and LLM-check the remaining study records (target 30–50 in total) | Corpus test passes: all indexed records checked; coverage per persona reported |
| 2.2 | Add guideline excerpts and the guidelines source | Guideline citations appear with their own label |
| 2.3 | Complete the reference range table for all three personas | Lookup tests for each persona |
| 2.4 | Safety rule table and safety source; banner in the UI | Rules unit tested; pregnant persona with elevated reading shows the banner with its citation |
| 2.5 | Remaining two personas and preset readings | Selectable in the gallery |
| 2.6 | Router for follow-up turns: picks sources, writes queries, declines off-topic | Routing tests for typical, off-topic and malformed output |
| 2.7 | Follow-up conversation with history, clarifying questions, low-confidence reading wording | Manual run of the walkthrough in requirements section 3 |
| 2.8 | Matched-citation accent and grouped source list | Persona switch with the same reading visibly changes the matched group |
| 2.9 | Remove the unused specialists, drug check and patient endpoints; update affected tests | `pytest tests/ -v --ignore=tests/eval` passes |

## M3 — Polish and proof

| # | Task | Done when |
|---|---|---|
| 3.1 | Evaluation cases for scenarios A1–A8 | All pass, results recorded in `docs/eval-results.md` |
| 3.2 | German: translation keys for all new UI text; one full run in German | No untranslated text |
| 3.3 | Accessibility pass on new components (focus, screen reader labels, contrast, dark mode) | Automated check clean; bottom sheet usable by keyboard |
| 3.4 | Response time check on the first turn | Measured and written down; token streaming considered if it feels slow |
| 3.5 | Update `CLAUDE.md`, `README.md`, and the `ARCHITECTURE.md` files for changed modules | Docs match the code |
| 3.6 | **(you, with me)** Demo script: the five-minute path, including the persona switch and one evidence gap | Rehearsed once end to end |

## Not planned

- Live literature search (design decision D2: curated corpus first).
- Medication labels from OpenFDA (design decision D4).
- Everything under non-goals in the requirements.

## Where your time goes

Most of the build I can carry. The parts that need you are M0.3 (personas) and the look-and-feel checks in 1.19 and 3.6. Study records are checked by a second LLM pass, not by you and not by a clinical expert; the demo should say so if asked.
