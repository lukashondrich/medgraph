# Claude Context: pH Companion

**Last Updated:** 2026-11-13

---

## Project Overview

**pH Companion** — a demo that explains an at-home vaginal pH test result for a specific woman, citing real studies, including studies in women like her. Built on LangGraph as a gather-then-write system: evidence is collected first, and one writer composes the answer from that evidence only.

This branch (`ph-companion`) adapts the earlier medgraph health navigator to this domain. Specs live in `docs/specs/ph-companion/`.

### Architecture

```
Persona (3 demo profiles)  +  Reading (pH, confidence)
        |
     [Planner] — which sources, which search queries
        |          (fixed plan for a new reading; model call for a question)
   ┌────────┬────────────┬──────────────┬────────────┐
   v        v            v              v
[Safety] [Reference  [Study library  [Guidelines]     no model calls
 rules]   ranges]     two lanes]
   └────────┴────────────┴──────────────┘
        |
     [Writer] — answer from gathered evidence only
        |        + citation check (deterministic)
   Answer + citation records (SSE)
```

### Tech Stack

- **Orchestration:** LangGraph (StateGraph, conditional edges, Send for fan-out)
- **LLM calls:** litellm `acompletion()` (model from env; planner and writer only)
- **Corpus:** one YAML record per paper in `data/corpus/studies/`, drafted and checked by LLM passes
- **Search:** Qdrant embedded store + Haystack + sentence-transformers
- **Models:** Pydantic + TypedDict state with Annotated reducers
- **Web app:** FastAPI + vanilla HTML/CSS/JS with Server-Sent Events
- **Testing:** pytest + pytest-asyncio

### Components

| Component | Location |
|-----------|----------|
| State model (MedGraphState) | `src/models/state.py` |
| Evidence models (SourceItem, Citation) | `src/models/evidence.py` |
| Profiles, readings, personas | `src/data/profile.py`, `src/data/personas.py`, `src/data/personas/` |
| Study records and corpus build | `src/knowledge_pipeline/study_schemas.py`, `corpus.py` |
| Corpus data (studies, reference ranges, safety rules) | `data/corpus/` |
| Sources (matching, lanes, ranges, safety, queries) | `src/sources/` |
| Graph nodes (planner, sources, writer, citation check) | `src/agents/` |
| Prompts (planner, writer) | `src/prompts/` |
| Graph | `src/orchestrator/graph.py` |
| Web app | `src/api.py` + `src/static/` |
| CLI | `src/main.py` |
| Unit tests | `tests/test_ph_companion.py` |
| Acceptance scenarios (real model calls) | `tests/eval/` |

---

## New Here? Start Here

1. **This file**
2. **`docs/specs/ph-companion/`** — requirements, design, tasks (with status notes), corpus candidates, demo script
3. **`docs/system-overview.md`** — flow and event stream
4. Then by task:
   - Ranking, matching, ranges, safety → `src/sources/ARCHITECTURE.md`
   - Corpus and search → `src/knowledge_pipeline/ARCHITECTURE.md`
   - Graph nodes and prompts → `src/agents/ARCHITECTURE.md`, `src/prompts/ARCHITECTURE.md`
   - State → `src/models/ARCHITECTURE.md`
   - Frontend → `src/static/ARCHITECTURE.md`
   - Evaluation → `tests/eval/ARCHITECTURE.md`

---

## Do's and Don'ts

### Do's

- Use `litellm.acompletion()` for all LLM calls (async)
- Use Pydantic models and type hints throughout
- Follow the state contract exactly (`src/models/state.py`)
- Keep sources free of model calls: ranking, ranges and safety rules are deterministic and unit tested
- Rebuild the index after changing study records: `python -m src.knowledge_pipeline.corpus build`
- Run `pytest tests/ -v --ignore=tests/eval` before committing

### Don'ts

- Don't commit `.env`
- Don't use LangChain ChatModel wrappers — use litellm directly
- Don't let the writer state facts that are not in the gathered evidence
- Don't index a study record that has not passed the check (`check.status: checked`)
- Don't add fields to MedGraphState without updating `src/models/state.py` and its docs
- Don't run the corpus build, the CLI or `tests/eval` while the web app is running: the embedded store allows one process
- **Don't use plan mode.** Discuss plans in chat, ask the user when ready to implement. Use a markdown doc for documentation.

---

## Key Constraints

### Technical

- Python 3.10+, LangGraph, litellm, Pydantic, pytest
- `.env` contains `OPENAI_API_KEY` and/or `GEMINI_API_KEY`; override the model with `MEDGRAPH_MODEL`
- `CORPUS_CHECK_MODEL` selects a different model for the second check of study records
- Messages are plain dicts (OpenAI format)
- The profile and reading reach every prompt through `patient_summary` (base class injection)

### Domain

- Answers must be safe, calm and in plain language
- Never diagnose or prescribe; a home pH test cannot confirm or rule out an infection
- Ancestry selects evidence; it is never used to state an individual's risk
- Study records were checked by a model, not by a clinical expert

---

## Quick Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run web app
uvicorn src.api:app --port 8000

# One turn in the terminal
python -m src.main --persona amara --ph 5.0

# Unit tests
pytest tests/ -v --ignore=tests/eval

# Acceptance scenarios (API key needed, web app stopped)
pytest tests/eval/ -v

# Corpus: draft records, check them, rebuild the index
python -m src.knowledge_pipeline.corpus draft <pubmed ids>
python -m src.knowledge_pipeline.corpus check
python -m src.knowledge_pipeline.corpus build
```
