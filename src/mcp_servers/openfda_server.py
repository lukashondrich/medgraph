"""FastMCP server wrapping MedGraph's OpenFDA screening tools."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.data.openfda import OpenFDAClient
from src.data.openfda.tools import (
    get_drug_label as fetch_drug_label,
    screen_all_pairs as screen_medication_pairs,
    screen_drug_pair as screen_pair,
)
from src.data.schemas import Medication

logger = logging.getLogger(__name__)

_CLIENT: OpenFDAClient | None = None


def get_openfda_client() -> OpenFDAClient:
    """Return the process-wide OpenFDA client used by MCP tool calls."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenFDAClient()
    return _CLIENT


def _to_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    return value


def _active_medications(medications: list[dict[str, Any]]) -> list[Medication]:
    active_medications: list[Medication] = []
    for index, medication in enumerate(medications):
        if medication.get("status") != "active":
            continue
        try:
            active_medications.append(Medication.model_validate(medication))
        except ValidationError as exc:
            raise ValueError(
                f"Invalid active medication at index {index}: {exc.errors()}"
            ) from exc
    return active_medications


def create_server():
    """Create and configure the FastMCP OpenFDA server."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised after dependency install
        raise RuntimeError(
            "FastMCP is required for the OpenFDA MCP server. "
            "Install project requirements or `pip install fastmcp`."
        ) from exc

    mcp = FastMCP(name="MedGraph OpenFDA")

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        client = get_openfda_client()
        return JSONResponse(
            {
                "status": "ok",
                "client_cache_entries": client.cache_size,
                "client_request_count": client.request_count,
            }
        )

    @mcp.tool
    def get_drug_label(drug_name: str) -> dict[str, Any] | None:
        """Fetch the parsed FDA structured product label for a generic drug."""
        return _to_json(fetch_drug_label(get_openfda_client(), drug_name))

    @mcp.tool
    def screen_drug_pair(drug_a: str, drug_b: str) -> dict[str, Any] | None:
        """Screen a drug pair for FDA label and FAERS interaction signals."""
        return _to_json(screen_pair(get_openfda_client(), drug_a, drug_b))

    @mcp.tool
    def screen_all_pairs(medications: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Screen all active medication pairs from serialized patient medications."""
        results = screen_medication_pairs(get_openfda_client(), _active_medications(medications))
        return _to_json(results)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    server = create_server()
    logger.info("Starting OpenFDA MCP server on %s:%s /mcp/", args.host, args.port)
    server.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
