# Models Architecture

## `state.py` — `MedGraphState`

The graph state (TypedDict). `HealthcareState` is an alias kept for the base agent.

| Field | Type | Reducer | Written by |
|---|---|---|---|
| `messages` | list of message dicts | append | API (history), writer |
| `user_input` | str | replace | API |
| `language` | str | replace | API |
| `patient` | dict (UserProfile) | replace | API |
| `patient_summary` | str | replace | API |
| `reading` | dict (TestReading) | replace | API |
| `turn_kind` | `new_reading` or `question` | replace | API |
| `route` | list of source names | replace | planner |
| `queries` | list of str | replace | planner |
| `route_reasoning` | str | replace | planner |
| `sources` | dict id → SourceItem | merge | all source nodes |
| `retrieval_trace` | list of dicts | append | all source nodes |
| `evidence_gap` | dict | replace | study library |
| `safety_reasons` | list of str | append | safety rules |
| `safety_escalation` | bool | OR | safety rules, writer |
| `final_response` | str | replace | writer |
| `citations` | list of Citation dicts | append | writer |
| `handoff_chain` | list of node names | append | every node |

Only one node writes each "replace" field in a turn, which is what makes the parallel fan-out safe.

## `evidence.py`

- `SourceItem` — one citable piece of evidence: study identity, design label, sample size, cohort summary, countries, matched attributes, the verbatim passage, group (`safety`, `matched`, `reference_range`, `guideline`, `overall`).
- `Citation` — what the browser receives: a number, the same descriptive fields, and `passages` (every passage cited from that study).
