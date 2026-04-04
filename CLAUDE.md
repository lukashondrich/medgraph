# Claude Context: medgraph

**Last Updated:** 2026-04-04

---

## Project Overview

**medgraph** — a patient-aware multiagent healthcare orchestration system built with LangGraph. A router agent classifies patient queries, delegates to 1-5 specialist agents in parallel, and a synthesizer merges their outputs into personalized, evidence-cited responses.

Tells two stories:
- **Demo:** Patient-aware health navigator. Load a patient, ask questions, get personalized evidence-cited answers.
- **Framework:** Reusable multi-agent architecture for high-stakes domains. Healthcare as reference implementation.

### Architecture

```
Patient Selection (gallery of 5 FHIR patients)
        |
  [Load FHIR Profile → PatientProfile → patient_summary]
        |
User message ──> [MedGraphState with patient context]
        |
     [Router] — selects 1-5 specialists
        |
   ┌────┬──────┬──────┬──────┐
   v    v      v      v      v
[Sym] [Med] [Life] [Evid] [Drug]
   |    |      |      |      |
   └────┴──────┴──────┴──────┘
        |
   [Synthesizer] — merges + citations
        |
   Final response (SSE)
```

### Tech Stack

- **Orchestration:** LangGraph (StateGraph, conditional edges, Send for fan-out)
- **LLM calls:** litellm `acompletion()` with Gemini / OpenAI (env-configurable, with fallback chain)
- **Patient data:** FHIR R4 parsing (Synthea bundles → Pydantic models)
- **Evidence:** Qdrant vector store + Haystack retrieval pipeline
- **Drug interactions:** OpenFDA label + FAERS screening
- **Models:** Pydantic (structured output) + TypedDict with Annotated reducers (state)
- **Web app:** FastAPI + vanilla HTML/CSS/JS with Server-Sent Events
- **Testing:** pytest + pytest-asyncio

### Components

| Component | Location |
|-----------|----------|
| State model (MedGraphState) | `src/models/state.py` |
| Patient data layer (FHIR, schemas, gallery) | `src/data/` |
| OpenFDA drug interaction tools | `src/data/openfda/` |
| Knowledge pipeline (Qdrant + Haystack) | `src/knowledge_pipeline/` |
| Agents (router, 3 specialists, evidence, drug_check, synthesizer) | `src/agents/` |
| Prompts (7 agents) | `src/prompts/` |
| Orchestrator (LangGraph graph) | `src/orchestrator/` |
| Config (env, model fallback) | `src/config.py` |
| Web app (FastAPI + SSE) | `src/api.py` + `src/static/` |
| CLI | `src/main.py` |
| Unit tests | `tests/` |
| Evaluation framework | `tests/eval/` |

---

## New Here? Start Here

**Reading order:**

1. **This file** (CLAUDE.md) — current state, quick overview
2. **`docs/system-overview.md`** — visual architecture with Mermaid diagrams
3. **`README.md`** — setup, demo scenarios, architecture
4. **Then based on your task:**
   - Agent/prompt work → `src/agents/ARCHITECTURE.md` + `src/prompts/ARCHITECTURE.md`
   - Patient data → `src/data/ARCHITECTURE.md`
   - Evidence/RAG → `src/knowledge_pipeline/ARCHITECTURE.md` + `src/agents/evidence.py`
   - Drug interactions → `src/data/ARCHITECTURE.md` (OpenFDA section) + `src/agents/drug_check.py`
   - State model → `src/models/ARCHITECTURE.md`
   - Orchestration → `src/orchestrator/ARCHITECTURE.md`
   - Frontend/UI → `src/static/ARCHITECTURE.md`
   - Evaluation → `tests/eval/ARCHITECTURE.md`

---

## Do's and Don'ts

### Do's

- Use `litellm.acompletion()` for all LLM calls (async)
- Use Pydantic models and type hints throughout
- Follow the state contract exactly (keys, types, reducers in `src/models/state.py`)
- Run `pytest tests/ -v --ignore=tests/eval` before committing

### Don'ts

- Don't commit `.env` — API keys stay local
- Don't use LangChain ChatModel wrappers — use litellm directly
- Don't let agents answer outside their domain
- Don't add fields to MedGraphState without updating `src/models/state.py` and dependent agents
- **Don't use plan mode.** Discuss plans in chat, ask the user when ready to implement. Use a markdown doc for documentation.

---

## Key Constraints

### Technical

- Python 3.10+, LangGraph, litellm, Pydantic, pytest
- LLM: Gemini or OpenAI via litellm (model auto-detected from available API keys)
- `.env` contains `GEMINI_API_KEY` and/or `OPENAI_API_KEY`
- Override model explicitly: `MEDGRAPH_MODEL=gpt-4o-mini`
- All agent nodes are async (`async def __call__` / `async def process`)
- Messages are plain dicts (OpenAI format), not LangChain message objects
- Patient awareness via base class prompt injection (no per-agent code changes needed)

### Domain

- Healthcare context — responses must be safe and empathetic
- Agents must never diagnose or prescribe
- Always recommend consulting a healthcare provider for serious concerns

---

## Quick Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run web app
uvicorn src.api:app --port 8000

# Run terminal CLI
python -m src.main

# Run unit tests
pytest tests/ -v --ignore=tests/eval

# Run evaluation (requires API key)
pytest tests/eval/ -v
```
