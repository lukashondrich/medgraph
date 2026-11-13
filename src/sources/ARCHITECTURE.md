# Sources Architecture

Evidence sources for pH Companion. Plain functions and classes with typed input and output. **No model calls**: everything here is deterministic and unit tested. Graph nodes in `src/agents/sources.py` wrap them.

## Files

| File | Purpose |
|---|---|
| `matching.py` | `match_cohort(profile, record)` — how closely a study cohort resembles a profile |
| `study_library.py` | `select_lanes`, `select_guidelines`, `StudyLibrary` (search over the Qdrant store) |
| `reference_ranges.py` | Lookup of expected pH statements by menopausal and pregnancy status |
| `safety.py` | Safety rule evaluation |
| `queries.py` | Fixed search queries for a new reading; fallback for questions |

## Cohort matching

| Attribute | Score | Makes a study "about women like you"? |
|---|---|---|
| Ancestry, exact | 3.0 | Yes, except white European |
| Ancestry, broader group (Indian → South Asian) | 1.5 | Yes |
| Pregnant, cohort pregnant | 2.0 | Yes |
| Postmenopausal, cohort postmenopausal | 1.0 | Yes |
| Premenopausal, cohort premenopausal | 1.0 | No — describes most cohorts |
| Age in range, not pregnant, country | 0.25–0.5 | No |

Ancestry matches wherever the study was run. A cohort described only as "Asian" is not a match for an Indian profile. White European ancestry is scored and shown but does not qualify, for the same reason premenopausal status does not.

## Two lanes

1. Passages come back from search with a cosine relevance. A study is used only if its best passage reaches `MIN_RELEVANCE` (0.30; unrelated questions peak near 0.2).
2. **Matched lane** (up to 3): qualifying studies ranked by `relevance × (1 + qualifying_score / 5)`. Study quality plays no part.
3. **Overall lane** (up to 4): the rest, ranked by `relevance × evidence_weight` (design and sample size).
4. A study appears in one lane only. If relevant studies exist but none matched, `no_matched_evidence` is set with the attributes that went unmatched.

Guidelines are excluded from both lanes and returned by `select_guidelines` (up to 2).

## Reference ranges and safety rules

Both are YAML tables in `data/corpus/`. Every reference range quotes a checked study verbatim; a test fails if the quote is not in the stored text. Safety rules fire on profile and reading only (pregnancy with pH ≥ 4.5, bleeding after menopause, fever or pelvic pain, recurring symptoms) and carry English and German messages.

## Tests

`tests/test_ph_companion.py`: `TestCohortMatch`, `TestLanes`, `TestGuidelines`, `TestReferenceRanges`, `TestSafety`, `TestQueries`.
