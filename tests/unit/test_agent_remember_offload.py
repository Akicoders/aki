"""Tests for AgentOS.remember offloading the blocking write to a thread."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from agentos.memory.models import EventType, MemoryEvent


@pytest.mark.asyncio
async def test_remember_offloads_to_thread_via_self_memory(monkeypatch):
    from agentos.agent.core import AgentOS

    agent = AgentOS.__new__(AgentOS)
    stored_event = MemoryEvent(
        id="evt-1",
        type=EventType.USER_PREFERENCE,
        project="aki",
        content="hello",
        source="user",
    )
    agent.memory = MagicMock()
    agent.memory.add_event.return_value = stored_event

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    result = await AgentOS.remember(agent, "hello", "aki", EventType.USER_PREFERENCE)

    assert result is stored_event
    assert calls, "asyncio.to_thread must be used to offload the write"
    assert calls[0][0] is agent.memory.add_event
    agent.memory.add_event.assert_called_once()
