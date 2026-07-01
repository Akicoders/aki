"""Contract tests over PASS_REGISTRY: schema conformance, empty/error-pass behavior."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agentos.cli.cockpit import ProjectRef
from agentos.cockpit.audit.base import AuditContext, AuditFinding, run_registered_passes
from agentos.cockpit.audit.passes import PASS_REGISTRY, TestsPass
from agentos.skills.code_intel import CodeIntelSkill
from agentos.skills.base import SkillResult


@pytest.fixture(autouse=True)
def _fast_code_intel(monkeypatch):
    """Never actually shell out to pytest/ruff/coverage inside these unit tests."""

    async def _ok_tests(self, path: str = ".", extra_args: str = "") -> SkillResult:
        return SkillResult(success=True, data={"command": "pytest", "returncode": 0, "stdout": "", "stderr": ""})

    async def _ok_lint(self, path: str = ".") -> SkillResult:
        return SkillResult(success=True, data={"command": "ruff", "returncode": 0, "stdout": "", "stderr": ""})

    async def _ok_coverage(self, path: str = ".") -> SkillResult:
        return SkillResult(success=True, data={"stdout": "", "stderr": ""})

    monkeypatch.setattr(CodeIntelSkill, "run_tests", _ok_tests)
    monkeypatch.setattr(CodeIntelSkill, "run_lint", _ok_lint)
    monkeypatch.setattr(CodeIntelSkill, "get_coverage", _ok_coverage)


def _make_ctx(tmp_path: Path) -> AuditContext:
    project = ProjectRef(key="demo", root_path=tmp_path, source="manual")
    return AuditContext(project=project, root_path=tmp_path, generated_at=datetime(2026, 1, 1))


def test_every_registered_pass_has_stable_id():
    ids = [p.id for p in PASS_REGISTRY]
    assert len(ids) == len(set(ids))
    assert len(PASS_REGISTRY) == 6


@pytest.mark.parametrize("pass_obj", PASS_REGISTRY, ids=lambda p: p.id)
def test_pass_emits_conforming_schema_or_nothing(pass_obj, tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    findings = pass_obj.run(ctx)
    assert isinstance(findings, list)
    for finding in findings:
        assert isinstance(finding, AuditFinding)
        assert finding.priority in {"P0", "P1", "P2", "P3"}
        assert finding.category
        assert finding.title
        assert finding.recommendation
        assert finding.evidence is not None
        assert isinstance(finding.autofixable_later, bool)


def test_empty_repo_produces_no_test_findings_when_tests_pass(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    findings = TestsPass().run(ctx)
    assert findings == []


def test_tests_pass_reports_p0_on_failure(tmp_path: Path, monkeypatch):
    async def _failing_tests(self, path: str = ".", extra_args: str = "") -> SkillResult:
        return SkillResult(success=False, data={"stderr": "1 failed"}, error="tests failed")

    monkeypatch.setattr(CodeIntelSkill, "run_tests", _failing_tests)
    ctx = _make_ctx(tmp_path)
    findings = TestsPass().run(ctx)
    assert any(f.priority == "P0" for f in findings)


def test_missing_sdd_pass_reports_finding(tmp_path: Path):
    from agentos.cockpit.audit.passes import SddPass

    ctx = _make_ctx(tmp_path)
    findings = SddPass().run(ctx)
    assert findings, "a project with no SDD dir at all should raise a finding"
    assert findings[0].category == "sdd"


def test_run_registered_passes_over_full_registry_never_raises(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    results = run_registered_passes(ctx, PASS_REGISTRY)
    assert len(results) == 6
    for _pass_id, findings in results:
        assert isinstance(findings, list)
