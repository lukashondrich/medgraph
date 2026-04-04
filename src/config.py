import logging
import os

from dotenv import load_dotenv

# Equivalent-quality model pairs for fallback
_MODEL_FALLBACKS: dict[str, str] = {
    "gemini/gemini-2.5-pro": "gpt-5.2",
    "gpt-5.2": "gemini/gemini-2.5-pro",
}


def load_config() -> dict:
    """Load environment variables and return project config.

    Supports Gemini (primary) and OpenAI (fallback) via litellm.
    litellm reads API keys from environment variables automatically.
    Sets MEDGRAPH_MODEL and MEDGRAPH_FALLBACK_MODEL env vars so
    agents pick up models at instantiation time.
    """
    load_dotenv()

    # Configure structured logging (safe to call multiple times)
    log_level = os.getenv("MEDGRAPH_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not gemini_key and not openai_key:
        raise ValueError(
            "No API key found. Set GEMINI_API_KEY or OPENAI_API_KEY in .env"
        )

    # Allow explicit override via env var, otherwise auto-detect from available keys
    explicit_model = os.getenv("MEDGRAPH_MODEL")
    if explicit_model:
        default_model = explicit_model
    elif openai_key:
        default_model = "gpt-5.2"
    else:
        default_model = "gemini/gemini-2.5-pro"

    # Determine fallback model (only if the other provider's key is available)
    fallback_model = os.getenv("MEDGRAPH_FALLBACK_MODEL") or _MODEL_FALLBACKS.get(default_model)
    if fallback_model:
        # Only keep fallback if we have the key for it
        needs_gemini = fallback_model.startswith("gemini/")
        needs_openai = not needs_gemini
        if (needs_gemini and not gemini_key) or (needs_openai and not openai_key):
            fallback_model = None

    # Set env vars so agents pick up models at instantiation time
    os.environ["MEDGRAPH_MODEL"] = default_model
    if fallback_model:
        os.environ["MEDGRAPH_FALLBACK_MODEL"] = fallback_model

    # Ollama (local model) configuration — router-only
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_router_model = os.getenv("OLLAMA_ROUTER_MODEL", "ollama_chat/gemma4:26b-a4b-it-q8_0")
    ollama_enabled = os.getenv("OLLAMA_ENABLED", "true").lower() in ("true", "1", "yes")
    ollama_auth_token = os.getenv("OLLAMA_AUTH_TOKEN", "")

    os.environ["OLLAMA_BASE_URL"] = ollama_base_url
    os.environ["OLLAMA_ROUTER_MODEL"] = ollama_router_model
    os.environ["OLLAMA_ENABLED"] = str(ollama_enabled).lower()
    if ollama_auth_token:
        os.environ["OLLAMA_AUTH_TOKEN"] = ollama_auth_token

    return {
        "default_model": default_model,
        "fallback_model": fallback_model,
        "ollama_base_url": ollama_base_url,
        "ollama_router_model": ollama_router_model,
        "ollama_enabled": ollama_enabled,
        "ollama_auth_token": bool(ollama_auth_token),
    }
