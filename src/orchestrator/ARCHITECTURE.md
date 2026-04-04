# Orchestrator Architecture

## Overview

Wires the LangGraph `StateGraph` — connects all agent nodes with edges, handles conditional routing and parallel fan-out to specialists. Exposes a single entry point: `build_graph()`.

**Related docs:** [State model](../models/ARCHITECTURE.md) · [Agents](../agents/ARCHITECTURE.md) · [System overview](../../docs/system-overview.md)

## Dependencies

- `langgraph` — `StateGraph`, `START`, `END`, `Send`
- `src/models/` — [`MedGraphState`](../models/ARCHITECTURE.md) (shared state TypedDict)
- `src/agents/` — all [7 agent classes](../agents/ARCHITECTURE.md) (`RouterAgent`, `SymptomAgent`, `MedicationAgent`, `LifestyleAgent`, `EvidenceAgent`, `DrugCheckAgent`, `SynthesizerAgent`)

## Directory Structure

```
src/orchestrator/
  __init__.py           # re-exports build_graph
  graph.py              # StateGraph construction + compile
```

## Key Components

### `build_graph() -> CompiledStateGraph`

Single entry point for the entire system. Called by both the web app (`src/api.py`) and CLI (`src/main.py`). Returns a compiled graph ready for `await graph.ainvoke(state)` or `graph.astream(state)`.

**Graph nodes:**
| Node name | Agent | Purpose |
|-----------|-------|---------|
| `router` | `RouterAgent` | Classifies intent, selects 1-5 specialists |
| `symptom_agent` | `SymptomAgent` | Symptom triage and clarification |
| `medication_agent` | `MedicationAgent` | Drug info, interactions, side effects |
| `lifestyle_agent` | `LifestyleAgent` | Diet, exercise, daily management |
| `evidence_agent` | `EvidenceAgent` | Retrieves clinical guidelines from Qdrant |
| `drug_check_agent` | `DrugCheckAgent` | Screens medications for drug interactions via OpenFDA |
| `synthesizer` | `SynthesizerAgent` | Merges all outputs into final response |

**Edge wiring:**
```
START ──> router ──> [conditional] ──> specialist(s) ──> synthesizer ──> END
```

### `route_to_specialists(state) -> list[Send]`

Pure routing function — no LLM calls, fully deterministic. Reads `state["route"]` and returns `Send()` objects for parallel dispatch.

**`AGENT_NODE_MAP`** maps route labels to node names:
```python
{
    "symptom": "symptom_agent",
    "medication": "medication_agent",
    "lifestyle": "lifestyle_agent",
    "evidence": "evidence_agent",
    "drug_check": "drug_check_agent",
}
```

**Fallback handling:**
- Empty route (off-topic query) → `Send("synthesizer", state)` (skip specialists)
- All labels unrecognised → same fallback (safety net)
- Synthesizer sees empty `specialist_outputs` and produces a polite redirect

### State Initialization

Callers must supply a full initial state dict:
```python
{
    "user_input": "...",
    "messages": [...],
    "route": [],
    "route_reasoning": "",
    "specialist_outputs": {},
    "final_response": "",
    "handoff_chain": [],
    "safety_escalation": False,
    "patient": {},
    "patient_summary": "",
    "evidence_context": {},
    "drug_interactions": [],
    "citations": [],
}
```

The graph is stateless — all context is passed in. Session persistence is handled by the caller (web app uses in-memory dict; CLI tracks history in a local list).

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Parallel fan-out | LangGraph `Send()` | True parallelism; all specialists run concurrently |
| Convergence | All specialists edge to `synthesizer` | LangGraph waits for all branches before running synthesizer |
| Routing function | Pure, deterministic | No side effects; easy to test; LLM call happens in the router node |
| Stateless graph | No checkpointing | Simplicity; callers own session state |
| `AGENT_NODE_MAP` constant | Dict mapping labels → node names | Single source of truth for route-label-to-node mapping |
| Fallback for empty route | Direct to synthesizer | Graceful handling of off-topic/inappropriate queries |

## Streaming (Web App Integration)

The web app (`src/api.py`) uses `graph.astream(state, stream_mode="updates")` to receive node-level state updates as they complete. This enables SSE events:

1. `routing` (status: processing) — emitted immediately when pipeline starts
2. `routing` (agents, reasoning) — emitted after router node completes
3. `specialist` (status: processing/done) — emitted per specialist
4. `synthesizing` — emitted when all specialists complete (before synthesizer finishes)
5. `response` — emitted with final response content
6. `done` — stream end signal

## Testing

- `tests/test_orchestrator.py` — 18 tests: route_to_specialists, single/multi fan-out, fallback, safety propagation, message history, agent node map
- `tests/test_graph_extended.py` — 10 tests: new agents in graph, routing to evidence/drug_check, full flow with all agents, backward compat
