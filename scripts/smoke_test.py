"""Quick smoke test: sends one query through the full pipeline with real API calls."""

import asyncio

from src.config import load_config
from src.orchestrator import build_graph


async def main():
    load_config()
    graph = build_graph()

    result = await graph.ainvoke({
        "user_input": "I have a headache after taking ibuprofen",
        "messages": [],
        "route": [],
        "route_reasoning": "",
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
        "metadata": {},
    })

    print("Route:", result["route"])
    print("Reasoning:", result["route_reasoning"])
    print("Specialists:", list(result["specialist_outputs"].keys()))
    print("Safety:", result["safety_escalation"])
    print("Handoff chain:", result["handoff_chain"])
    print()
    print("--- Response ---")
    print(result["final_response"])


if __name__ == "__main__":
    asyncio.run(main())
