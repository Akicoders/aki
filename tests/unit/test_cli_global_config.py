"""Tests for global-config CLI surface: _resolve_global_api_key, doctor notes,
and `aki config init`."""

import tempfile
import os

import pytest
from typer.testing import CliRunner

from agentos.cli.main import _resolve_global_api_key, app

runner = CliRunner()


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    return home, project


class TestResolveGlobalApiKey:
    def test_shell_env_wins_and_is_labeled(self, isolated_home, monkeypatch):
        monkeypatch.setenv("QWEN_API_KEY", "sk-shell")
        key, detail = _resolve_global_api_key()
        assert key == "sk-shell"
        assert "shell env" in detail.lower()

    def test_falls_back_to_global_env_file(self, isolated_home):
        home, _ = isolated_home
        (home / ".aki").mkdir(exist_ok=True)
        (home / ".aki" / ".env").write_text("QWEN_API_KEY=sk-global\n", encoding="utf-8")

        key, detail = _resolve_global_api_key()

        assert key == "sk-global"
        assert ".aki" in detail

    def test_falls_back_to_project_env_file_when_no_global(self, isolated_home):
        _, project = isolated_home
        (project / ".env").write_text("QWEN_API_KEY=sk-project\n", encoding="utf-8")

        key, detail = _resolve_global_api_key()

        assert key == "sk-project"

    def test_no_key_anywhere_reports_not_set(self, isolated_home):
        key, detail = _resolve_global_api_key()
        assert key == ""
        assert "not set" in detail.lower()

    def test_never_leaks_value_when_absent(self, isolated_home):
        _, detail = _resolve_global_api_key()
        assert "sk-" not in detail

    def test_stale_provenance_does_not_drop_a_real_env_var(self, isolated_home, monkeypatch):
        """Regression test for the order-dependent staleness bug (verify-report
        CRITICAL): if resolve_config() ran earlier (e.g. in a previous test in
        the same process, or an earlier call in a long-lived process) and left
        a stale `_env_provenance` snapshot that predates a later, externally
        set env var, `_resolve_global_api_key()` must NOT mislabel that var as
        dotenv-sourced and drop it. The snapshot doesn't know about the var
        either way (it isn't in `real`, `project`, or `global`), so the safe
        default is to trust it as a real env var rather than silently
        reporting the key as absent."""
        from agentos.core.config import resolve_config

        # Simulate a stale snapshot from an earlier resolve_config() call that
        # ran before QWEN_API_KEY existed anywhere in this process.
        resolve_config()

        # Now a real env var shows up "out of band" (e.g. set by a caller
        # after that earlier resolve_config() call, without a fresh one).
        monkeypatch.setenv("QWEN_API_KEY", "sk-shell-after-stale-snapshot")

        key, detail = _resolve_global_api_key()

        assert key == "sk-shell-after-stale-snapshot"
        assert "shell env" in detail.lower()


class TestDoctorApiKeySourceLabel:
    def test_doctor_reports_global_env_file_not_shell_env(self, isolated_home):
        """Regression test: a key that lives ONLY in ~/.aki/.env must never be
        mislabeled as 'shell env' in `aki doctor` output. This must go through
        the full Typer app (callback -> get_config -> resolve_config), because
        that's what mutates os.environ as a load_dotenv(override=False) side
        effect and previously fooled _resolve_global_api_key when called
        after the callback already ran."""
        home, _ = isolated_home
        (home / ".aki").mkdir(exist_ok=True)
        (home / ".aki" / ".env").write_text("QWEN_API_KEY=sk-global-only\n", encoding="utf-8")

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "shell env" not in result.output.lower()
        assert "found in" in result.output.lower()


class TestDoctorProjectLocalNote:
    def test_doctor_runs_outside_any_repo(self, monkeypatch):
        monkeypatch.delenv("QWEN_API_KEY", raising=False)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)
                result = runner.invoke(app, ["doctor"])
            finally:
                os.chdir(cwd)
        assert result.exit_code == 0
        assert "Aki Health Check" in result.output

    def test_doctor_reports_project_local_config_as_separate_note(self, isolated_home):
        _, project = isolated_home
        (project / "config.yaml").write_text("qwen:\n  model: repo-model\n", encoding="utf-8")

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Project-local config detected" in result.output


class TestConfigInitCommand:
    def test_first_time_init_creates_global_home(self, isolated_home):
        home, _ = isolated_home
        result = runner.invoke(app, ["config", "init", "--qwen-api-key", "sk-xyz"])

        assert result.exit_code == 0
        env_file = home / ".aki" / ".env"
        assert env_file.exists()
        assert "QWEN_API_KEY=sk-xyz" in env_file.read_text(encoding="utf-8")

    def test_existing_file_backed_up_before_overwrite(self, isolated_home):
        home, _ = isolated_home
        (home / ".aki").mkdir(parents=True)
        env_file = home / ".aki" / ".env"
        env_file.write_text("QWEN_API_KEY=sk-old\n", encoding="utf-8")

        result = runner.invoke(app, ["config", "init", "--qwen-api-key", "sk-new"])

        assert result.exit_code == 0
        assert "QWEN_API_KEY=sk-new" in env_file.read_text(encoding="utf-8")
        backups = list((home / ".aki").glob(".env.backup.*"))
        assert len(backups) == 1
        assert "QWEN_API_KEY=sk-old" in backups[0].read_text(encoding="utf-8")

    def test_dry_run_makes_no_filesystem_changes(self, isolated_home):
        home, _ = isolated_home
        result = runner.invoke(app, ["config", "init", "--qwen-api-key", "sk-xyz", "--dry-run"])

        assert result.exit_code == 0
        assert not (home / ".aki").exists()

    def test_non_interactive_missing_key_fails_clearly(self, isolated_home, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = runner.invoke(app, ["config", "init"])

        assert result.exit_code != 0
