from __future__ import annotations

from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext
from agentos.skills.base import SkillRegistry


class FakeMemory:
    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def write_checkpoint(self, *_args, **_kwargs) -> None:
        pass

    def read_checkpoint(self, project, session_id):
        return None


def _agent(monkeypatch) -> agent_core.AgentOS:
    monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)
    return agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=None,
        memory=FakeMemory(),
        skill_registry=SkillRegistry(),
    )


def _git_guidance_messages(messages: list[dict]) -> list[dict]:
    return [
        message
        for message in messages
        if message["role"] == "system" and "git_ops.status" in message["content"]
    ]


def test_build_messages_git_phrase_injects_guidance(monkeypatch) -> None:
    agent = _agent(monkeypatch)
    context = MemoryContext()

    messages = agent._build_messages("quiero versionamiento", context, "demo")

    matches = _git_guidance_messages(messages)
    assert len(matches) == 1
    assert "git_ops.init" in matches[0]["content"]


def test_build_messages_repo_status_phrase_injects_guidance(monkeypatch) -> None:
    agent = _agent(monkeypatch)
    context = MemoryContext()

    messages = agent._build_messages("revisar el estado del repo", context, "demo")

    matches = _git_guidance_messages(messages)
    assert len(matches) == 1
