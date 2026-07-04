"""Integration tests for multi-agent orchestration Phase 2: delegation
interception wiring inside `_reasoning_loop`.

Covers the end-to-end delegate call -> nested worker loop -> supervisor
continuation path, worker session isolation, worker tool-policy/destructive
gate composition, and the non-delegating-turn regression guarantee.
"""
from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.agents import AgentProfile, AgentRegistry, MemoryPolicy, ToolPolicy
from agentos.agents.registry import ProfileNotFoundError
from agentos.core.config import AgentConfig
from agentos.memory.models import EventType, MemoryFact
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


pytestmark = pytest.mark.integration


def _profile(
    profile_id: str,
    *,
    allowed: list[str] | None = None,
    memory_scope: str = "project",
) -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name=profile_id,
        description=f"{profile_id} profile",
        role="custom",
        prompt_template=f"You are the {profile_id} agent.",
        tools=ToolPolicy(allowed=allowed or ["memory.recall"]),
        memory=MemoryPolicy(scope=memory_scope),
    )


class ScriptedSkills(SkillRegistry):
    """Advertises memory.recall + filesystem.write; write is destructive."""

    def __init__(self):
        super().__init__()
        self.executed: list[tuple[str, str, dict]] = []

    def get_all_tools(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "memory_recall", "description": "Recall memory", "parameters": {}}},
            {"type": "function", "function": {"name": "filesystem_write", "description": "Write a file", "parameters": {}}},
        ]

    def is_destructive(self, _skill_name: str, fn_name: str) -> bool:
        return fn_name == "write"

    async def execute(self, skill_name: str, function: str, arguments: dict):
        self.executed.append((skill_name, function, arguments))

        class Result:
            success = True
            error = None

            def model_dump_json(self) -> str:
                return '{"ok":true}'

        return Result()


class ScriptedQwenClient:
    """Returns queued responses per call, keyed by call order across
    supervisor and nested worker invocations (they share one qwen client)."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, **kwargs) -> ChatResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _delegate_tool_call(call_id: str, profile_id: str, task: str = "do work") -> dict:
    return {
        "id": call_id,
        "function": {
            "name": "delegate",
            "arguments": {"profile_id": profile_id, "task": task},
        },
    }


def _response(content: str, tool_calls: list[dict] | None = None) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=tool_calls or [],
        usage={},
        model="fake-qwen",
        finish_reason="tool_calls" if tool_calls else "stop",
    )


@pytest.mark.asyncio
async def test_delegate_call_resolves_worker_and_returns_result_to_supervisor(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        _response("worker done"),  # nested worker loop, depth=1
        _response("supervisor final answer"),  # supervisor resumes
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor"), _profile("worker")]),
    )

    response = await agent.chat(
        "please delegate", project="demo", session_id="sess-1", profile_id="supervisor"
    )

    assert response == "supervisor final answer"
    # Second qwen.chat call is the worker's nested loop, at depth=1: no delegate tool.
    worker_tool_names = [t["function"]["name"] for t in qwen.calls[1]["tools"]]
    assert "delegate" not in worker_tool_names
    # Third call is the supervisor's resumed loop, consuming the tool result.
    resumed_messages = qwen.calls[2]["messages"]
    tool_result = next(m for m in resumed_messages if m.get("role") == "tool")
    assert tool_result["tool_call_id"] == "call-1"
    assert tool_result["content"] == "worker done"


@pytest.mark.asyncio
async def test_unknown_profile_id_appends_error_and_continues(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "nonexistent")]),
        _response("recovered without worker"),
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor")]),
    )

    response = await agent.chat(
        "please delegate", project="demo", session_id="sess-2", profile_id="supervisor"
    )

    assert response == "recovered without worker"
    resumed_messages = qwen.calls[1]["messages"]
    tool_result = next(m for m in resumed_messages if m.get("role") == "tool")
    assert tool_result["tool_call_id"] == "call-1"
    assert "unknown profile" in tool_result["content"]
    assert "nonexistent" in tool_result["content"]


@pytest.mark.asyncio
async def test_worker_hallucinated_delegate_call_rejected_no_depth_two(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        # Worker hallucinates a delegate-shaped call; tools list at depth=1
        # never advertises "delegate", so it must be rejected as an unknown
        # tool, and no further qwen.chat() call (depth=2) may occur. This ends
        # the worker's own nested loop (denial), and the supervisor resumes
        # with the adapted worker outcome as its tool result.
        _response("", tool_calls=[_delegate_tool_call("call-2", "someone-else")]),
        _response("supervisor final"),
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor"), _profile("worker")]),
    )

    response = await agent.chat(
        "please delegate", project="demo", session_id="sess-3", profile_id="supervisor"
    )

    # Exactly 3 qwen.chat calls: supervisor delegate call, worker's single
    # rejected attempt, supervisor's resumed final response. No depth=2 loop
    # (which would require a 4th call) is ever constructed.
    assert len(qwen.calls) == 3
    assert response == "supervisor final"
    resumed_messages = qwen.calls[2]["messages"]
    tool_result = next(m for m in resumed_messages if m.get("role") == "tool")
    assert "not allowed" in tool_result["content"]


@pytest.mark.asyncio
async def test_worker_tool_policy_restricts_tool_supervisor_could_use(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        _response("worker final"),
        _response("supervisor final"),
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([
            _profile("supervisor", allowed=["memory.recall", "filesystem.write"]),
            _profile("worker", allowed=["memory.recall"]),
        ]),
    )

    await agent.chat("please delegate", project="demo", session_id="sess-4", profile_id="supervisor")

    worker_tool_names = [t["function"]["name"] for t in qwen.calls[1]["tools"]]
    assert "filesystem_write" not in worker_tool_names
    assert "memory_recall" in worker_tool_names


@pytest.mark.asyncio
async def test_destructive_gate_fires_inside_worker_nested_loop(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        # Worker's model emits an under-specified destructive call.
        _response(
            "",
            tool_calls=[{
                "id": "call-2",
                "function": {"name": "filesystem_write", "arguments": {}},
            }],
        ),
        _response("supervisor final"),
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([
            _profile("supervisor"),
            _profile("worker", allowed=["memory.recall", "filesystem.write"]),
        ]),
    )

    response = await agent.chat(
        "please delegate", project="demo", session_id="sess-5", profile_id="supervisor"
    )

    assert response == "supervisor final"
    resumed_messages = qwen.calls[2]["messages"]
    tool_result = next(m for m in resumed_messages if m.get("role") == "tool")
    assert "destino exacto" in tool_result["content"] or "path" in tool_result["content"].lower()
    assert skills.executed == []


@pytest.mark.asyncio
async def test_worker_writes_do_not_leak_into_supervisor_checkpoint(memory_repo):
    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        _response("", tool_calls=[{
            "id": "call-2",
            "function": {"name": "memory_recall", "arguments": {"query": "x"}},
        }]),
        _response("worker final"),
        _response("supervisor final"),
    ])
    skills = ScriptedSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=memory_repo,
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor"), _profile("worker")]),
    )

    memory_repo.upsert_fact(
        MemoryFact(key="shared", value="project fact", scope="project:demo")
    )

    response = await agent.chat(
        "please delegate", project="demo", session_id="sess-6", profile_id="supervisor"
    )

    assert response == "supervisor final"
    worker_sid = agent_core.AgentOS._derive_worker_session_id("sess-6", "call-1")

    supervisor_checkpoint = memory_repo.read_checkpoint("demo", "sess-6")
    assert supervisor_checkpoint is not None
    # No worker-derived session id leaks into the supervisor's own checkpoint key.
    assert memory_repo.read_checkpoint("demo", worker_sid) is None

    worker_ctx = memory_repo.assemble_context(
        query="anything", project="demo", session_id=worker_sid, max_tokens=8000
    )
    assert any(fact.key == "shared" for fact in worker_ctx.facts)


@pytest.mark.asyncio
async def test_non_delegating_turn_is_unaffected_by_delegation_wiring(monkeypatch):
    """Regression: a turn where the model never emits `delegate` must behave
    identically to pre-Phase-2 behavior -- same response, same status events,
    no worker loop invoked."""
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([_response("plain response")])
    skills = ScriptedSkills()
    statuses: list[str] = []
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor")]),
    )

    response = await agent.chat(
        "hello",
        project="demo",
        session_id="sess-7",
        profile_id="supervisor",
        status_callback=statuses.append,
    )

    assert response == "plain response"
    assert len(qwen.calls) == 1
    assert statuses == [
        "Starting turn",
        "📚 Collecting project context",
        "🧠 Thinking — iteration 1/3",
        "💾 Saving conversation",
        "✅ Turn complete",
    ]


@pytest.mark.asyncio
async def test_worker_nested_loop_emits_generic_tool_status_shape(monkeypatch):
    """Worker's depth=1 nested loop must emit the identical generic
    `🔧 Running {name} ({k}/{m})` shape a depth-0 supervisor turn would emit,
    with no worker/supervisor/delegate vocabulary in the string."""
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = ScriptedQwenClient([
        _response("", tool_calls=[_delegate_tool_call("call-1", "worker")]),
        # Worker's own nested loop: 1st of 1 tool call, then final response.
        _response("", tool_calls=[{
            "id": "call-2",
            "function": {"name": "memory_recall", "arguments": {"query": "x"}},
        }]),
        _response("worker final"),
        _response("supervisor final"),
    ])
    skills = ScriptedSkills()
    statuses: list[str] = []
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=_NullMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile("supervisor"), _profile("worker")]),
    )

    response = await agent.chat(
        "please delegate",
        project="demo",
        session_id="sess-8",
        profile_id="supervisor",
        status_callback=statuses.append,
    )

    assert response == "supervisor final"
    tool_statuses = [s for s in statuses if s.startswith("🔧 Running")]
    assert tool_statuses == ["🔧 Running memory.recall (1/1)"]
    rendered = "\n".join(statuses)
    for forbidden in ("worker", "supervisor", "delegate", "delegation"):
        assert forbidden not in rendered.lower()


class _NullMemory:
    """Minimal memory stub for tests that don't exercise memory content."""

    def assemble_context(self, **_kwargs):
        from agentos.memory.models import MemoryContext

        return MemoryContext()

    def read_checkpoint(self, project, session_id):
        return None

    def write_checkpoint(self, **_kwargs):
        return None
