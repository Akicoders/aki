"""Markdown report generation and dual-sink persistence for `aki audit <project>`.

Dual-sink contract (design doc section 12 / spec "Dual-Sink Persistence"):
- Sink 1: local markdown file at docs/audits/YYYY-MM-DD-<project>-audit.md
- Sink 2: Engram-equivalent durable record, modeled here as MemoryFactModel rows in
  the same Aki memory SQLite database used elsewhere in the cockpit (scope="audit"),
  keyed as audit/<project>/<timestamp> (immutable) and audit/<project>/latest (pointer).
If either sink fails, the command must report the failed stage and exit non-zero,
preserving whatever partial artifact was produced.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from sqlalchemy import select

from agentos.cockpit.audit.base import AuditFinding
from agentos.memory.database import Database, get_database
from agentos.memory.models import MemoryFactModel

_PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
_PRIORITY_LABELS = {
    "P0": "P0 (Blockers)",
    "P1": "P1 (High priority)",
    "P2": "P2 (Medium priority)",
    "P3": "P3 (Low priority)",
}


def _priority_counts(findings: list[AuditFinding]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in findings:
        counts[finding.priority] += 1
    return counts


def render_markdown(
    project_key: str,
    root_path: Path,
    generated_at: datetime,
    findings: list[AuditFinding],
) -> str:
    """Render the audit report markdown with all six required sections, in order."""
    counts = _priority_counts(findings)
    lines: list[str] = []

    lines.append(f"# Audit Report: {project_key}")
    lines.append("")

    # 1. Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    if not findings:
        lines.append("No issues were found by any audit pass. The project looks healthy.")
    else:
        blockers = counts.get("P0", 0)
        lines.append(
            f"{len(findings)} finding(s) across all audit passes "
            f"({blockers} blocker(s), {counts.get('P1', 0)} high, "
            f"{counts.get('P2', 0)} medium, {counts.get('P3', 0)} low priority)."
        )
    lines.append("")

    # 2. Snapshot metadata
    lines.append("## Snapshot Metadata")
    lines.append("")
    lines.append(f"- Project: `{project_key}`")
    lines.append(f"- Root path: `{root_path}`")
    lines.append(f"- Generated at: `{generated_at.isoformat()}`")
    lines.append("")

    # 3. Priority tables P0-P3
    lines.append("## Priority Tables")
    lines.append("")
    for priority in _PRIORITY_ORDER:
        bucket = [f for f in findings if f.priority == priority]
        lines.append(f"### {_PRIORITY_LABELS[priority]}")
        lines.append("")
        if not bucket:
            lines.append("_No findings at this priority._")
            lines.append("")
            continue
        lines.append("| Area | Finding | Evidence | Recommendation | Autofix Later |")
        lines.append("|---|---|---|---|---|")
        for finding in bucket:
            lines.append(
                f"| {finding.category} | {finding.title} | {finding.evidence} | "
                f"{finding.recommendation} | {'yes' if finding.autofixable_later else 'no'} |"
            )
        lines.append("")

    # 4. Detailed findings by area
    lines.append("## Findings by Area")
    lines.append("")
    by_category: dict[str, list[AuditFinding]] = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)
    if not by_category:
        lines.append("_No findings to report by area._")
        lines.append("")
    else:
        for category in sorted(by_category):
            lines.append(f"### {category}")
            lines.append("")
            for finding in by_category[category]:
                lines.append(f"- **[{finding.priority}] {finding.title}** — {finding.evidence}")
            lines.append("")

    # 5. Recommended next actions
    lines.append("## Recommended Next Actions")
    lines.append("")
    if not findings:
        lines.append("No action required.")
    else:
        ordered = sorted(findings, key=lambda f: (_PRIORITY_ORDER.index(f.priority), f.category))
        for finding in ordered[:10]:
            lines.append(f"1. [{finding.priority}] {finding.recommendation}")
    lines.append("")

    # 6. Appendix: evidence and command references
    lines.append("## Appendix")
    lines.append("")
    lines.append("Full evidence and command references, one row per finding:")
    lines.append("")
    lines.append("| Priority | Category | Title | Evidence | Command Reference |")
    lines.append("|---|---|---|---|---|")
    for finding in findings:
        lines.append(
            f"| {finding.priority} | {finding.category} | {finding.title} | "
            f"{finding.evidence} | `aki cockpit {finding.category}` |"
        )
    lines.append("")

    return "\n".join(lines)


def write_markdown_report(
    root_path: Path,
    project_key: str,
    generated_at: datetime,
    findings: list[AuditFinding],
) -> Path:
    """Write the rendered markdown report to docs/audits/YYYY-MM-DD-<project>-audit.md."""
    content = render_markdown(project_key, root_path, generated_at, findings)
    report_path = root_path / "docs" / "audits" / f"{generated_at:%Y-%m-%d}-{project_key}-audit.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    return report_path


def persist_to_engram(
    project_key: str,
    report_path: Path,
    generated_at: datetime,
    findings: list[AuditFinding],
    database: Optional[Database] = None,
) -> None:
    """Persist the audit as an immutable timestamped record plus a 'latest' pointer.

    Modeled as MemoryFactModel rows (scope="audit") in the same Aki memory SQLite
    database used elsewhere in the cockpit, since this codebase has no standalone
    Engram client library. Keys mirror the design's Engram storage model:
    audit/<project>/<timestamp> (immutable) and audit/<project>/latest (pointer).
    """
    db = database or get_database()
    counts = _priority_counts(findings)
    payload = {
        "project_key": project_key,
        "root_path": str(report_path.parent.parent.parent) if report_path else None,
        "report_path": str(report_path),
        "generated_at": generated_at.isoformat(),
        "priority_counts": counts,
        "findings": [
            {
                "priority": f.priority,
                "category": f.category,
                "title": f.title,
                "evidence": f.evidence,
                "recommendation": f.recommendation,
                "autofixable_later": f.autofixable_later,
            }
            for f in findings
        ],
    }
    value = json.dumps(payload)
    immutable_topic = f"audit/{project_key}/{generated_at:%Y%m%dT%H%M%S}"
    latest_topic = f"audit/{project_key}/latest"

    with db.session() as session:
        for topic in (immutable_topic, latest_topic):
            existing = session.execute(
                select(MemoryFactModel).where(
                    MemoryFactModel.scope == "audit", MemoryFactModel.key == topic
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    MemoryFactModel(
                        id=f"audit_{uuid4().hex[:12]}",
                        key=topic,
                        value=value,
                        scope="audit",
                    )
                )
            else:
                existing.value = value


@dataclass
class AuditPersistOutcome:
    success: bool
    report_path: Optional[Path]
    failed_stage: Optional[str]
    exit_code: int


def persist_audit(
    root_path: Path,
    project_key: str,
    generated_at: datetime,
    findings: list[AuditFinding],
    database: Optional[Database] = None,
    write_markdown: Optional[Callable[[Path, str, datetime, list[AuditFinding]], Path]] = None,
    persist_engram: Optional[Callable[..., None]] = None,
) -> AuditPersistOutcome:
    """Orchestrate dual-sink persistence with the non-zero-exit-on-partial-failure contract.

    `write_markdown`/`persist_engram` default to the module-level functions, resolved at
    call time (not import time) so tests can monkeypatch this module's attributes.
    """
    write_markdown = write_markdown or write_markdown_report
    persist_engram = persist_engram if persist_engram is not None else persist_to_engram

    try:
        report_path = write_markdown(root_path, project_key, generated_at, findings)
    except Exception:
        return AuditPersistOutcome(
            success=False,
            report_path=None,
            failed_stage="local markdown persistence failed",
            exit_code=1,
        )

    try:
        persist_engram(project_key, report_path, generated_at, findings, database=database)
    except Exception:
        return AuditPersistOutcome(
            success=False,
            report_path=report_path,
            failed_stage="Engram persistence failed",
            exit_code=1,
        )

    return AuditPersistOutcome(success=True, report_path=report_path, failed_stage=None, exit_code=0)
