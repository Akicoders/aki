"""Locking/regression tests (Phase 4 of sdd-scaffolding-flow-suggestion):

- worker delegation (`_run_delegation` -> `_reasoning_loop(depth=1)`) never
  triggers the new-product suggestion, since it never routes through `chat()`.
- `stream_chat` inherits the `chat()` short-circuit for free.

No production code changes in this phase; these tests lock in structural
guarantees already provided by Phase 3's placement in `chat()`.
"""

from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.agents import AgentProfile, MemoryPolicy, ToolPolicy
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


NEW_PRODUCT_INPUT = "armar toda la app"


def _profile() -> AgentProfile:
    return AgentProfile(
        id="worker-profile",
        name="Worker",
        description="d",
        role="builder",
        prompt_template="You are a worker.",
        tools=ToolPolicy(allowed=["filesystem.read"]),
        memory=MemoryPolicy(scope="project"),
    )


class FakeMemory:
    def __init__(self):
        self.checkpoints: dict[tuple[str, str], dict | None] = {}
        self.write_checkpoint_calls: list[dict] = []

    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def read_checkpoint(self, project: str, session_id: str):
        return self.checkpoints.get((project, session_id))

    def write_checkpoint(self, project, session_id, **kwargs) -> None:
        self.write_checkpoint_calls.append({"project": project, "session_id": session_id, **kwargs})
        self.checkpoints[(project, session_id)] = {"goal": kwargs.get("goal")}


class FakeQwenClient:
    def __init__(self, responses: list[ChatResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, **kwargs) -> ChatResponse:
        self.calls.append(kwargs)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


class FakeSkills(SkillRegistry):
    def __init__(self):
        super().__init__()
        self.executed: list[tuple[str, str, dict]] = []

    def get_all_tools(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "filesystem_read", "description": "Read file", "parameters": {}}},
        ]

    def is_destructive(self, _skill_name: str, _fn_name: str) -> bool:
        return False

    async def execute(self, skill_name: str, function: str, arguments: dict):
        self.executed.append((skill_name, function, arguments))

        class Result:
            success = True
            error = None

            def model_dump_json(self) -> str:
                return '{"ok":true}'

        return Result()


def _make_agent(monkeypatch, memory, qwen, skills):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)
    return agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=qwen,
        memory=memory,
        skill_registry=skills,
    )


@pytest.mark.asyncio
async def test_delegation_worker_never_triggers_new_product_suggestion(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(content="worker did the task", tool_calls=[], usage={}, model="fake", finish_reason="stop"),
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)
    agent.agent_registry.resolve = lambda _pid: _profile()

    tool_result_msg = await agent._run_delegation(
        fn_args={"profile_id": "worker-profile", "task": NEW_PRODUCT_INPUT},
        project="demo",
        session_id="sess-1",
        tool_call_id="call-1",
        status_callback=None,
    )

    # The worker's own reasoning loop ran normally (LLM was consulted),
    # and produced its actual answer -- not the SDD suggestion text.
    assert len(qwen.calls) == 1
    assert tool_result_msg["content"] == "worker did the task"
    assert "sdd-init" not in tool_result_msg["content"].lower()


@pytest.mark.asyncio
async def test_stream_chat_first_turn_new_product_request_yields_suggestion(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(content="should not be reached", tool_calls=[], usage={}, model="fake", finish_reason="stop"),
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    chunks = [
        chunk async for chunk in agent.stream_chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1")
    ]
    streamed = "".join(chunks).strip()

    assert qwen.calls == []
    assert skills.executed == []
    assert "sdd" in streamed.lower()
