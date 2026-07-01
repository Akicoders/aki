"""Audit pass plugin interface and deterministic finding merge for `aki audit`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Protocol

Priority = Literal["P0", "P1", "P2", "P3"]

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True)
class AuditFinding:
    """Uniform structured finding emitted by every audit pass."""

    priority: Priority
    category: str
    title: str
    evidence: str
    recommendation: str
    autofixable_later: bool = False


@dataclass
class AuditContext:
    """Read-only context passed into every audit pass."""

    project: object
    root_path: Path
    generated_at: datetime


@dataclass
class AuditReportRef:
    project_key: str
    report_path: Path
    engram_topic: str
    generated_at: datetime
    priority_counts: dict[str, int]


class AuditPass(Protocol):
    """Contract every audit pass must satisfy."""

    id: str

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        ...


def merge_findings(pass_results: list[tuple[str, list[AuditFinding]]]) -> list[AuditFinding]:
    """Deterministically merge findings from all passes into priority-ranked order.

    Ordering is independent of the order passes were executed/registered in:
    sorted by (priority rank, category, title).
    """
    all_findings: list[AuditFinding] = []
    for _pass_id, findings in pass_results:
        all_findings.extend(findings)

    return sorted(
        all_findings,
        key=lambda f: (_PRIORITY_ORDER.get(f.priority, 99), f.category, f.title),
    )


def run_registered_passes(
    ctx: AuditContext, passes: list[AuditPass]
) -> list[tuple[str, list[AuditFinding]]]:
    """Run every pass, isolating failures as a single P2 finding instead of crashing."""
    results: list[tuple[str, list[AuditFinding]]] = []
    for pass_obj in passes:
        try:
            findings = list(pass_obj.run(ctx))
        except Exception as exc:  # noqa: BLE001 - audit passes must never crash the audit
            findings = [
                AuditFinding(
                    priority="P2",
                    category=pass_obj.id,
                    title=f"Audit pass '{pass_obj.id}' failed",
                    evidence=str(exc),
                    recommendation="Investigate and fix the audit pass implementation.",
                    autofixable_later=False,
                )
            ]
        results.append((pass_obj.id, findings))
    return results
