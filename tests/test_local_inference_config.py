"""Focused tests for local inference attempt construction."""

from __future__ import annotations

import pytest

from src.agents.base import HealthcareAgent


@pytest.mark.asyncio
async def test_build_llm_attempts_prefers_local_then_cloud(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_SPECIALIST_MODEL", "openai/specialist")
    monkeypatch.setenv("LOCAL_LLM_API_BASE", "http://localhost:8080/v1")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-token")
    monkeypatch.setenv("MEDGRAPH_FALLBACK_MODEL", "openai/fallback")

    agent = HealthcareAgent(
        name="symptom",
        system_prompt="test",
        model="gemini/primary",
        local_first=True,
        local_model_env="LOCAL_SPECIALIST_MODEL",
        cache_prompt_local=True,
    )

    attempts = await agent._build_llm_attempts()

    assert [attempt["model"] for attempt in attempts] == [
        "openai/specialist",
        "gemini/primary",
        "openai/fallback",
    ]
    assert attempts[0]["model_source"] == "local"
    assert attempts[0]["api_base"] == "http://localhost:8080/v1"
    assert attempts[0]["api_key"] == "local-token"
    assert attempts[0]["cache_prompt"] is True
    assert attempts[1]["model_source"] == "cloud"
    assert attempts[2]["model_source"] == "cloud"


@pytest.mark.asyncio
async def test_build_llm_attempts_respects_role_specific_api_base(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ROUTER_MODEL", "openai/router")
    monkeypatch.setenv("LOCAL_LLM_API_BASE", "http://localhost:8080/v1")
    monkeypatch.setenv("LOCAL_ROUTER_API_BASE", "http://localhost:18080/v1")
    monkeypatch.delenv("MEDGRAPH_FALLBACK_MODEL", raising=False)

    agent = HealthcareAgent(
        name="router",
        system_prompt="test",
        model="gemini/primary",
        local_first=True,
        local_model_env="LOCAL_ROUTER_MODEL",
        local_api_base_env="LOCAL_ROUTER_API_BASE",
    )

    attempts = await agent._build_llm_attempts()

    assert attempts[0]["model"] == "openai/router"
    assert attempts[0]["api_base"] == "http://localhost:18080/v1"
    assert [attempt["model_source"] for attempt in attempts] == ["local", "cloud"]


@pytest.mark.asyncio
async def test_build_llm_attempts_skips_local_when_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")
    monkeypatch.setenv("LOCAL_SPECIALIST_MODEL", "openai/specialist")
    monkeypatch.setenv("LOCAL_LLM_API_BASE", "http://localhost:8080/v1")
    monkeypatch.delenv("MEDGRAPH_FALLBACK_MODEL", raising=False)

    agent = HealthcareAgent(
        name="symptom",
        system_prompt="test",
        model="gemini/primary",
        local_first=True,
        local_model_env="LOCAL_SPECIALIST_MODEL",
    )

    assert await agent._build_llm_attempts() == [
        {"model": "gemini/primary", "model_source": "cloud"}
    ]


def test_kwargs_for_attempt_injects_cache_prompt_only_for_local_cache_attempt():
    agent = HealthcareAgent(name="symptom", system_prompt="test", model="gemini/primary")

    local_kwargs = agent._kwargs_for_attempt(
        base_kwargs={"temperature": 0.2, "extra_body": {"seed": 7}},
        attempt={
            "model": "openai/specialist",
            "model_source": "local",
            "api_base": "http://localhost:8080/v1",
            "api_key": "local",
            "cache_prompt": True,
        },
        response_format_factory=None,
    )
    cloud_kwargs = agent._kwargs_for_attempt(
        base_kwargs={"temperature": 0.2},
        attempt={
            "model": "gemini/primary",
            "model_source": "cloud",
            "cache_prompt": False,
        },
        response_format_factory=None,
    )

    assert local_kwargs["api_base"] == "http://localhost:8080/v1"
    assert local_kwargs["api_key"] == "local"
    assert local_kwargs["extra_body"] == {
        "seed": 7,
        "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    assert "api_base" not in cloud_kwargs
    assert "api_key" not in cloud_kwargs
    assert "extra_body" not in cloud_kwargs
