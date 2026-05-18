# MedGraph Deployment Runbook

This runbook captures the repeatable commands for the local-inference infrastructure demo.

## Local Inference Demo

Install the local serving tools:

```bash
brew install llama.cpp
brew tap mostlygeek/llama-swap
brew install llama-swap
```

Start `llama-swap` with the checked-in example config:

```bash
llama-server -hf unsloth/Qwen3-8B-GGUF:Q4_K_M --port 8081  # download/smoke test, then Ctrl-C
llama-server -hf unsloth/Qwen3.6-27B-GGUF:Q4_K_M --port 8082  # download/smoke test, then Ctrl-C

export MEDGRAPH_ROUTER_GGUF="$HOME/.cache/huggingface/hub/models--unsloth--Qwen3-8B-GGUF/snapshots/a6adef130ffb23ddaf1a62fec9dced968c9bc482/Qwen3-8B-Q4_K_M.gguf"
export MEDGRAPH_SPECIALIST_GGUF="$HOME/.cache/huggingface/hub/models--unsloth--Qwen3.6-27B-GGUF/snapshots/82d411acf4a06cfb8d9b073a5211bf410bfc29bf/Qwen3.6-27B-Q4_K_M.gguf"
llama-swap -config configs/llama-swap.yaml -listen :8080
```

The paths above are the validated Hugging Face cache locations for the MacBook
demo: Qwen3-8B for routing and Qwen3.6-27B for the specialist model. If the
snapshot hash changes after a model update, adjust the env vars to the new local
GGUF paths. Validate each model with direct `llama-server` startup before
recording results.

Configure MedGraph to use the OpenAI-compatible endpoint:

```bash
export LOCAL_LLM_API_BASE=http://localhost:8080/v1
export LOCAL_ROUTER_MODEL=openai/router
export LOCAL_SPECIALIST_MODEL=openai/specialist
```

Warm both models:

```bash
python scripts/prewarm_inference.py
```

Run the local inference benchmark:

```bash
python scripts/benchmark_inference.py \
  --model-pair "Qwen3-8B router + Qwen3.6-27B specialist" \
  --output docs/local-inference-benchmark.md
```

The checked-in benchmark document records the Qwen3-8B/Qwen3.6-27B pair used
for the current quality validation. Rerun it if model paths, quantization,
parallelism, or context size change.

Verify residency before the demo:

```bash
curl http://localhost:8080/v1/models
ps -ax -o pid=,command= | grep '[l]lama-server'
```

Both upstream `llama-server` processes should remain running after warm-up. The
`llama-swap` config uses matrix preloading plus `ttl: 0` so the router and
specialist models stay resident.

## MCP Server

Start the OpenFDA MCP server:

```bash
python -m src.mcp_servers.openfda_server --host 0.0.0.0 --port 8001
```

Smoke-test it:

```bash
python scripts/smoke_mcp_openfda.py --url http://localhost:8001/mcp/
```

Run the app against the MCP server:

```bash
export USE_MCP=true
export OPENFDA_MCP_URL=http://localhost:8001/mcp/
uvicorn src.api:app --port 8000
```

## Docker Compose

The compose file runs the orchestrator and OpenFDA MCP server. Qdrant remains embedded in `src/knowledge_pipeline/qdrant_store`; external Qdrant is a future `QDRANT_URL` task.

Render/validate compose:

```bash
docker compose config
```

Run locally:

```bash
docker compose up --build
```

For Docker Desktop on macOS, the default local inference endpoint points at `host.docker.internal:11435`, the authenticated host proxy.

## Helm

Render default manifests:

```bash
helm template medgraph charts/medgraph
```

Render the optional GPU/vLLM path:

```bash
helm template medgraph charts/medgraph -f charts/medgraph/values-gpu.yaml
```

The chart uses restricted-compatible pod/container security contexts and does not create OpenShift SCCs. If a cluster requires a custom SCC for GPU workloads, bind that outside the application chart.
