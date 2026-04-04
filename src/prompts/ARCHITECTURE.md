# Prompts Architecture

## Overview

System prompt definitions for all seven agents. Each prompt defines a role, expertise boundaries, guardrails, and output expectations. The prompts module has no code dependencies — it exports plain strings consumed by the agents module.

**Related docs:** [Agents](../agents/ARCHITECTURE.md) · [Quality criteria](../../docs/quality-criteria.md) · [Specialist feedback](../../docs/specialist-feedback.md)

## Interface & Exports

Every file exports a `SYSTEM_PROMPT: str` constant. The synthesizer additionally exports `build_prompt()` for injecting runtime context (specialist outputs, evidence, citations, drug interactions, safety notices).

```
src/prompts/
  __init__.py         # re-exports SYSTEM_PROMPT constants
  router.py           # SYSTEM_PROMPT — JSON classifier, no user-facing text
  symptom.py          # SYSTEM_PROMPT — triage specialist
  medication.py       # SYSTEM_PROMPT — drug info specialist
  lifestyle.py        # SYSTEM_PROMPT — wellness specialist
  evidence.py         # SYSTEM_PROMPT — clinical guideline retrieval
  drug_check.py       # SYSTEM_PROMPT — drug interaction screening
  synthesizer.py      # SYSTEM_PROMPT + build_prompt() — response merger
```

## Design Philosophy

**Separation of concerns:** Specialists produce domain-accurate content; the synthesizer makes it conversational. This means:
- Specialist prompts can be thorough and technical without worrying about tone consistency
- The synthesizer focuses on coherence, empathy, and natural conversation flow
- Changes to one agent's personality don't ripple through the system

**Self-contained prompts:** Each agent understands its full role from its prompt alone. No prompt depends on another prompt's content.

**Guardrails embedded in role definition:** Guardrails are repeated in every prompt rather than injected programmatically. LLMs respond better to constraints that are part of their role definition.

## Shared Guardrails

All seven prompts include these constraints:
1. Part of a healthcare information system — does not replace professional medical advice
2. Never diagnose conditions or prescribe treatments
3. Flag emergencies clearly and recommend immediate medical attention
4. Maintain professional, empathetic tone
5. Acknowledge when a question is outside expertise

## Communication Style Pattern

All specialist prompts and the synthesizer share a consistent communication style:
- Use the patient's own words and register (casual input gets conversational response)
- Use **bold** for questions and action recommendations
- Limit to 1-2 clarifying questions per turn (question parsimony)
- Lead with clinical relevance, acknowledge prior information
- Keep responses brief when the situation is urgent

This consistency prevents jarring tone shifts when the synthesizer merges multiple specialist outputs.

## Safety Mechanism

Specialists are prompted to include `[SAFETY_ESCALATION]` in their response when they detect emergencies (chest pain, dangerous drug interactions, severe symptoms, etc.). The base agent class detects this marker and sets the state flag. The synthesizer:
1. Reads the `safety_escalation` flag
2. Injects a safety notice block into its dynamic prompt via `build_prompt()`
3. Integrates the disclaimer naturally into the response
4. Strips the marker from the final output

**Why markers over code heuristics:** The LLM understands medical context better than keyword matching. "Chest pain after exercise in a 25-year-old" is different from "chest pain with shortness of breath in a 60-year-old" — the LLM can make this judgment.

## Synthesizer Dynamic Prompt (`build_prompt()`)

```python
build_prompt(
    specialist_outputs: dict[str, str],
    safety_escalation: bool = False,
    evidence_context: dict[str, str] | None = None,
    citations: list[dict] | None = None,
    drug_interactions: list[dict] | None = None,
) -> str
```

Builds the full synthesizer system prompt at runtime. Injects up to 5 optional sections:
1. **Specialist Outputs** — each specialist's response, labeled by agent name
2. **Retrieved Evidence** — clinical guideline excerpts from Qdrant (if present)
3. **Citations** — source attribution with confidence tier and grade (if present)
4. **Drug Interaction Screening Results** — interaction details with severity (if present)
5. **Safety Notice** — injected when `safety_escalation=True`

Empty sections are omitted entirely — the prompt stays clean when not all agents are routed.

## Clinical Frameworks

Medical professional feedback referenced structured clinical frameworks:
- **SOCRATES** (Site, Onset, Character, Radiation, Associations, Time, Exacerbating/relieving, Severity) — pain assessment
- **OLDCARTS** (Onset, Location, Duration, Character, Aggravating, Relieving, Temporal, Severity) — symptom history
- **Calgary-Cambridge** — consultation structure

These frameworks informed the prompt design (clarifying question patterns, severity assessment approach) but are not explicitly encoded as structured steps. See `docs/specialist-feedback.md` for the full feedback.

## Quality Criteria Integration

Prompts encode several criteria from `docs/quality-criteria.md`:

| Criterion | How encoded |
|-----------|------------|
| Question Parsimony | "Limit yourself to one or two clarifying questions per turn" |
| Register Adaptation | "Use the patient's own words and register" |
| Architecture Abstraction | "Never reference internal system components" in guardrails |
| Actionable Completeness | Specialists prompted to provide practical next steps |
| Urgency-Proportional Brevity | "Keep responses brief when urgent" |
| Clinical Relevance Prioritization | "Lead with clinical relevance" |

## Domain Boundaries

| Agent | Focus | Cannot do |
|-------|-------|-----------|
| Router | Intent classification, specialist selection | Respond to user, provide advice |
| Symptom | Severity assessment, clarifying questions, emergency flagging | Diagnose, prescribe |
| Medication | Drug info, interactions, side effects | Prescribe, recommend dosage changes |
| Lifestyle | Diet, exercise, daily management | Provide medical treatment advice |
| Evidence | Clinical guideline retrieval, citation formatting | Fabricate evidence, provide recommendations directly |
| Drug Check | Medication pair screening, severity classification | Make dosage changes, diagnose |
| Synthesizer | Merge outputs, maintain conversation flow | Add medical claims not from specialists |
