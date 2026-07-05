"""Unit tests for AgentConfig.max_iterations default, override, and bounds."""
import pytest
from pydantic import ValidationError

from agentos.core.config import AgentConfig


def test_default_max_iterations_is_twenty(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ITERATIONS", raising=False)
    config = AgentConfig()
    assert config.max_iterations == 20


def test_env_override_resolves_to_configured_value(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "10")
    config = AgentConfig()
    assert config.max_iterations == 10


def test_max_iterations_above_ceiling_raises(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "150")
    with pytest.raises(ValidationError):
        AgentConfig()


def test_max_iterations_non_positive_raises(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "0")
    with pytest.raises(ValidationError):
        AgentConfig()
