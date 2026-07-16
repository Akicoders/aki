"""CLI integration tests for `aki salvage`."""

from __future__ import annotations

from pathlib import Path
import pytest
from typer.testing import CliRunner

from agentos.cli.main import app

runner = CliRunner()


def _make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "salvage-project"
    project_root.mkdir()
    return project_root


def test_salvage_dry_run_generates_diagnose_file(tmp_path, monkeypatch):
    project_root = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Let's create an .env.example
    (project_root / ".env.example").write_text("SOME_KEY=example", encoding="utf-8")

    result = runner.invoke(app, ["salvage", "--dir", str(project_root), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Aki Salvage Diagnostics Summary" in result.output
    assert "Written detailed diagnosis report to" in result.output
    
    # Check that aki_diagnose.md exists
    diagnose_file = project_root / "aki_diagnose.md"
    assert diagnose_file.is_file()
    diagnose_content = diagnose_file.read_text(encoding="utf-8")
    assert "Aki Salvage Diagnosis" in diagnose_content
    assert "proposal.md" in diagnose_content

    # In dry-run, .env should NOT be created
    assert not (project_root / ".env").is_file()


def test_salvage_with_fixes_applies_them_when_confirmed(tmp_path, monkeypatch):
    project_root = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Create .env.example and mock Git repo by creating a .git folder
    (project_root / ".env.example").write_text("SOME_KEY=example", encoding="utf-8")
    (project_root / ".git").mkdir()

    # Run command and input 'y' for confirmation
    result = runner.invoke(
        app, 
        ["salvage", "--dir", str(project_root)], 
        input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "Applied fixes:" in result.output
    assert "Restored missing .env file" in result.output
    assert "Created default config.yaml file." in result.output
    assert "Created default .gitignore file." in result.output

    # Check files are created
    assert (project_root / ".env").is_file()
    assert (project_root / "config.yaml").is_file()
    assert (project_root / ".gitignore").is_file()
    assert (project_root / "aki_diagnose.md").is_file()


def test_salvage_with_fixes_cancelled_by_user(tmp_path, monkeypatch):
    project_root = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    (project_root / ".env.example").write_text("SOME_KEY=example", encoding="utf-8")

    # Run command and input 'n' to cancel fixes
    result = runner.invoke(
        app, 
        ["salvage", "--dir", str(project_root)], 
        input="n\n"
    )

    assert result.exit_code == 0, result.output
    assert "Salvage fixes cancelled by user." in result.output

    # Check files are NOT created
    assert not (project_root / ".env").is_file()
    assert not (project_root / "config.yaml").is_file()
    assert (project_root / "aki_diagnose.md").is_file()
