# System Overview

Visual guide to how the medgraph multiagent system works. For setup and examples, see the [README](../README.md). For per-module details, see the ARCHITECTURE.md files in each `src/` subdirectory.

---

## High-Level Architecture

```mermaid
graph TD
    User([User]) -->|message| WebApp["Web App<br/><small>FastAPI + SSE</small>"]
    User -->|message| CLI["Terminal CLI"]

    WebApp -->|initial state| Graph
    CLI -->|initial state| Graph

    subgraph Graph ["LangGraph Orchestration"]
        direction TB
        Router["Router Agent<br/><small>Intent classifier</small>"]
        Router -->|Send| Symptom["Symptom Agent"]
        Router -->|Send| Medication["Medication Agent"]
        Router -->|Send| Lifestyle["Lifestyle Agent"]
        Router -->|Send| Evidence["Evidence Agent"]
        Router -->|Send| DrugCheck["Drug Check Agent"]
        Symptom --> Synthesizer["Synthesizer Agent"]
        Medication --> Synthesizer
        Lifestyle --> Synthesizer
        Evidence --> Synthesizer
        DrugCheck --> Synthesizer
    end

    Qdrant["Qdrant Store<br/><small>Clinical Guidelines</small>"] -.->|retrieval| Evidence
    OpenFDA["OpenFDA API<br/><small>Labels + FAERS</small>"] -.->|screening| DrugCheck
    PatientData["Patient Data<br/><small>FHIR Profiles</small>"] -.->|context| Graph

    Graph -->|final response| WebApp
    Graph -->|final response| CLI
```

The router selects 1-5 specialists per query. LangGraph's `Send()` dispatches them in parallel. The synthesizer waits for all branches to complete, then merges their outputs with evidence citations and drug interaction data.

---

## Request Lifecycle

Step-by-step flow for a single user message:

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant R as Router
    participant S as Symptom/Med/Lifestyle
    participant E as Evidence Agent
    participant DC as Drug Check Agent
    participant Syn as Synthesizer

    U->>API: POST /api/chat {message, patient_id?}
    API->>API: Load patient profile, build summary
    API->>R: graph.astream(state)
    API-->>U: SSE: routing {status: processing}
    R->>R: Classify intent (JSON output)
    API-->>U: SSE: routing {agents, reasoning}

    par Parallel fan-out
        R->>S: Send(specialist, state)
        R->>E: Send(evidence_agent, state)
        R->>DC: Send(drug_check_agent, state)
    end

    S-->>API: SSE: specialist {agent, done, output}
    E-->>API: SSE: specialist {agent, done, output, citations}
    DC-->>API: SSE: specialist {agent, done, output, drug_interactions}

    API-->>U: SSE: synthesizing
    S & E & DC ->>Syn: specialist_outputs, evidence_context, citations, drug_interactions merged via reducers

    Syn->>Syn: Merge outputs + evidence + safety flags
    Syn-->>API: SSE: response {content, safety_escalation}
    API-->>U: SSE: done
```

---

## State Machine

The `MedGraphState` TypedDict flows through the graph, accumulating data at each node:

```mermaid
stateDiagram-v2
    [*] --> Router: user_input, messages,<br/>patient_summary

    Router --> Specialists: + route, route_reasoning,<br/>handoff_chain

    state Specialists {
        [*] --> Symptom
        [*] --> Medication
        [*] --> Lifestyle
        [*] --> Evidence
        [*] --> DrugCheck
    }

    Specialists --> Synthesizer: + specialist_outputs,<br/>safety_escalation,<br/>evidence_context,<br/>drug_interactions,<br/>citations,<br/>handoff_chain

    Synthesizer --> [*]: + final_response,<br/>messages (appended)
```

### State Fields and Reducers

| Field | Type | Reducer | Written by |
|-------|------|---------|------------|
| `messages` | `list[dict]` | `operator.add` (append) | Synthesizer |
| `user_input` | `str` | replace | Caller |
| `route` | `list[str]` | replace | Router |
| `route_reasoning` | `str` | replace | Router |
| `specialist_outputs` | `dict[str, str]` | `_merge_dicts` (merge) | Specialists |
| `final_response` | `str` | replace | Synthesizer |
| `handoff_chain` | `list[str]` | `operator.add` (append) | All agents |
| `safety_escalation` | `bool` | `_or_reduce` (logical OR) | Specialists |
| `patient` | `dict` | replace | Caller |
| `patient_summary` | `str` | replace | Caller |
| `evidence_context` | `dict[str, str]` | `_merge_dicts` (merge) | Evidence |
| `drug_interactions` | `list[dict]` | replace | DrugCheck |
| `citations` | `list[dict]` | `operator.add` (append) | Evidence |

The custom reducers are critical for parallel fan-out:
- **`_merge_dicts`**: When 2-5 specialists run in parallel, each returns `{self.name: response}`. The reducer merges them into a single dict without overwrites.
- **`_or_reduce`**: If ANY specialist flags a safety concern, the flag is `True` for the synthesizer.

---

## Module Map

```mermaid
graph LR
    subgraph Entrypoints
        API["api.py<br/><small>FastAPI + SSE</small>"]
        CLI["main.py<br/><small>Terminal REPL</small>"]
    end

    subgraph Core
        Config["config.py<br/><small>Env + model detection</small>"]
        Orchestrator["orchestrator/graph.py<br/><small>StateGraph + edges</small>"]
    end

    subgraph Agents ["agents/"]
        Base["base.py<br/><small>HealthcareAgent</small>"]
        RouterA["router.py"]
        SymptomA["symptom.py"]
        MedicationA["medication.py"]
        LifestyleA["lifestyle.py"]
        EvidenceA["evidence.py"]
        DrugCheckA["drug_check.py"]
        SynthesizerA["synthesizer.py"]
    end

    subgraph DataModels ["Data & Models"]
        Models["models/<br/><small>MedGraphState, RouteDecision</small>"]
        Prompts["prompts/<br/><small>7 system prompts</small>"]
        PatientData["data/<br/><small>FHIR, Gallery, OpenFDA</small>"]
        KnowledgePipeline["knowledge_pipeline/<br/><small>Qdrant + Haystack</small>"]
    end

    API --> Config
    CLI --> Config
    API --> Orchestrator
    CLI --> Orchestrator
    API --> PatientData
    CLI --> PatientData
    Orchestrator --> RouterA & SymptomA & MedicationA & LifestyleA & EvidenceA & DrugCheckA & SynthesizerA
    RouterA & SymptomA & MedicationA & LifestyleA & EvidenceA & DrugCheckA & SynthesizerA --> Base
    Base --> Models
    RouterA & SymptomA & MedicationA & LifestyleA & EvidenceA & DrugCheckA & SynthesizerA --> Prompts
    EvidenceA --> KnowledgePipeline
    DrugCheckA --> PatientData
```

---

## Agent Interfaces

What each agent reads and writes:

```mermaid
graph LR
    subgraph Router
        R_in["Reads:<br/>user_input, messages,<br/>patient_summary"]
        R_out["Writes:<br/>route, route_reasoning,<br/>handoff_chain"]
        R_in --> R_out
    end

    subgraph Specialist ["Specialist (x3: Symptom, Medication, Lifestyle)"]
        S_in["Reads:<br/>user_input, messages,<br/>patient_summary"]
        S_out["Writes:<br/>specialist_outputs,<br/>handoff_chain,<br/>safety_escalation"]
        S_in --> S_out
    end

    subgraph EvidenceAgent ["Evidence Agent"]
        E_in["Reads:<br/>user_input,<br/>patient_summary"]
        E_out["Writes:<br/>specialist_outputs,<br/>evidence_context,<br/>citations,<br/>handoff_chain"]
        E_in --> E_out
    end

    subgraph DrugCheckAgent ["Drug Check Agent"]
        DC_in["Reads:<br/>patient,<br/>user_input"]
        DC_out["Writes:<br/>specialist_outputs,<br/>drug_interactions,<br/>safety_escalation,<br/>handoff_chain"]
        DC_in --> DC_out
    end

    subgraph Synthesizer
        Syn_in["Reads:<br/>specialist_outputs,<br/>safety_escalation,<br/>evidence_context,<br/>citations,<br/>drug_interactions,<br/>user_input, messages"]
        Syn_out["Writes:<br/>final_response,<br/>messages"]
        Syn_in --> Syn_out
    end
```

---

## LLM Call Flow

How the base agent class handles model selection and retry:

```mermaid
flowchart TD
    A[Agent.process] -->|builds messages| B[_call_llm]
    B --> C{Try primary model}
    C -->|success| D[Return response]
    C -->|failure| E{Fallback model configured?}
    E -->|yes| F{Try fallback model}
    E -->|no| G[Return FALLBACK_MESSAGE]
    F -->|success| D
    F -->|failure| G
```

**Model resolution:** Agents read `MEDGRAPH_MODEL` and `MEDGRAPH_FALLBACK_MODEL` from env vars, set by `load_config()` at startup. This supports Gemini, OpenAI, or any litellm-compatible provider.

---

## Web App

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/patients` | Patient gallery listing (5 cards) |
| GET | `/api/patients/{id}` | Full patient profile |
| POST | `/api/chat` | SSE stream of agent pipeline events |
| GET | `/api/health` | Health check |
| GET | `/` | Serves frontend |

### Chat Request

```json
{
    "message": "Should I take ibuprofen?",
    "session_id": "optional-uuid",
    "patient_id": "optional-patient-uuid"
}
```

When `patient_id` is provided, the API loads the patient profile, builds the patient summary, and includes both in the initial state. All agents then receive patient context automatically.

### SSE Event Flow

```mermaid
sequenceDiagram
    participant Browser
    participant FastAPI
    participant LangGraph

    Browser->>FastAPI: POST /api/chat
    FastAPI-->>Browser: event: routing (processing)
    FastAPI->>LangGraph: graph.astream(state, mode="updates")

    LangGraph-->>FastAPI: router node update
    FastAPI-->>Browser: event: routing (agents, reasoning)

    LangGraph-->>FastAPI: specialist node updates
    FastAPI-->>Browser: event: specialist (processing → done)

    FastAPI-->>Browser: event: synthesizing
    LangGraph-->>FastAPI: synthesizer node update
    FastAPI-->>Browser: event: response

    FastAPI-->>Browser: event: done
```

**SSE event types:**

| Event | Payload | When |
|-------|---------|------|
| `routing` | `{status: "processing"}` | Pipeline starts |
| `routing` | `{agents, reasoning}` | Router completes |
| `specialist` | `{agent, status, output?, citations?, drug_interactions?}` | Per specialist (processing → done) |
| `synthesizing` | `{}` | All specialists complete |
| `response` | `{content, safety_escalation, session_id}` | Final response ready |
| `error` | `{message}` | On exception |
| `done` | `{session_id}` | Stream end |

### Frontend (`src/static/`)

- **Patient gallery bar:** Horizontal button row for selecting patients
- **Patient summary card:** Shows name, age/sex, headline, condition tags after selection
- **Chat interface:** User/assistant bubbles with markdown rendering (via marked.js)
- **Pipeline status:** Real-time agent badges (Routing spinner → specialist spinners → checkmarks → Synthesizing → checkmark)
- Vanilla HTML/CSS/JS, no build step, single-page app with SSE streaming

---

## Streaming Implementation

- **Why `astream(mode="updates")`** — Node-level granularity was chosen because the UI needs to know when each agent completes. Clean state diffs per node simplify event generation.

- **Event deduplication** — `api.py` tracks which events have been sent using flags (`routing_sent`, `synthesizing_sent`, `specialists_seen` set) to prevent duplicate SSE events.

- **Agent naming in SSE** — Graph node names use `_agent` suffix (e.g. `symptom_agent`). SSE events strip this to plain labels (`symptom`) for the frontend.

- **Session persistence** — Web app uses in-memory dict (`_sessions`) keyed by `session_id`. CLI tracks history in a local list. Neither uses LangGraph checkpointing.

---

## Safety Mechanism

```mermaid
flowchart LR
    A["Specialist detects<br/>emergency in context"] -->|includes marker| B["Response contains<br/>[SAFETY_ESCALATION]"]
    B --> C["Base class sets<br/>safety_escalation = True"]
    C --> D["_or_reduce merges<br/>flags from all branches"]
    D --> E["Synthesizer reads flag,<br/>integrates disclaimer"]
    E --> F["Marker stripped<br/>from final output"]
```

Safety is prompt-driven: the LLM decides whether a situation is urgent based on medical context. This is more nuanced than keyword matching.

---

## Evaluation Framework

```mermaid
graph TD
    subgraph Datasets
        LQA["LiveQA<br/><small>104 samples, NLM-validated</small>"]
        MQA["MedicationQA<br/><small>~690 samples, CC BY</small>"]
        SAF["Adversarial Prompts<br/><small>~120 safety tests</small>"]
    end

    subgraph Dimensions
        Routing["Routing Accuracy<br/><small>Exact-match, per-agent F1</small>"]
        Quality["Specialist Quality<br/><small>LLM judge vs reference</small>"]
        Safety["Safety Compliance<br/><small>No diagnose/prescribe</small>"]
        Persona["Persona Simulation<br/><small>Multi-turn patient scenarios</small>"]
    end

    LQA --> Routing
    MQA --> Routing
    LQA & MQA --> Quality
    SAF --> Safety
    LQA --> Persona

    subgraph Tools
        RE["RoutingEvaluator<br/><small>Confusion matrix, F1</small>"]
        Judge["LLM Judge<br/><small>Clinical quality,<br/>communication,<br/>questioning criteria</small>"]
        PersonaSim["Persona Simulator<br/><small>Simulated patient turns</small>"]
    end

    Routing --> RE
    Quality --> Judge
    Safety --> Judge
    Persona --> PersonaSim
```

Tests run via `pytest tests/eval/ -v` (requires API key). See `tests/eval/ARCHITECTURE.md` for implementation and `docs/quality-criteria.md` for criteria definitions.

---

## Project Structure

```
medgraph/
  src/
    api.py                     # FastAPI backend with SSE
    main.py                    # Terminal CLI
    config.py                  # Env + model config
    static/                    # Frontend (HTML/CSS/JS)
    models/
      state.py                 # MedGraphState (TypedDict, 13 fields)
      routing.py               # RouteDecision (Pydantic)
    prompts/                   # System prompts (7 agents)
    agents/
      base.py                  # HealthcareAgent base class
      router.py                # RouterAgent
      symptom.py               # SymptomAgent
      medication.py            # MedicationAgent
      lifestyle.py             # LifestyleAgent
      evidence.py              # EvidenceAgent (Qdrant RAG)
      drug_check.py            # DrugCheckAgent (OpenFDA)
      synthesizer.py           # SynthesizerAgent
    orchestrator/
      graph.py                 # LangGraph StateGraph (7 nodes)
    data/
      schemas.py               # PatientProfile, Condition, Medication, etc.
      fhir_parser.py           # FHIR R4 Bundle → PatientProfile
      condition_maps.py        # SNOMED/LOINC → friendly names
      patient_context.py       # build_patient_summary()
      gallery.py               # Patient gallery loader
      openfda/                 # Drug interaction screening (6 files)
    knowledge_pipeline/
      pipeline.py              # Haystack indexing + retrieval
      schemas.py               # ChunkMetadata, ConfidenceTier
      qdrant_store/            # Pre-indexed clinical guidelines
  tests/
    test_agents.py             # Agent contract tests (14)
    test_routing.py            # Router tests (12)
    test_orchestrator.py       # Graph integration tests (18)
    test_patient_data.py       # Patient data tests (27)
    test_state_compat.py       # Backward compatibility (9)
    test_patient_aware_agents.py  # Evidence + DrugCheck (11)
    test_synthesizer_extended.py  # Extended build_prompt (8)
    test_graph_extended.py     # New agents in graph (10)
    test_api_extended.py       # Patient API endpoints (6)
    eval/                      # Evaluation framework (requires API key)
  data/eval/                   # Evaluation datasets
  docs/                        # Documentation
```
