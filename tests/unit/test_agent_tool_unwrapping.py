import pytest
from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry, SkillResult
from agentos.memory.models import MemoryContext


class FakeMemory:
    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()
    def write_checkpoint(self, *_args, **_kwargs) -> None:
        pass
    def read_checkpoint(self, project, session_id):
        return None


class FakeToolQwenClient:
    async def chat(self, **_kwargs) -> ChatResponse:
        return ChatResponse(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "function": {
                        "name": "dummy_skill.dummy_fn",
                        "arguments": {},
                    },
                }
            ],
            usage={},
            model="fake-qwen",
            finish_reason="tool_calls",
        )


@pytest.mark.asyncio
async def test_agent_unwraps_successful_tool_result(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    class CustomToolRegistry(SkillRegistry):
        def is_destructive(self, _skill_name: str, _fn_name: str) -> bool:
            return False
        async def execute(self, skill_name: str, function: str, arguments: dict) -> SkillResult:
            return SkillResult(success=True, data={"secret_key": "abc-123"}, error=None)

    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=1),
        qwen_client=FakeToolQwenClient(),
        memory=FakeMemory(),
        skill_registry=CustomToolRegistry(),
    )

    messages = []
    await agent._reasoning_loop(
        messages=messages,
        tools=[],
        project="default",
        session_id="s1",
        status_callback=lambda x: None,
    )

    # Check that tool result content is unwrapped (only data payload is serialized)
    tool_msg = next(msg for msg in messages if msg["role"] == "tool")
    assert tool_msg["content"] == '{"secret_key": "abc-123"}'
    assert "success" not in tool_msg["content"]
    assert "error" not in tool_msg["content"]


@pytest.mark.asyncio
async def test_agent_wraps_error_tool_result_cleanly(monkeypatch):
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    monkeypatch.setattr(agent_core, "create_event", lambda **_kwargs: None)

    class CustomToolRegistry(SkillRegistry):
        def is_destructive(self, _skill_name: str, _fn_name: str) -> bool:
            return False
        async def execute(self, skill_name: str, function: str, arguments: dict) -> SkillResult:
            return SkillResult(success=False, data=None, error="Custom system error message")

    agent = agent_core.AgentOS(
        config=AgentConfig(max_iterations=1),
        qwen_client=FakeToolQwenClient(),
        memory=FakeMemory(),
        skill_registry=CustomToolRegistry(),
    )

    messages = []
    await agent._reasoning_loop(
        messages=messages,
        tools=[],
        project="default",
        session_id="s1",
        status_callback=lambda x: None,
    )

    tool_msg = next(msg for msg in messages if msg["role"] == "tool")
    assert tool_msg["content"] == '{"error": "Custom system error message"}'
