"""Unit tests for multi-agent orchestration helpers.

Phase 1: depth threading, delegate tool schema helper, worker session-id
derivation, and outcome adaptation.
Phase 2 (unit-level only; end-to-end interception is covered in
tests/integration/test_delegation_runtime.py): `_run_delegation`'s isolated
unknown-profile_id error-adaptation behavior.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentos.agent.core import AgentOS, ReasoningOutcome
from agentos.qwen.client import ChatResponse


pytestmark = pytest.mark.unit


def _no_tool_call_response() -> ChatResponse:
    return ChatResponse(
        content="done",
        tool_calls=[],
        usage={},
        model="qwen-max",
        finish_reason="stop",
    )


@pytest.fixture
def agent_with_simple_response(monkeypatch):
    config = MagicMock()
    config.max_iterations = 3
    config.temperature = 0.0

    qwen = AsyncMock()
    qwen.chat.side_effect = [_no_tool_call_response() for _ in range(10)]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    skills.get_all_tools = MagicMock(return_value=[])

    monkeypatch.setattr("agentos.agent.core.create_event", MagicMock())

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)
    return agent, qwen


def test_reasoning_loop_includes_delegate_tool_at_depth_zero(agent_with_simple_response):
    agent, qwen = agent_with_simple_response

    asyncio.run(
        agent._reasoning_loop(
            messages=[], tools=[], project="default", session_id="s1", depth=0
        )
    )

    called_tools = qwen.chat.call_args.kwargs["tools"]
    tool_names = [t["function"]["name"] for t in called_tools]
    assert "delegate" in tool_names


def test_reasoning_loop_excludes_delegate_tool_at_depth_one(agent_with_simple_response):
    agent, qwen = agent_with_simple_response

    asyncio.run(
        agent._reasoning_loop(
            messages=[], tools=[], project="default", session_id="s1", depth=1
        )
    )

    called_tools = qwen.chat.call_args.kwargs["tools"]
    tool_names = [t["function"]["name"] for t in called_tools]
    assert "delegate" not in tool_names


def test_reasoning_loop_default_depth_includes_delegate_tool(agent_with_simple_response):
    """No `depth` arg passed (chat()'s call site) defaults to depth 0 behavior."""
    agent, qwen = agent_with_simple_response

    asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    called_tools = qwen.chat.call_args.kwargs["tools"]
    tool_names = [t["function"]["name"] for t in called_tools]
    assert "delegate" in tool_names


def test_build_delegate_tool_schema_shape():
    schema = AgentOS._build_delegate_tool_schema()

    assert schema["function"]["name"] == "delegate"
    params = schema["function"]["parameters"]["properties"]
    assert "profile_id" in params
    assert "task" in params
    required = schema["function"]["parameters"].get("required", [])
    assert "profile_id" in required
    assert "task" in required


def test_derive_worker_session_id_is_deterministic():
    first = AgentOS._derive_worker_session_id("sess_abc", "call-1")
    second = AgentOS._derive_worker_session_id("sess_abc", "call-1")
    assert first == second
    assert first == "sess_abc:delegate:call-1"


def test_derive_worker_session_id_differs_per_tool_call_id():
    first = AgentOS._derive_worker_session_id("sess_abc", "call-1")
    second = AgentOS._derive_worker_session_id("sess_abc", "call-2")
    assert first != second


def test_adapt_worker_outcome_success_contains_only_response():
    outcome = ReasoningOutcome(
        response="worker finished the task successfully",
        last_tool_summary="filesystem.read, memory.recall",
        exhausted=False,
    )

    content = AgentOS._adapt_worker_outcome(outcome)

    assert content == outcome.response
    assert "filesystem.read" not in content


def test_run_delegation_unknown_profile_returns_error_tool_result_without_propagating():
    """Task 2.5: unknown profile_id is adapted into an error tool-result
    message, not a raised/propagated ProfileNotFoundError."""
    from agentos.agents.registry import ProfileNotFoundError

    config = MagicMock()
    config.max_iterations = 3
    config.temperature = 0.0

    qwen = AsyncMock()
    registry = MagicMock()
    registry.resolve = MagicMock(side_effect=ProfileNotFoundError("agent profile not found: ghost"))

    agent = AgentOS(
        config=config,
        qwen_client=qwen,
        memory=MagicMock(),
        skill_registry=MagicMock(),
        agent_registry=registry,
    )

    message = asyncio.run(
        agent._run_delegation(
            fn_args={"profile_id": "ghost", "task": "do work"},
            project="default",
            session_id="s1",
            tool_call_id="call-9",
            status_callback=None,
        )
    )

    assert message == {
        "role": "tool",
        "tool_call_id": "call-9",
        "content": "delegate error: unknown profile 'ghost'",
    }
    qwen.chat.assert_not_called()


def test_adapt_worker_outcome_exhaustion_has_clear_marker():
    outcome = ReasoningOutcome(
        response="The turn reached the 5-iteration budget...",
        last_tool_summary="memory.recall",
        exhausted=True,
    )

    content = AgentOS._adapt_worker_outcome(outcome)

    assert "did not finish" in content.lower()
    assert "budget" in content.lower()
    assert content != outcome.response
