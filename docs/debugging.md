# Debugging Guide

Common issues and how to resolve them.

---

## Python Version

The codebase uses Python 3.10+ syntax (`X | None` union types). If you see:

```
TypeError: unsupported operand type(s) for |: 'types.GenericAlias' and 'NoneType'
```

You're running with Python 3.9 or earlier. Use the project venv:

```bash
source .venv/bin/activate  # Python 3.11
```

## API Keys

```
ValueError: No API key found. Set GEMINI_API_KEY or OPENAI_API_KEY in .env
```

Create a `.env` file in the project root with at least one key:

```
GEMINI_API_KEY=your-key
# or
OPENAI_API_KEY=your-key
```

Both can be set for automatic fallback. Override the model explicitly with `MEDGRAPH_MODEL=gpt-4o-mini`.

## LLM Call Failures

Agents never raise on LLM failures — they return a safe fallback message. Check logs for details:

```
WARNING router LLM call failed with model gemini/gemini-2.5-pro: ...
```

If both primary and fallback models fail, look for:

```
ERROR router LLM call failed after all attempts: ...
```

Common causes: invalid API key, rate limiting, model name typo in `MEDGRAPH_MODEL`.

## Qdrant Store Not Found

The Evidence agent logs a warning and returns empty results if the pre-indexed store is missing:

```
WARNING Qdrant store not found at ...
```

This is graceful degradation — the system works without evidence grounding. The store should be at `src/knowledge_pipeline/qdrant_store/`.

## Tests Failing to Collect

If `pytest` fails to collect tests with import errors, ensure you're using the venv Python and running from the project root:

```bash
source .venv/bin/activate
pytest tests/ -v --ignore=tests/eval
```

Eval tests require API keys and are skipped automatically without them.

## SSE Streaming Issues

If the web UI doesn't show pipeline status updates:
- Check browser console for fetch errors
- Verify the server is running: `curl http://localhost:8000/api/health`
- Check for proxy/buffering: the response headers include `X-Accel-Buffering: no` and `Cache-Control: no-cache`

## OpenFDA Rate Limiting

The OpenFDA client uses token bucket rate limiting (4 req/sec). If you see 429 responses in logs, the client retries with exponential backoff automatically. Set `OPENFDA_API_KEY` in `.env` for higher rate limits.
