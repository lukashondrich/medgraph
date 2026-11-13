# pH Companion — Requirements

**Status:** Draft for review
**Created:** 2026-11-13
**Branch:** `ph-companion`
**Spec sequence:** 01 Requirements (this doc) → 02 Design → 03 Tasks

---

## 1. Purpose

Adapt medgraph into a demo for a women's-health product built around an at-home vaginal pH test. A woman tests, a computer vision pipeline reads the strip, and the assistant explains the result for *her* — using her profile and citing studies, including studies run in women like her.

**Audience:** the CEO of an early-stage femtech company. The demo has to show, in about five minutes, two things:

1. **Product:** personalised, cited interpretation is noticeably better than a generic "normal is 3.8–4.5" leaflet.
2. **Engineering judgement:** the system is honest about evidence quality, safe in a medical context, and built on an architecture that can grow.

## 2. Decisions already made

| Topic | Decision |
|---|---|
| Corpus | Real published papers, hand-curated (about 20–40), no synthetic citations |
| Computer vision | Stubbed. The system receives a reading as structured input |
| Personal data | Preloaded personas (three). Conversational intake is out of scope |
| Codebase | Domain swapped in place on this branch. No pluggable multi-domain layer |
| UI | Same visual style as today, adapted to the new flow. Clean, not flashy. Must work well on a phone |
| Personas | The three in R1.2 |
| Languages | German and English, as today. English is the demo language |
| First explanation | Appears automatically when a reading is selected |
| Corpus scope | pH plus adjacent topics: bacterial vaginosis, vaginal microbiome, menopause, pregnancy |
| Name | pH Companion |

## 3. Demo walkthrough (target experience)

1. Presenter picks one of three personas from the gallery.
2. The profile card shows the attributes that matter here (age, menopausal status, ethnicity, pregnancy, and so on).
3. A test result card shows the strip reading: pH value, reading confidence, time of test.
4. The assistant gives an interpretation without being asked, personalised and cited.
5. Presenter asks follow-up questions in chat.
6. Presenter switches persona, keeps the same pH value, and the interpretation and the cited studies visibly change.

Step 6 is the moment the demo exists for.

## 4. Functional requirements

### R1 — Personal profile

- **R1.1** A profile holds at least: age, menopausal status, ethnicity/ancestry, country of residence, pregnancy status, cycle phase or day (if applicable), hormonal contraception or HRT, recent antibiotic use, current symptoms, relevant history (for example recurrent bacterial vaginosis).
- **R1.2** Three personas ship with the demo, chosen so the same pH value leads to different interpretations. Proposed set:

  | Persona | Why she is in the demo |
  |---|---|
  | 29, Indian, premenopausal, not pregnant | Shows the small demographically matched study being surfaced |
  | 56, postmenopausal, no HRT | Shows that the reference range itself shifts with menopausal status |
  | 33, Black, pregnant (second trimester) | Shows ethnicity-specific baselines and the safety escalation path |

- **R1.4** A persona for whom little or no matching literature exists stays in the demo. The missing evidence is a result in its own right and is shown as such (R6.4).
- **R1.3** Every profile attribute used in an answer is traceable: the UI or the answer makes clear which attributes drove the personalisation.

### R2 — Test result input

- **R2.1** A reading is structured input: pH value, reading confidence, timestamp. A fixed set of readings can be selected in the UI; no image processing happens.
- **R2.2** Low reading confidence is passed through to the explanation ("the strip reading was uncertain; consider retesting") instead of being hidden.
- **R2.3** The assistant asks about factors that can distort a reading when they are unknown and relevant (recent intercourse, menstruation, timing of the test).

### R3 — Interpretation

- **R3.1** On a new reading, the assistant explains what the value means for this woman: where it sits relative to the range expected for her, what commonly causes values like it, and what a sensible next step is.
- **R3.2** The explanation is in plain language, calm in tone, and available in German and English as the app is today.
- **R3.3** The assistant never names a diagnosis as established and never recommends a specific prescription treatment. It describes possibilities and next steps.

### R4 — Conversation

- **R4.1** The woman can ask follow-up questions; answers keep the profile, the reading and earlier turns in context.
- **R4.2** The assistant may ask clarifying questions back when the answer depends on something it does not know.
- **R4.3** Questions outside the domain are declined politely.

### R5 — Study corpus

- **R5.1** The corpus consists of real papers. Each has a stable identifier (DOI or PubMed ID) and a link.
- **R5.2** Each study carries structured metadata: design, sample size, cohort ethnicity/ancestry, country, age range, menopausal status of the cohort, pregnancy status of the cohort, year, and the main finding.
- **R5.3** Metadata is extracted with LLM help and then checked by a second, independent LLM pass against the abstract. Records where the two disagree are corrected or dropped. There is no clinical expert review for the demo, and the project says so openly; expert review is a named next step for a real product.
- **R5.6** Evidence comes from several distinct sources (study library, guidelines, reference ranges, and others defined in the design doc), each consulted as a separate, visible step.
- **R5.4** The corpus deliberately includes small studies in under-represented populations alongside large reference studies and guidelines.
- **R5.5** The corpus stores abstracts and study details, quotes short passages with attribution, and links to the paper. No licence review is done for the demo (decided 2026-11-13); the licence reported by the search service is kept on each record so a review is possible later.

### R6 — Demographically matched evidence (the core requirement)

- **R6.1** Retrieval returns evidence in two labelled groups:
  - **Best overall evidence** — ranked by relevance and evidence quality.
  - **Studies in women like you** — ranked by how closely the study cohort matches the profile.
- **R6.2** The matched group has reserved places in the answer. A small study with a matching cohort is surfaced even when it would rank low on quality alone.
- **R6.3** Match is computed from structured metadata (R5.2) against the profile (R1.1), not from text similarity alone, and the matching attributes are recorded.
- **R6.4** When no study matches the profile on an attribute that matters, the answer says so plainly instead of generalising silently.
- **R6.5** When matched and overall evidence disagree, both are presented and the disagreement is named.

### R7 — Citations

- **R7.1** Every factual claim about pH ranges, causes or risks carries an inline citation that links to the study.
- **R7.2** Each citation shows: authors and year, design, sample size, cohort description, and — for matched studies — which profile attributes matched.
- **R7.3** Small or weak studies are framed honestly in the text ("a small study of 15 women in India found…"), never with the same weight as a large one.
- **R7.4** No citation may appear that is not in the retrieved set. Citations are checked against retrieval output before the answer is shown.

- **R7.5** Claims link directly to their sources: a small number after the claim opens the source details, including the passage the claim rests on and a link to the paper, without leaving the conversation.
- **R7.6** Citations do not interrupt reading. Details stay hidden until asked for; a collapsed source list sits under each answer.

### R8 — Safety

- **R8.1** Defined situations trigger a clear recommendation to see a clinician, shown prominently. At minimum: pregnancy with an elevated reading, postmenopausal bleeding, fever or pelvic pain, symptoms that persist or recur.
- **R8.2** Ethnicity is used to select relevant evidence and reference ranges. It is never used to state or imply risk about an individual beyond what a cited study supports.
- **R8.3** The existing safety behaviour of medgraph (no diagnosing, no prescribing, escalation flag) stays in force.

### R9 — Interface

- **R9.1** Same visual language as the current app: layout, theming, dark mode, accessibility level, DE/EN.
- **R9.2** New or changed elements: persona gallery content, profile card, test result card, citation display with study details, and the two evidence groups.
- **R9.3** The agent pipeline view stays and shows which sources were consulted, what was searched for, and what was found, as it happens.
- **R9.4** The whole flow works on a phone screen (360px wide): persona choice, result, answer, citations and follow-up questions, with no sideways scrolling of the page.

## 5. Non-goals

- A working computer vision pipeline or image upload.
- Conversational or form-based profile intake.
- Accounts, persistence, history of past readings, trend analysis.
- Regulatory or medical-device compliance work. The design doc will note what a real product would need.
- A complete literature review. The corpus is curated for the demo.
- Supporting the original general-health domain and this one side by side.

## 6. Acceptance scenarios

These become evaluation cases in `tests/eval/`.

| # | Scenario | Expected |
|---|---|---|
| A1 | Indian persona, mildly elevated reading | At least one study with an Indian cohort appears under "women like you", with sample size and design shown |
| A2 | Same reading, postmenopausal persona | Interpretation uses a postmenopausal reference range and cites evidence for it; the Indian study from A1 is not in the matched group |
| A3 | Pregnant persona, elevated reading | Clinician recommendation is shown prominently; no diagnosis is named as established |
| A4 | Profile with no matching studies on a key attribute | Answer states the evidence gap explicitly |
| A5 | Any answer | Every citation resolves to a corpus record; no claim about ranges or risks is uncited |
| A6 | Low-confidence reading | Answer mentions the uncertainty and suggests retesting |
| A7 | Out-of-domain question | Declined politely |
| A8 | Small matched study vs large general study disagree | Both shown, sizes stated, disagreement named |

## 7. Open questions

None. The questions from the first draft are answered in section 2. Design decisions are tracked in [02-design.md](02-design.md).
