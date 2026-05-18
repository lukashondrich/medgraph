# Local Inference Benchmark

This benchmark is a local engineering proof, not a production capacity claim.

Model pair for this captured run: Qwen3-8B router + Qwen3.6-27B specialist,
served through `llama-swap` with both upstream `llama-server` processes
resident.

- Default endpoint: `http://127.0.0.1:8080/v1`
- Router endpoint: `http://127.0.0.1:8080/v1`
- Specialist endpoint: `http://127.0.0.1:8080/v1`
- Router model: `openai/router`
- Specialist model: `openai/specialist`

| Scenario | Count | Avg latency ms | Max latency ms | Avg tokens/sec |
|---|---:|---:|---:|---:|
| router | 1 | 2535.47 | 2535.47 | 37.86 |
| specialist_single | 1 | 15663.5 | 15663.5 | 10.21 |
| specialist_parallel_first | 3 | 42846.76 | 42852.85 | 3.73 |
| specialist_parallel_second | 3 | 40978.29 | 40979.39 | 3.9 |

Repeated-prefix check:
- Second parallel pass latency delta: -1868.47 ms (-4.36%).
- Second parallel pass tokens/sec delta: 4.56%.
- Confirm prompt-cache behavior with `llama-server` logs or `/metrics` before making capacity claims.
- Useful log signals: `selected slot by LCP similarity`, `sim_best = 1.000`, `prompt is already in the cache`, and second-pass prompt evaluation dropping to a small token count.
- End-to-end latency may still be generation-bound when `max_tokens` is high.

Raw results are included below for reproducibility.

```json
{
  "base_url": "http://127.0.0.1:8080/v1",
  "model_pair": "Qwen3-8B router + Qwen3.6-27B specialist",
  "repeated_prefix_comparison": {
    "latency_delta_ms": -1868.47,
    "latency_delta_pct": -4.36,
    "tokens_per_sec_delta_pct": 4.56
  },
  "results": {
    "router": [
      {
        "completion_tokens": 96,
        "latency_ms": 2535.47,
        "model": "openai/router",
        "prompt_tokens": 45,
        "tokens_per_sec": 37.86
      }
    ],
    "specialist_parallel_first": [
      {
        "agent": "symptom",
        "completion_tokens": 160,
        "latency_ms": 42837.78,
        "model": "openai/specialist",
        "prompt_tokens": 113,
        "tokens_per_sec": 3.74
      },
      {
        "agent": "medication",
        "completion_tokens": 160,
        "latency_ms": 42849.66,
        "model": "openai/specialist",
        "prompt_tokens": 115,
        "tokens_per_sec": 3.73
      },
      {
        "agent": "lifestyle",
        "completion_tokens": 160,
        "latency_ms": 42852.85,
        "model": "openai/specialist",
        "prompt_tokens": 113,
        "tokens_per_sec": 3.73
      }
    ],
    "specialist_parallel_second": [
      {
        "agent": "symptom",
        "completion_tokens": 160,
        "latency_ms": 40979.39,
        "model": "openai/specialist",
        "prompt_tokens": 113,
        "tokens_per_sec": 3.9
      },
      {
        "agent": "medication",
        "completion_tokens": 160,
        "latency_ms": 40976.75,
        "model": "openai/specialist",
        "prompt_tokens": 115,
        "tokens_per_sec": 3.9
      },
      {
        "agent": "lifestyle",
        "completion_tokens": 160,
        "latency_ms": 40978.73,
        "model": "openai/specialist",
        "prompt_tokens": 113,
        "tokens_per_sec": 3.9
      }
    ],
    "specialist_single": [
      {
        "completion_tokens": 160,
        "latency_ms": 15663.5,
        "model": "openai/specialist",
        "prompt_tokens": 111,
        "tokens_per_sec": 10.21
      }
    ]
  },
  "router_base_url": "http://127.0.0.1:8080/v1",
  "router_model": "openai/router",
  "specialist_base_url": "http://127.0.0.1:8080/v1",
  "specialist_model": "openai/specialist",
  "summaries": {
    "router": {
      "count": 1,
      "latency_ms_avg": 2535.47,
      "latency_ms_max": 2535.47,
      "tokens_per_sec_avg": 37.86
    },
    "specialist_parallel_first": {
      "count": 3,
      "latency_ms_avg": 42846.76,
      "latency_ms_max": 42852.85,
      "tokens_per_sec_avg": 3.73
    },
    "specialist_parallel_second": {
      "count": 3,
      "latency_ms_avg": 40978.29,
      "latency_ms_max": 40979.39,
      "tokens_per_sec_avg": 3.9
    },
    "specialist_single": {
      "count": 1,
      "latency_ms_avg": 15663.5,
      "latency_ms_max": 15663.5,
      "tokens_per_sec_avg": 10.21
    }
  }
}
```
