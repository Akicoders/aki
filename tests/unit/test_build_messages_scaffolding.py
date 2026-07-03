"""Tests for the scaffolding-intent prompt addendum branch in `_build_messages`."""

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


def _scaffolding_messages(messages: list[dict]) -> list[dict]:
    return [
        m for m in messages
        if m["role"] == "system" and "scaffolding" in m["content"].lower()
        or (m["role"] == "system" and "scaffolding" in m["content"].lower())
    ]


def test_build_messages_scaffolding_keyword_injects_addendum(monkeypatch):
    agent = _agent(monkeypatch)
    context = MemoryContext()

    messages = agent._build_messages("creá un componente nuevo", context, "demo")

    matches = [
        m for m in messages
        if m["role"] == "system" and "scaffolding" in m["content"].lower()
    ]
    assert len(matches) == 1


def test_build_messages_non_scaffolding_input_no_addendum(monkeypatch):
    agent = _agent(monkeypatch)
    context = MemoryContext()

    messages = agent._build_messages("leé el archivo config.py", context, "demo")

    matches = [
        m for m in messages
        if m["role"] == "system" and "scaffolding" in m["content"].lower()
    ]
    assert matches == []


def test_build_messages_english_scaffolding_keyword_injects_addendum(monkeypatch):
    agent = _agent(monkeypatch)
    context = MemoryContext()

    messages = agent._build_messages("create a new component", context, "demo")

    matches = [
        m for m in messages
        if m["role"] == "system" and "scaffolding" in m["content"].lower()
    ]
    assert len(matches) == 1

    messages2 = agent._build_messages("set up the project structure", context, "demo")
    matches2 = [
        m for m in messages2
        if m["role"] == "system" and "scaffolding" in m["content"].lower()
    ]
    assert len(matches2) == 1
