from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentos.agent.core import AgentOS
from agentos.qwen.client import ChatResponse


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

    result = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    assert "3" in result  # max_iterations surfaced
    assert "memory.recall" in result  # last tool used surfaced
    assert "no voy a reintentar" in result.lower() or "no reintent" in result.lower()
    assert "otra forma" not in result.lower() or "no voy a" in result.lower()
