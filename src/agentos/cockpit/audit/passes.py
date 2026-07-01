"""The six read-only audit passes for `aki audit <project>`.

Each pass reuses existing Aki building blocks rather than reimplementing
detection/health logic:
- tests: CodeIntelSkill (async), bridged via asyncio.run at this sync call site.
- sdd: agentos.sdd.detector.
- git: agentos.cli.cockpit._collect_git_summary (same GitPython probing as the cockpit).
- env: agentos.cli.cockpit._build_env_health (READ-ONLY, calls get_config()).
- mcp: agentos.cli.cockpit._build_mcp_health (agentos.cli.mcp_hosts helpers).
- memory: agentos.cli.cockpit._build_memory_summary (existing MemoryFactModel/MemoryEventModel queries).
"""

from __future__ import annotations

import asyncio

from agentos.cli.cockpit import (
    HealthCheckResult,
    _build_env_health,
    _build_mcp_health,
    _build_memory_summary,
    _build_sdd_summary,
    _collect_git_summary,
)
from agentos.cockpit.audit.base import AuditContext, AuditFinding
from agentos.sdd.detector import SDD_FILES
from agentos.skills.code_intel import CodeIntelSkill

_HEALTH_TO_PRIORITY = {
    "failing": "P0",
    "warning": "P2",
    "unknown": "P3",
}


def _health_to_findings(check: HealthCheckResult, category: str) -> list[AuditFinding]:
    if check.status == "healthy":
        return []
    priority = _HEALTH_TO_PRIORITY.get(check.status, "P3")
    return [
        AuditFinding(
            priority=priority,
            category=category,
            title=check.summary,
            evidence=check.detail,
            recommendation=f"Review the '{category}' posture and re-run 'aki audit' once addressed.",
            autofixable_later=False,
        )
    ]


class TestsPass:
    """Test/runtime posture pass — reuses CodeIntelSkill instead of new subprocess calls."""

    id = "tests"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        skill = CodeIntelSkill(config={"test_command": "pytest -q"})

        async def _run_all():
            tests_result = await skill.run_tests(str(ctx.root_path))
            lint_result = await skill.run_lint(str(ctx.root_path))
            coverage_result = await skill.get_coverage(str(ctx.root_path))
            return tests_result, lint_result, coverage_result

        tests_result, lint_result, _coverage_result = asyncio.run(_run_all())

        findings: list[AuditFinding] = []
        if not tests_result.success:
            evidence = tests_result.error or str((tests_result.data or {}).get("stderr", ""))
            findings.append(
                AuditFinding(
                    priority="P0",
                    category="tests",
                    title="Test suite is failing or could not run",
                    evidence=evidence[:1000],
                    recommendation="Run the test suite locally and fix failing tests before merging further changes.",
                    autofixable_later=False,
                )
            )
        if not lint_result.success:
            evidence = lint_result.error or str((lint_result.data or {}).get("stdout", ""))
            findings.append(
                AuditFinding(
                    priority="P2",
                    category="tests",
                    title="Lint check reported issues",
                    evidence=evidence[:1000],
                    recommendation="Run the linter locally and address the reported issues.",
                    autofixable_later=False,
                )
            )
        return findings


class SddPass:
    """SDD completeness and artifact quality pass."""

    id = "sdd"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        summary = _build_sdd_summary(ctx.root_path)
        if not summary.has_sdd:
            return [
                AuditFinding(
                    priority="P1",
                    category="sdd",
                    title="No SDD structure detected",
                    evidence="No docs/sdd, .sdd, or openspec directory found.",
                    recommendation="Run 'aki sdd-init' to bootstrap proposal/spec/design/tasks.",
                    autofixable_later=False,
                )
            ]
        if summary.missing_artifacts:
            return [
                AuditFinding(
                    priority="P2",
                    category="sdd",
                    title=f"SDD is incomplete ({summary.completeness})",
                    evidence=f"Missing: {', '.join(summary.missing_artifacts)} in {summary.sdd_dir}.",
                    recommendation=f"Create {summary.missing_artifacts[0]} under {summary.sdd_dir}.",
                    autofixable_later=False,
                )
            ]
        return []


class GitPass:
    """Git and repository hygiene pass — reuses the same GitPython probing as the cockpit."""

    id = "git"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        git_summary = _collect_git_summary(ctx.root_path)
        findings: list[AuditFinding] = []

        if git_summary.branch is None and git_summary.is_dirty is None:
            findings.append(
                AuditFinding(
                    priority="P3",
                    category="git",
                    title="Git status unavailable",
                    evidence=git_summary.detail,
                    recommendation="Verify this project is a git repository if version control is expected.",
                    autofixable_later=False,
                )
            )
        elif git_summary.has_conflicts:
            findings.append(
                AuditFinding(
                    priority="P0",
                    category="git",
                    title="Repository has unresolved merge conflicts",
                    evidence=git_summary.detail,
                    recommendation="Resolve merge conflicts before continuing work.",
                    autofixable_later=False,
                )
            )
        elif git_summary.is_dirty:
            findings.append(
                AuditFinding(
                    priority="P2",
                    category="git",
                    title="Working tree is dirty",
                    evidence=git_summary.detail,
                    recommendation="Review 'git status --short' and commit or stash outstanding changes.",
                    autofixable_later=False,
                )
            )
        return findings


class EnvPass:
    """Env/config posture pass — READ-ONLY, reuses agentos.core.config.get_config() via the
    existing cockpit health check. Does not modify config.py's load/write path."""

    id = "env"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        check = _build_env_health(ctx.root_path, ctx.generated_at)
        return _health_to_findings(check, "env")


class McpPass:
    """MCP readiness and host integration posture pass."""

    id = "mcp"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        check = _build_mcp_health(ctx.generated_at)
        return _health_to_findings(check, "mcp")


class MemoryPass:
    """Memory posture and memory gaps pass."""

    id = "memory"

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        summary = _build_memory_summary(ctx.project)
        if summary.note:
            return [
                AuditFinding(
                    priority="P3",
                    category="memory",
                    title="No durable project memory yet",
                    evidence=summary.note,
                    recommendation="Use 'aki remember' / 'aki set-fact' to start building durable project memory.",
                    autofixable_later=False,
                )
            ]
        return []


PASS_REGISTRY: list = [
    TestsPass(),
    SddPass(),
    GitPass(),
    EnvPass(),
    McpPass(),
    MemoryPass(),
]

__all__ = [
    "TestsPass",
    "SddPass",
    "GitPass",
    "EnvPass",
    "McpPass",
    "MemoryPass",
    "PASS_REGISTRY",
    "SDD_FILES",
]
