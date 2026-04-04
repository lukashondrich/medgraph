"""Terminal CLI for the healthcare multiagent orchestration system.

Interactive async chat loop that invokes the LangGraph graph and displays
routing decisions, specialist processing, and synthesized responses.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time


# ---------------------------------------------------------------------------
# ANSI colour helpers (degrade gracefully on dumb terminals)
# ---------------------------------------------------------------------------

_SUPPORTS_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _SUPPORTS_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text


logger = logging.getLogger(__name__)


def _bold(text: str) -> str:
    return _c("1", text)


def _dim(text: str) -> str:
    return _c("2", text)


def _blue(text: str) -> str:
    return _c("34", text)


def _green(text: str) -> str:
    return _c("32", text)


def _yellow(text: str) -> str:
    return _c("33", text)


def _red(text: str) -> str:
    return _c("31", text)


def _cyan(text: str) -> str:
    return _c("36", text)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    # Load config (sets env vars for litellm)
    from src.config import load_config

    load_config()

    # Import graph builder (may fail if orchestrator not yet implemented)
    from src.orchestrator import build_graph

    graph = build_graph()

    # Session state
    messages: list[dict[str, str]] = []

    # Welcome banner
    print()
    print(_bold("=" * 56))
    print(_bold("  medgraph AI Assistant"))
    print(_dim("  Healthcare guidance powered by specialist agents"))
    print(_bold("=" * 56))
    print()
    print(
        _dim(
            "  Type your health question and press Enter.\n"
            '  Type "quit" or "exit" to end the session.\n'
        )
    )
    print(
        _yellow(
            "  Disclaimer: This AI cannot diagnose or prescribe.\n"
            "  Always consult a healthcare provider for medical concerns.\n"
        )
    )

    while True:
        # Prompt
        try:
            user_input = input(_bold("You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + _dim("Goodbye!"))
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print(_dim("Goodbye!"))
            break

        # Build initial state for this turn
        initial_state = {
            "messages": messages + [{"role": "user", "content": user_input}],
            "user_input": user_input,
            "route": [],
            "route_reasoning": "",
            "specialist_outputs": {},
            "final_response": "",
            "handoff_chain": [],
            "safety_escalation": False,
        }

        print()
        t_start = time.perf_counter()

        try:
            # Stream node-level updates from the graph
            final_state = dict(initial_state)
            routing_shown = False
            specialists_shown: set[str] = set()
            synthesizer_shown = False

            async for event in graph.astream(initial_state, stream_mode="updates"):
                for node_name, state_update in event.items():
                    if state_update is None:
                        continue

                    # Merge update into tracking state
                    if isinstance(state_update, dict):
                        for key, value in state_update.items():
                            if key in ("messages", "handoff_chain") and isinstance(value, list):
                                if key not in final_state:
                                    final_state[key] = []
                                final_state[key] = final_state[key] + value
                            else:
                                final_state[key] = value

                    # Router completed
                    if node_name == "router" and not routing_shown:
                        routing_shown = True
                        route = final_state.get("route", [])
                        reasoning = final_state.get("route_reasoning", "")
                        agents_str = ", ".join(
                            _cyan(a.capitalize()) for a in route
                        )
                        print(
                            _blue("  [Router]")
                            + f" Routing to: {agents_str}"
                        )
                        if reasoning:
                            print(
                                _dim(f"  Reasoning: {reasoning}")
                            )
                        print()

                    # Specialist completed
                    elif node_name in ("symptom_agent", "medication_agent", "lifestyle_agent"):
                        agent_label = node_name.replace("_agent", "")
                        if agent_label not in specialists_shown:
                            specialists_shown.add(agent_label)
                            print(
                                _green(f"  [{agent_label.capitalize()}]")
                                + _dim(" done")
                            )

                    # Synthesizer completed
                    elif node_name == "synthesizer" and not synthesizer_shown:
                        synthesizer_shown = True

            # Show final response
            final_response = final_state.get("final_response", "")
            safety = final_state.get("safety_escalation", False)

            print()
            print(_bold("Assistant: ") + final_response)

            if safety:
                print()
                print(
                    _yellow(
                        "  [Safety Notice] Please consult a qualified healthcare "
                        "provider for personalized medical advice. This AI assistant "
                        "cannot diagnose conditions or prescribe treatments."
                    )
                )

            # Show handoff chain
            handoff = final_state.get("handoff_chain", [])
            if handoff:
                chain_str = " -> ".join(handoff)
                print(_dim(f"\n  Pipeline: {chain_str}"))

            print()

            # Log request summary
            elapsed = time.perf_counter() - t_start
            route = final_state.get("route", [])
            logger.info(
                "Request completed: agents=%s safety=%s elapsed=%.3fs",
                route, safety, elapsed,
            )

            # Update conversation history
            messages.append({"role": "user", "content": user_input})
            messages.append(
                {"role": "assistant", "content": final_response}
            )

        except Exception as exc:
            print(_red(f"\n  Error: {exc}\n"))


def run() -> None:
    """Entry point for the CLI."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(_dim("\nGoodbye!"))


if __name__ == "__main__":
    run()
