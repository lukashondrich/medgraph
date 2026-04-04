# Workflow Patterns

How to structure work, decompose tasks, and use subagents effectively.

---

## Overview

For complex or specialized work, lean towards using subagents. This keeps the main conversation focused and recoverable.

| Workflow | Approach | Documentation |
|----------|----------|---------------|
| Research & Exploration | Explore → plan → critique → decide | Below |
| Building Features | Task decomposition, parallel execution | Below |
| Bug Investigation | Reproduce → fix → test | Below |
| Testing | Use specialized subagents | Below |

---

## Working on a Module

When assigned a module to implement or modify, follow this protocol:

```
1. Read CLAUDE.md (current state, constraints)
2. Read docs/system-overview.md (module map, data flow)
3. Read your module's ARCHITECTURE.md (detailed design, interfaces)
4. Read any dependent module's ARCHITECTURE.md (understand interfaces you consume)
5. Implement — the ARCHITECTURE.md defines WHAT, you decide HOW
6. Write tests alongside implementation
7. Update src/[module]/ARCHITECTURE.md with any new decisions
8. Report results: what was built, what was validated, any open questions
```

### ARCHITECTURE.md vs Implementation Freedom

ARCHITECTURE.md files specify:
- **Purpose** — what the module does
- **Interface** — function signatures, input/output contracts
- **Key decisions** — design choices with rationale
- **File structure** — what files exist

ARCHITECTURE.md files do NOT specify:
- Internal implementation details
- Helper functions or utilities
- Error handling strategy (beyond "handle gracefully")
- Code organization within files

You have full freedom on the HOW. If you discover a better approach, implement it and document the reasoning in ARCHITECTURE.md.

### Cross-Module Dependencies

Check `docs/system-overview.md` for the module map and dependency graph. Each module's ARCHITECTURE.md documents the interfaces it exposes and consumes.

---

## Research & Exploration

For modules with real complexity, research and explore before planning implementation.

```
1. Read challenge spec + CLAUDE.md + relevant ARCHITECTURE.md
2. Research approaches, produce [module]/PLAN.md in the module's folder
3. Ask the user about any assumptions
4. Critically review the plan (as a separate step — challenge your own proposal)
5. Synthesize plan + critique, present to user for decision before implementing
6. Implement and self-validate (run tests, fix issues)
7. Present results to user, discuss next steps
```

### Plan Document

Place in the module's folder (e.g., `src/agents/PLAN.md`). Include:

- **Goal** — what this module needs to accomplish
- **Candidate Architectures** — competing approaches with tradeoffs
- **Recommended Approach** — and why
- **Assumptions** — flag anything uncertain, ask the user
- **Self-check Plan** — what the agent can validate itself (tests, linting) vs. what needs the user (design decisions, tradeoffs, integration questions)
- **Open Questions** — for the user

### Decision Handoff

When presenting to the user, provide:
- A concise summary of the recommendation
- Options with tradeoffs where alternatives exist
- Clear questions requiring their input

### Iteration & Decision Log

When an approach is explored and rejected, keep it in the plan doc under "Candidate Architectures" with a note on why it was rejected. This prevents re-exploring dead ends and preserves reasoning context for other agents.

### After Implementation

- Update the module's `ARCHITECTURE.md` with settled decisions
- Archive or remove the `PLAN.md` (key content now lives in ARCHITECTURE.md)
- Report results to user: what was built, what was validated, what needs discussion

---

## Building Features

```
1. Read CLAUDE.md + relevant ARCHITECTURE.md
2. Create *_PLAN.md if complex (3+ files, architectural decisions, or unclear scope)
3. Implement with tests
4. Update ARCHITECTURE.md with key changes
5. Archive plan doc
```

### When to Create a Plan

Create a `*_PLAN.md` when:
- The feature touches 3+ files
- There are architectural decisions to make
- The scope is unclear and needs exploration first
- You want to get alignment before writing code

Skip the plan when:
- Single-file change with clear requirements
- Bug fix with obvious root cause
- Small refactor within one module

### Multi-Phase Task Workflow

For complex features with 3+ distinct phases, use task decomposition:

```
Phase 1: Setup/Infrastructure (Sequential)
    └── Task 1.1: Prerequisites
    └── Task 1.2: Verification

Phase 2: Implementation (Parallel where possible)
    ├── Task 2.1: Component A
    ├── Task 2.2: Component B
    └── Task 2.3: Component C

Phase 3: Integration & Verification (Sequential)
    └── Task 3.1: Full test run
    └── Task 3.2: Documentation update
```

**Task definition:**

| Field | Description | Example |
|-------|-------------|---------|
| **Subject** | Brief imperative title | "Implement Router Agent" |
| **Description** | What needs to be done, acceptance criteria | "Route user queries to correct specialist" |
| **ActiveForm** | Present continuous for spinner display | "Implementing Router Agent" |
| **Dependencies** | What must complete first | blockedBy: ["1"] |

**Progress tracking:** `pending → in_progress → completed`

---

## Bug Investigation

```
1. Reproduce the issue (on which platform/environment?)
2. Identify root cause (logs, debugging, bisect)
3. Create minimal fix (don't over-engineer)
4. Add regression test if applicable
5. Document in debugging.md if it's a gotcha others will hit
```

### Escalation Triggers

Stop and reassess when:
- Build/install failures blocking progress
- Unclear requirements (ask the user)
- Architectural decisions affecting multiple files (create a plan)
- Test failures with unclear root cause (investigate before fixing)

---

## Using Subagents

### When to Use Subagents

| Situation | Subagent Type | Why |
|-----------|---------------|-----|
| Exploring unfamiliar code | Explore | Keeps main context clean |
| Running tests | Bash | Long output doesn't pollute conversation |
| Research (web, docs) | general-purpose | Can fetch and synthesize independently |
| Parallel independent tasks | Any | Speed — run simultaneously |

### When NOT to Use Subagents

- Simple file reads or searches (use Glob/Grep directly)
- Single-step operations
- Tasks where you need the result immediately for the next line of thought
- When the overhead of context transfer exceeds the benefit

### Subagent Principles

1. **Parallelize aggressively** — if tasks don't depend on each other, run them simultaneously
2. **Fail fast** — verify prerequisites before starting main work
3. **Keep main context focused** — delegate specialized/verbose work to subagents
4. **Don't duplicate** — if you delegate research, don't also search yourself

---

## Testing Workflows

| Test Type | Suggested Approach |
|-----------|--------------------|
| Unit tests (routing logic) | Run directly with `pytest tests/ -v` |
| Agent behavior tests | pytest with mocked LLM calls |
| Integration tests | Bash subagent (actual API calls, may be slow) |

**Template for test subagent prompt:**
```
Run [test suite] and report:
1. Total pass/fail count
2. Any failures with error messages
3. Whether failures are new or known flaky tests
```

---

## Tips

- **Parallelize aggressively**: If tasks don't depend on each other, run them simultaneously
- **Fail fast**: Verify prerequisites before starting main work
- **Document as you go**: Update docs while context is fresh, not after
- **Lean towards subagents**: For testing, exploration, and long-running operations
- **Observations vs. diagnoses**: When investigating issues, report what you see before jumping to conclusions
