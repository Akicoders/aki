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
