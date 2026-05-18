# ADR 001: Local Inference Backend

## Decision

Use `llama-server` plus `llama-swap` for the local demo path, exposed as a single OpenAI-compatible endpoint. Keep the application model routing API-compatible with vLLM for Kubernetes/GPU deployment.

## Context

Ollama was sufficient for early local routing, but the portfolio goal is to demonstrate inference-serving literacy: role-based model routing, concurrent specialist fan-out, constrained router decoding, prefix-cache-aware prompt structure, and benchmarkable latency/token metrics.

## Consequences

- Router and specialist agents use local OpenAI-compatible inference when configured.
- The validated MacBook demo model pair is Qwen3-8B for routing and Qwen3.6-27B for specialists. Both are served as GGUFs through `llama-server` behind `llama-swap`.
- A smaller Qwen3 4B/Hermes 8B pair remains useful for low-latency benchmarking, but the current quality validation uses the 8B/27B pair.
- Synthesizer remains cloud-only because it needs the largest context and highest response quality.
- Local MacBook demo uses `llama-swap`; Kubernetes/GPU manifests document a vLLM path.
- The app supports role-specific API bases so separate router/specialist vLLM services can be used without code changes.
