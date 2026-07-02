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
