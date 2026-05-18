"""Benchmark MedGraph's local OpenAI-compatible inference endpoint.

The benchmark is intentionally small: it measures router latency, specialist
single-request latency, concurrent specialist fan-out, and a second repeated
fan-out pass to make prefix-cache effects visible when the backend reports or
benefits from them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


ROUTE_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "RouteDecision",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "symptom",
                            "medication",
                            "lifestyle",
                            "evidence",
                            "drug_check",
                        ],
                    },
                },
                "reasoning": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["agents", "reasoning", "confidence"],
        },
        "strict": True,
    },
}


PATIENT_CONTEXT = """--- PATIENT CONTEXT ---
Name: Demo Patient | Age: 73F

Active conditions:
  - Type 2 diabetes
  - Hypertension
  - Chronic kidney disease stage 3

Current medications:
  - Metformin
  - Olmesartan
  - Naproxen

--- END PATIENT CONTEXT ---"""


SPECIALIST_PROMPTS = {
    "symptom": "Assess knee pain urgency and what to watch for.",
    "medication": "Explain whether ibuprofen is appropriate with this medication list.",
    "lifestyle": "Suggest conservative non-drug steps for knee pain.",
}


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def _headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _api_model_name(model: str) -> str:
    """Convert LiteLLM's openai/<model> name to the raw OpenAI API model id."""
    if model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _usage(data: dict[str, Any], key: str) -> int | None:
    value = (data.get("usage") or {}).get(key)
    return int(value) if isinstance(value, (int, float)) else None


async def _chat(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
    cache_prompt: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": _api_model_name(model),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if response_format:
        payload["response_format"] = response_format
    if cache_prompt:
        payload["cache_prompt"] = True
    payload["chat_template_kwargs"] = {"enable_thinking": False}

    t0 = time.perf_counter()
    response = await client.post(f"{base_url}/chat/completions", json=payload)
    elapsed = time.perf_counter() - t0
    response.raise_for_status()
    data = response.json()
    completion_tokens = _usage(data, "completion_tokens")
    return {
        "model": model,
        "latency_ms": round(elapsed * 1000, 2),
        "prompt_tokens": _usage(data, "prompt_tokens"),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": (
            round(completion_tokens / elapsed, 2)
            if completion_tokens is not None and elapsed > 0
            else None
        ),
    }


async def _run_specialist_batch(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
) -> list[dict[str, Any]]:
    tasks = []
    for agent, prompt in SPECIALIST_PROMPTS.items():
        tasks.append(
            _chat(
                client,
                base_url=base_url,
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": f"{PATIENT_CONTEXT}\n\n{prompt}",
                    },
                    {
                        "role": "user",
                        "content": "Should I take ibuprofen for my knee pain?",
                    },
                ],
                max_tokens=160,
                cache_prompt=True,
            )
        )
    results = await asyncio.gather(*tasks)
    for agent, result in zip(SPECIALIST_PROMPTS, results):
        result["agent"] = agent
    return results


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [r["latency_ms"] for r in results]
    tok_s = [r["tokens_per_sec"] for r in results if r["tokens_per_sec"] is not None]
    return {
        "count": len(results),
        "latency_ms_avg": round(statistics.mean(latencies), 2),
        "latency_ms_max": round(max(latencies), 2),
        "tokens_per_sec_avg": round(statistics.mean(tok_s), 2) if tok_s else None,
    }


def _repeated_prefix_comparison(report: dict[str, Any]) -> dict[str, Any]:
    first = report["summaries"]["specialist_parallel_first"]
    second = report["summaries"]["specialist_parallel_second"]
    first_latency = first["latency_ms_avg"]
    second_latency = second["latency_ms_avg"]
    first_tok_s = first["tokens_per_sec_avg"]
    second_tok_s = second["tokens_per_sec_avg"]
    return {
        "latency_delta_ms": round(second_latency - first_latency, 2),
        "latency_delta_pct": (
            round(((second_latency - first_latency) / first_latency) * 100, 2)
            if first_latency
            else None
        ),
        "tokens_per_sec_delta_pct": (
            round(((second_tok_s - first_tok_s) / first_tok_s) * 100, 2)
            if first_tok_s
            else None
        ),
    }


def _markdown_report(report: dict[str, Any]) -> str:
    comparison = report["repeated_prefix_comparison"]
    lines = [
        "# Local Inference Benchmark",
        "",
        "This benchmark is a local engineering proof, not a production capacity claim.",
        "",
    ]
    if report.get("model_pair"):
        lines.extend(
            [
                f"Model pair for this captured run: {report['model_pair']}.",
                "",
            ]
        )
    lines.extend(
        [
            f"- Default endpoint: `{report['base_url']}`",
            f"- Router endpoint: `{report['router_base_url']}`",
            f"- Specialist endpoint: `{report['specialist_base_url']}`",
            f"- Router model: `{report['router_model']}`",
            f"- Specialist model: `{report['specialist_model']}`",
            "",
            "| Scenario | Count | Avg latency ms | Max latency ms | Avg tokens/sec |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name in [
        "router",
        "specialist_single",
        "specialist_parallel_first",
        "specialist_parallel_second",
    ]:
        item = report["summaries"][name]
        lines.append(
            f"| {name} | {item['count']} | {item['latency_ms_avg']} | "
            f"{item['latency_ms_max']} | {item['tokens_per_sec_avg']} |"
        )
    lines.extend(
        [
            "",
            "Repeated-prefix check:",
            (
                f"- Second parallel pass latency delta: "
                f"{comparison['latency_delta_ms']} ms "
                f"({comparison['latency_delta_pct']}%)."
            ),
            (
                f"- Second parallel pass tokens/sec delta: "
                f"{comparison['tokens_per_sec_delta_pct']}%."
            ),
            (
                "- Confirm prompt-cache behavior with `llama-server` logs or "
                "`/metrics` before making capacity claims."
            ),
            (
                "- Useful log signals: `selected slot by LCP similarity`, "
                "`sim_best = 1.000`, `prompt is already in the cache`, and "
                "second-pass prompt evaluation dropping to a small token count."
            ),
            (
                "- End-to-end latency may still be generation-bound when "
                "`max_tokens` is high."
            ),
        ]
    )
    lines.extend(
        [
            "",
            "Raw results are included below for reproducibility.",
            "",
            "```json",
            json.dumps(report, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("LOCAL_LLM_API_BASE", "http://localhost:8080/v1"),
    )
    parser.add_argument(
        "--router-base-url",
        default=os.getenv("LOCAL_ROUTER_API_BASE", ""),
    )
    parser.add_argument(
        "--specialist-base-url",
        default=os.getenv("LOCAL_SPECIALIST_API_BASE", ""),
    )
    parser.add_argument(
        "--router-model",
        default=os.getenv("LOCAL_ROUTER_MODEL", "openai/router"),
    )
    parser.add_argument(
        "--specialist-model",
        default=os.getenv("LOCAL_SPECIALIST_MODEL", "openai/specialist"),
    )
    parser.add_argument("--api-key", default=os.getenv("LOCAL_LLM_API_KEY", ""))
    parser.add_argument(
        "--output",
        default="docs/local-inference-benchmark.md",
    )
    parser.add_argument(
        "--model-pair",
        default=os.getenv("LOCAL_LLM_MODEL_PAIR", ""),
        help="Human-readable model pair label included in the markdown report.",
    )
    args = parser.parse_args()

    base_url = _normalize_base_url(args.base_url)
    router_base_url = _normalize_base_url(args.router_base_url or args.base_url)
    specialist_base_url = _normalize_base_url(args.specialist_base_url or args.base_url)
    async with httpx.AsyncClient(
        timeout=180,
        headers=_headers(args.api_key),
    ) as client:
        router_result = await _chat(
            client,
            base_url=router_base_url,
            model=args.router_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Route a health question. Return JSON only with agents, "
                        "reasoning, confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": "Can I take ibuprofen for knee pain with kidney disease?",
                },
            ],
            max_tokens=96,
            response_format=ROUTE_RESPONSE_FORMAT,
        )
        single_specialist = await _chat(
            client,
            base_url=specialist_base_url,
            model=args.specialist_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{PATIENT_CONTEXT}\n\n"
                        "Explain whether ibuprofen is appropriate."
                    ),
                },
                {
                    "role": "user",
                    "content": "Should I take ibuprofen for my knee pain?",
                },
            ],
            max_tokens=160,
            cache_prompt=True,
        )
        parallel_first = await _run_specialist_batch(
            client,
            base_url=specialist_base_url,
            model=args.specialist_model,
        )
        parallel_second = await _run_specialist_batch(
            client,
            base_url=specialist_base_url,
            model=args.specialist_model,
        )

    report = {
        "base_url": base_url,
        "router_base_url": router_base_url,
        "specialist_base_url": specialist_base_url,
        "router_model": args.router_model,
        "specialist_model": args.specialist_model,
        "model_pair": args.model_pair,
        "results": {
            "router": [router_result],
            "specialist_single": [single_specialist],
            "specialist_parallel_first": parallel_first,
            "specialist_parallel_second": parallel_second,
        },
        "summaries": {
            "router": _summary([router_result]),
            "specialist_single": _summary([single_specialist]),
            "specialist_parallel_first": _summary(parallel_first),
            "specialist_parallel_second": _summary(parallel_second),
        },
    }
    report["repeated_prefix_comparison"] = _repeated_prefix_comparison(report)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_markdown_report(report))
    print(f"Wrote {output}")


if __name__ == "__main__":
    asyncio.run(_main())
