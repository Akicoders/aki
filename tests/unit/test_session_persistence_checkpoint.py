"""Unit tests for session-persistence checkpoint write/read (Phase 2 / PR #2).

Covers task 2.1 (`write_checkpoint` / `read_checkpoint`) and task 2.2
(checkpoint write also touches `session:last`, no duplicate rows).
"""

import json

from sqlalchemy import select

from agentos.memory.models import MemoryFactModel
from agentos.memory.repository import CHECKPOINT_FIELD_CHAR_CAP


def _count_facts(memory_repo, key: str, scope: str) -> int:
    with memory_repo.db.session() as session:
        stmt = select(MemoryFactModel).where(
            MemoryFactModel.key == key, MemoryFactModel.scope == scope
        )
        return len(session.execute(stmt).scalars().all())


class TestWriteReadCheckpoint:
    """Task 2.1: core write_checkpoint / read_checkpoint."""

    def test_write_then_read_checkpoint_roundtrip(self, memory_repo):
        memory_repo.write_checkpoint(
            project="demo",
            session_id="sess_aaaaaaaa",
            goal="Implement checkpoint write",
            last_response="Done implementing.",
            last_tool_result="ran pytest, 5 passed",
            iterations_exhausted=False,
        )

        checkpoint = memory_repo.read_checkpoint("demo", "sess_aaaaaaaa")

        assert checkpoint is not None
        assert checkpoint["goal"] == "Implement checkpoint write"
        assert checkpoint["open_items"] == []
        assert checkpoint["last_tool_result"] == "ran pytest, 5 passed"
        assert checkpoint["last_response"] == "Done implementing."
        assert checkpoint["iterations_exhausted"] is False

    def test_write_checkpoint_caps_long_fields(self, memory_repo):
        long_goal = "x" * (CHECKPOINT_FIELD_CHAR_CAP + 500)

        memory_repo.write_checkpoint(
            project="demo",
            session_id="sess_bbbbbbbb",
            goal=long_goal,
            last_response="short",
            last_tool_result="short",
            iterations_exhausted=False,
        )

        checkpoint = memory_repo.read_checkpoint("demo", "sess_bbbbbbbb")

        assert checkpoint is not None
        assert len(checkpoint["goal"]) == CHECKPOINT_FIELD_CHAR_CAP
        assert checkpoint["goal"] == long_goal[:CHECKPOINT_FIELD_CHAR_CAP]

    def test_read_checkpoint_missing_returns_none(self, memory_repo):
        assert memory_repo.read_checkpoint("demo", "sess_missing0") is None

    def test_read_checkpoint_tolerates_missing_version(self, memory_repo):
        blob = json.dumps(
            {
                "session_id": "sess_legacy00",
                "project": "demo",
                "goal": "legacy goal",
                "open_items": [],
                "last_tool_result": "",
                "last_response": "",
                "iterations_exhausted": False,
                "updated_at": "2024-01-01T00:00:00Z",
            }
        )
        memory_repo._upsert_reserved_fact(
            "session:sess_legacy00:checkpoint", "project:demo", blob
        )

        checkpoint = memory_repo.read_checkpoint("demo", "sess_legacy00")

        assert checkpoint is not None
        assert checkpoint["goal"] == "legacy goal"


class TestCheckpointTouchesLastSession:
    """Task 2.2: checkpoint write also upserts session:last, no duplicate rows."""

    def test_write_checkpoint_touches_last_session(self, memory_repo):
        memory_repo.write_checkpoint(
            project="demo",
            session_id="sess_cccccccc",
            goal="goal",
            last_response="response",
            last_tool_result="tool result",
            iterations_exhausted=False,
        )

        assert memory_repo.get_last_session("demo") == "sess_cccccccc"

    def test_write_checkpoint_no_duplicate_rows_across_multiple_writes(self, memory_repo):
        for i in range(3):
            memory_repo.write_checkpoint(
                project="demo",
                session_id="sess_dddddddd",
                goal=f"goal {i}",
                last_response=f"response {i}",
                last_tool_result=f"tool result {i}",
                iterations_exhausted=False,
            )

        assert _count_facts(
            memory_repo, "session:sess_dddddddd:checkpoint", "project:demo"
        ) == 1
        assert _count_facts(memory_repo, "session:last", "project:demo") == 1
        assert memory_repo.get_last_session("demo") == "sess_dddddddd"
