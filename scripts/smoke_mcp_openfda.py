"""Smoke-test the OpenFDA FastMCP server over Streamable HTTP."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8001/mcp/")
    parser.add_argument("--drug-a", default="naproxen")
    parser.add_argument("--drug-b", default="olmesartan")
    args = parser.parse_args()

    try:
        from fastmcp import Client
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("fastmcp is required; install project requirements first") from exc

    async with Client(args.url) as client:
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools)
        result: Any = await client.call_tool(
            "screen_drug_pair",
            {"drug_a": args.drug_a, "drug_b": args.drug_b},
        )

    print("tools:", ", ".join(tool_names))
    print(json.dumps(getattr(result, "data", result), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
