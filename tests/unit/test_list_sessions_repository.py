"""Unit tests for `MemoryRepository.list_sessions` (session-list-and-help, Phase 1)."""

import json
from datetime import datetime, timedelta

import pytest

from agentos.memory.repository import SessionSummary


def _seed_checkpoint(memory_repo, project, session_id, *, goal="", updated_at=None, iterations_exhausted=False):
    memory_repo.write_checkpoint(
        project,
        session_id,
        goal=goal,
        last_response="",
        last_tool_result="",
        iterations_exhausted=iterations_exhausted,
    )
    if updated_at is not None:
        # Overwrite the row's updated_at (both payload + column) for deterministic ordering.
        key = f"session:{session_id}:checkpoint"
        scope = f"project:{project}"
        fact = memory_repo.get_fact(key, scope)
        data = json.loads(fact.value)
        data["updated_at"] = updated_at.isoformat() + "Z"
        from agentos.memory.models import MemoryFactModel

        with memory_repo.db.session() as session:
            model = session.get(MemoryFactModel, fact.id)
            model.value = json.dumps(data)
            model.updated_at = updated_at


class TestListSessionsOrdering:
    def test_list_sessions_orders_newest_first(self, memory_repo):
        base = datetime(2024, 1, 1, 12, 0, 0)
        _seed_checkpoint(memory_repo, "demo", "sess_aaaa0001", goal="first", updated_at=base)
        _seed_checkpoint(memory_repo, "demo", "sess_bbbb0002", goal="second", updated_at=base + timedelta(hours=1))
        _seed_checkpoint(memory_repo, "demo", "sess_cccc0003", goal="third", updated_at=base + timedelta(hours=2))

        result = memory_repo.list_sessions("demo")

        assert all(isinstance(r, SessionSummary) for r in result)
        assert [r.session_id for r in result] == ["sess_cccc0003", "sess_bbbb0002", "sess_aaaa0001"]


class TestListSessionsExcludesLastPointer:
    def test_list_sessions_excludes_last_pointer(self, memory_repo):
        _seed_checkpoint(memory_repo, "demo", "sess_real0001", goal="real session")

        result = memory_repo.list_sessions("demo")

        assert len(result) == 1
        assert result[0].session_id == "sess_real0001"


class TestListSessionsCorruptRow:
    def test_list_sessions_skips_corrupt_row_logs_warning(self, memory_repo, caplog):
        _seed_checkpoint(memory_repo, "demo", "sess_good0001", goal="good one")
        memory_repo._upsert_reserved_fact(
            "session:sess_bad00001:checkpoint", "project:demo", "{not-json"
        )

        with caplog.at_level("WARNING"):
            result = memory_repo.list_sessions("demo")

        assert [r.session_id for r in result] == ["sess_good0001"]
        assert any("sess_bad00001" in record.message for record in caplog.records)

    def test_read_checkpoint_still_raises_on_corrupt_row(self, memory_repo):
        memory_repo._upsert_reserved_fact(
            "session:sess_bad00002:checkpoint", "project:demo", "{not-json"
        )

        with pytest.raises(Exception):
            memory_repo.read_checkpoint("demo", "sess_bad00002")


class TestListSessionsFallbacks:
    def test_list_sessions_updated_at_falls_back_to_column(self, memory_repo):
        memory_repo.write_checkpoint(
            "demo",
            "sess_nodate01",
            goal="no updated_at in payload",
            last_response="",
            last_tool_result="",
            iterations_exhausted=False,
        )
        key = "session:sess_nodate01:checkpoint"
        scope = "project:demo"
        fact = memory_repo.get_fact(key, scope)
        data = json.loads(fact.value)
        del data["updated_at"]

        from agentos.memory.models import MemoryFactModel

        with memory_repo.db.session() as session:
            model = session.get(MemoryFactModel, fact.id)
            model.value = json.dumps(data)

        with memory_repo.db.session() as session:
            column_updated_at = session.get(MemoryFactModel, fact.id).updated_at

        result = memory_repo.list_sessions("demo")

        assert len(result) == 1
        assert result[0].updated_at == column_updated_at

    def test_list_sessions_empty_project_returns_empty_list(self, memory_repo):
        assert memory_repo.list_sessions("empty-project") == []
