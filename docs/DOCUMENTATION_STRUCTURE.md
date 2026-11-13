# Documentation Structure Guide

**Created:** 2026-03-11
**Purpose:** Define how documentation is organized in this project

---

## Philosophy

Documentation is organized by **type of knowledge**:

1. **Process Knowledge** — How to work on this project (setup, testing, debugging)
2. **Factual Knowledge** — What the system is and how it works (architecture, schemas, APIs)
3. **Active Work** — Temporary planning docs for features in progress

---

## Documentation Tree

All docs connect back to `CLAUDE.md` (the entry point):

```
CLAUDE.md (AI Entry Point)
│
├─► README.md                              (what it is, how to run it)
│
├─► docs/specs/ph-companion/               ★ requirements, design, tasks, demo script
├─► docs/system-overview.md                (flow, event stream, data)
├─► docs/eval-results.md                   (acceptance scenarios, timing, accessibility)
├─► docs/WORKFLOW_PATTERNS.md
├─► docs/DOCUMENTATION_STRUCTURE.md        (this file)
│
├─► src/sources/ARCHITECTURE.md            (matching, lanes, ranges, safety)
├─► src/knowledge_pipeline/ARCHITECTURE.md (study records, corpus build, search)
├─► src/agents/ARCHITECTURE.md             (planner, sources, writer, citation check)
├─► src/prompts/ARCHITECTURE.md            (planner and writer prompts)
├─► src/models/ARCHITECTURE.md             (state, evidence models)
├─► src/orchestrator/ARCHITECTURE.md       (graph)
├─► src/data/ARCHITECTURE.md               (profiles, personas)
├─► src/static/ARCHITECTURE.md             (frontend)
└─► tests/eval/ARCHITECTURE.md             (acceptance scenarios)
```

**Navigation principle:** If lost, return to `CLAUDE.md`.

**Critical:** Read `WORKFLOW_PATTERNS.md` before starting any task.

---

## Target Structure

### Process Knowledge (How to Work)

| Document | Purpose | Audience |
|----------|---------|----------|
| `CLAUDE.md` | AI assistant quick context — current state, pointers | AI assistants |
| `docs/WORKFLOW_PATTERNS.md` | How to structure work, use subagents | AI assistants |
| `README.md` | Architecture overview, setup, prompt design decisions | Reviewers |
| `docs/debugging.md` | Common issues, debugging tips | Developers |

### Factual Knowledge (What It Is)

| Document | Purpose | Audience |
|----------|---------|----------|
| `docs/system-overview.md` | Visual architecture diagrams, data flow, SSE events | Developers |
| `src/models/ARCHITECTURE.md` | MedGraphState (13 fields), RouteDecision, reducers | Developers |
| `src/agents/ARCHITECTURE.md` | 7 agents, base class, patient awareness, error handling | Developers |
| `src/prompts/ARCHITECTURE.md` | 7 system prompts, design philosophy, domain boundaries | Developers |
| `src/orchestrator/ARCHITECTURE.md` | LangGraph wiring, fan-out, streaming integration | Developers |
| `src/data/ARCHITECTURE.md` | FHIR parsing, patient schemas, gallery, OpenFDA integration | Developers |
| `src/knowledge_pipeline/ARCHITECTURE.md` | Qdrant store, Haystack pipelines, embeddings | Developers |
| `tests/eval/ARCHITECTURE.md` | Evaluation framework, criteria, datasets, judge | Developers |
| `docs/quality-criteria.md` | Response quality criteria definitions | Developers |

### Active Work (Temporary)

| Document | Purpose | Lifecycle |
|----------|---------|-----------|
| `src/[module]/PLAN.md` | Research, candidate architectures, decisions | Create during exploration → Merge into ARCHITECTURE.md when settled |

---

## Document Lifecycle

```
1. Research & explore module
   └─► Create src/[module]/PLAN.md (candidate architectures, tradeoffs, questions)

2. Review & decide with user
   └─► Critique plan, synthesize, get user approval

3. Implement & self-validate
   └─► Build, run tests, fix issues, report results to user

4. Settle documentation
   ├─► Merge key decisions into [module]/ARCHITECTURE.md
   ├─► Remove PLAN.md (content now in ARCHITECTURE.md)
   └─► Update CLAUDE.md "Recent Updates"
```

---

## CLAUDE.md Guidelines

CLAUDE.md should be **slim and focused** (~150-200 lines):

### Include:
- Project overview (1 paragraph + architecture diagram)
- Current state summary
- Documentation pointers
- Do's and Don'ts
- Recent updates (last 7 days only)
- Quick commands

### Exclude (move to other docs):
- Detailed architecture → `[component]/ARCHITECTURE.md`
- Debugging tips → `docs/debugging.md`
- Historical updates (>7 days) → delete (in git history)

---

## Archive Policy

The `archive/` folder contains completed planning documents.

**When to archive:** After extracting key information to permanent docs.
