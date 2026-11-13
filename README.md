# pH Companion

A demo that explains an at-home vaginal pH test result for a specific woman. It cites real studies for every claim and deliberately surfaces studies done in women like her, even when those studies are small.

Choose a profile, choose a reading, and the same pH value is interpreted differently for a 29-year-old woman of Indian ancestry, a 56-year-old woman after menopause, and a 33-year-old pregnant Black woman.

## What it shows

- **Personalised interpretation.** The reference range, the likely explanations and the next step depend on the profile.
- **Two kinds of evidence, kept apart.** "Best overall evidence" is ranked by relevance and study quality. "Studies in women like you" is ranked by how closely the study cohort matches her, so a 40-woman study can appear next to one with 12,000.
- **Honest citations.** Each claim carries a number. Tapping it shows the study, its design and size, what matched, where it was run, the exact quoted passage and a link.
- **Stated gaps.** When no study matches her, the answer says so.
- **Deterministic safety.** A small rule table decides when to say "please see a clinician"; it is not left to the model.
- **Visible work.** The page shows which sources were consulted and what was searched, as it happens.

## How it works

```
Persona + reading
      |
   Planner            fixed plan for a new reading, model call for a question
      |
 Safety rules | Reference ranges | Study library (two lanes) | Guidelines
      |                 (no model calls)
   Writer             answers from the gathered evidence only
      |
 Citation check       removes any citation that was not retrieved
```

The corpus is 63 published papers, stored as one reviewed record per paper in `data/corpus/studies/`. Records were drafted by one model pass and checked by a second; they have not been reviewed by a clinical expert.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env with OPENAI_API_KEY or GEMINI_API_KEY
uvicorn src.api:app --port 8000        # then open http://localhost:8000
```

Terminal version: `python -m src.main --persona amara --ph 5.0`

## Tests

```bash
pytest tests/ -v --ignore=tests/eval   # unit tests, no network
pytest tests/eval/ -v                  # eight acceptance scenarios, real model calls
```

## Limits

This is a demonstration, not a medical product. The strip reading is simulated, profiles are fictional, the study records are machine-checked only, and nothing here has been through regulatory review.

More detail: `CLAUDE.md`, `docs/specs/ph-companion/`, `docs/system-overview.md`.
