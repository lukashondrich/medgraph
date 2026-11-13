"""Terminal CLI for pH Companion.

    python -m src.main --persona priya --ph 4.8
    python -m src.main --persona amara --ph 5.0 --ask "Should I be worried?"

Runs one turn through the graph and prints what was looked up, the answer
and its sources.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime


async def run(persona_id: str, ph: float, confidence: float, question: str | None, language: str) -> int:
    from src.agents.writer import NEW_READING_INPUT
    from src.data.personas import list_personas, load_persona
    from src.data.profile import TestReading, build_profile_summary
    from src.orchestrator import build_ph_graph

    profile = load_persona(persona_id)
    if profile is None:
        known = ", ".join(p["persona_id"] for p in list_personas())
        print(f"Unknown persona '{persona_id}'. Available: {known}")
        return 1
    reading = TestReading(ph=ph, confidence=confidence, taken_at=datetime.now())

    state = {
        "messages": [],
        "user_input": question or NEW_READING_INPUT,
        "language": language,
        "patient": profile.to_dict(),
        "patient_summary": build_profile_summary(profile, reading),
        "reading": reading.to_dict(),
        "turn_kind": "question" if question else "new_reading",
        "route": [], "queries": [], "route_reasoning": "",
        "sources": {}, "retrieval_trace": [], "evidence_gap": {},
        "safety_reasons": [], "safety_escalation": False,
        "final_response": "", "citations": [], "handoff_chain": [],
    }
    result = await build_ph_graph().ainvoke(state)

    print(f"\n{profile.name}, pH {reading.ph:.1f}\n")
    print("Looked up:")
    for trace in result["retrieval_trace"]:
        counts = ", ".join(f"{k} {v}" for k, v in trace.get("counts", {}).items())
        print(f"  - {trace['source']}: {counts}")
    for reason in result["safety_reasons"]:
        print(f"\n! {reason}")
    print("\n" + result["final_response"] + "\n")
    if result["citations"]:
        print("Sources:")
    for c in result["citations"]:
        size = f"{c['sample_size']:,} participants" if c["sample_size"] else "size not stated"
        match = f" | matches: {', '.join(c['matched_attributes'])}" if c["matched_attributes"] else ""
        print(f"  [{c['number']}] {c['authors']} {c['year']} · {c['design']} · {size}{match}\n      {c['url']}")
    return 0


def main() -> None:
    from src.config import load_config

    parser = argparse.ArgumentParser(description="Run one pH Companion turn in the terminal.")
    parser.add_argument("--persona", default="priya")
    parser.add_argument("--ph", type=float, default=4.8)
    parser.add_argument("--confidence", type=float, default=0.92)
    parser.add_argument("--ask", help="a follow-up question instead of the first interpretation")
    parser.add_argument("--language", default="en", choices=["en", "de"])
    args = parser.parse_args()

    load_config()
    logging.getLogger().setLevel(logging.WARNING)
    raise SystemExit(asyncio.run(run(args.persona, args.ph, args.confidence, args.ask, args.language)))


if __name__ == "__main__":
    main()
