# Models Architecture

## Overview

Shared data structures used across all modules. This is the foundation layer — every other module imports from here. Contains pure data definitions with no business logic.

**Related docs:** [Agents](../agents/ARCHITECTURE.md) · [Orchestrator](../orchestrator/ARCHITECTURE.md) · [System overview](../../docs/system-overview.md)

## Dependencies

- `typing`, `typing_extensions`, `operator` (stdlib)
- `pydantic` (BaseModel, Field)
- No internal dependencies

## Directory Structure

```
src/models/
  __init__.py      # re-exports MedGraphState, HealthcareState, RouteDecision
  state.py         # MedGraphState TypedDict (central data contract)
  routing.py       # RouteDecision Pydantic model
```

## MedGraphState (`state.py`)

Central data contract for the entire system. A TypedDict with Annotated reducers that handle parallel writes from LangGraph's fan-out branches.

### Fields

**Original fields (8):**

| Field | Type | Reducer | Written by |
|-------|------|---------|------------|
| `messages` | `list[dict[str, str]]` | `operator.add` (append) | Synthesizer |
| `user_input` | `str` | replace | Caller |
| `route` | `list[str]` | replace | Router |
| `route_reasoning` | `str` | replace | Router |
| `specialist_outputs` | `dict[str, str]` | `_merge_dicts` | Specialists |
| `final_response` | `str` | replace | Synthesizer |
| `handoff_chain` | `list[str]` | `operator.add` (append) | All agents |
| `safety_escalation` | `bool` | `_or_reduce` (logical OR) | Specialists |

**New medgraph fields (5):**

| Field | Type | Reducer | Written by |
|-------|------|---------|------------|
| `patient` | `dict` | replace | Caller |
| `patient_summary` | `str` | replace | Caller |
| `evidence_context` | `dict[str, str]` | `_merge_dicts` | Evidence agent |
| `drug_interactions` | `list[dict]` | replace | DrugCheck agent |
| `citations` | `list[dict]` | `operator.add` (append) | Evidence agent |

### Custom Reducers

```python
def _merge_dicts(left, right) -> dict:
    """Merges dicts from parallel branches. Returns new dict (no mutation)."""
    return {**left, **right}

def _or_reduce(left, right) -> bool:
    """True if ANY branch escalates safety."""
    return left or right
```

These are critical for parallel fan-out:
- **`_merge_dicts`**: When 2-5 specialists run in parallel, each returns `{self.name: response}`. The reducer merges them without overwrites.
- **`_or_reduce`**: If ANY specialist flags danger, the synthesizer sees `safety_escalation=True`.

### Backward Compatibility

```python
HealthcareState = MedGraphState  # Alias for backward compat
```

## RouteDecision (`routing.py`)

Structured output from the router LLM call. Used with litellm's `response_format={"type": "json_object"}` for typed JSON output.

```python
class RouteDecision(BaseModel):
    agents: list[Literal["symptom", "medication", "lifestyle", "evidence", "drug_check"]]
    reasoning: str
    confidence: float  # 0.0 - 1.0
```

Five valid agent labels. The router can select 1-5 agents per query.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| TypedDict over Pydantic | LangGraph idiom | LangGraph uses TypedDict with Annotated reducers natively |
| `_merge_dicts` for parallel writes | Custom reducer | Needed for fan-out: each branch writes its own key |
| `_or_reduce` for safety | Custom reducer | Any-branch-escalates semantics |
| `HealthcareState` alias | Backward compat | Original name used in tests and some imports |
| Literal agent labels | Type-checked routing | Invalid agent names caught at validation time |
