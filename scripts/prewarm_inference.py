"""Prewarm MedGraph's local OpenAI-compatible inference endpoint.

This script sends a short request to the router and specialist models so the
demo does not pay cold-start latency on the first real chat turn.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Any

import httpx


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


async def _prewarm_model(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    response = await client.post(
        f"{base_url}/chat/completions",
        json={
            "model": _api_model_name(model),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 16,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    elapsed = time.perf_counter() - t0
    response.raise_for_status()
    data = response.json()
    return {
        "model": model,
        "latency_ms": round(elapsed * 1000, 2),
        "content": data["choices"][0]["message"].get("content", ""),
    }


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
    parser.add_argument(
        "--api-key",
        default=os.getenv("LOCAL_LLM_API_KEY", ""),
    )
    args = parser.parse_args()

    base_url = _normalize_base_url(args.base_url)
    router_base_url = _normalize_base_url(args.router_base_url or args.base_url)
    specialist_base_url = _normalize_base_url(args.specialist_base_url or args.base_url)
    async with httpx.AsyncClient(
        timeout=120,
        headers=_headers(args.api_key),
    ) as client:
        for result in [
            await _prewarm_model(
                client,
                base_url=router_base_url,
                model=args.router_model,
                prompt="Return the word ready.",
            ),
            await _prewarm_model(
                client,
                base_url=specialist_base_url,
                model=args.specialist_model,
                prompt="Return the word ready.",
            ),
        ]:
            print(
                f"{result['model']}: {result['latency_ms']}ms "
                f"content={result['content']!r}"
            )


if __name__ == "__main__":
    asyncio.run(_main())
