"""Tests for the `aki update` command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from agentos.cli.main import app
from agentos.cli.update import find_install_source_dir


runner = CliRunner()


class TestUpdateCommand:
    def test_update_runs_git_pull_and_uv_sync_in_source_dir(self, tmp_path):
        source_dir = tmp_path / "aki-src"
        _write_source_checkout(source_dir)

        rev_parse = _completed(stdout=f"{source_dir}\n")
        success = _completed()

        with patch(
            "agentos.cli.main.locate_installed_source_dir",
            return_value=source_dir,
        ), patch(
            "agentos.cli.update.shutil.which",
            return_value="/usr/bin/uv",
        ), patch(
            "agentos.cli.update.subprocess.run",
            side_effect=[rev_parse, success, success, success],
        ) as mock_run:
            result = runner.invoke(app, ["update"])

        assert result.exit_code == 0
        assert "updated successfully" in result.output.lower()

        commands = [call.args[0] for call in mock_run.call_args_list]
        assert commands == [
            ["git", "rev-parse", "--show-toplevel"],
            ["git", "pull"],
            ["/usr/bin/uv", "sync", "--all-extras"],
            ["/usr/bin/uv", "tool", "install", "--editable", ".[web]", "--force"],
        ]
        assert all(call.kwargs.get("cwd") == source_dir for call in mock_run.call_args_list)

    def test_update_reports_non_source_install(self):
        with patch(
            "agentos.cli.main.locate_installed_source_dir",
            return_value=None,
        ):
            result = runner.invoke(app, ["update"])

        assert result.exit_code != 0
        normalized = " ".join(result.output.lower().split())
        assert "source checkout" in normalized
        assert "cloned repository" in normalized

    def test_update_fails_when_install_source_is_not_a_git_repo(self, tmp_path):
        source_dir = tmp_path / "aki-src"
        _write_source_checkout(source_dir)

        not_git_repo = _completed(returncode=128, stderr="fatal: not a git repository\n")

        with patch(
            "agentos.cli.main.locate_installed_source_dir",
            return_value=source_dir,
        ), patch(
            "agentos.cli.update.subprocess.run",
            return_value=not_git_repo,
        ) as mock_run:
            result = runner.invoke(app, ["update"])

        assert result.exit_code != 0
        assert "not a git checkout" in result.output.lower()
        assert mock_run.call_count == 1
        assert mock_run.call_args.args[0] == ["git", "rev-parse", "--show-toplevel"]

    def test_update_fails_when_uv_is_missing(self, tmp_path):
        source_dir = tmp_path / "aki-src"
        _write_source_checkout(source_dir)

        rev_parse = _completed(stdout=f"{source_dir}\n")

        with patch(
            "agentos.cli.main.locate_installed_source_dir",
            return_value=source_dir,
        ), patch(
            "agentos.cli.update.subprocess.run",
            return_value=rev_parse,
        ) as mock_run, patch(
            "agentos.cli.update.shutil.which",
            return_value=None,
        ), patch(
            "agentos.cli.update.Path.home",
            return_value=tmp_path,
        ):
            result = runner.invoke(app, ["update"])

        assert result.exit_code != 0
        assert "uv is required" in result.output.lower()
        assert mock_run.call_count == 1

    def test_find_install_source_dir_walks_up_to_expected_checkout_root(self, tmp_path):
        root = tmp_path / "repo"
        pkg_dir = root / "src" / "agentos"
        pkg_dir.mkdir(parents=True)
        _write_source_checkout(root)
        fake_init = pkg_dir / "__init__.py"
        fake_init.write_text("")

        found = find_install_source_dir(fake_init)
        assert found == root

    def test_find_install_source_dir_ignores_partial_install_markers(self, tmp_path):
        root = tmp_path / "repo"
        pkg_dir = root / "src" / "agentos"
        pkg_dir.mkdir(parents=True)
        (root / "install.sh").write_text("#!/bin/sh\n")
        fake_init = pkg_dir / "__init__.py"
        fake_init.write_text("")

        found = find_install_source_dir(fake_init)
        assert found is None

    def test_find_install_source_dir_returns_none_when_no_anchor(self, tmp_path):
        pkg_dir = tmp_path / "site-packages" / "agentos"
        pkg_dir.mkdir(parents=True)
        fake_init = pkg_dir / "__init__.py"
        fake_init.write_text("")

        found = find_install_source_dir(fake_init)
        assert found is None


def _completed(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return type(
        "Completed",
        (),
        {"returncode": returncode, "stdout": stdout, "stderr": stderr},
    )()


def _write_source_checkout(root: Path) -> None:
    (root / "src" / "agentos" / "cli").mkdir(parents=True, exist_ok=True)
    (root / "install.sh").write_text("#!/bin/sh\n")
    (root / "README.md").write_text("# Aki\n")
    (root / ".env.example").write_text("QWEN_API_KEY=\n")
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "aki-memory"\n',
        encoding="utf-8",
    )
    (root / "src" / "agentos" / "cli" / "main.py").write_text("# cli\n", encoding="utf-8")
    os.chmod(root / "install.sh", 0o755)
