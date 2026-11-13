# pH Companion — Demo Script

About five minutes. Have the app running (`uvicorn src.api:app --port 8000`) and open it on a phone or a narrow browser window. Run through once beforehand: the first request after start takes about 13 seconds, later ones 5 to 6.

## 1. The situation (30 seconds)

"A woman has just used a pH test strip at home. The camera read the strip; that part is simulated here. What she gets today is a leaflet that says normal is 3.8 to 4.5. What she should get is an answer for her."

## 2. Priya: studies in women like her (90 seconds)

1. Tap **Priya**. Open the profile card: 29, Indian ancestry, lives in Germany.
2. Tap **pH 4.8**. Point at the lookup card while it runs: safety check, reference ranges, study library ("3 in women like you"), guidelines.
3. Read the first paragraph aloud. Then the second: what studies in Indian women found, and what they did not look at.
4. Tap a **green number**. Show the card: study, size, "Matches you: Indian ancestry", "Run in: India", the quoted passage, the link.

Say: "The system knows this study was run in India and she lives in Germany. It matches on ancestry and shows the difference."

## 3. Anna: same number, different meaning (60 seconds)

1. Tap **Anna**. The same pH 4.8 is explained again without touching the reading.
2. The answer now says 4.8 is on the acidic side for after menopause, where 6.0 is typical without hormone therapy.
3. Open **Sources**: different studies from Priya's.

Say: "Same strip, same number, different woman, different answer. That is the product."

## 4. Amara: safety is not left to the model (60 seconds)

1. Tap **Amara**, pregnant, second trimester.
2. The notice appears above the answer: show this to your midwife or doctor.
3. Open the lookup card: "Safety check: 1 reason to see a clinician".

Say: "This rule is four lines in a table, tested, with the study behind it. The language model writes around it; it does not decide it."

## 5. Honesty about evidence (60 seconds)

Pick one, depending on the audience:

- **A gap.** With Priya selected, ask: *"Could antibiotics I took last month explain it?"* The answer says the library has no study on that.
- **A disagreement.** With Amara selected, ask: *"Does testing my pH at home during pregnancy actually help prevent preterm birth?"* A large German trial found no benefit; an earlier German programme reported one. Check beforehand that both appear; in testing the answer named both in about half the runs.
- **Off-topic.** Ask about laptops. Nothing is looked up, and it declines.

## 6. What is underneath (30 seconds)

- 63 real papers, one reviewed record each, in the repository.
- Every citation is checked against what was actually retrieved; a citation that was not retrieved cannot appear.
- Ranking, reference ranges and safety rules are ordinary code with tests.

## If asked

| Question | Answer |
|---|---|
| Who checked the studies? | Two model passes; 37 of 63 records were disputed and corrected. No clinician yet — that is the first thing a real product needs. |
| Is this a medical device? | No. It would need regulatory work that has not been started. |
| Why does a 40-woman study show up? | On purpose, and labelled as small. For many women it is the only evidence in women like them. |
| What about a woman no study matches? | She is told so. |
| Where does the pH come from? | Simulated. The strip-reading step is a fixed input with a confidence value. |
