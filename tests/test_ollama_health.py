"""Unit tests for the Ollama health checker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from src.ollama_health import OllamaHealthChecker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checker():
    """Fresh health checker for each test (no shared cache)."""
    return OllamaHealthChecker()


# ---------------------------------------------------------------------------
# Basic reachability
# ---------------------------------------------------------------------------


class TestOllamaReachability:
    """Test basic probe behaviour."""

    @pytest.mark.asyncio
    async def test_reachable_returns_true(self, checker):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await checker.check()

        assert result is True
        assert checker.is_available is True

    @pytest.mark.asyncio
    async def test_connection_refused_returns_false(self, checker):
        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await checker.check()

        assert result is False
        assert checker.is_available is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self, checker):
        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await checker.check()

        assert result is False


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestOllamaCaching:
    """Test TTL cache prevents excessive HTTP calls."""

    @pytest.mark.asyncio
    async def test_cache_within_ttl_no_extra_call(self, checker):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await checker.check()
            await checker.check()
            await checker.check()

        # AsyncClient should only be instantiated once (cached after first call)
        assert MockClient.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expired_refreshes(self, checker):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await checker.check()
            # Expire the cache by rewinding last_check
            checker._last_check = 0.0
            await checker.check()

        assert MockClient.call_count == 2

    @pytest.mark.asyncio
    async def test_force_bypasses_cache(self, checker):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await checker.check()
            await checker.check(force=True)

        assert MockClient.call_count == 2


# ---------------------------------------------------------------------------
# OLLAMA_ENABLED=false
# ---------------------------------------------------------------------------


class TestOllamaDisabled:
    """Test that OLLAMA_ENABLED=false skips HTTP entirely."""

    @pytest.mark.asyncio
    async def test_disabled_skips_http(self, checker):
        with patch.dict("os.environ", {"OLLAMA_ENABLED": "false"}):
            with patch("src.ollama_health.httpx.AsyncClient") as MockClient:
                result = await checker.check()

        assert result is False
        assert checker.is_available is False
        MockClient.assert_not_called()
