"""Multi-turn persona evaluation using simulated patient conversations.

Runs each persona through the PersonaSimulator, then evaluates:
- Per-turn: each assistant response with Communication (Group B) and
  Questioning (Group C) judges.
- Cross-turn: the full transcript with Conversation (Group D) judge.

Requires an API key (makes real LLM calls for the system, simulator, and judge).
"""

from __future__ import annotations

from typing import List

import pytest

from tests.eval.conftest import requires_api_key
from tests.eval.judge import GroupResult
from tests.eval.persona import Persona, PersonaSimulator, Transcript

# Minimum acceptable average pass rate across all personas
_MIN_AVG_PASS_RATE = 0.5


def _get_assistant_turns(transcript: Transcript) -> List[tuple[str, str]]:
    """Extract (user_query, assistant_response) pairs from transcript."""
    pairs = []
    turns = transcript.turns
    for i in range(len(turns) - 1):
        if turns[i]["role"] == "user" and turns[i + 1]["role"] == "assistant":
            pairs.append((turns[i]["content"], turns[i + 1]["content"]))
    return pairs


def _aggregate_group_results(results: List[GroupResult]) -> float:
    """Compute combined pass rate across multiple GroupResults."""
    total_applicable = sum(g.applicable_count for g in results)
    if total_applicable == 0:
        return 1.0
    total_passed = sum(
        sum(1 for s in g.scores.values() if s.score == 1)
        for g in results
    )
    return total_passed / total_applicable


@pytest.mark.eval
@requires_api_key
class TestPersonaEval:
    """Evaluate multi-turn conversations via persona simulation."""

    @pytest.mark.asyncio
    async def test_persona_conversations(
        self,
        persona_simulator: PersonaSimulator,
        personas: List[Persona],
        judge,
    ) -> None:
        """Average pass rate across all personas should meet threshold."""
        assert len(personas) > 0, "No personas defined"

        persona_results: list[dict] = []

        for persona in personas:
            # Run the conversation
            transcript = await persona_simulator.run(persona)

            # Collect per-turn judge results
            per_turn_results: list[GroupResult] = []
            turn_details: list[dict] = []
            assistant_turns = _get_assistant_turns(transcript)

            for query, response in assistant_turns:
                if not response:
                    continue

                turn_groups: list[GroupResult] = []

                # Group B: Communication (always run if in eval_groups)
                if "communication" in persona.eval_groups:
                    comm = await judge.evaluate_communication(
                        query=query, agent_response=response,
                    )
                    turn_groups.append(comm)
                    per_turn_results.append(comm)

                # Group C: Questioning (always run if in eval_groups)
                if "questioning" in persona.eval_groups:
                    quest = await judge.evaluate_questioning(
                        query=query, agent_response=response,
                    )
                    turn_groups.append(quest)
                    per_turn_results.append(quest)

                turn_pass = _aggregate_group_results(turn_groups) if turn_groups else 1.0
                turn_details.append({
                    "query": query[:60],
                    "pass_rate": turn_pass,
                })

            # Group D: Conversation quality (cross-turn, if in eval_groups)
            cross_turn_result: GroupResult | None = None
            if "conversation" in persona.eval_groups and transcript.turn_count >= 2:
                cross_turn_result = await judge.evaluate_conversation(
                    transcript=transcript.turns,
                )

            # Combine all results for this persona
            all_results = list(per_turn_results)
            if cross_turn_result is not None:
                all_results.append(cross_turn_result)

            persona_pass_rate = _aggregate_group_results(all_results) if all_results else 1.0

            persona_results.append({
                "name": persona.name,
                "turn_count": transcript.turn_count,
                "pass_rate": persona_pass_rate,
                "turn_details": turn_details,
                "cross_turn": (
                    cross_turn_result.pass_rate if cross_turn_result else None
                ),
                "per_turn_results": per_turn_results,
                "cross_turn_result": cross_turn_result,
            })

        avg_pass_rate = (
            sum(p["pass_rate"] for p in persona_results) / len(persona_results)
            if persona_results
            else 0.0
        )

        # Print report
        print(f"\n{'='*60}")
        print(f"Persona Evaluation Report ({len(personas)} personas)")
        print(f"{'='*60}")
        print(f"Average pass rate: {avg_pass_rate:.3f}")

        for pr in persona_results:
            print(f"\n--- {pr['name']} ({pr['turn_count']} turns) ---")
            print(f"  Overall pass rate: {pr['pass_rate']:.3f}")
            if pr["cross_turn"] is not None:
                print(f"  Cross-turn score:  {pr['cross_turn']:.3f}")

            # Per-turn breakdown
            for i, td in enumerate(pr["turn_details"]):
                print(f"  Turn {i+1}: [{td['pass_rate']:.2f}] {td['query']}...")

            # Per-criterion breakdown
            all_scores: dict[str, list[int]] = {}
            for gr in pr["per_turn_results"]:
                for name, cs in gr.scores.items():
                    if cs.score is not None:
                        all_scores.setdefault(name, []).append(cs.score)
            if pr["cross_turn_result"]:
                for name, cs in pr["cross_turn_result"].scores.items():
                    if cs.score is not None:
                        all_scores.setdefault(name, []).append(cs.score)

            if all_scores:
                print(f"  Per-criterion:")
                for name, scores in sorted(all_scores.items()):
                    rate = sum(scores) / len(scores)
                    print(f"    {name}: {rate:.2f} ({sum(scores)}/{len(scores)})")

        assert avg_pass_rate >= _MIN_AVG_PASS_RATE, (
            f"Average persona pass rate {avg_pass_rate:.3f} below threshold "
            f"{_MIN_AVG_PASS_RATE}"
        )
