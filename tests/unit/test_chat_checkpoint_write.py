"""Unit tests for AgentOS.chat() checkpoint write site (task 2.4)."""

from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


class FakeMemory:
    def __init__(self):
        self.checkpoint_calls: list[dict] = []

    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def write_checkpoint(self, project, session_id, *, goal, last_response, last_tool_result, iterations_exhausted):
        self.checkpoint_calls.append(
            {
                "project": project,
                "session_id": session_id,
                "goal": goal,
                "last_response": last_response,
                "last_tool_result": last_tool_result,
                "iterations_exhausted": iterations_exhausted,
            }
        )


class FakeQwenClient:
    def __init__(self, response: ChatResponse):
        self._response = response

    async def chat(self, **_kwargs) -> ChatResponse:
        return self._response


def _final_response(content: str) -> ChatResponse:
    return ChatResponse(content=content, tool_calls=[], usage={}, model="fake-qwen", finish_reason="stop")


@pytest.mark.asyncio
async def test_chat_writes_checkpoint_each_turn(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    memory = FakeMemory()
    agent = agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=FakeQwenClient(_final_response("Final answer.")),
        memory=memory,
        skill_registry=SkillRegistry(),
    )

    response = await agent.chat("do the thing", project="demo", session_id="sess_aaaaaaaa")

    assert response == "Final answer."
    assert len(memory.checkpoint_calls) == 1
    call = memory.checkpoint_calls[0]
    assert call["project"] == "demo"
    assert call["session_id"] == "sess_aaaaaaaa"
    assert call["goal"] == "do the thing"
    assert call["last_response"] == "Final answer."
    assert call["iterations_exhausted"] is False


@pytest.mark.asyncio
async def test_chat_writes_checkpoint_on_exhaustion(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    config = AgentConfig()
    config.max_iterations = 1

    memory = FakeMemory()
    tool_call_response = ChatResponse(
        content="",
        tool_calls=[{"id": "call-1", "function": {"name": "memory_recall", "arguments": "{}"}}],
        usage={},
        model="fake-qwen",
        finish_reason="tool_calls",
    )

    class FakeSkills(SkillRegistry):
        pass

    skills = SkillRegistry()

    class FakeResult:
        success = True
        error = None

        def model_dump_json(self):
            return "{}"

    async def fake_execute(*_args, **_kwargs):
        return FakeResult()

    monkeypatch.setattr(skills, "execute", fake_execute)
    monkeypatch.setattr(skills, "get_all_tools", lambda: [])

    agent = agent_core.AgentOS(
        config=config,
        qwen_client=FakeQwenClient(tool_call_response),
        memory=memory,
        skill_registry=skills,
    )

    response = await agent.chat("do the thing", project="demo", session_id="sess_bbbbbbbb")

    assert len(memory.checkpoint_calls) == 1
    call = memory.checkpoint_calls[0]
    assert call["iterations_exhausted"] is True
    assert call["last_response"] == response
