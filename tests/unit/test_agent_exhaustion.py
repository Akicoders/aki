from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentos.agent.core import AgentOS
from agentos.qwen.client import ChatResponse


pytestmark = pytest.mark.unit


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


@pytest.fixture
def agent_with_infinite_tool_calls(monkeypatch):
    config = MagicMock()
    config.max_iterations = 3
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

    monkeypatch.setattr("agentos.agent.core.create_event", MagicMock())

    agent = AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)
    return agent


def test_exhaustion_message_is_honest_and_actionable(agent_with_infinite_tool_calls):
    """The exhaustion message must not claim a retry that never happens, and
    must report concrete usage: limit, tool call count, last tools used."""
    agent = agent_with_infinite_tool_calls

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )
    result = outcome.response

    assert "3" in result  # max_iterations surfaced
    assert "memory.recall" in result  # last tool used surfaced
    assert "No final answer was produced" in result
    assert "simplify" in result.lower() or "clarify" in result.lower()
    forbidden_terms = ("worker", "sub-agent", "delegation", "routing", "orchestration")
    assert all(term not in result.lower() for term in forbidden_terms)


def test_exhaustion_message_without_tool_activity_names_reasoning_phase():
    result = AgentOS._format_exhaustion_message(
        max_iterations=2,
        total_tool_calls=0,
        last_tools_used=[],
    )

    assert "2" in result
    assert "No final answer was produced" in result
    assert "Last attempted: reasoning iteration" in result
    assert "tool" not in result.split("Last attempted:", 1)[1].split(".", 1)[0].lower()
