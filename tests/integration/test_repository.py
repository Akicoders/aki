"""Integration tests for memory repository."""

import pytest

from agentos.memory.models import EventType, MemoryEvent, MemoryFact


class TestMemoryRepository:
    """Test memory repository operations."""

    def test_add_and_get_event(self, memory_repo):
        event = memory_repo.add_event(MemoryEvent(
            type=EventType.USER_PREFERENCE,
            project="test-project",
            content="Me gusta Python",
            meta={"lang": "es"},
        ))
        assert event.id is not None
        assert event.project == "test-project"

        retrieved = memory_repo.get_event(event.id)
        assert retrieved is not None
        assert retrieved.content == "Me gusta Python"
        assert retrieved.meta["lang"] == "es"

    def test_search_events(self, memory_repo):
        memory_repo.add_event(MemoryEvent(type=EventType.USER_PREFERENCE, project="proj1", content="prefiero pnpm"))
        memory_repo.add_event(MemoryEvent(type=EventType.DECISION, project="proj1", content="usar FastAPI"))
        memory_repo.add_event(MemoryEvent(type=EventType.CONVERSATION, project="proj2", content="hola mundo"))

        results = memory_repo.search_events("pnpm", project="proj1")
        assert len(results) >= 1
        assert any("pnpm" in r.content for r in results)

    def test_search_events_by_type(self, memory_repo):
        memory_repo.add_event(MemoryEvent(type=EventType.USER_PREFERENCE, project="proj", content="pref 1"))
        memory_repo.add_event(MemoryEvent(type=EventType.DECISION, project="proj", content="dec 1"))
        memory_repo.add_event(MemoryEvent(type=EventType.USER_PREFERENCE, project="proj", content="pref 2"))

        prefs = memory_repo.search_events("", project="proj", event_types=[EventType.USER_PREFERENCE])
        assert len(prefs) == 2
        assert all(r.type == EventType.USER_PREFERENCE for r in prefs)

    def test_recent_events(self, memory_repo):
        memory_repo.add_event(MemoryEvent(type=EventType.CONVERSATION, project="proj", content="msg 1"))
        memory_repo.add_event(MemoryEvent(type=EventType.CONVERSATION, project="proj", content="msg 2"))

        recent = memory_repo.get_recent_events(project="proj", limit=5, hours=1)
        assert len(recent) == 2

    def test_upsert_fact(self, memory_repo):
        fact = MemoryFact(
            key="package_manager",
            value="pnpm",
            scope="project:test-project",
            confidence=0.9,
        )
        memory_repo.upsert_fact(fact)

        retrieved = memory_repo.get_fact("package_manager", "project:test-project")
        assert retrieved is not None
        assert retrieved.value == "pnpm"
        assert retrieved.confidence == 0.9

    def test_update_fact(self, memory_repo):
        fact = MemoryFact(key="k", value="v1", scope="project:p")
        memory_repo.upsert_fact(fact)

        fact.value = "v2"
        fact.confidence = 0.8
        memory_repo.upsert_fact(fact)

        retrieved = memory_repo.get_fact("k", "project:p")
        assert retrieved.value == "v2"
        assert retrieved.confidence == 0.8

    def test_search_facts(self, memory_repo):
        memory_repo.upsert_fact(MemoryFact(key="pkg_mgr", value="pnpm", scope="project:p"))
        memory_repo.upsert_fact(MemoryFact(key="editor", value="nvim", scope="project:p"))
        memory_repo.upsert_fact(MemoryFact(key="os", value="arch", scope="global"))

        results = memory_repo.search_facts("pkg", scope="project:p")
        assert len(results) == 1
        assert results[0].key == "pkg_mgr"

    def test_facts_by_scope(self, memory_repo):
        memory_repo.upsert_fact(MemoryFact(key="a", value="1", scope="project:p1"))
        memory_repo.upsert_fact(MemoryFact(key="b", value="2", scope="project:p1"))
        memory_repo.upsert_fact(MemoryFact(key="c", value="3", scope="project:p2"))

        facts = memory_repo.get_facts_by_scope("project:p1")
        assert len(facts) == 2

    def test_assemble_context(self, memory_repo):
        memory_repo.add_event(MemoryEvent(type=EventType.USER_PREFERENCE, project="proj", content="uso pnpm"))
        memory_repo.upsert_fact(MemoryFact(key="pkg", value="pnpm", scope="project:proj"))

        context = memory_repo.assemble_context("package manager", project="proj")
        assert len(context.facts) >= 1
        assert len(context.events) >= 1
        formatted = context.format_for_prompt()
        assert "pnpm" in formatted

    def test_empty_query_search_uses_filters_without_embedding(self, memory_repo, fake_embedder):
        memory_repo.add_event(MemoryEvent(type=EventType.USER_PREFERENCE, project="proj", content="pref 1"))
        memory_repo.add_event(MemoryEvent(type=EventType.DECISION, project="proj", content="dec 1"))
        calls_after_writes = list(fake_embedder.calls)

        results = memory_repo.search_events(
            "",
            project="proj",
            event_types=[EventType.USER_PREFERENCE],
        )

        assert [event.type for event in results] == [EventType.USER_PREFERENCE]
        assert fake_embedder.calls == calls_after_writes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
