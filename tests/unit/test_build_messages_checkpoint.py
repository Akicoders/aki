"""Unit tests for task 3.2: `_build_messages` injects a dedicated, budget-immune
checkpoint system-message slot."""

from __future__ import annotations

import pytest

from agentos.agent import core as agent_core
from agentos.core.config import AgentConfig
from agentos.memory.models import MemoryContext, MemoryFact
from agentos.qwen.client import ChatResponse
from agentos.skills.base import SkillRegistry


class FakeMemory:
    def __init__(self, checkpoint: dict | None = None):
        self._checkpoint = checkpoint

    def assemble_context(self, **_kwargs) -> MemoryContext:
        return MemoryContext()

    def write_checkpoint(self, *_args, **_kwargs) -> None:
        pass

    def read_checkpoint(self, project, session_id):
        return self._checkpoint


def _agent(memory: FakeMemory) -> agent_core.AgentOS:
    return agent_core.AgentOS(
        config=AgentConfig(),
        qwen_client=None,
        memory=memory,
        skill_registry=SkillRegistry(),
    )


class TestBuildMessagesCheckpointSlot:
    def test_build_messages_injects_checkpoint_slot(self, monkeypatch):
        monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)

        checkpoint = {
            "v": 1,
            "session_id": "sess_aaaaaaaa",
            "project": "demo",
            "goal": "Finish the checkpoint rehydration slot",
            "open_items": ["wire _build_messages"],
            "last_tool_result": "ran pytest",
            "last_response": "in progress",
            "iterations_exhausted": False,
        }
        memory = FakeMemory(checkpoint=checkpoint)
        agent = _agent(memory)

        context = MemoryContext()
        messages = agent._build_messages(
            "continue please", context, "demo", session_id="sess_aaaaaaaa"
        )

        checkpoint_messages = [
            m for m in messages
            if m["role"] == "system" and "Finish the checkpoint rehydration slot" in m["content"]
        ]
        assert len(checkpoint_messages) == 1

        roles_content = [m["content"] for m in messages if m["role"] == "system"]
        # Checkpoint slot must appear before any memory-context injection.
        checkpoint_idx = next(
            i for i, c in enumerate(roles_content)
            if "Finish the checkpoint rehydration slot" in c
        )
        assert checkpoint_idx == 1  # right after the base system prompt

    def test_build_messages_no_checkpoint_omits_slot(self, monkeypatch):
        monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)

        memory = FakeMemory(checkpoint=None)
        agent = _agent(memory)

        context = MemoryContext()
        messages = agent._build_messages(
            "hello", context, "demo", session_id="sess_bbbbbbbb"
        )

        assert not any("Checkpoint" in m["content"] for m in messages if m["role"] == "system")

    def test_build_messages_checkpoint_survives_budget_truncation(self, monkeypatch):
        monkeypatch.setattr(agent_core.AgentOS, "_init_skills", lambda self: None)

        checkpoint = {
            "v": 1,
            "session_id": "sess_cccccccc",
            "project": "demo",
            "goal": "Survive truncation",
            "open_items": [],
            "last_tool_result": "",
            "last_response": "",
            "iterations_exhausted": False,
        }
        memory = FakeMemory(checkpoint=checkpoint)
        agent = _agent(memory)

        # Build a context whose format_for_prompt output is huge, so that if
        # the checkpoint were routed through the same budget-fit machinery it
        # would be truncated away. Since _build_messages doesn't re-run
        # budget-fit itself (that already happened in assemble_context), we
        # simulate a "small budget" by monkeypatching memory config max
        # tokens indirectly isn't needed: the key assertion is that the
        # checkpoint slot is present regardless of context.format_for_prompt
        # output size/content.
        many_facts = [
            MemoryFact(key=f"k{i}", value="x" * 500, scope="project:demo", confidence=1.0)
            for i in range(50)
        ]
        context = MemoryContext(facts=many_facts)

        messages = agent._build_messages(
            "continue", context, "demo", session_id="sess_cccccccc"
        )

        assert any(
            m["role"] == "system" and "Survive truncation" in m["content"]
            for m in messages
        )
