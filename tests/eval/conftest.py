"""Shared pytest fixtures for the evaluation test suite."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from tests.eval.datasets import DatasetLoader

# Load .env so GEMINI_API_KEY is available when needed (e.g. judge tests)
load_dotenv()


def _has_api_key() -> bool:
    """Check whether a Gemini or OpenAI API key is configured."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))


requires_api_key = pytest.mark.skipif(
    not _has_api_key(),
    reason="No API key configured (GEMINI_API_KEY or OPENAI_API_KEY)",
)


# ---------------------------------------------------------------------------
# Dataset fixtures (no API key needed)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dataset_loader() -> DatasetLoader:
    """Session-scoped DatasetLoader instance."""
    return DatasetLoader()


@pytest.fixture(scope="session")
def liveqa_samples(dataset_loader: DatasetLoader):
    """Load LiveQA samples once per test session."""
    return dataset_loader.load_liveqa()


@pytest.fixture(scope="session")
def medication_qa_samples(dataset_loader: DatasetLoader):
    """Load MedicationQA samples once per test session."""
    return dataset_loader.load_medication_qa()


@pytest.fixture(scope="session")
def safety_samples(dataset_loader: DatasetLoader):
    """Load safety/adversarial samples once per test session."""
    return dataset_loader.load_safety()


@pytest.fixture(scope="session")
def has_gemini_api_key() -> bool:
    """Check whether a Gemini API key is configured."""
    return bool(os.getenv("GEMINI_API_KEY"))


# ---------------------------------------------------------------------------
# Real system fixtures (require API key)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def system_config():
    """Load project config (sets model env vars). Session-scoped."""
    from src.config import load_config

    return load_config()


@pytest.fixture(scope="session")
def graph(system_config):
    """Build the LangGraph orchestration graph. Session-scoped."""
    from src.orchestrator.graph import build_graph

    return build_graph()


@pytest.fixture(scope="session")
def router(system_config):
    """RouterAdapter wrapping the real RouterAgent. Session-scoped."""
    from src.agents.router import RouterAgent
    from tests.eval.routing import RouterAdapter

    return RouterAdapter(RouterAgent())


@pytest.fixture(scope="session")
def judge(system_config):
    """LLM judge instance, using the same model as the system. Session-scoped."""
    from tests.eval.judge import Judge

    return Judge(
        model=system_config["default_model"],
        fallback_model=system_config.get("fallback_model"),
    )


@pytest.fixture(scope="session")
def persona_simulator(system_config, graph):
    """PersonaSimulator instance. Session-scoped (needs graph + config)."""
    from tests.eval.persona import PersonaSimulator

    return PersonaSimulator(
        model=system_config["default_model"],
        graph=graph,
    )


@pytest.fixture(scope="session")
def personas():
    """List of all defined evaluation personas."""
    from tests.eval.personas import ALL_PERSONAS

    return ALL_PERSONAS
