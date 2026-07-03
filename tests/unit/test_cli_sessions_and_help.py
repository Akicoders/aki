"""Unit tests for `/sessions` command and contextual `_show_help` (session-list-and-help)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from agentos.cli.main import _handle_command, _show_help, _show_sessions
from agentos.memory.repository import SessionSummary


class _StubMemory:
    def __init__(self, sessions=None, checkpoint=None, raise_on_read=False):
        self._sessions = sessions or []
        self._checkpoint = checkpoint
        self._raise_on_read = raise_on_read

    def list_sessions(self, project, limit=20):
        return self._sessions

    def read_checkpoint(self, project, session_id):
        if self._raise_on_read:
            raise RuntimeError("corrupt checkpoint")
        return self._checkpoint


class _StubAgent:
    def __init__(self, memory):
        self.memory = memory


class TestShowSessions:
    @pytest.mark.asyncio
    async def test_show_sessions_empty_state_prints_dim_message(self, capsys):
        agent = _StubAgent(_StubMemory(sessions=[]))
        await _show_sessions(agent, "demo")
        out = capsys.readouterr().out
        assert "No sessions" in out

    @pytest.mark.asyncio
    async def test_show_sessions_renders_table_newest_first(self, capsys):
        sessions = [
            SessionSummary("sess_2", "second goal", datetime(2024, 1, 2), False),
            SessionSummary("sess_1", "first goal", datetime(2024, 1, 1), False),
        ]
        agent = _StubAgent(_StubMemory(sessions=sessions))
        await _show_sessions(agent, "demo")
        out = capsys.readouterr().out
        assert out.index("sess_2") < out.index("sess_1")

    @pytest.mark.asyncio
    async def test_show_sessions_blank_goal_falls_back_to_session_id(self, capsys):
        sessions = [SessionSummary("sess_blank", "", datetime(2024, 1, 1), False)]
        agent = _StubAgent(_StubMemory(sessions=sessions))
        await _show_sessions(agent, "demo")
        out = capsys.readouterr().out
        assert "(no goal) sess_blank" in out


class TestHandleCommandDispatch:
    @pytest.mark.asyncio
    async def test_handle_command_sessions_dispatches_to_show_sessions(self, monkeypatch):
        mock_show_sessions = AsyncMock()
        monkeypatch.setattr("agentos.cli.main._show_sessions", mock_show_sessions)
        agent = _StubAgent(_StubMemory())

        await _handle_command("/sessions", agent, "demo", "sess_123")

        mock_show_sessions.assert_awaited_once_with(agent, "demo")

    @pytest.mark.asyncio
    async def test_handle_command_facts_still_dispatches(self, monkeypatch):
        mock_show_facts = AsyncMock()
        monkeypatch.setattr("agentos.cli.main._show_facts", mock_show_facts)
        agent = _StubAgent(_StubMemory())

        await _handle_command("/facts", agent, "demo", "sess_123")

        mock_show_facts.assert_awaited_once_with(agent, "demo")


class TestShowHelp:
    def test_show_help_resumed_session_shows_last_goal(self, capsys):
        agent = _StubAgent(_StubMemory(checkpoint={"goal": "refactor auth"}))
        _show_help(agent, "demo", "sess_123")
        out = capsys.readouterr().out
        assert "Resuming" in out
        assert "sess_123" in out
        assert "refactor auth" in out

    def test_show_help_new_session_no_checkpoint(self, capsys):
        agent = _StubAgent(_StubMemory(checkpoint=None))
        _show_help(agent, "demo", "sess_new")
        out = capsys.readouterr().out
        assert "New" in out
        assert "no history yet" in out

    def test_show_help_read_checkpoint_raising_falls_back_to_new(self, capsys):
        agent = _StubAgent(_StubMemory(raise_on_read=True))
        _show_help(agent, "demo", "sess_corrupt")
        out = capsys.readouterr().out
        assert "New" in out

    def test_show_help_lists_all_commands_including_sessions(self, capsys):
        agent = _StubAgent(_StubMemory(checkpoint=None))
        _show_help(agent, "demo", "sess_x")
        out = capsys.readouterr().out
        for cmd in ("/help", "/memory", "/facts", "/skills", "/sdd", "/clear", "exit/quit", "/sessions"):
            assert cmd in out
