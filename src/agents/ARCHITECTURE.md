# Agents Architecture

## Overview

Seven healthcare agents serve as LangGraph nodes. Each is an async callable that receives the full `MedGraphState` and returns a partial state update dict. A shared base class handles message construction, LLM invocation, retry/fallback, patient context injection, and safety detection.

**Related docs:** [State model](../models/ARCHITECTURE.md) · [Prompts](../prompts/ARCHITECTURE.md) · [Orchestrator](../orchestrator/ARCHITECTURE.md) · [Knowledge pipeline](../knowledge_pipeline/ARCHITECTURE.md) · [Patient data](../data/ARCHITECTURE.md)

## Tech Stack

- **LLM Interface:** litellm `acompletion()` (async, supports Gemini + OpenAI)
- **Structured Output:** Pydantic `RouteDecision` + `response_format={"type": "json_object"}` (router only)
- **State Contract:** `MedGraphState` TypedDict with Annotated reducers (aliased as `HealthcareState`)

## Directory Structure

```
src/agents/
  __init__.py           # re-exports all agent classes
  base.py               # HealthcareAgent base class
  router.py             # RouterAgent (JSON classifier)
  symptom.py            # SymptomAgent
  medication.py         # MedicationAgent
  lifestyle.py          # LifestyleAgent
  evidence.py           # EvidenceAgent (Qdrant RAG retrieval)
  drug_check.py         # DrugCheckAgent (OpenFDA interaction screening)
  synthesizer.py        # SynthesizerAgent
```

## Agent Design

### Base Class: `HealthcareAgent` (`base.py`)

All agents inherit from this. Key design decisions:

**`__call__` → `process()` split:**
`__call__(state)` is the LangGraph entry point; it delegates to `process(state)` which subclasses override. This keeps the node interface clean while allowing per-agent logic.

**Patient awareness via prompt injection:**
`_build_messages()` automatically appends `state["patient_summary"]` to the system prompt when present. This makes all agents patient-aware with zero per-agent code changes:

```python
patient_summary = state.get("patient_summary", "")
if patient_summary:
    prompt = prompt + "\n\n" + patient_summary
```

Any new agent automatically gets patient context. Without a patient loaded, behavior is identical.

**Model resolution via environment:**
Constructor accepts `model: str | None`. If `None` (default), reads `MEDGRAPH_MODEL` env var (set by `load_config()`). This decouples agents from config — they don't import the config module.

**Retry with model fallback:**
`_call_llm()` tries the primary model first. On failure, if `MEDGRAPH_FALLBACK_MODEL` is set, retries with that model. If all attempts fail, returns a safe `FALLBACK_MESSAGE` rather than raising.

**Message construction:**
`_build_messages(state)` builds an OpenAI-format list: system prompt (+ patient context) → conversation history (`state["messages"]`) → current user input. Accepts `system_prompt_override` for agents that need dynamic prompts (synthesizer).

**Safety detection:**
`_detect_safety_escalation(text)` checks for the `[SAFETY_ESCALATION]` marker in LLM output. This is a static method — detection is prompt-driven, not heuristic.

### Router: `RouterAgent` (`router.py`)

- **Reads:** `user_input`, `messages`, `patient_summary`
- **Writes:** `route` (list of 1-5 specialist labels), `route_reasoning`, `handoff_chain`
- Uses `response_format={"type": "json_object"}` for structured output
- Parses JSON into `RouteDecision` Pydantic model via `model_validate()`
- **Retry strategy:** Two attempts at structured parsing. On failure: falls back to `RouteDecision(agents=["symptom"], reasoning="Routing failed; defaulting to symptom specialist.", confidence=0.0)`. This ensures the system always produces a response even if the LLM returns unparseable output.
- Never produces user-facing text — only a routing decision

### Specialists: `SymptomAgent`, `MedicationAgent`, `LifestyleAgent`

All three follow the same pattern:

- **Reads:** `user_input`, `messages`, `patient_summary` (via base class injection)
- **Writes:** `specialist_outputs` ({self.name: response}), `handoff_chain`, `safety_escalation`
- Each writes only its own key in `specialist_outputs` — the `_merge_dicts` reducer combines parallel writes
- Safety escalation detected from LLM response text via `_detect_safety_escalation()`

### Evidence Agent: `EvidenceAgent` (`evidence.py`)

- **Reads:** `user_input`, `patient_summary`
- **Writes:** `specialist_outputs`, `handoff_chain`, `safety_escalation`, `evidence_context`, `citations`
- Uses `retrieve_evidence()` standalone function — not an LLM call, but a Qdrant retrieval pipeline
- Query expansion: appends patient conditions to the query for better retrieval
- Returns evidence as `{source_id: text}` dict and structured citations `[{source, tier, grade, text}]`
- **Graceful degradation:** Returns empty results if Qdrant store is unavailable — system continues without evidence grounding

### DrugCheck Agent: `DrugCheckAgent` (`drug_check.py`)

- **Reads:** `patient` (dict), `user_input`
- **Writes:** `specialist_outputs`, `handoff_chain`, `safety_escalation`, `drug_interactions`
- Uses `screen_patient_medications()` standalone function — calls OpenFDA APIs
- Resolves patient medications to FDA generic names, generates all unique pairs, screens each
- **Severity logic:** "high" if FDA label cross-mentions the other drug; "moderate" otherwise
- Sets `safety_escalation = True` when any high-severity interaction is found
- **Graceful degradation:** Returns empty results on any exception; handles missing/no medications gracefully

### Synthesizer: `SynthesizerAgent` (`synthesizer.py`)

- **Reads:** `specialist_outputs`, `safety_escalation`, `user_input`, `messages`, `evidence_context`, `citations`, `drug_interactions`
- **Writes:** `final_response`, `messages` (appends user+assistant pair)
- Calls `build_prompt()` from `src/prompts/synthesizer.py` to inject all available context into the system prompt at runtime
- `build_prompt()` accepts: `specialist_outputs`, `safety_escalation`, `evidence_context`, `citations`, `drug_interactions` — empty sections are omitted
- Strips `[SAFETY_ESCALATION]` marker from final output
- Returns `FALLBACK_MESSAGE` if synthesized response is empty

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Patient awareness | Base class prompt injection (5 lines) | Zero per-agent changes; automatic for new agents |
| Safety detection | Prompt marker (`[SAFETY_ESCALATION]`) | LLM understands medical context better than keyword heuristics |
| Model configuration | Env vars, not constructor args | Decouples agents from config; allows runtime override |
| Structured output | `response_format` + Pydantic | Reliable JSON from LLM; validated parsing |
| Fallback on failure | Safe message, not exception | System stays usable even when LLM is unavailable |
| Specialist isolation | Each writes own key | Parallel fan-out without race conditions; `_merge_dicts` reducer combines |
| Evidence graceful degradation | Empty results, not errors | System works without Qdrant; evidence is additive |
| Drug interaction severity | Label cross-mention = high | FDA label mentions are the strongest signal for clinical relevance |

## Error Handling

Four failure patterns are handled:

1. **LLM call failures:** `_call_llm()` tries the primary model, then the fallback model (if configured). If both fail, returns `FALLBACK_MESSAGE` rather than raising.

2. **Invalid routing decision:** The router attempts structured JSON parsing twice. On failure, defaults to `RouteDecision(agents=["symptom"], confidence=0.0)`. The system never stalls on a bad route.

3. **Malformed structured output:** JSON that parses but doesn't match `RouteDecision` is caught by Pydantic `model_validate()`. Counts as a failed attempt.

4. **External service failures:** Evidence agent handles Qdrant connection failures; DrugCheck agent handles OpenFDA API failures. Both return empty results rather than propagating exceptions.

## Testing

- `tests/test_agents.py` — 14 tests: agent contracts, safety escalation, retry/fallback
- `tests/test_routing.py` — 12 tests: single/multi routing, off-topic, malformed JSON, fallback
- `tests/test_patient_aware_agents.py` — 11 tests: evidence + drug_check outputs, safety escalation, empty handling
- `tests/test_synthesizer_extended.py` — 8 tests: build_prompt backward compat, evidence/citations/interactions sections

All mock `litellm.acompletion` with `AsyncMock` — no real API calls in unit tests.

## Deviations from Original Blueprint

Three intentional simplifications from the original design:

1. **`metadata` field removed.** No agent ever read or wrote it — eliminated dead code.

2. **No single-specialist pass-through in synthesizer.** The synthesizer handles all cases uniformly, which is simpler and produces consistent output.

3. **Empty route vs. default route on failure.** Off-topic queries return `route: []` (intentional). Parsing failures default to `["symptom"]` (safety net). The distinction is between an intentional "no route" and an unintentional failure.
