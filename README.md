# medgraph

A patient-aware multiagent healthcare orchestration system. Load a FHIR patient profile, ask a health question, and get personalized responses grounded in clinical evidence and drug interaction data.

## Architecture

```
Patient FHIR Bundle → PatientProfile → patient_summary (injected into all agent prompts)

User question → Router → [1-5 specialists in parallel] → Synthesizer → Response

Specialists:
  Symptom    — triage and severity assessment
  Medication — drug info, side effects, interactions
  Lifestyle  — diet, exercise, sleep, wellness
  Evidence   — RAG retrieval from clinical guidelines (Qdrant)
  Drug Check — OpenFDA label + FAERS interaction screening
```

The router classifies queries and selects 1-5 specialists. All run in parallel via LangGraph's `Send()` fan-out. The synthesizer merges outputs into a single response with inline citations.

**Patient awareness** works via a single 5-line change in the base agent class — `patient_summary` is appended to every agent's system prompt when a patient is loaded. Zero per-agent code changes required.

## Key Demo Scenario

Load patient: **Nelia Rolfson** (73F, T2DM + HTN + CKD, on Metformin + Olmesartan + Naproxen)

Ask: *"Should I take ibuprofen for my knee pain?"*

1. **Router** → `[symptom, medication, drug_check, evidence]`
2. **Symptom**: patient-aware triage (knee pain + existing conditions)
3. **Medication**: knows patient's current meds, NSAID context
4. **Drug Check**: flags NSAID + ARB renal risk → `safety_escalation = True`
5. **Evidence**: retrieves ADA/NICE guidelines on NSAIDs in CKD
6. **Synthesizer**: personalized response with inline citations + safety integration

## Quick Start

```bash
# Clone and setup
git clone <repo-url> medgraph && cd medgraph
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Add API keys
echo "GEMINI_API_KEY=your-key" > .env
# or: echo "OPENAI_API_KEY=your-key" > .env

# Run web app
uvicorn src.api:app --port 8000

# Run tests
pytest tests/ -v --ignore=tests/eval
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph (StateGraph, Send, conditional edges) |
| LLM | litellm → Gemini / OpenAI (auto-detected, with fallback) |
| Patient data | FHIR R4 Synthea bundles → Pydantic models |
| Evidence retrieval | Qdrant (embedded) + Haystack + sentence-transformers |
| Drug interactions | OpenFDA labels + FAERS adverse events |
| Web | FastAPI + SSE + vanilla JS |
| Testing | pytest + eval framework |

## Test Suite

```bash
# Run unit tests (no API key needed)
pytest tests/ -v --ignore=tests/eval

# Run evaluation (requires GEMINI_API_KEY or OPENAI_API_KEY)
pytest tests/eval/ -v
```

```
tests/
├── test_agents.py               # Agent contracts, safety escalation, retry/fallback
├── test_routing.py              # Router classification, off-topic, fallback
├── test_orchestrator.py         # Graph wiring, fan-out, safety propagation
├── test_patient_data.py         # FHIR parsing, schemas, gallery loading
├── test_state_compat.py         # Backward compatibility (HealthcareState alias)
├── test_patient_aware_agents.py # Evidence + DrugCheck agent integration
├── test_synthesizer_extended.py # Extended build_prompt with evidence/citations
├── test_graph_extended.py       # New agents in graph, full flow
├── test_api_extended.py         # Patient API endpoints
└── eval/                        # Evaluation framework (requires API key)
    ├── test_quality.py          # LLM-judged response quality
    ├── test_routing.py          # Routing accuracy on medical datasets
    ├── test_safety.py           # Safety escalation detection
    ├── test_persona.py          # Multi-turn persona conversations
    └── test_personalization.py  # Patient grounding verification
```

## Project Structure

```
src/
├── agents/          # 7 agent implementations (base, router, 3 specialists, evidence, drug_check, synthesizer)
├── data/            # Patient data layer
│   ├── schemas.py       # PatientProfile, Condition, Medication, etc.
│   ├── fhir_parser.py   # FHIR R4 Bundle → PatientProfile
│   ├── condition_maps.py # SNOMED-CT → abbreviation/ICD-10 mappings
│   ├── gallery.py       # Patient gallery for the demo
│   ├── patient_context.py # build_patient_summary() for prompt injection
│   ├── openfda/         # OpenFDA drug interaction tools (6 files)
│   └── patients/        # 5 pre-parsed FHIR patient profiles
├── knowledge_pipeline/  # Qdrant + Haystack retrieval
│   ├── schemas.py       # ChunkMetadata, ConfidenceTier, RecommendationGrade
│   ├── pipeline.py      # Haystack pipeline templates
│   └── qdrant_store/    # Pre-indexed clinical guidelines (968KB)
├── models/          # MedGraphState (TypedDict) + RouteDecision (Pydantic)
├── orchestrator/    # LangGraph graph construction
├── prompts/         # System prompts for all 7 agents
├── static/          # Frontend (HTML + CSS + JS)
├── api.py           # FastAPI backend with SSE streaming
├── config.py        # Environment config + model fallback
└── main.py          # Terminal CLI
```
