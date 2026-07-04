from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

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


def test_reasoning_loop_can_bootstrap_git_without_filesystem_writes() -> None:
    project_path = "/tmp/project"
    qwen = AsyncMock()
    qwen.chat.side_effect = [
        _tool_call_response("git_ops_status", "call-1", {"path": project_path}),
        _tool_call_response("git_ops_init", "call-2", {"path": project_path, "initial_branch": "main"}),
        _final_response("Git initialized."),
    ]

    skills = MagicMock()

    def is_destructive(skill_name, fn_name):
        return skill_name == "git_ops" and fn_name == "init"

    skills.is_destructive = MagicMock(side_effect=is_destructive)

    status_result = MagicMock()
    status_result.success = False
    status_result.error = f"Not a git repository: {project_path}"
    status_result.model_dump_json.return_value = "{}"

    init_result = MagicMock()
    init_result.success = True
    init_result.error = None
    init_result.model_dump_json.return_value = "{}"

    skills.execute = AsyncMock(side_effect=[status_result, init_result])

    agent = _make_agent(qwen, skills)

    outcome = asyncio.run(
        agent._reasoning_loop(messages=[], tools=[], project="default", session_id="s1")
    )

    assert outcome.response == "Git initialized."
    assert skills.execute.await_args_list == [
        call("git_ops", "status", {"path": project_path}),
        call("git_ops", "init", {"path": project_path, "initial_branch": "main"}),
    ]
