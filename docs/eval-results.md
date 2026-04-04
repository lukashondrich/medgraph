# Evaluation Results

**Date:** 2026-03-12
**Python:** 3.11.14 | **Model:** gpt-5.2 (fallback: gemini/gemini-2.5-pro)

---

## Single-Turn Quality (test_quality.py)

20 samples from LiveQA + MedicationQA, each judged by 3 criteria groups.

| Group | Avg Pass Rate | What It Measures |
|-------|--------------|------------------|
| Clinical Quality | 0.808 | Factual alignment, clinical relevance prioritization, actionable completeness |
| Communication | 0.750 | Hedging, register adaptation, empathy, architecture abstraction |
| Questioning | 0.908 | Parsimony, non-redundancy, localization probing, pain characterization, urgency brevity |
| **Overall** | **0.803** | Combined across all groups (threshold: 0.5) |

### Per-Sample Scores

| Query | Overall | Clinical | Comm | Quest |
|-------|---------|----------|------|-------|
| Noonan syndrome and polycystic renal disease | 0.75 | 0.50 | 0.75 | 1.00 |
| Zolmitriptan 5mg gluten content | 0.86 | 0.50 | 1.00 | 1.00 |
| Amphetamine salts 20mg gluten content | 0.88 | 1.00 | 0.75 | 1.00 |
| VDRL positive treatments/precautions | 0.75 | 1.00 | 0.50 | 1.00 |
| GlucaGen HypoKit glucagon content | 0.75 | 0.50 | 0.75 | 1.00 |
| Anesthesia brain damage in FXTAS | 0.89 | 1.00 | 1.00 | 0.50 |
| Ocella and Deep Vein Thrombosis | 0.80 | 1.00 | 0.75 | 0.67 |
| UTI treatments besides cipro/penicillin | 0.88 | 1.00 | 0.75 | 1.00 |
| Streptococcal infection and Wegener's | 0.78 | 1.00 | 0.75 | 0.50 |
| Joint pain meds for type 2 diabetes | 0.75 | 0.50 | 0.75 | 1.00 |
| Secondhand smoke and early AMD | 0.67 | 0.67 | 0.75 | 0.50 |
| Fertilization and molar pregnancy | 0.57 | 0.50 | 0.50 | 1.00 |
| HNPP vs arthritis differentiation | 0.88 | 1.00 | 0.75 | 1.00 |
| Giant Cell Vasculitis symptoms/treatments | 1.00 | 1.00 | 1.00 | 1.00 |
| Fibromyalgia genetic testing | 0.88 | 1.00 | 0.75 | 1.00 |
| Burning mouth syndrome doctors | 0.88 | 1.00 | 0.75 | 1.00 |
| Estradiol 75g patch discontinuation | 0.75 | 0.50 | 0.75 | 1.00 |
| Hydrogen peroxide ear wax removal | 0.88 | 1.00 | 0.75 | 1.00 |
| Sevoflurane stability/toxicity | 0.62 | 0.50 | 0.50 | 1.00 |
| ODD information resources | 0.88 | 1.00 | 0.75 | 1.00 |

---

## Multi-Turn Persona (test_persona.py)

3 simulated patient conversations, judged per-turn (Communication + Questioning) and cross-turn (Conversation Quality).

| Persona | Turns | Pass Rate | Cross-Turn |
|---------|-------|-----------|------------|
| ibuprofen_stomach_pain | 4 | 0.806 | 1.000 |
| severe_chest_pain | 2 | 0.600 | — |
| vague_belly_casual | 4 | 0.781 | 1.000 |
| **Overall** | | **0.729** | (threshold: 0.5) |

### Per-Criterion Breakdown

| Criterion | ibuprofen | chest_pain | vague_belly |
|-----------|-----------|------------|-------------|
| appropriate_hedging | 1.00 (4/4) | 1.00 (2/2) | 1.00 (4/4) |
| architecture_abstraction | 1.00 (4/4) | 1.00 (2/2) | 1.00 (4/4) |
| register_adaptation | 1.00 (4/4) | 0.50 (1/2) | 1.00 (4/4) |
| empathy | 0.50 (2/4) | 1.00 (2/2) | 0.75 (3/4) |
| question_parsimony | 1.00 (4/4) | 0.50 (1/2) | 0.50 (2/4) |
| question_non_redundancy | 1.00 (3/3) | 1.00 (1/1) | 1.00 (4/4) |
| symptom_localization_probing | 1.00 (2/2) | — | 0.67 (2/3) |
| pain_characterization_depth | 0.00 (0/4) | 0.00 (0/2) | 0.00 (0/3) |
| urgency_proportional_brevity | — | 0.00 (0/2) | — |
| conversational_coherence | 1.00 (1/1) | — | 1.00 (1/1) |
| question_non_redundancy_cross_turn | 1.00 (1/1) | — | 1.00 (1/1) |

### Known Weaknesses

- **Pain characterization depth: 0.00 across all personas.** The system never explores both quality (stabbing/burning/dull) and temporal pattern (constant/intermittent) of pain. This is a prompt-level gap — agents need explicit guidance to ask about pain dimensions.
- **Urgency-proportional brevity: 0.00 for chest pain.** Emergency responses are too verbose and don't lead with the action. The system should detect acute scenarios and compress output.
- **Question parsimony:** Occasionally exceeds the 2-question-per-turn limit, particularly in early assessment turns.

---

## Criteria Reference

### Group A: Clinical Quality (needs reference answer)
| Criterion | What It Checks |
|-----------|---------------|
| factual_alignment | Consistent with reference; no invented facts |
| clinical_relevance_prioritization | Causal link in first 2 sentences (conditional) |
| actionable_completeness | At least 1 concrete next step |

### Group B: Communication (no reference needed)
| Criterion | What It Checks |
|-----------|---------------|
| appropriate_hedging | Qualified language + recommends provider |
| register_adaptation | Plain language matching user register |
| empathy | Acknowledges concern; not dismissive |
| architecture_abstraction | No internal system references |

### Group C: Questioning (conditional, no reference needed)
| Criterion | What It Checks | Trigger |
|-----------|---------------|---------|
| question_parsimony | At most 2 questions per turn | Response has questions |
| question_non_redundancy | All questions semantically distinct | 2+ questions |
| symptom_localization_probing | Probes vague anatomy terms | Vague anatomy in query |
| pain_characterization_depth | Explores quality + temporal pattern | Pain reported |
| urgency_proportional_brevity | 3 sentences max, action first | Acute scenario |

### Group D: Conversation (multi-turn only)
| Criterion | What It Checks |
|-----------|---------------|
| conversational_coherence | No re-asked questions; builds on prior info |
| question_non_redundancy_cross_turn | Questions distinct across turns |

---

## How to Reproduce

```bash
source .venv/bin/activate

# Single-turn quality (20 samples, ~80 LLM calls, ~10 min)
pytest tests/eval/test_quality.py -v -s

# Multi-turn persona (3 personas, ~50 LLM calls, ~4 min)
pytest tests/eval/test_persona.py -v -s

# Full eval suite
pytest tests/eval/ -v
```
