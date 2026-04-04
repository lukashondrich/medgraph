"""Pydantic v2 output models for OpenFDA drug interaction tools.

These models define the typed return values from all tool functions.
Follows project conventions: Field descriptions, str Enums, docstrings.
"""

from typing import Optional

from pydantic import BaseModel, Field, computed_field


class DrugIdentity(BaseModel):
    """Resolved drug identity from OpenFDA."""

    query_name: str = Field(
        description="The input name from the patient record"
    )
    generic_name: str = Field(
        description="FDA generic name, e.g. 'METFORMIN HYDROCHLORIDE'"
    )
    brand_names: list[str] = Field(
        default_factory=list,
        description="Known brand names from the label"
    )
    is_combo_product: bool = Field(
        default=False,
        description="Whether the original medication was a combination product"
    )


class LabelSectionContent(BaseModel):
    """One parsed section from an FDA drug label."""

    section: str = Field(
        description="Section key, e.g. 'drug_interactions', 'boxed_warning'"
    )
    raw_text: str = Field(
        description="Cleaned text content"
    )
    character_count: int = Field(
        description="Length of raw_text"
    )


class DrugLabelResult(BaseModel):
    """Complete FDA label data for one drug."""

    drug: DrugIdentity = Field(
        description="Resolved drug identity"
    )
    sections: dict[str, LabelSectionContent] = Field(
        default_factory=dict,
        description="Available label sections keyed by section name"
    )
    set_id: Optional[str] = Field(
        default=None,
        description="DailyMed set_id for citation"
    )
    effective_date: Optional[str] = Field(
        default=None,
        description="Label effective date (YYYYMMDD format)"
    )

    @computed_field
    @property
    def has_boxed_warning(self) -> bool:
        """Whether this drug has a boxed (black box) warning."""
        return "boxed_warning" in self.sections

    @computed_field
    @property
    def has_interactions(self) -> bool:
        """Whether this drug has a drug_interactions section."""
        return "drug_interactions" in self.sections


class AdverseReaction(BaseModel):
    """Single FAERS reaction term with report count."""

    term: str = Field(
        description="MedDRA preferred term"
    )
    count: int = Field(
        description="Number of reports"
    )


class AdverseEventResult(BaseModel):
    """Aggregated FAERS adverse event data."""

    drugs_queried: list[str] = Field(
        description="Drug names used in the query"
    )
    total_reports: Optional[int] = Field(
        default=None,
        description="Total matching reports (if available)"
    )
    serious_only: bool = Field(
        description="Whether query was filtered to serious events only"
    )
    top_reactions: list[AdverseReaction] = Field(
        default_factory=list,
        description="Top adverse reactions by report count"
    )


class InteractionScreenResult(BaseModel):
    """Result of screening a drug pair for interactions."""

    drug_a: str = Field(
        description="First drug generic name"
    )
    drug_b: str = Field(
        description="Second drug generic name"
    )
    label_a_mentions_b: bool = Field(
        default=False,
        description="Whether drug A's label mentions drug B"
    )
    label_b_mentions_a: bool = Field(
        default=False,
        description="Whether drug B's label mentions drug A"
    )
    interaction_text_a: Optional[str] = Field(
        default=None,
        description="Relevant excerpt from drug A's label mentioning drug B"
    )
    interaction_text_b: Optional[str] = Field(
        default=None,
        description="Relevant excerpt from drug B's label mentioning drug A"
    )
    faers_coreported: Optional[AdverseEventResult] = Field(
        default=None,
        description="FAERS co-reporting signal for this drug pair"
    )
    confidence_note: str = Field(
        default="",
        description="Explains data completeness and limitations"
    )
