"""Unit tests for `_reasoning_loop`'s ReasoningOutcome return shape (task 2.3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentos.agent.core import AgentOS
from agentos.qwen.client import ChatResponse


pytestmark = pytest.mark.unit


def _final_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=None,
        usage={},
        model="qwen-max",
        finish_reason="stop",
    )


def _tool_call_response(tool_name: str, call_id: str) -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=[
            {
                "id": call_id,
                "function": {"name": tool_name, "arguments": "{}"},
            }
        ],
        usage={},
        model="qwen-max",
        finish_reason="tool_calls",
    )


def test_reasoning_loop_natural_completion_returns_outcome_with_tool_summary():
    config = MagicMock()
    config.max_iterations = 5
    config.temperature = 0.0

    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("memory_recall", "call-1"),
        _final_response("Final answer."),
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    assert outcome.response == "Final answer."
    assert outcome.exhausted is False
    assert "memory.recall" in outcome.last_tool_summary


def test_reasoning_loop_exhaustion_returns_outcome_with_exhausted_true():
    config = MagicMock()
    config.max_iterations = 2
    config.temperature = 0.0

    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("memory_recall", f"call-{i}") for i in range(10)
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    assert outcome.exhausted is True
    assert "memory.recall" in outcome.last_tool_summary
    assert "2" in outcome.response


def test_reasoning_loop_reports_iteration_progress_and_final_warning_before_exhaustion():
    config = MagicMock()
    config.max_iterations = 2
    config.temperature = 0.0

    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("memory_recall", f"call-{i}") for i in range(10)
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)
    status_updates: list[str] = []

    outcome = asyncio.run(
        agent._reasoning_loop(
            messages=[],
            tools=[],
            project="default",
            session_id="s1",
            status_callback=status_updates.append,
        )
    )

    assert outcome.exhausted is True
    assert status_updates[:3] == [
        "🧠 Thinking — iteration 1/2",
        "🔧 Running memory.recall (1/1)",
        "🧠 Thinking — iteration 2/2",
    ]
    assert "Final iteration 2/2; no automatic retry remains" not in status_updates


def test_profile_max_iterations_override_wins_over_new_global_default():
    """Regression guard (task 2.2): profile override must still take
    precedence over `AgentConfig.max_iterations` after the default bump
    from 5 to 20 (see core.py:398-402)."""
    config = MagicMock()
    config.max_iterations = 20
    config.temperature = 0.0

    profile = MagicMock()
    profile.max_iterations = 3
    profile.temperature = None
    profile.model = None

    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("memory_recall", f"call-{i}") for i in range(10)
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)
    status_updates: list[str] = []

    outcome = asyncio.run(
        agent._reasoning_loop(
            messages=[],
            tools=[],
            project="default",
            session_id="s1",
            profile=profile,
            status_callback=status_updates.append,
        )
    )

    # Effective budget must be the profile's 3, not the config's new default of 20.
    assert outcome.exhausted is True
    assert "3" in outcome.response
    assert status_updates[0] == "🧠 Thinking — iteration 1/3"
    assert qwen.chat.await_count == 3


def test_worker_depth_one_iteration_pool_independent_of_supervisor_after_default_bump():
    """Regression guard (task 2.3): a depth=1 worker loop resolves and
    tracks its own iteration budget independently from the depth=0
    supervisor's pool (core.py:572-580), unaffected by the default bump."""
    config = MagicMock()
    config.max_iterations = 20
    config.temperature = 0.0

    worker_profile = MagicMock()
    worker_profile.max_iterations = 2
    worker_profile.temperature = None
    worker_profile.model = None

    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("memory_recall", f"call-{i}") for i in range(10)
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)

    # depth=1 worker loop: exhausts against its own profile budget (2),
    # never touches the supervisor's config default (20).
    outcome = asyncio.run(
        agent._reasoning_loop(
            messages=[],
            tools=[],
            project="default",
            session_id="worker-s1",
            profile=worker_profile,
            depth=1,
        )
    )

    assert outcome.exhausted is True
    assert "2" in outcome.response
    assert qwen.chat.await_count == 2
