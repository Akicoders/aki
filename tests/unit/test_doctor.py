"""Tests for doctor command."""

import os
import tempfile

import pytest
from typer.testing import CliRunner

from agentos.cli.main import app


runner = CliRunner()


class TestDoctorCommand:
    def test_doctor_runs_without_error(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_shows_health_check_table(self):
        result = runner.invoke(app, ["doctor"])
        assert "Aki Health Check" in result.output
        assert "Python" in result.output
        assert "uv" in result.output

    def test_doctor_does_not_reference_project_files(self):
        """doctor MUST NOT check for CWD-relative .env or uv.lock (global-only)."""
        result = runner.invoke(app, ["doctor"])
        assert ".env" not in result.output
        assert "uv.lock" not in result.output

    def test_doctor_identical_from_unrelated_directory(self, monkeypatch):
        """Running doctor outside any Aki project MUST NOT show ❌ for missing project files,
        and MAY show a non-failing informational note."""
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
        assert ".env" not in result.output
        assert "uv.lock" not in result.output
        assert "❌" not in result.output or "API key" in result.output

    def test_doctor_uses_env_var_for_api_key(self, monkeypatch):
        monkeypatch.setenv("QWEN_API_KEY", "sk-test-key")
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        result = runner.invoke(app, ["doctor"])
        assert "API key" in result.output
        assert "QWEN_API_KEY" in result.output
