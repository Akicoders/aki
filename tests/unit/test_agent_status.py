from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


class FakeMemory:
    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()


class FakeQwenClient:
    async def chat(self, **_kwargs) -> ChatResponse:
        return ChatResponse(
            content="hola",
            tool_calls=[],
            usage={},
            model="fake-qwen",
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_agent_chat_emits_useful_status_updates(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    agent = agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=FakeQwenClient(),
        memory=FakeMemory(),
        skill_registry=SkillRegistry(),
    )
    status_updates: list[str] = []

    response = await agent.chat("hola", status_callback=status_updates.append)

    assert response == "hola"
    assert status_updates == [
        "Collecting project context",
        "Reasoning with Qwen",
        "Saving conversation",
    ]
