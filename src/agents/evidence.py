"""Evidence retrieval agent — RAG over Qdrant clinical guidelines."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.models.state import HealthcareState
from src.prompts.evidence import SYSTEM_PROMPT

from .base import HealthcareAgent

logger = logging.getLogger(__name__)


def retrieve_evidence(query: str, patient_summary: str = "") -> dict[str, Any]:
    """Retrieve clinical guidelines from Qdrant.

    Args:
        query: The user's question.
        patient_summary: Patient context for query expansion.

    Returns:
        Dict with evidence_context and citations.
    """
    try:
        from src.knowledge_pipeline.pipeline import (
            build_retrieval_pipeline,
            get_document_store,
            DEFAULT_QDRANT_PATH,
        )

        # Use the pre-indexed store shipped with the project
        store_path = Path(__file__).parent.parent / "knowledge_pipeline" / "qdrant_store"
        if not store_path.exists():
            logger.warning("Qdrant store not found at %s", store_path)
            return {"evidence_context": {}, "citations": []}

        doc_store = get_document_store(location=str(store_path))
        pipeline = build_retrieval_pipeline(doc_store, top_k=5)

        # Expand query with patient conditions if available
        expanded_query = query
        if patient_summary:
            # Extract key terms from patient summary for better retrieval
            expanded_query = f"{query} {patient_summary[:200]}"

        result = pipeline.run({"embedder": {"text": expanded_query}})
        documents = result.get("retriever", {}).get("documents", [])

        evidence_context = {}
        citations = []
        for doc in documents:
            meta = doc.meta or {}
            source_id = meta.get("guideline_id", f"doc-{doc.id[:8]}" if doc.id else "unknown")
            evidence_context[source_id] = doc.content or ""
            citations.append({
                "source": source_id,
                "tier": meta.get("confidence_tier", "unknown"),
                "grade": meta.get("recommendation_grade"),
                "text": (doc.content or "")[:200],
            })

        return {"evidence_context": evidence_context, "citations": citations}

    except Exception as e:
        logger.warning("Evidence retrieval failed: %s", e)
        return {"evidence_context": {}, "citations": []}


class EvidenceAgent(HealthcareAgent):
    """Retrieves clinical guidelines from Qdrant knowledge base."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(name="evidence", system_prompt=SYSTEM_PROMPT, model=model)

    async def process(self, state: HealthcareState) -> dict:
        query = state.get("user_input", "")
        patient_summary = state.get("patient_summary", "")

        # Retrieve evidence from knowledge base
        retrieval = retrieve_evidence(query, patient_summary)

        # Format a summary for the specialist_outputs
        evidence_texts = list(retrieval["evidence_context"].values())
        if evidence_texts:
            summary = "Relevant clinical guidelines:\n\n" + "\n\n".join(
                f"[{i+1}] {text[:300]}" for i, text in enumerate(evidence_texts)
            )
        else:
            summary = "No relevant clinical guidelines found for this query."

        return {
            "specialist_outputs": {self.name: summary},
            "handoff_chain": [self.name],
            "safety_escalation": False,
            "evidence_context": retrieval["evidence_context"],
            "citations": retrieval["citations"],
        }
