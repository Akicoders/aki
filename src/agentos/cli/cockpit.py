"""Operational cockpit rendering and project resolution for Aki."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from textwrap import shorten
from typing import Literal, Optional

import yaml
from git import Repo
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from agentos.cli.mcp_hosts import _get_host_config_path, _get_mcp_snippet
from agentos.cockpit import registry
from agentos.core.config import get_config
from agentos.core.project_breadcrumb import write_breadcrumb
from agentos.memory.database import Database
from agentos.memory.models import EventType, MemoryEventModel, MemoryFactModel
from agentos.sdd.detector import SDD_FILES, detect_sdd_artifacts, load_sdd_artifact

HealthState = Literal["healthy", "warning", "failing", "unknown"]
ProjectSource = Literal["git", "marker", "manual"]

PROJECT_ROOT_MARKERS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "docs/sdd",
    ".sdd",
    "openspec",
)
LOCKFILES = ("uv.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "go.sum")
WORKFLOW_EVENT_TYPES = (EventType.TASK, EventType.OUTCOME, EventType.CODE_CHANGE, EventType.DEPLOY)


@dataclass
class ProjectRef:
    key: str
    root_path: Path
    source: ProjectSource
    last_opened_at: datetime | None = None
    last_audit_at: datetime | None = None
    last_memory_activity_at: datetime | None = None


@dataclass
class GitSummary:
    branch: str | None
    is_dirty: bool | None
    modified_count: int = 0
    untracked_count: int = 0
    has_conflicts: bool = False
    detail: str = ""


@dataclass
class HealthCheckResult:
    id: str
    status: HealthState
    summary: str
    detail: str
    updated_at: datetime | None
    source: str
    is_stale: bool = False


@dataclass
class ActionItem:
    severity: str
    title: str
    evidence: str
    command: str


@dataclass
class MemoryFactSummary:
    key: str
    value: str
    updated_at: datetime | None


@dataclass
class MemorySummary:
    recent_facts: list[MemoryFactSummary] = field(default_factory=list)
    latest_decision: str | None = None
    recent_workflow_memory: str | None = None
    last_activity_at: datetime | None = None
    note: str | None = None


@dataclass
class SDDSummary:
    has_sdd: bool
    sdd_dir: str | None
    found_artifacts: list[str]
    missing_artifacts: list[str]
    latest_artifact: str | None
    latest_artifact_updated_at: datetime | None
    latest_preview: str | None
    next_step: str

    @property
    def completeness(self) -> str:
        return f"{len(self.found_artifacts)}/{len(SDD_FILES)}"


@dataclass
class CockpitSnapshot:
    project: ProjectRef
    generated_at: datetime
    action_items: list[ActionItem]
    health_checks: list[HealthCheckResult]
    memory_summary: MemorySummary
    sdd_summary: SDDSummary
    git_summary: GitSummary


def render_default_entry(console: Console, start_path: Optional[Path] = None) -> None:
    project = resolve_project_ref(start_path)
    if project is None:
        render_projects_browse(
            console,
            current_path=(start_path or Path.cwd()).resolve(),
            reason="The current directory could not be found on disk.",
        )
        return
    render_cockpit_overview(console, project)


def render_projects_browse(console: Console, current_path: Path, reason: str | None = None) -> None:
    lines = []
    if reason:
        lines.append(f"[yellow]{reason}[/yellow]")
        lines.append("")
    lines.extend([
        "[bold]Projects browsing is the fallback entry for unresolved directories.[/bold]",
        "The full multi-project browser is deferred to a later cockpit slice.",
        "",
        f"Current path: [cyan]{current_path}[/cyan]",
        "",
        "[bold]Next paths[/bold]",
        "1. cd into a project root and run [cyan]aki[/cyan]",
        "2. open a project explicitly with [cyan]aki cockpit --path /absolute/path/to/project[/cyan]",
        "3. use [cyan]aki --help[/cyan] for the existing explicit commands",
    ])
    console.print(Panel("\n".join(lines), title="Projects Browse", border_style="yellow"))


def render_cockpit_overview(console: Console, project: ProjectRef) -> None:
    snapshot = build_cockpit_snapshot(project)
    console.print(_render_header(snapshot))
    panels = [
        Panel(_render_action_required_panel(snapshot), title="Action Required", border_style="red"),
        Panel(_render_health_panel(snapshot), title="Project Health", border_style="green"),
        Panel(_render_memory_panel(snapshot), title="Memory", border_style="blue"),
        Panel(_render_sdd_panel(snapshot), title="SDD Status", border_style="magenta"),
    ]
    console.print(Columns(panels, equal=True, expand=True))
    console.print(_render_footer())


def render_cockpit_detail(console: Console, project: ProjectRef, section: str) -> None:
    snapshot = build_cockpit_snapshot(project)
    console.print(_render_header(snapshot))

    if section == "action":
        console.print(_render_action_detail(snapshot))
    elif section == "health":
        console.print(_render_health_detail(snapshot))
    elif section == "memory":
        console.print(_render_memory_detail(snapshot))
    elif section == "sdd":
        console.print(_render_sdd_detail(snapshot))
    else:
        raise ValueError(f"Unknown cockpit section: {section}")

    console.print(Panel("Return to the overview with [cyan]aki cockpit[/cyan].", title="Navigation", border_style="cyan"))


def resolve_project_ref(start_path: Optional[Path] = None) -> ProjectRef | None:
    candidate = (start_path or Path.cwd()).expanduser().resolve()

    # Only genuinely unresolvable paths (nonexistent paths) fall through to
    # the Projects Browse screen. This mirrors detect_project()'s
    # permissiveness (src/agentos/mcp/project.py) so `aki cockpit` works in
    # any real directory, the same way `aki chat`/`aki interactive` do.
    if not candidate.exists():
        return None

    current = candidate if candidate.is_dir() else candidate.parent
    if not current.is_dir():
        return None

    git_root = _find_git_root(current)
    if git_root is not None and git_root.name:
        return ProjectRef(key=git_root.name, root_path=git_root, source="git")

    if _has_project_markers(current) and current.name:
        return ProjectRef(key=current.name, root_path=current, source="marker")

    if current.name:
        return ProjectRef(key=current.name, root_path=current, source="manual")

    return None


def build_cockpit_snapshot(project: ProjectRef, record_open: bool = True) -> CockpitSnapshot:
    generated_at = datetime.now()
    git_summary = _collect_git_summary(project.root_path)
    sdd_summary = _build_sdd_summary(project.root_path)
    memory_summary = _build_memory_summary(project)
    project.last_opened_at = generated_at
    project.last_memory_activity_at = memory_summary.last_activity_at
    if record_open:
        registry.upsert_project(project.key, project.root_path, source=project.source)
        write_breadcrumb(project.root_path)

    health_checks = [
        _build_tests_health(project.root_path, generated_at),
        _build_sdd_health(sdd_summary, generated_at),
        _build_git_health(git_summary, generated_at),
        _build_env_health(project.root_path, generated_at),
        _build_mcp_health(generated_at),
    ]
    action_items = _build_action_items(health_checks, sdd_summary)

    return CockpitSnapshot(
        project=project,
        generated_at=generated_at,
        action_items=action_items,
        health_checks=health_checks,
        memory_summary=memory_summary,
        sdd_summary=sdd_summary,
        git_summary=git_summary,
    )


def _find_git_root(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _has_project_markers(path: Path) -> bool:
    return any((path / marker).exists() for marker in PROJECT_ROOT_MARKERS)


def _collect_git_summary(root_path: Path) -> GitSummary:
    git_root = _find_git_root(root_path)
    if git_root is None:
        return GitSummary(branch=None, is_dirty=None, detail="Not a git repository")

    try:
        repo = Repo(git_root)
        modified_files = [item.a_path for item in repo.index.diff(None)]
        untracked_files = list(repo.untracked_files)
        conflicts = repo.index.unmerged_blobs()
        is_dirty = repo.is_dirty(untracked_files=True)
        branch_name = repo.active_branch.name if not repo.head.is_detached else "detached"
        detail = f"{branch_name} | modified {len(modified_files)} | untracked {len(untracked_files)}"
        return GitSummary(
            branch=branch_name,
            is_dirty=is_dirty,
            modified_count=len(modified_files),
            untracked_count=len(untracked_files),
            has_conflicts=bool(conflicts),
            detail=detail,
        )
    except Exception as exc:
        return GitSummary(branch=None, is_dirty=None, detail=f"Git inspection unavailable: {exc}")


def _build_tests_health(root_path: Path, generated_at: datetime) -> HealthCheckResult:
    pytest_cache = root_path / ".pytest_cache"
    if not pytest_cache.exists():
        return HealthCheckResult(
            id="tests",
            status="unknown",
            summary="No cached test result yet",
            detail="Cached test posture is not wired yet in this slice. Run pytest manually or use a later audit slice.",
            updated_at=None,
            source="placeholder",
            is_stale=True,
        )

    updated_at = datetime.fromtimestamp(pytest_cache.stat().st_mtime)
    return HealthCheckResult(
        id="tests",
        status="unknown",
        summary="Pytest cache found, result parsing deferred",
        detail="Aki detected pytest metadata but does not compute pass/fail state from it yet in this slice.",
        updated_at=updated_at,
        source="filesystem",
        is_stale=True,
    )


def _build_sdd_summary(root_path: Path) -> SDDSummary:
    status = detect_sdd_artifacts(root_path)
    latest_artifact = None
    latest_artifact_updated_at = None
    latest_preview = None

    if status.has_sdd and status.sdd_dir:
        sdd_dir = root_path / status.sdd_dir
        latest_path = None
        for artifact in status.found_artifacts:
            artifact_path = sdd_dir / artifact
            if latest_path is None or artifact_path.stat().st_mtime > latest_path.stat().st_mtime:
                latest_path = artifact_path
        if latest_path is not None:
            latest_artifact = latest_path.name
            latest_artifact_updated_at = datetime.fromtimestamp(latest_path.stat().st_mtime)
            content = load_sdd_artifact(latest_artifact, root_path)
            if content:
                latest_preview = "\n".join(content.strip().splitlines()[:6])

    if not status.has_sdd:
        next_step = "Run aki sdd-init to create the base proposal/spec/design/tasks structure."
    elif status.missing_artifacts:
        next_step = f"Create {status.missing_artifacts[0]} under {status.sdd_dir}."
    else:
        next_step = "All core SDD artifacts are present."

    return SDDSummary(
        has_sdd=status.has_sdd,
        sdd_dir=status.sdd_dir,
        found_artifacts=status.found_artifacts,
        missing_artifacts=status.missing_artifacts,
        latest_artifact=latest_artifact,
        latest_artifact_updated_at=latest_artifact_updated_at,
        latest_preview=latest_preview,
        next_step=next_step,
    )


def _build_sdd_health(summary: SDDSummary, generated_at: datetime) -> HealthCheckResult:
    if not summary.has_sdd:
        return HealthCheckResult(
            id="sdd",
            status="warning",
            summary="0/4 core artifacts present",
            detail="No SDD directory detected.",
            updated_at=generated_at,
            source="filesystem",
        )

    if summary.missing_artifacts:
        return HealthCheckResult(
            id="sdd",
            status="warning",
            summary=f"{summary.completeness} artifacts present",
            detail=f"Missing: {', '.join(summary.missing_artifacts)}",
            updated_at=summary.latest_artifact_updated_at or generated_at,
            source="filesystem",
        )

    return HealthCheckResult(
        id="sdd",
        status="healthy",
        summary="4/4 core artifacts present",
        detail=f"Using {summary.sdd_dir}",
        updated_at=summary.latest_artifact_updated_at or generated_at,
        source="filesystem",
    )


def _build_git_health(git_summary: GitSummary, generated_at: datetime) -> HealthCheckResult:
    if git_summary.branch is None and git_summary.is_dirty is None:
        return HealthCheckResult(
            id="git",
            status="unknown",
            summary="Git status unavailable",
            detail=git_summary.detail,
            updated_at=generated_at,
            source="git",
        )

    if git_summary.has_conflicts:
        return HealthCheckResult(
            id="git",
            status="failing",
            summary="Repository has merge conflicts",
            detail=git_summary.detail,
            updated_at=generated_at,
            source="git",
        )

    if git_summary.is_dirty:
        return HealthCheckResult(
            id="git",
            status="warning",
            summary="Working tree is dirty",
            detail=git_summary.detail,
            updated_at=generated_at,
            source="git",
        )

    return HealthCheckResult(
        id="git",
        status="healthy",
        summary="Working tree is clean",
        detail=git_summary.detail,
        updated_at=generated_at,
        source="git",
    )


def _build_env_health(root_path: Path, generated_at: datetime) -> HealthCheckResult:
    py_ok = sys.version_info >= (3, 11)
    uv_path = shutil.which("uv")
    env_example = root_path / ".env.example"
    env_path = root_path / ".env"
    config_path = root_path / "config.yaml"

    detail_parts = [f"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"]
    warnings: list[str] = []
    failing: list[str] = []

    if py_ok:
        detail_parts.append("Python ok")
    else:
        failing.append("Python 3.11+ required")

    if uv_path:
        detail_parts.append("uv installed")
    else:
        warnings.append("uv not found")

    if env_example.exists() and not env_path.exists():
        warnings.append(".env missing")
    elif env_path.exists():
        detail_parts.append(".env present")
        env_text = env_path.read_text(encoding="utf-8")
        has_qwen = "QWEN_API_KEY=" in env_text and "QWEN_API_KEY=your_" not in env_text
        has_dashscope = "DASHSCOPE_API_KEY=" in env_text and "DASHSCOPE_API_KEY=your_" not in env_text
        if has_qwen or has_dashscope:
            detail_parts.append("API key present")
        elif "QWEN_API_KEY=" in env_text or "DASHSCOPE_API_KEY=" in env_text:
            warnings.append("API key still placeholder")

    lockfile_name = next((name for name in LOCKFILES if (root_path / name).exists()), None)
    if (root_path / "pyproject.toml").exists() and lockfile_name is None:
        warnings.append("no lockfile detected")
    elif lockfile_name:
        detail_parts.append(f"lockfile {lockfile_name}")

    if config_path.exists():
        try:
            yaml.safe_load(config_path.read_text(encoding="utf-8"))
            detail_parts.append("config.yaml parses")
        except yaml.YAMLError as exc:
            failing.append(f"config.yaml invalid: {exc}")

    if failing:
        status: HealthState = "failing"
        summary = "; ".join(failing)
    elif warnings:
        status = "warning"
        summary = "; ".join(warnings)
    else:
        status = "healthy"
        summary = "Local env/config looks usable"

    detail = "; ".join(detail_parts) if detail_parts else "No env/config signals detected"
    return HealthCheckResult(
        id="env",
        status=status,
        summary=summary,
        detail=detail,
        updated_at=generated_at,
        source="system+filesystem",
    )


def _build_mcp_health(generated_at: datetime) -> HealthCheckResult:
    config_path = _get_host_config_path("opencode")
    snippet = _get_mcp_snippet("opencode")

    if not config_path.exists():
        return HealthCheckResult(
            id="mcp",
            status="warning",
            summary="OpenCode host config not found",
            detail=f"Expected {config_path}",
            updated_at=None,
            source="filesystem",
        )

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return HealthCheckResult(
            id="mcp",
            status="failing",
            summary="OpenCode MCP config is unreadable",
            detail=str(exc),
            updated_at=generated_at,
            source="filesystem",
        )

    expected_entry = snippet.get("mcp", {}).get("aki_memory")
    actual_entry = data.get("mcp", {}).get("aki_memory")
    if actual_entry == expected_entry:
        return HealthCheckResult(
            id="mcp",
            status="healthy",
            summary="OpenCode MCP entry is configured",
            detail=str(config_path),
            updated_at=datetime.fromtimestamp(config_path.stat().st_mtime),
            source="filesystem",
        )

    return HealthCheckResult(
        id="mcp",
        status="warning",
        summary="Aki MCP entry missing or drifted",
        detail=f"Check {config_path}",
        updated_at=datetime.fromtimestamp(config_path.stat().st_mtime),
        source="filesystem",
    )


def _build_memory_summary(project: ProjectRef) -> MemorySummary:
    db_path = _resolve_memory_db_path(project.root_path)
    if not db_path.exists():
        return MemorySummary(note="No local memory database found for this project yet.")

    database = Database(db_path)
    scope = f"project:{project.key}"
    try:
        with database.session() as session:
            facts = session.execute(
                select(MemoryFactModel)
                .where(MemoryFactModel.scope == scope)
                .order_by(MemoryFactModel.updated_at.desc(), MemoryFactModel.confidence.desc())
                .limit(5)
            ).scalars().all()

            latest_decision = session.execute(
                select(MemoryEventModel)
                .where(
                    MemoryEventModel.project == project.key,
                    MemoryEventModel.type == EventType.DECISION,
                )
                .order_by(MemoryEventModel.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()

            workflow_memory = session.execute(
                select(MemoryEventModel)
                .where(
                    MemoryEventModel.project == project.key,
                    MemoryEventModel.type.in_(WORKFLOW_EVENT_TYPES),
                )
                .order_by(MemoryEventModel.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()

            latest_event = session.execute(
                select(MemoryEventModel)
                .where(MemoryEventModel.project == project.key)
                .order_by(MemoryEventModel.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()
    finally:
        database.close()

    fact_summaries = [
        MemoryFactSummary(key=fact.key, value=fact.value, updated_at=fact.updated_at)
        for fact in facts
    ]
    latest_fact_time = max((fact.updated_at for fact in facts), default=None)
    latest_event_time = latest_event.timestamp if latest_event is not None else None
    last_activity_at = max((ts for ts in (latest_fact_time, latest_event_time) if ts is not None), default=None)

    note = None
    if not fact_summaries and latest_decision is None and workflow_memory is None:
        note = "No durable project memory found yet. Use remember/facts as memory fills in."

    return MemorySummary(
        recent_facts=fact_summaries,
        latest_decision=latest_decision.content if latest_decision is not None else None,
        recent_workflow_memory=workflow_memory.content if workflow_memory is not None else None,
        last_activity_at=last_activity_at,
        note=note,
    )


def _resolve_memory_db_path(project_root: Path) -> Path:
    db_path = get_config().memory.db_path
    return db_path if db_path.is_absolute() else project_root / db_path


def _build_action_items(health_checks: list[HealthCheckResult], sdd_summary: SDDSummary) -> list[ActionItem]:
    items: list[ActionItem] = []
    checks_by_id = {check.id: check for check in health_checks}

    git_check = checks_by_id["git"]
    if git_check.status == "failing":
        items.append(ActionItem("critical", "Resolve git conflicts", git_check.detail, "git status --short"))
    elif git_check.status == "warning":
        items.append(ActionItem("warning", "Review dirty working tree", git_check.detail, "git status --short"))

    env_check = checks_by_id["env"]
    if env_check.status in {"warning", "failing"}:
        items.append(ActionItem("warning", "Fix env/config posture", env_check.summary, "aki doctor"))

    mcp_check = checks_by_id["mcp"]
    if mcp_check.status in {"warning", "failing"}:
        items.append(ActionItem("warning", "Complete OpenCode MCP readiness", mcp_check.summary, "aki mcp-setup opencode"))

    if not sdd_summary.has_sdd:
        items.append(ActionItem("warning", "Initialize SDD structure", "No SDD directory detected", "aki sdd-init"))
    elif sdd_summary.missing_artifacts:
        items.append(
            ActionItem(
                "warning",
                "Complete missing SDD artifacts",
                f"Missing: {', '.join(sdd_summary.missing_artifacts)}",
                "aki cockpit sdd",
            )
        )

    return items


def _render_header(snapshot: CockpitSnapshot) -> Panel:
    git_summary = snapshot.git_summary
    branch = git_summary.branch or "n/a"
    dirty = "dirty" if git_summary.is_dirty else ("clean" if git_summary.is_dirty is False else "unknown")

    ascii_art = (
        "[bold cyan]"
        "██████╗ ██╗  ██╗██╗\n"
        "██╔══██╗██║ ██╔╝██║\n"
        "███████║█████╔╝ ██║\n"
        "██╔══██║██╔═██╗ ██║\n"
        "██║  ██║██║  ██╗██║\n"
        "╚═╝  ╚═╝╚═╝  ╚═╝╚═╝"
        "[/bold cyan]"
    )

    info_text = (
        f"[bold white]Project :[/bold white] [bold yellow]{snapshot.project.key}[/bold yellow]\n"
        f"[bold white]Root    :[/bold white] [cyan]{snapshot.project.root_path}[/cyan]\n"
        f"[bold white]Source  :[/bold white] [yellow]{snapshot.project.source}[/yellow] | "
        f"[bold white]Branch  :[/bold white] [magenta]{branch}[/magenta] | "
        f"[bold white]State   :[/bold white] [green]{dirty}[/green]\n"
        f"[bold white]Refreshed:[/bold white] [dim]{snapshot.generated_at:%Y-%m-%d %H:%M:%S}[/dim]"
    )

    # Use a grid for side-by-side layout
    table = Table.grid(expand=True)
    table.add_column(ratio=2)
    table.add_column(ratio=3)
    table.add_row(ascii_art, info_text)

    return Panel(table, title="[bold cyan]AKI OPERATIONAL COCKPIT[/bold cyan]", border_style="cyan")


def _render_footer() -> Panel:
    body = "Drill-down: [cyan]aki cockpit action[/cyan] | [cyan]health[/cyan] | [cyan]memory[/cyan] | [cyan]sdd[/cyan] | Browse fallback: [cyan]aki projects browse[/cyan]"
    return Panel(body, title="Navigation", border_style="cyan")


def _render_action_required_panel(snapshot: CockpitSnapshot) -> str:
    if not snapshot.action_items:
        return "[green]No immediate action required from the current snapshot.[/green]\nUse [cyan]aki cockpit health[/cyan] for per-check details."

    lines = []
    for item in snapshot.action_items[:4]:
        lines.append(
            f"[{_severity_style(item.severity)}]{item.severity.upper()}[/] {item.title}\n"
            f"{item.evidence}\n"
            f"[dim]{item.command}[/dim]"
        )
    return "\n\n".join(lines)


def _render_health_panel(snapshot: CockpitSnapshot) -> str:
    lines = []
    for check in snapshot.health_checks:
        lines.append(f"[{_health_style(check.status)}]{check.id}[/]: {check.summary}")
    return "\n".join(lines)


def _render_memory_panel(snapshot: CockpitSnapshot) -> str:
    memory = snapshot.memory_summary
    lines = []

    if memory.recent_facts:
        lines.append("[bold]Facts[/bold]")
        for fact in memory.recent_facts[:3]:
            lines.append(f"- [cyan]{fact.key}[/cyan]: {shorten(fact.value, width=56, placeholder='...')}")
    else:
        lines.append("[dim]No durable facts yet[/dim]")

    lines.append(f"Decision: {shorten(memory.latest_decision, width=56, placeholder='...') if memory.latest_decision else '[dim]none yet[/dim]'}")
    lines.append(
        f"Workflow: {shorten(memory.recent_workflow_memory, width=56, placeholder='...') if memory.recent_workflow_memory else '[dim]none yet[/dim]'}"
    )
    lines.append(f"Last activity: [dim]{_format_timestamp(memory.last_activity_at)}[/dim]")

    if memory.note:
        lines.append(f"[dim]{memory.note}[/dim]")

    return "\n".join(lines)


def _render_sdd_panel(snapshot: CockpitSnapshot) -> str:
    sdd = snapshot.sdd_summary
    lines = [f"Completeness: [yellow]{sdd.completeness}[/yellow]"]
    lines.append(f"Directory: [cyan]{sdd.sdd_dir or 'not detected'}[/cyan]")
    lines.append(f"Latest: {sdd.latest_artifact or '[dim]none[/dim]'}")
    if sdd.missing_artifacts:
        lines.append(f"Missing: [yellow]{', '.join(sdd.missing_artifacts)}[/yellow]")
    lines.append(sdd.next_step)
    return "\n".join(lines)


def _render_action_detail(snapshot: CockpitSnapshot) -> Panel:
    if not snapshot.action_items:
        return Panel("No action items are currently raised by the cockpit snapshot.", title="Action Required Detail", border_style="green")

    table = Table(title="Action Required Detail")
    table.add_column("Severity", style="bold")
    table.add_column("Title", style="white")
    table.add_column("Evidence", style="dim")
    table.add_column("Command", style="cyan")
    for item in snapshot.action_items:
        table.add_row(item.severity, item.title, item.evidence, item.command)
    return Panel(table, border_style="red")


def _render_health_detail(snapshot: CockpitSnapshot) -> Panel:
    table = Table(title="Project Health Detail")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Summary", style="white")
    table.add_column("Detail", style="dim")
    table.add_column("Updated", style="yellow")
    table.add_column("Source", style="green")
    for check in snapshot.health_checks:
        table.add_row(
            check.id,
            check.status,
            check.summary,
            check.detail,
            _format_timestamp(check.updated_at),
            check.source,
        )
    return Panel(table, border_style="green")


def _render_memory_detail(snapshot: CockpitSnapshot) -> Panel:
    memory = snapshot.memory_summary
    body: list[object] = []

    facts_table = Table(title="Recent Durable Facts")
    facts_table.add_column("Key", style="cyan")
    facts_table.add_column("Value", style="white")
    facts_table.add_column("Updated", style="yellow")
    if memory.recent_facts:
        for fact in memory.recent_facts:
            facts_table.add_row(fact.key, shorten(fact.value, width=90, placeholder="..."), _format_timestamp(fact.updated_at))
    else:
        facts_table.add_row("-", "No facts stored for this project yet", "-")
    body.append(facts_table)

    decision = memory.latest_decision or "No decision memory stored yet"
    workflow = memory.recent_workflow_memory or "No workflow memory stored yet"
    body.append(Panel(decision, title="Latest Decision", border_style="blue"))
    body.append(Panel(workflow, title="Workflow Memory", border_style="blue"))
    body.append(Panel(f"Last activity: {_format_timestamp(memory.last_activity_at)}", title="Memory Activity", border_style="blue"))
    if memory.note:
        body.append(Panel(memory.note, title="Notes", border_style="dim"))
    return Panel(Columns(body, equal=True, expand=True), title="Memory Detail", border_style="blue")


def _render_sdd_detail(snapshot: CockpitSnapshot) -> Panel:
    sdd = snapshot.sdd_summary
    table = Table(title="SDD Artifact Status")
    table.add_column("Artifact", style="cyan")
    table.add_column("Status", style="bold")

    for artifact in SDD_FILES:
        status = "present" if artifact in sdd.found_artifacts else "missing"
        table.add_row(artifact, status)

    panels: list[object] = [table, Panel(sdd.next_step, title="Next Step", border_style="magenta")]
    if sdd.latest_preview:
        title = f"Latest Artifact Preview: {sdd.latest_artifact}"
        panels.append(Panel(sdd.latest_preview, title=title, border_style="magenta"))

    return Panel(Columns(panels, equal=True, expand=True), title="SDD Detail", border_style="magenta")


def _health_style(status: HealthState) -> str:
    return {
        "healthy": "green",
        "warning": "yellow",
        "failing": "red",
        "unknown": "dim",
    }[status]


def _severity_style(severity: str) -> str:
    return {
        "critical": "red",
        "warning": "yellow",
        "info": "cyan",
    }.get(severity, "white")


def _format_timestamp(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else "unknown"
