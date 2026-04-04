"""FAERS adverse event queries via the OpenFDA drug/event API.

Two query patterns:
1. Single drug: top serious reactions
2. Drug pair co-reporting: both drugs in search → co-reported reactions

Uses the `count` endpoint for aggregated data (no individual reports).

Usage:
    from data.openfda.client import OpenFDAClient
    from data.openfda.adverse_events import get_top_adverse_events, get_pair_adverse_events

    with OpenFDAClient() as client:
        result = get_top_adverse_events(client, "WARFARIN")
        pair = get_pair_adverse_events(client, "WARFARIN", "NAPROXEN")
"""

import logging
from typing import Optional

from .client import FAERS_CACHE_TTL, OpenFDAClient
from .schemas import AdverseEventResult, AdverseReaction

logger = logging.getLogger(__name__)


def get_top_adverse_events(
    client: OpenFDAClient,
    drug_name: str,
    serious_only: bool = True,
    limit: int = 15,
) -> Optional[AdverseEventResult]:
    """Get top adverse events for a single drug from FAERS.

    Args:
        client: OpenFDA HTTP client.
        drug_name: Uppercase generic name, e.g. "WARFARIN".
        serious_only: Filter to serious events only (default True).
        limit: Number of top reactions to return.

    Returns:
        AdverseEventResult with top reactions, or None if no data.
    """
    name_upper = drug_name.upper()

    search = f'patient.drug.openfda.generic_name:"{name_upper}"'
    if serious_only:
        search += " AND serious:1"

    data = client.get(
        "drug/event",
        params={
            "search": search,
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": str(limit),
        },
        cache_ttl=FAERS_CACHE_TTL,
    )

    if not data:
        logger.debug("No FAERS data for %s", drug_name)
        return None

    results = data.get("results", [])
    if not results:
        return None

    reactions = [
        AdverseReaction(term=r["term"], count=r["count"])
        for r in results
        if "term" in r and "count" in r
    ]

    # Get total from meta if available
    total = data.get("meta", {}).get("results", {}).get("total")

    return AdverseEventResult(
        drugs_queried=[name_upper],
        total_reports=total,
        serious_only=serious_only,
        top_reactions=reactions,
    )


def get_pair_adverse_events(
    client: OpenFDAClient,
    drug_a: str,
    drug_b: str,
    serious_only: bool = True,
    limit: int = 10,
) -> Optional[AdverseEventResult]:
    """Get co-reported adverse events for a drug pair from FAERS.

    High co-reporting counts indicate a potential interaction signal.

    Args:
        client: OpenFDA HTTP client.
        drug_a: First drug uppercase generic name.
        drug_b: Second drug uppercase generic name.
        serious_only: Filter to serious events only (default True).
        limit: Number of top reactions to return.

    Returns:
        AdverseEventResult with co-reported reactions, or None if no data.
    """
    a_upper = drug_a.upper()
    b_upper = drug_b.upper()

    search = (
        f'patient.drug.openfda.generic_name:"{a_upper}" AND '
        f'patient.drug.openfda.generic_name:"{b_upper}"'
    )
    if serious_only:
        search += " AND serious:1"

    data = client.get(
        "drug/event",
        params={
            "search": search,
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": str(limit),
        },
        cache_ttl=FAERS_CACHE_TTL,
    )

    if not data:
        logger.debug("No FAERS co-report data for %s + %s", drug_a, drug_b)
        return None

    results = data.get("results", [])
    if not results:
        return None

    reactions = [
        AdverseReaction(term=r["term"], count=r["count"])
        for r in results
        if "term" in r and "count" in r
    ]

    total = data.get("meta", {}).get("results", {}).get("total")

    return AdverseEventResult(
        drugs_queried=[a_upper, b_upper],
        total_reports=total,
        serious_only=serious_only,
        top_reactions=reactions,
    )
