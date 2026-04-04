"""HTTP client for the OpenFDA API with rate limiting, retries, and caching.

Synchronous httpx.Client wrapper matching the project's sync-first codebase.
Handles the OpenFDA rate limit (240 requests/minute without key, higher with).

Usage:
    from data.openfda.client import OpenFDAClient

    client = OpenFDAClient()
    result = client.get("drug/label", {"search": 'openfda.generic_name:"METFORMIN"'})
    client.close()
"""

import logging
import os
import random
import time
from collections import OrderedDict
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov"


# ── Token Bucket Rate Limiter ────────────────────────────────────────────


class _TokenBucket:
    """Simple token bucket for rate limiting.

    Allows burst traffic at start (e.g. proactive scan), then throttles
    to a steady rate.
    """

    def __init__(self, rate: float = 4.0, burst: int = 10):
        self._rate = rate          # tokens per second
        self._burst = burst        # max tokens
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Sleep until at least one token is available
            wait = (1.0 - self._tokens) / self._rate
            time.sleep(wait)


# ── In-Memory TTL Cache ──────────────────────────────────────────────────


class _TTLCache:
    """In-memory cache with per-entry TTL and LRU eviction.

    Caches parsed results to avoid re-parsing. Also caches "not found"
    (None) results with a shorter TTL.
    """

    _SENTINEL = object()  # Distinguishes cached None from cache miss

    def __init__(self, max_entries: int = 500):
        self._max = max_entries
        # OrderedDict for LRU: most recently accessed at end
        self._store: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str) -> object:
        """Return cached value or _SENTINEL if miss/expired."""
        entry = self._store.get(key)
        if entry is None:
            return self._SENTINEL

        expiry, value = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return self._SENTINEL

        # Move to end (most recently used)
        self._store.move_to_end(key)
        return value

    def put(self, key: str, value: object, ttl: float) -> None:
        """Cache a value with TTL in seconds."""
        expiry = time.monotonic() + ttl
        self._store[key] = (expiry, value)
        self._store.move_to_end(key)

        # Evict oldest if over capacity
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._store)


# ── OpenFDA Client ───────────────────────────────────────────────────────


# Default TTLs (seconds)
LABEL_CACHE_TTL = 3600.0       # 1 hour for drug labels
FAERS_CACHE_TTL = 14400.0      # 4 hours for FAERS (updates quarterly)
NOT_FOUND_CACHE_TTL = 600.0    # 10 minutes for "not found" results

# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0         # seconds
RETRY_MAX_DELAY = 10.0


class OpenFDAClient:
    """Synchronous HTTP client for the OpenFDA API.

    Handles rate limiting (token bucket), retries with exponential backoff,
    and in-memory caching. Works without an API key (1000 req/day) or with
    one (120k/day) via OPENFDA_API_KEY env var.

    Usage:
        client = OpenFDAClient()
        try:
            data = client.get("drug/label", {"search": '...'})
        finally:
            client.close()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 20.0,
    ):
        self._api_key = api_key or os.environ.get("OPENFDA_API_KEY")
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._bucket = _TokenBucket(rate=4.0, burst=10)
        self._cache = _TTLCache(max_entries=500)
        self._request_count = 0

    # ── Public API ────────────────────────────────────────────────────

    def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        cache_ttl: Optional[float] = None,
    ) -> Optional[dict]:
        """Make a GET request to the OpenFDA API.

        Args:
            endpoint: API path, e.g. "drug/label" or "drug/event".
            params: Query parameters (search, count, limit, etc.).
            cache_ttl: Cache TTL in seconds. None = no caching.

        Returns:
            Parsed JSON dict, or None if no results / error.
        """
        params = dict(params) if params else {}
        if self._api_key:
            params["api_key"] = self._api_key

        # Build cache key from endpoint + sorted params (excluding api_key)
        cache_key = None
        if cache_ttl is not None:
            cache_params = {k: v for k, v in sorted(params.items()) if k != "api_key"}
            cache_key = f"{endpoint}|{cache_params}"
            cached = self._cache.get(cache_key)
            if cached is not self._cache._SENTINEL:
                logger.debug("Cache hit: %s", cache_key[:80])
                return cached

        # Rate limit
        self._bucket.acquire()

        # Request with retries
        result = self._request_with_retries(endpoint, params)

        # Cache the result (including None for not-found)
        if cache_key is not None:
            ttl = cache_ttl if result is not None else NOT_FOUND_CACHE_TTL
            self._cache.put(cache_key, result, ttl)

        return result

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()
        logger.debug(
            "OpenFDA client closed. %d requests made, %d cache entries.",
            self._request_count, self._cache.size,
        )

    @property
    def request_count(self) -> int:
        """Total API requests made (excludes cache hits)."""
        return self._request_count

    @property
    def cache_size(self) -> int:
        """Current number of cached entries."""
        return self._cache.size

    # ── Internal ──────────────────────────────────────────────────────

    def _request_with_retries(
        self, endpoint: str, params: dict
    ) -> Optional[dict]:
        """Execute request with exponential backoff + jitter on 429/5xx."""
        url = f"/{endpoint}.json"

        for attempt in range(MAX_RETRIES + 1):
            try:
                self._request_count += 1
                resp = self._http.get(url, params=params)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 404:
                    # No data found — don't retry
                    logger.debug("404 for %s — no data found", endpoint)
                    return None

                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES:
                        delay = min(
                            RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                            RETRY_MAX_DELAY,
                        )
                        logger.warning(
                            "OpenFDA %d on %s, retry %d/%d in %.1fs",
                            resp.status_code, endpoint, attempt + 1,
                            MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                        self._bucket.acquire()
                        continue
                    logger.error(
                        "OpenFDA %d on %s after %d retries",
                        resp.status_code, endpoint, MAX_RETRIES,
                    )
                    return None

                # Other error codes — log and return None
                logger.warning(
                    "OpenFDA unexpected status %d on %s",
                    resp.status_code, endpoint,
                )
                return None

            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Timeout on %s, retry %d/%d in %.1fs",
                        endpoint, attempt + 1, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Timeout on %s after %d retries", endpoint, MAX_RETRIES)
                return None

            except httpx.HTTPError as e:
                logger.error("HTTP error on %s: %s", endpoint, e)
                return None

        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
