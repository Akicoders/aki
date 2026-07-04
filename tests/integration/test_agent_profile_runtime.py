from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.agents import AgentProfile, AgentRegistry, DelegationMetadata, MemoryPolicy, ToolPolicy
from agentos.core.config import AgentConfig
from agentos.memory.models import EventType, MemoryContext, MemoryEvent, MemoryFact
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


pytestmark = pytest.mark.integration


def _profile(
    profile_id: str = "reviewer",
    *,
    prompt_template: str = "You are a careful reviewer.",
    allowed: list[str] | None = None,
    memory_scope: str = "project",
    model: str | None = None,
    temperature: float | None = None,
    max_iterations: int | None = None,
) -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name="Reviewer",
        description="Reviews changes",
        role="reviewer",
        prompt_template=prompt_template,
        model=model,
        temperature=temperature,
        max_iterations=max_iterations,
        tools=ToolPolicy(allowed=allowed or ["memory.recall"]),
        memory=MemoryPolicy(scope=memory_scope),
    )


class RecordingMemory:
    def __init__(self, context: MemoryContext | None = None):
        self.context = context or MemoryContext()
        self.assemble_calls: list[dict] = []
        self.read_checkpoint_calls: list[tuple[str, str]] = []
        self.checkpoint_calls: list[dict] = []

    def assemble_context(self, **kwargs) -> MemoryContext:
        self.assemble_calls.append(kwargs)
        return self.context

    def read_checkpoint(self, project: str, session_id: str):
        self.read_checkpoint_calls.append((project, session_id))
        return None

    def write_checkpoint(self, project, session_id, **kwargs) -> None:
        self.checkpoint_calls.append({"project": project, "session_id": session_id, **kwargs})


class RecordingQwenClient:
    def __init__(self, responses: list[ChatResponse] | None = None):
        self.responses = responses or [
            ChatResponse(
                content="default response",
                tool_calls=[],
                usage={},
                model="fake-qwen",
                finish_reason="stop",
            )
        ]
        self.calls: list[dict] = []

    async def chat(self, **kwargs) -> ChatResponse:
        self.calls.append(kwargs)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


class RecordingSkills(SkillRegistry):
    def __init__(self):
        super().__init__()
        self.executed: list[tuple[str, str, dict]] = []

    def get_all_tools(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "memory_recall", "description": "Recall memory", "parameters": {}}},
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


@pytest.mark.asyncio
async def test_no_profile_chat_preserves_default_prompt_model_tools_and_memory(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    events: list[dict] = []
    monkeypatch.setattr(agent_core, "create_event", lambda **kwargs: events.append(kwargs))

    memory = RecordingMemory()
    qwen = RecordingQwenClient()
    skills = RecordingSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3, temperature=0.4),
        qwen_client=qwen,
        memory=memory,
        skill_registry=skills,
    )

    response = await agent.chat("hello", project="demo", session_id="sess-default")

    assert response == "default response"
    assert memory.assemble_calls == [
        {"query": "hello", "project": "demo", "session_id": "sess-default", "max_tokens": 8000}
    ]
    assert qwen.calls[0]["temperature"] == 0.4
    assert "model" not in qwen.calls[0]
    assert [tool["function"]["name"] for tool in qwen.calls[0]["tools"]] == [
        "memory_recall",
        "filesystem_read",
        "delegate",
    ]
    assert events[0]["meta"] == {"role": "user"}
    assert events[1]["meta"] == {"role": "assistant"}
    assert memory.checkpoint_calls[0].get("active_profile_id") is None


@pytest.mark.asyncio
async def test_stream_chat_passes_no_profile_by_default(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = RecordingQwenClient([
        ChatResponse(content="streamed response", tool_calls=[], usage={}, model="fake", finish_reason="stop")
    ])
    agent = agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=qwen,
        memory=RecordingMemory(),
        skill_registry=RecordingSkills(),
    )

    chunks = [chunk async for chunk in agent.stream_chat("hello", project="demo", session_id="sess-stream")]

    assert "".join(chunks).strip() == "streamed response"
    assert qwen.calls[0]["messages"][0]["content"].startswith("You are Aki")


@pytest.mark.asyncio
async def test_selected_profile_applies_prompt_model_temperature_iterations_and_tool_filter(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = RecordingQwenClient([
        ChatResponse(content="profiled", tool_calls=[], usage={}, model="qwen-plus", finish_reason="stop")
    ])
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=5, temperature=0.8),
        qwen_client=qwen,
        memory=RecordingMemory(),
        skill_registry=RecordingSkills(),
        agent_registry=AgentRegistry([
            _profile(
                prompt_template="Reviewer prompt: inspect risks.",
                allowed=["memory.recall"],
                model="qwen-plus",
                temperature=0.1,
                max_iterations=1,
            )
        ]),
    )

    response = await agent.chat("review", project="demo", session_id="sess-profile", profile_id="reviewer")

    assert response == "profiled"
    assert qwen.calls[0]["messages"][0] == {"role": "system", "content": "Reviewer prompt: inspect risks."}
    assert qwen.calls[0]["model"] == "qwen-plus"
    assert qwen.calls[0]["temperature"] == 0.1
    assert [tool["function"]["name"] for tool in qwen.calls[0]["tools"]] == ["memory_recall", "delegate"]


@pytest.mark.asyncio
async def test_unknown_profile_fails_before_persisting_user_input_or_calling_qwen(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    events: list[dict] = []
    monkeypatch.setattr(agent_core, "create_event", lambda **kwargs: events.append(kwargs))

    qwen = RecordingQwenClient()
    memory = RecordingMemory()
    agent = agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=qwen,
        memory=memory,
        skill_registry=RecordingSkills(),
        agent_registry=AgentRegistry([_profile()]),
    )

    with pytest.raises(KeyError, match="missing"):
        await agent.chat("hello", project="demo", session_id="sess-missing", profile_id="missing")

    assert events == []
    assert memory.assemble_calls == []
    assert qwen.calls == []


@pytest.mark.asyncio
async def test_disallowed_tool_is_blocked_before_skill_registry_execution(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    qwen = RecordingQwenClient([
        ChatResponse(
            content="",
            tool_calls=[
                {"id": "call-1", "function": {"name": "filesystem_read", "arguments": {"path": "README.md"}}}
            ],
            usage={},
            model="fake",
            finish_reason="tool_calls",
        )
    ])
    skills = RecordingSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=RecordingMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([_profile(allowed=["memory.recall"])]),
    )

    response = await agent.chat("read", project="demo", session_id="sess-tools", profile_id="reviewer")

    assert "not allowed" in response
    assert "filesystem.read" in response
    assert skills.executed == []


@pytest.mark.asyncio
async def test_session_memory_policy_filters_context_and_records_profile_metadata(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    events: list[dict] = []
    monkeypatch.setattr(agent_core, "create_event", lambda **kwargs: events.append(kwargs))

    context = MemoryContext(
        facts=[MemoryFact(key="project-secret", value="do not leak", scope="project:demo")],
        events=[
            MemoryEvent(type=EventType.CONVERSATION, project="demo", content="same session", source="user", session_id="sess-allowed"),
            MemoryEvent(type=EventType.CONVERSATION, project="demo", content="other session", source="user", session_id="sess-other"),
        ],
    )
    memory = RecordingMemory(context)
    qwen = RecordingQwenClient()
    agent = agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=qwen,
        memory=memory,
        skill_registry=RecordingSkills(),
        agent_registry=AgentRegistry([_profile(memory_scope="session")]),
    )

    await agent.chat("remember?", project="demo", session_id="sess-allowed", profile_id="reviewer")

    rendered_messages = "\n".join(message["content"] for message in qwen.calls[0]["messages"])
    assert "same session" in rendered_messages
    assert "project-secret" not in rendered_messages
    assert "other session" not in rendered_messages
    assert events[0]["meta"] == {"role": "user", "active_profile_id": "reviewer"}
    assert events[1]["meta"] == {"role": "assistant", "active_profile_id": "reviewer"}
    assert memory.checkpoint_calls[0]["active_profile_id"] == "reviewer"


@pytest.mark.asyncio
async def test_disabled_memory_policy_skips_memory_reads_and_writes(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    events: list[dict] = []
    monkeypatch.setattr(agent_core, "create_event", lambda **kwargs: events.append(kwargs))

    memory = RecordingMemory(MemoryContext(facts=[MemoryFact(key="secret", value="hidden", scope="project:demo")]))
    qwen = RecordingQwenClient([
        ChatResponse(
            content="",
            tool_calls=[
                {"id": "call-1", "function": {"name": "memory_recall", "arguments": {"query": "hello"}}}
            ],
            usage={},
            model="fake",
            finish_reason="tool_calls",
        )
    ])
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=1),
        qwen_client=qwen,
        memory=memory,
        skill_registry=RecordingSkills(),
        agent_registry=AgentRegistry([_profile(memory_scope="disabled")]),
    )

    await agent.chat("hello", project="demo", session_id="sess-disabled", profile_id="reviewer")

    assert memory.assemble_calls == []
    assert memory.read_checkpoint_calls == []
    assert events == []
    assert memory.checkpoint_calls == []
    assert "secret" not in "\n".join(message["content"] for message in qwen.calls[0]["messages"])


@pytest.mark.asyncio
async def test_delegation_metadata_remains_inert_during_selected_profile_turn(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    profile = _profile().model_copy(
        update={"delegation": DelegationMetadata(enabled=True, strategy="future-worker-chain")}
    )
    qwen = RecordingQwenClient([
        ChatResponse(
            content="single loop response",
            tool_calls=[],
            usage={},
            model="fake",
            finish_reason="stop",
        )
    ])
    skills = RecordingSkills()
    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=3),
        qwen_client=qwen,
        memory=RecordingMemory(),
        skill_registry=skills,
        agent_registry=AgentRegistry([profile]),
    )

    response = await agent.chat(
        "review",
        project="demo",
        session_id="sess-delegation",
        profile_id="reviewer",
    )

    assert response == "single loop response"
    assert len(qwen.calls) == 1
    assert skills.executed == []
