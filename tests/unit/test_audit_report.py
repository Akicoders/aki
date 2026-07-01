"""Tests for markdown report generation and dual-sink persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agentos.cockpit.audit.base import AuditFinding
from agentos.cockpit.audit.report import (
    persist_audit,
    persist_to_engram,
    render_markdown,
    write_markdown_report,
)
from agentos.memory.database import Database
from agentos.memory.models import MemoryFactModel
from sqlalchemy import select


FINDINGS = [
    AuditFinding(priority="P0", category="tests", title="Suite failing", evidence="1 failed", recommendation="fix it", autofixable_later=False),
    AuditFinding(priority="P2", category="git", title="Dirty tree", evidence="modified 3", recommendation="commit", autofixable_later=False),
]


def test_render_markdown_contains_all_six_sections_in_order():
    content = render_markdown("demo", Path("/tmp/demo"), datetime(2026, 1, 1), FINDINGS)

    section_titles = [
        "## Executive Summary",
        "## Snapshot Metadata",
        "## Priority Tables",
        "## Findings by Area",
        "## Recommended Next Actions",
        "## Appendix",
    ]
    positions = [content.index(title) for title in section_titles]
    assert positions == sorted(positions)


def test_render_markdown_priority_tables_include_findings():
    content = render_markdown("demo", Path("/tmp/demo"), datetime(2026, 1, 1), FINDINGS)
    assert "Suite failing" in content
    assert "Dirty tree" in content
    assert "P0" in content


def test_write_markdown_report_creates_expected_path(tmp_path: Path):
    report_path = write_markdown_report(tmp_path, "demo", datetime(2026, 3, 4), FINDINGS)
    assert report_path == tmp_path / "docs" / "audits" / "2026-03-04-demo-audit.md"
    assert report_path.exists()
    assert "Suite failing" in report_path.read_text(encoding="utf-8")


def test_persist_to_engram_writes_immutable_and_latest_records(tmp_path: Path):
    db = Database(tmp_path / "memory.sqlite3")
    report_path = tmp_path / "docs" / "audits" / "2026-03-04-demo-audit.md"
    persist_to_engram("demo", report_path, datetime(2026, 3, 4, 10, 30), FINDINGS, database=db)

    with db.session() as session:
        rows = session.execute(
            select(MemoryFactModel).where(MemoryFactModel.scope == "audit")
        ).scalars().all()
    keys = {row.key for row in rows}
    assert "audit/demo/latest" in keys
    assert any(k.startswith("audit/demo/2026") and k != "audit/demo/latest" for k in keys)


def test_persist_audit_success_both_sinks(tmp_path: Path):
    db = Database(tmp_path / "memory.sqlite3")
    outcome = persist_audit(tmp_path, "demo", datetime(2026, 1, 1), FINDINGS, database=db)
    assert outcome.success is True
    assert outcome.exit_code == 0
    assert outcome.report_path is not None
    assert outcome.report_path.exists()


def test_persist_audit_engram_failure_is_nonzero_but_keeps_markdown(tmp_path: Path):
    def _boom(*args, **kwargs):
        raise RuntimeError("engram down")

    outcome = persist_audit(
        tmp_path, "demo", datetime(2026, 1, 1), FINDINGS, persist_engram=_boom
    )
    assert outcome.success is False
    assert outcome.exit_code != 0
    assert outcome.failed_stage == "Engram persistence failed"
    assert outcome.report_path is not None
    assert outcome.report_path.exists()


def test_persist_audit_local_write_failure_is_nonzero():
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    outcome = persist_audit(
        Path("/tmp/does-not-matter"), "demo", datetime(2026, 1, 1), FINDINGS, write_markdown=_boom
    )
    assert outcome.success is False
    assert outcome.exit_code != 0
    assert outcome.failed_stage == "local markdown persistence failed"
    assert outcome.report_path is None
