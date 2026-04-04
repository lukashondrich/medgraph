# Knowledge Pipeline Architecture

## Overview

Haystack-based indexing and retrieval pipelines backed by a Qdrant embedded vector store. Provides semantic search over clinical guidelines for the Evidence agent's RAG retrieval.

The pre-indexed Qdrant store ships with the project — no Docker or external Qdrant server needed.

**Related docs:** [Evidence agent](../agents/ARCHITECTURE.md) (primary consumer) · [Models](../models/ARCHITECTURE.md) (evidence_context + citations in state)

## Dependencies

- `haystack-ai` — pipeline framework (indexing + retrieval)
- `qdrant-haystack` — Qdrant document store integration
- `qdrant-client` — Qdrant vector database client
- `sentence-transformers` — embedding model
- No dependency on agents/, orchestrator/, or data/

## Directory Structure

```
src/knowledge_pipeline/
  __init__.py
  pipeline.py          # Pipeline templates: get_document_store(), build_*_pipeline()
  schemas.py           # ConfidenceTier, RecommendationGrade, ChunkMetadata
  qdrant_store/        # Pre-indexed SQLite-based Qdrant embedded store
    .lock
    meta.json
    collection/        # clinical_guidelines collection data
```

## Schemas (`schemas.py`)

Metadata contract between indexing and retrieval:

### `ConfidenceTier` (str Enum)
Maps to a data-source confidence hierarchy:
- `regulatory` — FDA labels, EMA ("This IS the official guidance")
- `guideline` — ADA, NICE, WHO ("Expert consensus recommends")
- `strong_evidence` — Cochrane, meta-analyses ("Multiple studies show")
- `emerging_evidence` — Single RCTs, observational ("Research suggests")

### `RecommendationGrade` (str Enum)
Normalized from different grading systems (NICE strong/conditional, ADA A/B/C/E, GRADE):
- `strong`, `moderate`, `weak`, `expert`

### `ChunkMetadata` (Pydantic BaseModel)
Every chunk in Qdrant carries this metadata:
- **Source identification:** guideline_id, organization, document_title, publication_year
- **Content classification:** section_title, conditions, medications, populations
- **Evidence quality:** confidence_tier, recommendation_grade, original_grade
- **Chunking provenance:** chunk_strategy, page_numbers

`to_flat_dict()` converts to Qdrant-compatible format (strings, ints, lists of strings).

## Pipeline Templates (`pipeline.py`)

### `get_document_store(location, collection_name, embedding_dim, recreate)`
Three modes:
- **In-memory** (`":memory:"`) — for tests
- **Filesystem** (path string) — Qdrant embedded on-disk mode with SQLite backend
- **Server** (URL) — remote Qdrant instance

Uses `force_disable_check_same_thread=True` for filesystem mode to allow cross-thread usage.

### `build_pdf_indexing_pipeline(document_store, ...)`
Full pipeline: `PyPDFToDocument → DocumentCleaner → DocumentSplitter → SentenceTransformersDocumentEmbedder → DocumentWriter`

Configurable: split_by (sentence/word/page), split_length, split_overlap.

### `build_document_indexing_pipeline(document_store, ...)`
For pre-processed Document objects (custom splitting): `SentenceTransformersDocumentEmbedder → DocumentWriter`

### `build_retrieval_pipeline(document_store, ...)`
Query pipeline: `SentenceTransformersTextEmbedder → QdrantEmbeddingRetriever`

Configurable top_k (default 5).

## Configuration

| Setting | Value |
|---------|-------|
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimensions | 384 |
| Collection name | `clinical_guidelines` |
| Default persistent path | `knowledge_pipeline/qdrant_store` |

## Pre-indexed Store

- Ships as SQLite-based Qdrant embedded store in `qdrant_store/`
- Contains indexed clinical guideline chunks
- No Docker or external Qdrant server needed for the demo
- Evidence agent connects to this store at runtime via `get_document_store()`

## Integration

The Evidence agent (`src/agents/evidence.py`) is the primary consumer:
1. Calls `get_document_store()` with the persistent path
2. Builds a retrieval pipeline via `build_retrieval_pipeline()`
3. Runs query expansion (appends patient conditions to the query)
4. Returns top-k results as `evidence_context` and `citations` in state

Graceful degradation: if the Qdrant store is not found, the evidence agent returns empty results and the system continues without evidence grounding.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Qdrant embedded | SQLite backend, no server | Zero-infra demo; ships with the project |
| sentence-transformers | all-MiniLM-L6-v2 | Small (80MB), fast, good retrieval quality for medical text |
| Haystack pipelines | Template functions | Reusable; indexing and retrieval are separate concerns |
| Metadata schema | Pydantic ChunkMetadata | Typed contract between indexing and retrieval |
