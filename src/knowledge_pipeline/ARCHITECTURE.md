# Knowledge Pipeline Architecture

Study records, the corpus build, and the search index.

| File | Purpose |
|---|---|
| `study_schemas.py` | `StudyRecord`, `Cohort`, `CheckInfo`, vocabularies, ancestry hierarchy, YAML load/save, `split_passages()` |
| `corpus.py` | CLI: `draft`, `check`, `build` |
| `pipeline.py` | Haystack/Qdrant helpers (document store, retrieval pipeline) |
| `study_store/` | Qdrant embedded store built from the records |

## Records

One YAML file per paper in `data/corpus/studies/`. A record holds identifiers and link, design, sample size, cohort (ancestry, countries, age range, menopausal status, pregnancy), topics, a one-sentence key finding, the abstract, the licence reported by Europe PMC, and `check` (status, who checked, when, notes).

Controlled vocabularies are enforced (`vocabulary_errors()`). The ancestry hierarchy maps a group to its parent (Indian → South Asian, African American → Black) and deliberately stops there.

## Build steps

```
draft   Europe PMC record -> model drafts the structured fields -> status: unchecked
check   second model pass verifies each field against the abstract -> checked or disputed
build   passages of checked records -> embeddings -> study_store/
```

- Disputed records are corrected by hand (or dropped) and marked checked with a resolution note.
- `load_records()` returns checked records only by default, so an unchecked record can be neither indexed nor cited.
- Passages are two sentences each, verbatim from the abstract, with ids like `pmid-123#p2`. The title is embedded together with the passage.
- Set `CORPUS_CHECK_MODEL` to run the check with a different model than the draft.

## Search

`sentence-transformers/all-MiniLM-L6-v2` (384 dimensions), cosine similarity. The store runs embedded on disk and allows one process at a time; stop the web app before running `build`, the CLI or `tests/eval`.
