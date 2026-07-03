from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


pytestmark = pytest.mark.unit


class FakeMemory:
    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def write_checkpoint(self, *_args, **_kwargs) -> None:
        pass

    def read_checkpoint(self, project, session_id):
        return None


class FakeQwenClient:
    async def chat(self, **_kwargs) -> ChatResponse:
        return ChatResponse(
            content="hola",
            tool_calls=[],
            usage={},
            model="fake-qwen",
            finish_reason="stop",
        )


class FakeToolQwenClient:
    async def chat(self, **_kwargs) -> ChatResponse:
        return ChatResponse(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "function": {
                        "name": "memory_recall",
                        "arguments": {
                            "query": "api_key=secret-123",
                            "path": "/home/private/project/secret.txt",
                        },
                    },
                },
                {
                    "id": "call-2",
                    "function": {
                        "name": "filesystem_read",
                        "arguments": {"path": "/home/private/project/notes.md"},
                    },
                },
            ],
            usage={},
            model="fake-qwen",
            finish_reason="tool_calls",
        )


class FakeToolRegistry(SkillRegistry):
    def __init__(self):
        super().__init__()
        self.executed: list[tuple[str, str, object]] = []

    def is_destructive(self, _skill_name: str, _fn_name: str) -> bool:
        return False

    async def execute(self, skill_name: str, fn_name: str, args):
        self.executed.append((skill_name, fn_name, args))

        class Result:
            success = True
            error = None

            def model_dump_json(self) -> str:
                return '{"payload":"secret-result"}'

        return Result()


@pytest.mark.asyncio
async def test_agent_chat_emits_useful_status_updates(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=FakeQwenClient(),
        memory=FakeMemory(),
        skill_registry=SkillRegistry(),
    )
    status_updates: list[str] = []

    response = await agent.chat("hola", status_callback=status_updates.append)

    assert response == "hola"
    assert status_updates == [
        "Starting turn",
        "Collecting project context",
        "Reasoning iteration 1/3",
        "Saving conversation",
        "Turn complete",
    ]


@pytest.mark.asyncio
async def test_reasoning_loop_emits_safe_iteration_final_and_tool_statuses(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=1),
        qwen_client=FakeToolQwenClient(),
        memory=FakeMemory(),
        skill_registry=FakeToolRegistry(),
    )
    status_updates: list[str] = []

    outcome = await agent._reasoning_loop(
        messages=[],
        tools=[],
        project="default",
        session_id="s1",
        status_callback=status_updates.append,
    )

    assert outcome.exhausted is True
    assert status_updates == [
        "Reasoning iteration 1/1",
        "Final iteration 1/1; no automatic retry remains",
        "Running tool 1/2: memory.recall",
        "Running tool 2/2: filesystem.read",
    ]
    rendered_status = "\n".join(status_updates)
    assert "api_key=secret-123" not in rendered_status
    assert "/home/private/project" not in rendered_status
    assert "secret-result" not in rendered_status
