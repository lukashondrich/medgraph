# Evaluation

`test_scenarios.py` holds the eight acceptance scenarios from `docs/specs/ph-companion/01-requirements.md`. Each runs a real turn through the graph with the real study store.

| Test | Scenario |
|---|---|
| `test_a1` | Indian persona gets a matched study in Indian women |
| `test_a2` | Postmenopausal persona gets her own reference range |
| `test_a3` | Pregnant persona with an elevated reading is sent to a clinician; no diagnosis asserted |
| `test_a4` | A profile with no matching studies is told so |
| `test_a5` | Every citation resolves to a corpus record, quotes are verbatim, claims carry citations |
| `test_a6` | An uncertain strip reading is flagged |
| `test_a7` | An off-topic question is declined and nothing is looked up |
| `test_a8` | Studies that disagree are both cited and the disagreement is named |

Structural expectations (citations, groups, flags, verbatim quotes) are asserted directly. Expectations about wording are put to a model as a true/false statement (`judge()` in `conftest.py`).

Run with `pytest tests/eval/ -v`. Needs an API key and the web app stopped. Results: `docs/eval-results.md`.
