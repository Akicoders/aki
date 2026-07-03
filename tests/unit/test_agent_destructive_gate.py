"""Tests for the destructive-call gate wired into `_reasoning_loop` (Phase 3)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from agentos.agent.core import AgentOS
from agentos.qwen.client import ChatResponse


def _tool_call_response(tool_name: str, call_id: str, arguments: dict) -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=[
            {
                "id": call_id,
                "function": {"name": tool_name, "arguments": arguments},
            }
        ],
        usage={},
        model="qwen-max",
        finish_reason="tool_calls",
    )


def _batch_response(calls: list[tuple[str, str, dict]]) -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=[
            {"id": call_id, "function": {"name": name, "arguments": args}}
            for (name, call_id, args) in calls
        ],
        usage={},
        model="qwen-max",
        finish_reason="tool_calls",
    )


def _final_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=None,
        usage={},
        model="qwen-max",
        finish_reason="stop",
    )


def _make_agent(qwen, skills, config=None):
    if config is None:
        config = MagicMock()
        config.max_iterations = 5
        config.temperature = 0.0

    import agentos.agent.core as core_module
    core_module.create_event = MagicMock()

    return AgentOS(config=config, qwen_client=qwen, memory=MagicMock(), skill_registry=skills)


def test_reasoning_loop_gates_destructive_underspecified_call():
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("filesystem_write", "call-1", {"path": "", "content": "x"}),
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=True)
    skills.execute = AsyncMock()

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    skills.execute.assert_not_called()
    assert outcome.exhausted is False
    assert "?" in outcome.response


def test_reasoning_loop_executes_well_specified_destructive_call():
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("filesystem_write", "call-1", {"path": "/tmp/x.py", "content": "print(1)"}),
        _final_response("Done."),
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=True)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    skills.execute.assert_called_once_with("filesystem", "write", {"path": "/tmp/x.py", "content": "print(1)"})
    assert outcome.response == "Done."


def test_reasoning_loop_never_gates_nondestructive_calls():
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("filesystem_read", "call-1", {}),
        _final_response("Done."),
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=False)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    skills.execute.assert_called_once()
    assert outcome.response == "Done."


def test_reasoning_loop_gate_fires_without_scaffolding_keyword():
    """Independence scenario (ADR-4): the gate fires purely off destructive +
    under-specified args, with no dependency on the scaffolding prompt branch
    having matched (that branch lives in _build_messages, not the loop)."""
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("filesystem_delete", "call-1", {"path": ""}),
    ]

    skills = MagicMock()
    skills.is_destructive = MagicMock(return_value=True)
    skills.execute = AsyncMock()

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    skills.execute.assert_not_called()
    assert outcome.exhausted is False


def test_reasoning_loop_batch_nondestructive_before_gated_destructive():
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _batch_response([
            ("filesystem_read", "call-1", {"path": "/tmp/x.py"}),
            ("filesystem_write", "call-2", {"path": "", "content": "x"}),
        ]),
    ]

    def is_destructive(skill_name, fn_name):
        return fn_name == "write"

    skills = MagicMock()
    skills.is_destructive = MagicMock(side_effect=is_destructive)
    result = MagicMock()
    result.success = True
    result.error = None
    result.model_dump_json.return_value = "{}"
    skills.execute = AsyncMock(return_value=result)

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    skills.execute.assert_called_once_with("filesystem", "read", {"path": "/tmp/x.py"})
    assert outcome.exhausted is False
    assert "?" in outcome.response
