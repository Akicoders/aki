"""CLI integration tests for `aki audit <project>`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentos.cli.main import app
from agentos.cockpit.audit import report as report_module
from agentos.skills.base import SkillResult
from agentos.skills.code_intel import CodeIntelSkill

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fast_code_intel(monkeypatch):
    async def _ok(self, path: str = ".", extra_args: str = "") -> SkillResult:
        return SkillResult(success=True, data={"returncode": 0, "stdout": "", "stderr": ""})

    async def _ok_no_extra(self, path: str = ".") -> SkillResult:
        return SkillResult(success=True, data={"returncode": 0, "stdout": "", "stderr": ""})

    monkeypatch.setattr(CodeIntelSkill, "run_tests", _ok)
    monkeypatch.setattr(CodeIntelSkill, "run_lint", _ok_no_extra)
    monkeypatch.setattr(CodeIntelSkill, "get_coverage", _ok_no_extra)


def _make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "audited-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='audited-project'\n", encoding="utf-8")
    return project_root


def test_audit_command_writes_report_and_exits_zero(tmp_path, monkeypatch):
    project_root = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["audit", str(project_root)])

    assert result.exit_code == 0, result.output
    report_files = list((project_root / "docs" / "audits").glob("*-audited-project-audit.md"))
    assert len(report_files) == 1


def test_audit_command_unresolvable_project_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["audit", str(tmp_path / "does-not-exist")])
    assert result.exit_code != 0
    assert "project resolution failure" in result.output


def test_audit_command_engram_failure_exits_nonzero_but_keeps_markdown(tmp_path, monkeypatch):
    project_root = _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("engram down")

    monkeypatch.setattr(report_module, "persist_to_engram", _boom)

    result = runner.invoke(app, ["audit", str(project_root)])

    assert result.exit_code != 0
    report_files = list((project_root / "docs" / "audits").glob("*.md"))
    assert len(report_files) == 1
