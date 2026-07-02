from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from agentos.cli.main import app

runner = CliRunner()


def test_chat_resolves_project_via_git_root(tmp_path, monkeypatch):
    """Without --project, chat must resolve the project from git root, not hardcode 'default'."""
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent):
        result = runner.invoke(app, ["chat", "hello"])

    assert result.exit_code == 0
    called_project = agent.chat.call_args.args[1]
    assert called_project == "my-repo"


def test_chat_explicit_project_overrides_detection(tmp_path, monkeypatch):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)

    agent = AsyncMock()
    agent.chat.return_value = "hi"

    with patch("agentos.cli.main._get_agent", return_value=agent):
        result = runner.invoke(app, ["chat", "hello", "--project", "explicit-proj"])

    assert result.exit_code == 0
    called_project = agent.chat.call_args.args[1]
    assert called_project == "explicit-proj"
