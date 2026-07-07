"""Unit tests for session-persistence repository helpers (Phase 1 / PR #1).

Covers task 1.1 (`_upsert_reserved_fact`) and task 1.2 (`touch_last_session`,
`get_last_session`).
"""

from sqlalchemy import select

from agentos.memory.models import MemoryFactModel


def _count_facts(memory_repo, key: str, scope: str) -> int:
    with memory_repo.db.session() as session:
        stmt = select(MemoryFactModel).where(
            MemoryFactModel.key == key, MemoryFactModel.scope == scope
        )
        return len(session.execute(stmt).scalars().all())


class TestUpsertReservedFact:
    """Task 1.1: dedicated no-duplicate-rows test for the reserved-fact upsert helper."""

    def test_upsert_reserved_fact_updates_in_place(self, memory_repo):
        key = "session:last"
        scope = "project:demo"

        memory_repo._upsert_reserved_fact(key, scope, "sess_first00")
        memory_repo._upsert_reserved_fact(key, scope, "sess_second0")

        assert _count_facts(memory_repo, key, scope) == 1
        fact = memory_repo.get_fact(key, scope)
        assert fact is not None
        assert fact.value == "sess_second0"


class TestLastSessionHelpers:
    """Task 1.2: last-session read/write helpers."""

    def test_get_last_session_absent_returns_none(self, memory_repo):
        assert memory_repo.get_last_session("demo") is None

    def test_touch_last_session_upserts_pointer(self, memory_repo):
        memory_repo.touch_last_session("demo", "sess_aaaaaaaa")
        memory_repo.touch_last_session("demo", "sess_bbbbbbbb")

        assert memory_repo.get_last_session("demo") == "sess_bbbbbbbb"
        assert _count_facts(memory_repo, "session:last", "project:demo") == 1


class TestSessionConversation:
    """Validate session conversation history retrieval and older session context integration."""

    def test_get_session_conversation_retrieves_ordered_history(self, memory_repo):
        from datetime import datetime, timedelta
        from agentos.memory.models import MemoryEvent, EventType

        session_id = "sess_history123"
        project = "demo"

        # Create two conversation events with distinct timestamps
        evt1 = MemoryEvent(
            type=EventType.CONVERSATION,
            project=project,
            content="Hello agent",
            source="user",
            session_id=session_id,
            timestamp=datetime.utcnow() - timedelta(minutes=10)
        )
        evt2 = MemoryEvent(
            type=EventType.CONVERSATION,
            project=project,
            content="Hello user",
            source="agent",
            session_id=session_id,
            timestamp=datetime.utcnow() - timedelta(minutes=5)
        )
        # Event from a different session
        evt_diff = MemoryEvent(
            type=EventType.CONVERSATION,
            project=project,
            content="Other session message",
            source="user",
            session_id="sess_different",
            timestamp=datetime.utcnow()
        )

        memory_repo.add_event(evt1)
        memory_repo.add_event(evt2)
        memory_repo.add_event(evt_diff)

        history = memory_repo.get_session_conversation(session_id)
        assert len(history) == 2
        assert history[0].content == "Hello agent"
        assert history[1].content == "Hello user"

    def test_assemble_context_includes_older_session_events(self, memory_repo):
        from datetime import datetime, timedelta
        from agentos.memory.models import MemoryEvent, EventType

        session_id = "sess_old_context"
        project = "demo"

        # Create a conversation event older than 2 hours (e.g. 5 hours ago)
        old_evt = MemoryEvent(
            type=EventType.CONVERSATION,
            project=project,
            content="Durable decision context",
            source="user",
            session_id=session_id,
            timestamp=datetime.utcnow() - timedelta(hours=5)
        )
        memory_repo.add_event(old_evt)

        # Assemble context for this session
        context = memory_repo.assemble_context(query="some query", project=project, session_id=session_id)

        # Assert that the old event is indeed retrieved because it belongs to the session_id
        session_event_contents = [e.content for e in context.events]
        assert "Durable decision context" in session_event_contents
