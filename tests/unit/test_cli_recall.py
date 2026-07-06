"""Tests for `aki recall --id` exact-ID lookup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from agentos.cli.main import app
from agentos.memory.models import EventType, MemoryEvent


runner = CliRunner()


def _make_event(event_id: str = "evt-123") -> MemoryEvent:
    return MemoryEvent(
        id=event_id,
        type=EventType.USER_PREFERENCE,
        project="aki",
        content="hello world",
        source="user",
    )


class TestRecallById:
    def test_recall_by_id_found(self):
        agent = MagicMock()
        agent.memory.get_event.return_value = _make_event("evt-123")

        with patch("agentos.cli.main._get_agent", return_value=agent):
            result = runner.invoke(app, ["recall", "--id", "evt-123"])

        assert result.exit_code == 0
        assert "evt-123" in result.output
        agent.memory.get_event.assert_called_once_with("evt-123")

    def test_recall_by_id_not_found(self):
        agent = MagicMock()
        agent.memory.get_event.return_value = None

        with patch("agentos.cli.main._get_agent", return_value=agent):
            result = runner.invoke(app, ["recall", "--id", "missing-id"])

        assert result.exit_code != 0
        assert "missing-id" in result.output

    def test_recall_rejects_id_and_query_together(self):
        agent = MagicMock()

        with patch("agentos.cli.main._get_agent", return_value=agent):
            result = runner.invoke(app, ["recall", "--id", "evt-123", "some query"])

        assert result.exit_code != 0
        agent.memory.get_event.assert_not_called()

    def test_recall_by_query_still_works(self):
        agent = MagicMock()
        agent.recall = AsyncMock(return_value=MagicMock(facts=[], events=[], skills=[]))

        with patch("agentos.cli.main._get_agent", return_value=agent):
            result = runner.invoke(app, ["recall", "some query"])

        assert result.exit_code == 0
        agent.recall.assert_awaited_once()
