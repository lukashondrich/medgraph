"""FDA drug label fetching and section parsing via the OpenFDA drug/label API.

Fetches structured product labels (SPL), extracts safety-relevant sections,
and cleans HTML markup. Handles both Rx and OTC label formats.

Usage:
    from data.openfda.client import OpenFDAClient
    from data.openfda.drug_labels import fetch_drug_label

    with OpenFDAClient() as client:
        result = fetch_drug_label(client, "WARFARIN")
"""

import html
import logging
import re
from typing import Optional

from .client import LABEL_CACHE_TTL, OpenFDAClient
from .schemas import DrugIdentity, DrugLabelResult, LabelSectionContent

logger = logging.getLogger(__name__)


# ── Section Keys ─────────────────────────────────────────────────────────

# Sections we extract from Rx labels (in priority order)
_RX_SECTIONS = [
    "boxed_warning",
    "contraindications",
    "warnings_and_cautions",
    "warnings_and_precautions",
    "warnings",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
]

# Sections from OTC labels that contain interaction-like info
_OTC_SECTIONS = [
    "do_not_use",
    "stop_use",
    "ask_doctor",
    "ask_doctor_or_pharmacist",
    "when_using",
]

# Normalize variant warning section names to a canonical key
_SECTION_NORMALIZE = {
    "warnings_and_precautions": "warnings_and_cautions",
}


# ── Text Cleaning ────────────────────────────────────────────────────────


def _clean_label_text(raw: str) -> str:
    """Clean FDA label text: decode HTML entities, strip tags, normalize whitespace."""
    # Decode HTML entities
    text = html.unescape(raw)

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace: collapse runs, preserve paragraph breaks (double newline)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"\n ", "\n", text)
    text = text.strip()

    return text


# ── Label Selection ──────────────────────────────────────────────────────


def _is_combo_label(label: dict, target_drug: str) -> bool:
    """Check if a label is for a combo product that doesn't match our target.

    We want to avoid fetching a combo product label when looking for a
    single drug — the interaction sections would be misleading.
    """
    openfda = label.get("openfda", {})
    substance_names = openfda.get("substance_name", [])

    if len(substance_names) <= 1:
        return False

    # It's a combo — but is our target drug actually in it?
    target_upper = target_drug.upper()
    for name in substance_names:
        if target_upper in name.upper():
            return False

    return True


def _score_label(label: dict) -> int:
    """Score a label by how many useful sections it has."""
    score = 0
    for section in _RX_SECTIONS:
        if label.get(section):
            score += 2
    for section in _OTC_SECTIONS:
        if label.get(section):
            score += 1
    # Bonus for having openfda metadata
    if label.get("openfda", {}).get("generic_name"):
        score += 1
    return score


def _select_best_label(results: list[dict], drug_name: str) -> Optional[dict]:
    """From a list of label results, pick the best one.

    Filters out combo products, then picks the label with the most sections.
    """
    candidates = [r for r in results if not _is_combo_label(r, drug_name)]

    if not candidates:
        # Fall back to all results if filtering removed everything
        candidates = results

    if not candidates:
        return None

    return max(candidates, key=_score_label)


# ── Label Fetching ───────────────────────────────────────────────────────


def fetch_drug_label(
    client: OpenFDAClient,
    drug_name: str,
) -> Optional[DrugLabelResult]:
    """Fetch and parse the FDA label for a drug.

    Tries three search strategies with fallback:
    1. Generic name + warnings_and_cautions exists (best Rx labels)
    2. Generic name + adverse_reactions exists
    3. Generic name only (may get OTC)

    Args:
        client: OpenFDA HTTP client.
        drug_name: Uppercase generic name, e.g. "METFORMIN".

    Returns:
        DrugLabelResult with parsed sections, or None if not found.
    """
    name_upper = drug_name.upper()

    # Try three search strategies
    queries = [
        f'openfda.generic_name:"{name_upper}" AND _exists_:warnings_and_cautions',
        f'openfda.generic_name:"{name_upper}" AND _exists_:adverse_reactions',
        f'openfda.generic_name:"{name_upper}"',
    ]

    best_label = None

    for query in queries:
        data = client.get(
            "drug/label",
            params={"search": query, "limit": "5"},
            cache_ttl=LABEL_CACHE_TTL,
        )

        if not data:
            continue

        results = data.get("results", [])
        if not results:
            continue

        label = _select_best_label(results, name_upper)
        if label and (best_label is None or _score_label(label) > _score_label(best_label)):
            best_label = label

        # If we found a good label on the first try, stop
        if best_label and _score_label(best_label) >= 4:
            break

    if best_label is None:
        logger.debug("No label found for %s", drug_name)
        return None

    return _parse_label(best_label, drug_name)


def _parse_label(label: dict, query_name: str) -> DrugLabelResult:
    """Parse a raw OpenFDA label dict into a DrugLabelResult."""
    openfda = label.get("openfda", {})

    # Build DrugIdentity
    generic_names = openfda.get("generic_name", [])
    brand_names = openfda.get("brand_name", [])

    drug = DrugIdentity(
        query_name=query_name,
        generic_name=generic_names[0] if generic_names else query_name,
        brand_names=brand_names,
        is_combo_product=len(openfda.get("substance_name", [])) > 1,
    )

    # Extract sections
    sections: dict[str, LabelSectionContent] = {}

    for section_key in _RX_SECTIONS:
        raw_list = label.get(section_key)
        if raw_list and isinstance(raw_list, list):
            raw_text = _clean_label_text(" ".join(raw_list))
            if raw_text:
                # Normalize section name
                canonical = _SECTION_NORMALIZE.get(section_key, section_key)
                # Don't overwrite a better section with the same canonical key
                if canonical not in sections or len(raw_text) > sections[canonical].character_count:
                    sections[canonical] = LabelSectionContent(
                        section=canonical,
                        raw_text=raw_text,
                        character_count=len(raw_text),
                    )

    # For OTC labels missing drug_interactions, synthesize from OTC fields
    if "drug_interactions" not in sections:
        otc_parts = []
        for section_key in _OTC_SECTIONS:
            raw_list = label.get(section_key)
            if raw_list and isinstance(raw_list, list):
                cleaned = _clean_label_text(" ".join(raw_list))
                if cleaned:
                    otc_parts.append(f"[{section_key}] {cleaned}")

        if otc_parts:
            combined = "\n\n".join(otc_parts)
            sections["drug_interactions_otc"] = LabelSectionContent(
                section="drug_interactions_otc",
                raw_text=combined,
                character_count=len(combined),
            )

    # Metadata
    set_id = label.get("set_id")
    effective_date = label.get("effective_time")

    return DrugLabelResult(
        drug=drug,
        sections=sections,
        set_id=set_id,
        effective_date=effective_date,
    )
