"""CLI integration tests for --new-session flag + auto-resume wiring (task 1.4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from agentos.cli.main import app

runner = CliRunner()


def _patch_memory(last_session):
    memory = AsyncMock()
    memory.get_last_session = lambda project: last_session
    return patch("agentos.cli.main._memory", return_value=memory)


def test_chat_explicit_session_wins(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(app, ["chat", "hello", "--session", "sess_explicit"])

    assert result.exit_code == 0
    called_session = agent.chat.call_args.args[2]
    assert called_session == "sess_explicit"


def test_chat_resumes_last_session_fact(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(app, ["chat", "hello"])

    assert result.exit_code == 0
    called_session = agent.chat.call_args.args[2]
    assert called_session == "sess_stored00"


def test_chat_new_session_ignores_last_fact(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(app, ["chat", "hello", "--new-session"])

    assert result.exit_code == 0
    called_session = agent.chat.call_args.args[2]
    assert called_session != "sess_stored00"
    assert called_session.startswith("sess_")


def test_chat_no_fact_mints_random(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory(None):
        result = runner.invoke(app, ["chat", "hello"])

    assert result.exit_code == 0
    called_session = agent.chat.call_args.args[2]
    assert called_session.startswith("sess_")


def test_chat_session_and_new_session_prefers_explicit(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(
            app, ["chat", "hello", "--session", "sess_explicit", "--new-session"]
        )

    assert result.exit_code == 0
    called_session = agent.chat.call_args.args[2]
    assert called_session == "sess_explicit"


def test_interactive_resumes_last_session_fact(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()

    async def fake_recall(query, project):
        from agentos.memory.models import MemoryContext

        return MemoryContext()

    agent.recall = fake_recall

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(app, ["interactive"], input="exit\n")

    assert result.exit_code == 0
    assert "sess_stored00" in result.stdout


def test_interactive_new_session_ignores_last_fact(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()

    async def fake_recall(query, project):
        from agentos.memory.models import MemoryContext

        return MemoryContext()

    agent.recall = fake_recall

    with patch("agentos.cli.main._get_agent", return_value=agent), _patch_memory("sess_stored00"):
        result = runner.invoke(app, ["interactive", "--new-session"], input="exit\n")

    assert result.exit_code == 0
    assert "sess_stored00" not in result.stdout
