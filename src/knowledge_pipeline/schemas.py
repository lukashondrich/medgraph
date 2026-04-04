"""Metadata schema for guideline chunks in the knowledge pipeline.

Every chunk stored in Qdrant must carry this metadata so that retrieval
can filter, rank, and attribute sources correctly.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Confidence Tiers ──────────────────────────────────────────────────────

class ConfidenceTier(str, Enum):
    """Maps to the data-source confidence hierarchy.

    Tier 1: Regulatory (FDA labels, EMA) — "This IS the official guidance"
    Tier 2: Guideline (ADA, NICE, STIKO, WHO) — "Expert consensus recommends"
    Tier 3: Strong evidence (Cochrane, meta-analyses) — "Multiple studies show"
    Tier 4: Emerging evidence (single RCTs, observational) — "Research suggests"
    """
    REGULATORY = "regulatory"
    GUIDELINE = "guideline"
    STRONG_EVIDENCE = "strong_evidence"
    EMERGING_EVIDENCE = "emerging_evidence"


class RecommendationGrade(str, Enum):
    """Standardized evidence grades across guideline systems.

    Different orgs use different scales (NICE: strong/conditional,
    ADA: A/B/C/E, GRADE: high/moderate/low/very_low). We normalize
    to a 4-level scale for consistent retrieval and display.
    """
    STRONG = "strong"          # NICE strong, ADA A, GRADE high
    MODERATE = "moderate"      # ADA B, GRADE moderate
    WEAK = "weak"              # NICE conditional, ADA C, GRADE low
    EXPERT_OPINION = "expert"  # ADA E, consensus without trial data


# ── Chunk Metadata ────────────────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """Metadata attached to every chunk stored in Qdrant.

    This schema is the contract between the indexing pipeline (sub-agents)
    and the retrieval pipeline (patient-facing agents). Both sides must
    agree on these fields.
    """

    # Source identification
    guideline_id: str = Field(
        description="Unique identifier for the source guideline, e.g. 'ADA-SOC-2025', 'NICE-NG28'"
    )
    organization: str = Field(
        description="Publishing organization, e.g. 'ADA', 'NICE', 'STIKO', 'WHO'"
    )
    document_title: str = Field(
        description="Full title of the source document"
    )
    publication_year: int = Field(
        description="Year of publication or last update"
    )

    # Content classification
    section_title: str = Field(
        description="Section/chapter title within the guideline"
    )
    section_number: Optional[str] = Field(
        default=None,
        description="Section number if available, e.g. '9.1', 'Chapter 6'"
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Medical conditions this chunk is relevant to, e.g. ['type_2_diabetes', 'hypertension']"
    )
    medications: list[str] = Field(
        default_factory=list,
        description="Medications mentioned in this chunk"
    )
    populations: list[str] = Field(
        default_factory=list,
        description="Target populations, e.g. ['adults', 'elderly', 'pediatric', 'pregnant']"
    )

    # Evidence quality
    confidence_tier: ConfidenceTier = Field(
        description="Which confidence tier this source belongs to"
    )
    recommendation_grade: Optional[RecommendationGrade] = Field(
        default=None,
        description="Evidence grade of the recommendation (if this chunk contains a recommendation)"
    )
    original_grade: Optional[str] = Field(
        default=None,
        description="The original grade as stated in the guideline, e.g. 'Grade A', 'Strong recommendation'"
    )

    # Chunking provenance
    chunk_strategy: str = Field(
        description="How this chunk was created, e.g. 'section_split', 'recommendation_extract', 'table_row'"
    )
    page_numbers: Optional[str] = Field(
        default=None,
        description="Page range in the source PDF, e.g. '45-47'"
    )

    def to_flat_dict(self) -> dict:
        """Convert to a flat dict suitable for Qdrant metadata storage.

        Qdrant metadata supports strings, ints, floats, bools, and lists of strings.
        Enum values are converted to their string values.
        """
        d = self.model_dump()
        # Convert enums to strings
        d["confidence_tier"] = self.confidence_tier.value
        if self.recommendation_grade:
            d["recommendation_grade"] = self.recommendation_grade.value
        return d
