"""Ollama health checker with TTL cache.

Pings the local Ollama server to determine availability before
attempting local model inference in the router agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_HEALTH_TTL_SECONDS = 30
_PROBE_TIMEOUT_SECONDS = 2


class OllamaHealthChecker:
    """Async health checker for a local Ollama instance.

    - ``check(force=False)`` pings ``GET {base_url}/api/tags`` with a short timeout.
    - Results are cached for ``_HEALTH_TTL_SECONDS`` to avoid hammering Ollama.
    - An ``asyncio.Lock`` prevents concurrent probes.
    - If ``OLLAMA_ENABLED`` is ``false``, ``check()`` short-circuits to ``False``.
    """

    def __init__(self) -> None:
        self._available: bool = False
        self._last_check: float = 0.0
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Lazily create a lock bound to the current event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def is_available(self) -> bool:
        """Non-blocking read of the last cached result."""
        return self._available

    async def check(self, *, force: bool = False) -> bool:
        """Probe Ollama and return availability (cached with TTL).

        Args:
            force: Bypass TTL cache and probe immediately.
        """
        enabled = os.environ.get("OLLAMA_ENABLED", "true").lower() in ("true", "1", "yes")
        if not enabled:
            self._available = False
            return False

        now = time.monotonic()
        if not force and (now - self._last_check) < _HEALTH_TTL_SECONDS:
            return self._available

        lock = self._get_lock()
        async with lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            now = time.monotonic()
            if not force and (now - self._last_check) < _HEALTH_TTL_SECONDS:
                return self._available

            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            auth_token = os.environ.get("OLLAMA_AUTH_TOKEN", "")
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{base_url}/api/tags",
                        headers=headers,
                        timeout=_PROBE_TIMEOUT_SECONDS,
                    )
                    self._available = resp.status_code == 200
            except (httpx.ConnectError, httpx.TimeoutException, OSError):
                self._available = False
            except Exception:  # noqa: BLE001
                self._available = False

            self._last_check = time.monotonic()
            logger.debug("Ollama health check: available=%s", self._available)
            return self._available


# Module-level singleton
ollama_health = OllamaHealthChecker()
