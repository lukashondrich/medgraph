# Prompts Architecture

Two prompts. Design notes sit at the top of each file.

| File | Used by | Output |
|---|---|---|
| `planner.py` | `PlannerAgent` | JSON: which sources, which queries, on-topic or not |
| `writer.py` | `WriterAgent` | The answer the user reads, with evidence keys |

## Writer prompt

`build_prompt()` assembles the system prompt for a turn:

- fixed rules (`SYSTEM_PROMPT`): cite every claim, say only what the quoted text supports, name small studies as small, mention evidence that points the other way, never tie individual risk to ancestry, plain words, one bold next step;
- the turn kind (first interpretation or follow-up);
- the evidence list, one block per item: key, group label, description, what matched, curated summary (reference ranges), verbatim text;
- evidence notes: safety rules that fired, a gap in matched evidence, an uncertain strip reading;
- the response language.

`assign_markers()` gives items their keys in a stable order: safety, reference ranges, matched studies, guidelines, overall.

The profile and reading are not in this prompt: the base agent appends `patient_summary` to every system prompt.

## Planner prompt

Lists the three optional sources and asks for self-contained topical queries. It is told to leave ancestry, age and country out of the queries, because the profile is applied through structured cohort matching.
