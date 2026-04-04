"""OpenFDA drug interaction tools — runtime API for the Drug Interaction Agent.

Public API:
    - OpenFDAClient: HTTP client with rate limiting, retries, caching
    - get_drug_label: Fetch FDA label for a drug
    - get_drug_label_for_medication: Fetch labels for a patient medication
    - get_adverse_events: Top FAERS serious adverse events
    - screen_drug_pair: Screen a drug pair for interactions
    - screen_all_pairs: Batch screen all patient medication pairs
    - resolve_medication: Resolve Synthea display text → generic names
    - extract_generic_name: Extract generic name from display text

Models:
    - DrugIdentity, DrugLabelResult, LabelSectionContent
    - AdverseReaction, AdverseEventResult
    - InteractionScreenResult
"""

from .client import OpenFDAClient
from .drug_resolver import extract_generic_name, resolve_medication
from .schemas import (
    AdverseEventResult,
    AdverseReaction,
    DrugIdentity,
    DrugLabelResult,
    InteractionScreenResult,
    LabelSectionContent,
)
from .tools import (
    get_adverse_events,
    get_drug_label,
    get_drug_label_for_medication,
    screen_all_pairs,
    screen_drug_pair,
)

__all__ = [
    # Client
    "OpenFDAClient",
    # Tools
    "get_drug_label",
    "get_drug_label_for_medication",
    "get_adverse_events",
    "screen_drug_pair",
    "screen_all_pairs",
    # Resolver
    "resolve_medication",
    "extract_generic_name",
    # Models
    "DrugIdentity",
    "DrugLabelResult",
    "LabelSectionContent",
    "AdverseReaction",
    "AdverseEventResult",
    "InteractionScreenResult",
]
