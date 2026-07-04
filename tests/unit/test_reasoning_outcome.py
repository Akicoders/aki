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
