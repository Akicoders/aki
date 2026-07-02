"""Unit tests for the pure `_resolve_session_id` CLI helper (task 1.3)."""

from __future__ import annotations

from agentos.cli.main import _resolve_session_id


class _StubMemory:
    """Minimal stand-in exposing `get_last_session`, mirroring MemoryRepository."""

    def __init__(self, last_session: str | None):
        self._last_session = last_session

    def get_last_session(self, project: str) -> str | None:
        return self._last_session


def test_resolve_session_id_explicit_session_wins():
    memory = _StubMemory(last_session="sess_stored00")
    result = _resolve_session_id("demo", memory, session="sess_explicit", new_session=True)
    assert result == "sess_explicit"


def test_resolve_session_id_new_session_ignores_stored():
    memory = _StubMemory(last_session="sess_stored00")
    result = _resolve_session_id("demo", memory, session=None, new_session=True)
    assert result != "sess_stored00"
    assert result.startswith("sess_")


def test_resolve_session_id_resumes_stored_when_present():
    memory = _StubMemory(last_session="sess_stored00")
    result = _resolve_session_id("demo", memory, session=None, new_session=False)
    assert result == "sess_stored00"


def test_resolve_session_id_mints_fresh_when_no_stored_fact():
    memory = _StubMemory(last_session=None)
    result = _resolve_session_id("demo", memory, session=None, new_session=False)
    assert result.startswith("sess_")
