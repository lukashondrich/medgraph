"""Smoke-test one streamed MedGraph API request."""

from __future__ import annotations

import argparse
import json
from typing import Iterator

import httpx


def _events(lines: Iterator[str]) -> Iterator[tuple[str, dict]]:
    event_name = "message"
    data_lines: list[str] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            if data_lines:
                raw_data = "\n".join(data_lines)
                yield event_name, json.loads(raw_data or "{}")
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--message",
        default="Should I take ibuprofen for my knee pain?",
    )
    parser.add_argument("--patient-id", default="")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    payload = {
        "message": args.message,
        "patient_id": args.patient_id or None,
    }
    with httpx.stream(
        "POST",
        f"{args.base_url.rstrip('/')}/api/chat",
        json=payload,
        timeout=args.timeout,
    ) as response:
        response.raise_for_status()
        seen: list[str] = []
        final_response = ""
        for event_name, data in _events(response.iter_lines()):
            seen.append(event_name)
            if event_name == "response":
                final_response = data.get("content", "")

    print("events:", ", ".join(seen))
    print("final_response:", final_response[:500])
    if "response" not in seen:
        raise SystemExit("No final response event received")


if __name__ == "__main__":
    main()
