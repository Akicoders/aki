from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agentos.cli.main import _async_interactive


class _StubContext:
    facts: list = []
    events: list = []
    skills: list = []


@pytest.mark.parametrize("command", ["/memory", "/facts", "/skills"])
def test_slash_command_no_nested_event_loop_error(command):
    """Slash commands must not raise RuntimeError from nested asyncio.run while
    already inside the interactive event loop (regression for double asyncio.run bug)."""
    agent = AsyncMock()
    agent.recall.return_value = _StubContext()
    agent.get_facts.return_value = []

    inputs = iter([command, "exit"])

    with patch("agentos.cli.main.Prompt.ask", side_effect=lambda *a, **k: next(inputs)), \
         patch("agentos.skills.base.get_skill_registry") as mock_registry:
        mock_registry.return_value.list.return_value = []
        asyncio.run(_async_interactive(agent, "default", "session-1"))


def test_chat_turn_exception_does_not_crash_repl():
    """A generic exception raised during agent.chat must not crash the REPL loop —
    it should print a clean error and continue accepting input (regression test)."""
    agent = AsyncMock()
    agent.chat.side_effect = RuntimeError("boom")

    inputs = iter(["hello", "exit"])

    with patch("agentos.cli.main.Prompt.ask", side_effect=lambda *a, **k: next(inputs)):
        # Must not raise — loop continues past the exception and exits cleanly on "exit".
        asyncio.run(_async_interactive(agent, "default", "session-1"))

    agent.chat.assert_awaited_once()


def test_command_dispatch_exception_does_not_crash_repl():
    """An exception raised by _handle_command dispatch must not crash the REPL loop."""
    agent = AsyncMock()

    inputs = iter(["/facts", "exit"])

    with patch("agentos.cli.main.Prompt.ask", side_effect=lambda *a, **k: next(inputs)), \
         patch("agentos.cli.main._handle_command", side_effect=RuntimeError("dispatch boom")):
        asyncio.run(_async_interactive(agent, "default", "session-1"))
