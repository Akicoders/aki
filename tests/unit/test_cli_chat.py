from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

import agentos.cli.main as cli_main
from agentos.agents import AgentProfile, MemoryPolicy, ProfileNotFoundError, ToolPolicy


pytestmark = pytest.mark.unit


class FakeStatus:
    def __init__(self, messages: list[str], initial_message: str):
        self.messages = messages
        self.initial_message = initial_message

    def __enter__(self) -> "FakeStatus":
        self.messages.append(self.initial_message)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def update(self, message: str) -> None:
        self.messages.append(message)


class FakeConsole:
    def __init__(self):
        self.status_messages: list[str] = []
        self.print_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def status(self, message: str) -> FakeStatus:
        return FakeStatus(self.status_messages, message)

    def print(self, *objects, **kwargs) -> None:
        self.print_calls.append((objects, kwargs))

    def clear(self) -> None:
        return None


class FakeAgent:
    def __init__(self):
        self.chat_status_callbacks: list[object] = []
        self.chat_calls: list[dict[str, object]] = []
        self.agent_registry = FakeAgentRegistry()

    async def chat(
        self,
        _message,
        _project,
        _session,
        status_callback=None,
        profile_id=None,
    ) -> str:
        self.chat_calls.append({"profile_id": profile_id})
        self.chat_status_callbacks.append(status_callback)
        if status_callback is not None:
            status_callback("Collecting project context")
            status_callback("Reasoning iteration 1/3")
        return "hola"

    async def stream_chat(
        self,
        _message,
        _project,
        _session,
        status_callback=None,
        profile_id=None,
    ):
        self.chat_calls.append({"profile_id": profile_id, "stream": True})
        if status_callback is not None:
            status_callback("Collecting project context")
        yield "hola "


def _profile(profile_id: str = "reviewer") -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name="Reviewer",
        description="Reviews changes before they ship",
        role="reviewer",
        prompt_template="Review carefully.",
        tools=ToolPolicy(allowed=["memory.recall"]),
        memory=MemoryPolicy(scope="session"),
    )


class FakeAgentRegistry:
    def __init__(self):
        self.profiles = {"reviewer": _profile("reviewer")}

    def resolve(self, profile_id: str) -> AgentProfile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ProfileNotFoundError(f"agent profile not found: {profile_id}") from exc

    def list_profiles(self) -> list[AgentProfile]:
        return list(self.profiles.values())


def test_chat_command_shows_startup_status(monkeypatch):
    fake_console = FakeConsole()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: FakeAgent())

    result = CliRunner().invoke(cli_main.app, ["chat", "hola"])

    assert result.exit_code == 0
    assert any("Loading memory engine" in message for message in fake_console.status_messages)
    assert any("Collecting project context" in message for message in fake_console.status_messages)
    assert any("Reasoning iteration 1/3" in message for message in fake_console.status_messages)
    assert fake_console.print_calls


def test_chat_command_passes_selected_profile_and_prints_header(monkeypatch):
    fake_console = FakeConsole()
    fake_agent = FakeAgent()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: fake_agent)

    result = CliRunner().invoke(cli_main.app, ["chat", "hola", "--profile", "reviewer"])

    assert result.exit_code == 0
    assert fake_agent.chat_calls == [{"profile_id": "reviewer"}]
    printed_text = "\n".join(
        str(getattr(obj, "renderable", obj))
        for objects, _ in fake_console.print_calls
        for obj in objects
    )
    assert "Reviewer" in printed_text


def test_chat_command_rejects_unknown_profile_before_agent_execution(monkeypatch):
    fake_console = FakeConsole()
    fake_agent = FakeAgent()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: fake_agent)

    result = CliRunner().invoke(cli_main.app, ["chat", "hola", "--profile", "missing"])

    assert result.exit_code == 1
    assert fake_agent.chat_calls == []
    printed_text = "\n".join(str(obj) for objects, _ in fake_console.print_calls for obj in objects)
    assert "agent profile not found: missing" in printed_text


def test_agents_command_lists_configured_profiles(monkeypatch):
    fake_console = FakeConsole()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: FakeAgent())

    result = CliRunner().invoke(cli_main.app, ["agents"])

    assert result.exit_code == 0
    printed_tables = [obj for objects, _ in fake_console.print_calls for obj in objects]
    assert any(getattr(table, "title", "") == "Agent Profiles" for table in printed_tables)


def test_interactive_uses_status_callback_for_each_prompt(monkeypatch):
    fake_console = FakeConsole()
    fake_agent = FakeAgent()
    inputs = iter(["hola", "exit"])

    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main.Prompt, "ask", lambda *_args, **_kwargs: next(inputs))

    asyncio.run(cli_main._async_interactive(fake_agent, "default", "session-1"))

    assert fake_agent.chat_status_callbacks
    assert all(callback is not None for callback in fake_agent.chat_status_callbacks)
    assert any("Collecting project context" in message for message in fake_console.status_messages)
    assert any("Reasoning iteration 1/3" in message for message in fake_console.status_messages)
    assert fake_console.print_calls


def test_interactive_passes_selected_profile_for_each_prompt(monkeypatch):
    fake_console = FakeConsole()
    fake_agent = FakeAgent()
    inputs = iter(["hola", "exit"])

    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main.Prompt, "ask", lambda *_args, **_kwargs: next(inputs))

    asyncio.run(
        cli_main._async_interactive(fake_agent, "default", "session-1", profile_id="reviewer")
    )

    assert fake_agent.chat_calls == [{"profile_id": "reviewer"}]


def test_interactive_command_accepts_selected_profile_and_prints_header(monkeypatch):
    fake_console = FakeConsole()
    inputs = iter(["exit"])

    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(
        cli_main,
        "detect_sdd_artifacts",
        lambda: type("Status", (), {"has_sdd": True, "summary": lambda self: "ok"})(),
    )
    monkeypatch.setattr(cli_main.Prompt, "ask", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(cli_main, "_get_agent", lambda: FakeAgent())
    monkeypatch.setattr(cli_main, "_memory", lambda: object())
    monkeypatch.setattr(
        cli_main, "_resolve_session_id", lambda project, memory, session, new_session: "session-1"
    )

    result = CliRunner().invoke(cli_main.app, ["interactive", "--profile", "reviewer"])

    assert result.exit_code == 0
    printed_text = "\n".join(
        str(getattr(obj, "renderable", obj))
        for objects, _ in fake_console.print_calls
        for obj in objects
    )
    assert "Reviewer" in printed_text


def test_interactive_command_rejects_unknown_profile_before_prompt_loop(monkeypatch):
    fake_console = FakeConsole()
    fake_agent = FakeAgent()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: fake_agent)

    result = CliRunner().invoke(cli_main.app, ["interactive", "--profile", "missing"])

    assert result.exit_code == 1
    assert fake_agent.chat_calls == []
    printed_text = "\n".join(str(obj) for objects, _ in fake_console.print_calls for obj in objects)
    assert "agent profile not found: missing" in printed_text
