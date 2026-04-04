"""Haystack pipeline templates for the knowledge pipeline.

Provides reusable indexing and retrieval pipelines that sub-agents use
to process guidelines into Qdrant.
"""

from pathlib import Path
from haystack import Document, Pipeline
from haystack.components.converters import PyPDFToDocument
from haystack.components.preprocessors import DocumentCleaner, DocumentSplitter
from haystack.components.embedders import (
    SentenceTransformersDocumentEmbedder,
    SentenceTransformersTextEmbedder,
)
from haystack.components.writers import DocumentWriter
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever

# Default embedding model — small, fast, good enough for medical text retrieval
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384

# Qdrant collection name for guidelines
GUIDELINES_COLLECTION = "clinical_guidelines"

# Default persistent storage path (Qdrant embedded mode, no Docker needed)
DEFAULT_QDRANT_PATH = "knowledge_pipeline/qdrant_store"


def get_document_store(
    location: str = ":memory:",
    collection_name: str = GUIDELINES_COLLECTION,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    recreate: bool = False,
) -> QdrantDocumentStore:
    """Create or connect to a Qdrant document store.

    Args:
        location: ":memory:" for in-memory, a filesystem path for on-disk
                  persistence, or a URL (http://...) for a Qdrant server.
        collection_name: Name of the Qdrant collection.
        embedding_dim: Dimension of the embedding vectors.
        recreate: If True, drop and recreate the collection.
    """
    if location == ":memory:":
        return QdrantDocumentStore(
            location=":memory:",
            index=collection_name,
            embedding_dim=embedding_dim,
            recreate_index=recreate,
        )
    elif location.startswith("http"):
        return QdrantDocumentStore(
            url=location,
            index=collection_name,
            embedding_dim=embedding_dim,
            recreate_index=recreate,
        )
    else:
        # Local filesystem path — Qdrant embedded on-disk mode
        # force_disable_check_same_thread: allows cross-thread usage when
        # we handle serialization externally (backend.agents.retrieval._pipeline_lock)
        return QdrantDocumentStore(
            path=location,
            index=collection_name,
            embedding_dim=embedding_dim,
            recreate_index=recreate,
            force_disable_check_same_thread=True,
        )


def build_pdf_indexing_pipeline(
    document_store: QdrantDocumentStore,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    split_by: str = "sentence",
    split_length: int = 5,
    split_overlap: int = 1,
) -> Pipeline:
    """Build a pipeline that reads a PDF, splits, embeds, and stores in Qdrant.

    This is the default pipeline. Sub-agents may modify split parameters
    based on the specific guideline's structure.

    Args:
        document_store: Target Qdrant store.
        embedding_model: Sentence transformer model name.
        split_by: Split unit — "sentence", "word", or "page".
        split_length: Number of units per chunk.
        split_overlap: Overlap between chunks.
    """
    pipeline = Pipeline()
    pipeline.add_component("converter", PyPDFToDocument())
    pipeline.add_component("cleaner", DocumentCleaner(
        remove_empty_lines=True,
        remove_extra_whitespaces=True,
    ))
    pipeline.add_component("splitter", DocumentSplitter(
        split_by=split_by,
        split_length=split_length,
        split_overlap=split_overlap,
    ))
    pipeline.add_component("embedder", SentenceTransformersDocumentEmbedder(
        model=embedding_model,
    ))
    pipeline.add_component("writer", DocumentWriter(
        document_store=document_store,
    ))

    pipeline.connect("converter", "cleaner")
    pipeline.connect("cleaner", "splitter")
    pipeline.connect("splitter", "embedder")
    pipeline.connect("embedder", "writer")

    return pipeline


def build_document_indexing_pipeline(
    document_store: QdrantDocumentStore,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Pipeline:
    """Build a pipeline that takes pre-processed Document objects, embeds, and stores.

    Use this when the sub-agent handles its own splitting/chunking logic
    (e.g., for tables, recommendation extraction, or custom section parsing).

    Args:
        document_store: Target Qdrant store.
        embedding_model: Sentence transformer model name.
    """
    pipeline = Pipeline()
    pipeline.add_component("embedder", SentenceTransformersDocumentEmbedder(
        model=embedding_model,
    ))
    pipeline.add_component("writer", DocumentWriter(
        document_store=document_store,
    ))

    pipeline.connect("embedder", "writer")

    return pipeline


def build_retrieval_pipeline(
    document_store: QdrantDocumentStore,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    top_k: int = 5,
) -> Pipeline:
    """Build a query pipeline for testing retrieval quality.

    Args:
        document_store: Qdrant store to search.
        embedding_model: Must match the model used for indexing.
        top_k: Number of results to return.
    """
    pipeline = Pipeline()
    pipeline.add_component("embedder", SentenceTransformersTextEmbedder(
        model=embedding_model,
    ))
    pipeline.add_component("retriever", QdrantEmbeddingRetriever(
        document_store=document_store,
        top_k=top_k,
    ))

    pipeline.connect("embedder", "retriever")

    return pipeline
