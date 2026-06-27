"""Unit tests for AgentOS memory models."""

import pytest
from datetime import datetime
from uuid import uuid4

from agentos.memory.models import (
    MemoryEvent, MemoryFact, Skill, MemoryContext,
    EventType, MemoryEventModel, MemoryFactModel, SkillModel,
)


class TestMemoryEvent:
    def test_create_event(self):
        event = MemoryEvent(
            type=EventType.USER_PREFERENCE,
            project="ERP-AI",
            content="Usamos pnpm",
            meta={"key": "package_manager"},
        )
        assert event.type == EventType.USER_PREFERENCE
        assert event.project == "ERP-AI"
        assert event.content == "Usamos pnpm"
        assert event.meta["key"] == "package_manager"
        assert event.id.startswith("evt_")

    def test_event_roundtrip(self):
        event = MemoryEvent(
            type=EventType.DECISION,
            project="test",
            content="Decidí usar X",
        )
        model = event.to_model()
        assert model.id == event.id
        assert model.content == event.content

        restored = MemoryEvent.from_model(model)
        assert restored.id == event.id
        assert restored.content == event.content

    def test_event_with_embedding(self):
        event = MemoryEvent(
            type=EventType.CONVERSATION,
            project="test",
            content="Hola",
            embedding=[0.1, 0.2, 0.3],
        )
        model = event.to_model()
        assert model.embedding is not None
        import json
        assert json.loads(model.embedding) == [0.1, 0.2, 0.3]


class TestMemoryFact:
    def test_create_fact(self):
        fact = MemoryFact(
            key="package_manager",
            value="pnpm",
            scope="project:ERP-AI",
            confidence=0.95,
        )
        assert fact.key == "package_manager"
        assert fact.value == "pnpm"
        assert fact.scope == "project:ERP-AI"
        assert fact.confidence == 0.95
        assert fact.id.startswith("fact_")

    def test_fact_roundtrip(self):
        fact = MemoryFact(
            key="test_key",
            value="test_value",
            scope="global",
        )
        model = fact.to_model()
        restored = MemoryFact.from_model(model)
        assert restored.key == fact.key
        assert restored.value == fact.value
        assert restored.scope == fact.scope


class TestSkill:
    def test_create_skill(self):
        skill = Skill(
            name="git_ops",
            description="Git operations",
            functions=["status", "diff", "commit"],
        )
        assert skill.name == "git_ops"
        assert "status" in skill.functions
        assert skill.enabled is True

    def test_skill_json_properties(self):
        skill = Skill(
            name="test",
            description="Test",
            functions=["a", "b"],
            config={"opt": "val"},
        )
        assert skill.functions_json == '["a", "b"]'
        assert skill.config_json == '{"opt": "val"}'


class TestMemoryContext:
    def test_format_for_prompt(self):
        context = MemoryContext(
            facts=[
                MemoryFact(key="k1", value="v1", scope="project:test"),
                MemoryFact(key="k2", value="v2", scope="global"),
            ],
            events=[
                MemoryEvent(type=EventType.USER_PREFERENCE, project="test", content="prefiero X"),
            ],
            skills=[
                Skill(name="git", description="Git ops", functions=["status"]),
            ],
        )
        formatted = context.format_for_prompt()
        assert "Hechos conocidos" in formatted
        assert "k1 = v1" in formatted
        assert "Eventos recientes" in formatted
        assert "prefiero X" in formatted
        assert "Herramientas disponibles" in formatted
        assert "git" in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])