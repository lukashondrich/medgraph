# Specialist Agent Feedback

Collecting feedback from medical professionals, clinical frameworks, and testing before revising prompts.

---

## General (All Specialists)

### From medical professional (2026-03-11)

- **Patients describe symptoms incorrectly.** They have difficulty localizing -- e.g., "stomach cramps" may actually be lower abdomen. Agents must probe and clarify location, not take patient descriptions at face value.
- **Don't ask redundant questions.** E.g., "When did the cramps start?" and "How long have you been experiencing them?" are essentially the same question. Consolidate.

---

## Symptom Agent

### From medical professional (2026-03-11)

- **Pain characterization is critical.** When a patient reports pain, always explore:
  - **Quality:** stabbing, pressing, burning, dull, cramping, throbbing, sharp
  - **Temporal pattern:** constant, intermittent, comes and goes completely, waxing/waning
  - **Location accuracy:** probe beyond the patient's initial description (see general note above)
- Reference: Hamburger Untersuchungsmanual approach to pain assessment

### From framework review (2026-03-11)

- Current prompt says "ask clarifying questions about onset, duration, severity, associated symptoms" but doesn't give the agent a structured method. Consider embedding SOCRATES (Site, Onset, Character, Radiation, Associated symptoms, Time course, Exacerbating/relieving factors, Severity) or OLDCARTS as a systematic framework.
- Calgary-Cambridge model could improve consultation flow (initiating, gathering info, explaining, closing).

---

## Medication Agent

### From framework review (2026-03-11)

- No feedback yet from medical professionals. Placeholder for incoming.

---

## Lifestyle Agent

### From framework review (2026-03-11)

- No feedback yet from medical professionals. Placeholder for incoming.

---

## Synthesizer

- No feedback yet. Placeholder.

---

## Sources / References

- [SOCRATES mnemonic - Geeky Medics](https://geekymedics.com/the-socrates-acronym-in-history-taking/)
- [OLDCARTS - Osmosis](https://www.osmosis.org/answers/old-carts-history-taking-mnemonic)
- [Calgary-Cambridge Model - Wikipedia](https://en.wikipedia.org/wiki/Calgary%E2%80%93Cambridge_model)
- [StatPearls - Medical History (open access)](https://www.ncbi.nlm.nih.gov/books/NBK534249/)
- [Geeky Medics OSCE Guides (free)](https://geekymedics.com/osce-guides/)
- Thieme "Checkliste Anamnese und klinische Untersuchung" (Neurath & Lohse, 5th ed.) -- paywall, ~51 EUR
- Hamburger Untersuchungsmanual -- referenced by medical professional for pain assessment methodology
