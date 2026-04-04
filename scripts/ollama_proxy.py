"""Authenticated reverse proxy for Ollama.

Run this locally alongside Ollama, then expose it via Cloudflare Tunnel.
Requests without a valid Bearer token are rejected with 401.

Usage:
    export OLLAMA_AUTH_TOKEN="your-secret-token"
    python scripts/ollama_proxy.py

    # In another terminal:
    cloudflared tunnel --url http://localhost:11435
"""

import os
import sys

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response

OLLAMA_UPSTREAM = os.getenv("OLLAMA_UPSTREAM", "http://localhost:11434")
AUTH_TOKEN = os.getenv("OLLAMA_AUTH_TOKEN", "")
PROXY_PORT = int(os.getenv("OLLAMA_PROXY_PORT", "11435"))

if not AUTH_TOKEN:
    print("Error: OLLAMA_AUTH_TOKEN must be set.", file=sys.stderr)
    sys.exit(1)

app = FastAPI()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        return Response(status_code=401, content="Unauthorized")

    # Forward request to Ollama
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=f"{OLLAMA_UPSTREAM}/{path}",
            headers=headers,
            content=body,
            timeout=120,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


if __name__ == "__main__":
    print(f"Ollama auth proxy on :{PROXY_PORT} -> {OLLAMA_UPSTREAM}")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
