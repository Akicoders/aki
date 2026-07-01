"""Contract tests for the audit pass framework (AuditFinding schema, merge_findings, isolation)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agentos.cockpit.audit.base import (
    AuditContext,
    AuditFinding,
    merge_findings,
    run_registered_passes,
)
from agentos.cli.cockpit import ProjectRef


def _ctx(tmp_path: Path) -> AuditContext:
    project = ProjectRef(key="demo", root_path=tmp_path, source="manual")
    return AuditContext(project=project, root_path=tmp_path, generated_at=datetime(2026, 1, 1))


def test_audit_finding_has_six_fields():
    finding = AuditFinding(
        priority="P1",
        category="tests",
        title="Something",
        evidence="evidence",
        recommendation="fix it",
        autofixable_later=False,
    )
    assert finding.priority == "P1"
    assert finding.category == "tests"
    assert finding.title == "Something"
    assert finding.evidence == "evidence"
    assert finding.recommendation == "fix it"
    assert finding.autofixable_later is False


def test_merge_findings_is_deterministic_regardless_of_pass_order():
    f1 = AuditFinding(priority="P2", category="git", title="B", evidence="", recommendation="", autofixable_later=False)
    f2 = AuditFinding(priority="P0", category="tests", title="A", evidence="", recommendation="", autofixable_later=False)
    f3 = AuditFinding(priority="P1", category="sdd", title="C", evidence="", recommendation="", autofixable_later=False)

    merged_a = merge_findings([("git", [f1]), ("tests", [f2]), ("sdd", [f3])])
    merged_b = merge_findings([("sdd", [f3]), ("tests", [f2]), ("git", [f1])])

    assert [f.title for f in merged_a] == ["A", "C", "B"]
    assert merged_a == merged_b


def test_merge_findings_empty_pass_contributes_nothing():
    merged = merge_findings([("tests", []), ("git", [])])
    assert merged == []


class _RaisingPass:
    id = "broken"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        raise RuntimeError("boom")


class _OkPass:
    id = "ok"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        return [AuditFinding(priority="P3", category="ok", title="fine", evidence="", recommendation="", autofixable_later=False)]


def test_run_registered_passes_isolates_failure(tmp_path: Path):
    ctx = _ctx(tmp_path)
    results = run_registered_passes(ctx, [_RaisingPass(), _OkPass()])

    by_id = dict(results)
    assert "broken" in by_id
    assert "ok" in by_id
    assert by_id["ok"][0].title == "fine"
    assert len(by_id["broken"]) == 1
    assert by_id["broken"][0].priority == "P2"
    assert "broken" in by_id["broken"][0].category
