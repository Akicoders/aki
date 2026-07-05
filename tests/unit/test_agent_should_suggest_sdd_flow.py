"""Guard-ordered tests for `AgentOS._should_suggest_sdd_flow` (Phase 2 of
sdd-scaffolding-flow-suggestion).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agentos.agent.core import AgentOS
from agentos.agents import AgentProfile, MemoryPolicy, ToolPolicy


def _profile(scope: str) -> AgentProfile:
    return AgentProfile(
        id="p1",
        name="P1",
        description="d",
        role="reviewer",
        prompt_template="t",
        tools=ToolPolicy(allowed=["memory.recall"]),
        memory=MemoryPolicy(scope=scope),
    )


def _make_agent(memory) -> AgentOS:
    config = MagicMock()
    config.max_iterations = 5
    config.temperature = 0.0

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    return AgentOS(config=config, qwen_client=MagicMock(), memory=memory, skill_registry=MagicMock())


def test_should_suggest_disabled_scope_suppresses_even_on_match():
    memory = MagicMock()
    memory.read_checkpoint = MagicMock(return_value=None)
    agent = _make_agent(memory)

    result = agent._should_suggest_sdd_flow(
        "armar toda la app", _profile("disabled"), "proj", "sess-1"
    )

    assert result is False
    memory.read_checkpoint.assert_not_called()


def test_should_suggest_non_keyword_input_short_circuits():
    memory = MagicMock()
    memory.read_checkpoint = MagicMock(return_value=None)
    agent = _make_agent(memory)

    result = agent._should_suggest_sdd_flow(
        "leé el archivo config.py", _profile("project"), "proj", "sess-1"
    )

    assert result is False
    memory.read_checkpoint.assert_not_called()


def test_should_suggest_first_turn_matches_and_no_checkpoint():
    memory = MagicMock()
    memory.read_checkpoint = MagicMock(return_value=None)
    agent = _make_agent(memory)

    result = agent._should_suggest_sdd_flow(
        "armar toda la app", _profile("project"), "proj", "sess-1"
    )

    assert result is True
    memory.read_checkpoint.assert_called_once_with("proj", "sess-1")


def test_should_suggest_later_turn_checkpoint_present():
    memory = MagicMock()
    memory.read_checkpoint = MagicMock(return_value={"goal": "x"})
    agent = _make_agent(memory)

    result = agent._should_suggest_sdd_flow(
        "armar toda la app", _profile("project"), "proj", "sess-1"
    )

    assert result is False


def test_should_suggest_none_profile_treated_as_enabled():
    memory = MagicMock()
    memory.read_checkpoint = MagicMock(return_value=None)
    agent = _make_agent(memory)

    result = agent._should_suggest_sdd_flow(
        "armar toda la app", None, "proj", "sess-1"
    )

    assert result is True
