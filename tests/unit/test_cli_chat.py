from __future__ import annotations

from typer.testing import CliRunner

import agentos.cli.main as cli_main


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
    async def chat(self, _message, _project, _session, status_callback=None) -> str:
        if status_callback is not None:
            status_callback("Collecting project context")
            status_callback("Reasoning with Qwen")
        return "hola"


def test_chat_command_shows_startup_status(monkeypatch):
    fake_console = FakeConsole()
    monkeypatch.setattr(cli_main, "console", fake_console)
    monkeypatch.setattr(cli_main, "_get_agent", lambda: FakeAgent())

    result = CliRunner().invoke(cli_main.app, ["chat", "hola"])

    assert result.exit_code == 0
    assert any("Loading memory engine" in message for message in fake_console.status_messages)
    assert any("Collecting project context" in message for message in fake_console.status_messages)
    assert any("Reasoning with Qwen" in message for message in fake_console.status_messages)
    assert fake_console.print_calls
