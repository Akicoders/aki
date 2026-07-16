"""Call-site wiring tests for the SDD-suggestion short-circuit in `chat()`
(Phase 3 of sdd-scaffolding-flow-suggestion).
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
SCAFFOLDING_INPUT = "creá un componente nuevo"


def _profile(scope: str = "project") -> AgentProfile:
    return AgentProfile(
        id="p1",
        name="P1",
        description="d",
        role="reviewer",
        prompt_template="You are a reviewer.",
        tools=ToolPolicy(allowed=["memory.recall", "filesystem.read", "filesystem.write"]),
        memory=MemoryPolicy(scope=scope),
    )


class FakeMemory:
    """Records checkpoint state; `checkpoints` maps (project, session_id) -> dict|None."""

    def __init__(self):
        self.checkpoints: dict[tuple[str, str], dict | None] = {}
        self.read_checkpoint_calls: list[tuple[str, str]] = []
        self.write_checkpoint_calls: list[dict] = []

    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def read_checkpoint(self, project: str, session_id: str):
        self.read_checkpoint_calls.append((project, session_id))
        return self.checkpoints.get((project, session_id))

    def write_checkpoint(self, project, session_id, **kwargs) -> None:
        self.write_checkpoint_calls.append({"project": project, "session_id": session_id, **kwargs})
        self.checkpoints[(project, session_id)] = {"goal": kwargs.get("goal")}


class FakeQwenClient:
    def __init__(self, responses: list[ChatResponse] | None = None):
        self.responses = responses or [
            ChatResponse(content="tool-driven response", tool_calls=[], usage={}, model="fake", finish_reason="stop")
        ]
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
            {"type": "function", "function": {"name": "filesystem_write", "description": "Write file", "parameters": {}}},
        ]

    def is_destructive(self, skill_name: str, fn_name: str) -> bool:
        return fn_name == "write"

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
async def test_chat_first_turn_new_product_request_zero_tool_calls(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient()
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    response = await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)

    assert qwen.calls == []
    assert skills.executed == []
    assert "sdd" in response.lower() or "SDD" in response


@pytest.mark.asyncio
async def test_chat_first_turn_suggestion_writes_checkpoint(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient()
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)

    assert len(memory.write_checkpoint_calls) == 1
    assert memory.write_checkpoint_calls[0]["project"] == "demo"
    assert memory.write_checkpoint_calls[0]["session_id"] == "sess-1"
    assert memory.checkpoints[("demo", "sess-1")] is not None


@pytest.mark.asyncio
async def test_chat_second_turn_same_phrasing_proceeds_normally(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(content="normal loop response", tool_calls=[], usage={}, model="fake", finish_reason="stop")
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    # First turn: short-circuits and writes a checkpoint.
    await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)
    assert qwen.calls == []

    # Second turn, identical phrasing: checkpoint now exists -> loop must run.
    response = await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)

    assert len(qwen.calls) == 1
    assert response == "normal loop response"


@pytest.mark.asyncio
async def test_chat_disabled_memory_suppresses_short_circuit(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(content="loop ran despite disabled memory", tool_calls=[], usage={}, model="fake", finish_reason="stop")
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)
    agent.agent_registry.resolve = lambda _pid: _profile("disabled")

    response = await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id="p1")

    assert len(qwen.calls) == 1
    assert response == "loop ran despite disabled memory"
    assert memory.write_checkpoint_calls == []


@pytest.mark.asyncio
async def test_chat_scaffolding_addendum_and_destructive_gate_unaffected(monkeypatch):
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(
            content="",
            tool_calls=[
                {"id": "call-1", "function": {"name": "filesystem_write", "arguments": {"path": "", "content": "x"}}}
            ],
            usage={},
            model="fake",
            finish_reason="tool_calls",
        ),
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    # Turn 1: new-product short-circuit fires, no tool calls, checkpoint written.
    await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)
    assert qwen.calls == []

    # Turn 2: scaffolding phrase + under-specified destructive call.
    response = await agent.chat(SCAFFOLDING_INPUT, project="demo", session_id="sess-1", profile_id=None)

    assert len(qwen.calls) == 1
    scaffolding_addendum_present = any(
        "scaffolding" in m["content"].lower() or "estructura" in m["content"].lower()
        for m in qwen.calls[0]["messages"]
        if m["role"] == "system"
    )
    assert scaffolding_addendum_present
    skills.executed == []
    assert "?" in response


@pytest.mark.asyncio
async def test_chat_new_product_no_explicit_profile_forces_planner(monkeypatch):
    """No explicit profile_id + high-confidence new-product signal -> server
    forces resolution to the 'planner' profile for that turn's checkpoint."""
    memory = FakeMemory()
    qwen = FakeQwenClient()
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-1", profile_id=None)

    assert len(memory.write_checkpoint_calls) == 1
    assert memory.write_checkpoint_calls[0]["active_profile_id"] == "planner"


@pytest.mark.asyncio
async def test_chat_new_product_explicit_profile_not_overridden(monkeypatch):
    """An explicit caller-provided profile_id on a new-product message must
    win over the forced-planner routing (never override explicit input)."""
    memory = FakeMemory()
    qwen = FakeQwenClient([
        ChatResponse(content="builder ran", tool_calls=[], usage={}, model="fake", finish_reason="stop")
    ])
    skills = FakeSkills()
    agent = _make_agent(monkeypatch, memory, qwen, skills)

    # Turn 1 (short-circuits into the canned SDD suggestion regardless of
    # profile_id, since a checkpoint doesn't exist yet): profile still
    # resolves and records as the explicit 'builder', never 'planner'.
    await agent.chat(NEW_PRODUCT_INPUT, project="demo", session_id="sess-2", profile_id="builder")
    assert memory.write_checkpoint_calls[0]["active_profile_id"] == "builder"

    # Turn 2, same explicit profile_id + same new-product phrasing: checkpoint
    # now exists, so the reasoning loop runs -- forced routing still must not
    # override the explicit 'builder' profile_id.
    response = await agent.chat(
        NEW_PRODUCT_INPUT, project="demo", session_id="sess-2", profile_id="builder"
    )

    assert len(memory.write_checkpoint_calls) == 2
    assert memory.write_checkpoint_calls[1]["active_profile_id"] == "builder"
    assert response == "builder ran"
