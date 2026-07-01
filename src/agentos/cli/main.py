"""CLI entry point for Aki."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentos.cli.cockpit import (
    _build_sdd_summary,
    _collect_git_summary,
    _format_timestamp,
    render_cockpit_detail,
    render_cockpit_overview,
    render_default_entry,
    render_projects_browse,
    resolve_project_ref,
)
from agentos.cli.mcp_hosts import _get_host_config_path, _get_mcp_snippet, _merge_mcp_config
from agentos.cockpit.navigation import run_cockpit_loop
from agentos.cockpit import registry
from agentos.cockpit.registry import list_projects
from agentos.cockpit.audit.base import AuditContext, merge_findings, run_registered_passes
from agentos.cockpit.audit.passes import PASS_REGISTRY
from agentos.cockpit.audit.report import persist_audit
from agentos.core.config import get_config, reset_config
from agentos.memory.models import EventType
from agentos.skills.base import get_skill_registry
from agentos.skills import load_skills
from agentos.sdd.detector import detect_sdd_artifacts, summarize_sdd_context
from agentos.sdd.init import init_sdd_project

if TYPE_CHECKING:
    from agentos.agent.core import AgentOS

app = typer.Typer(
    name="aki",
    help="Aki - AI agent with portable project memory",
    add_completion=False,
)
cockpit_app = typer.Typer(help="Open the operational cockpit for a project.")
projects_app = typer.Typer(help="Browse projects when current context is unclear.")
app.add_typer(cockpit_app, name="cockpit")
app.add_typer(projects_app, name="projects")
console = Console()


def _get_agent():
    from agentos.agent.core import get_agent

    return get_agent()


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Aki is an AI agent with persistent cross-session project memory."""
    if config_path:
        reset_config()
        get_config(config_path)
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    if ctx.invoked_subcommand is None:
        render_default_entry(console)


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send"),
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
    stream: bool = typer.Option(False, "--stream", help="Stream response"),
):
    """Chat with Aki."""
    agent = _get_agent()

    async def run():
        if stream:
            async for chunk in agent.stream_chat(message, project, session):
                console.print(chunk, end="")
            console.print()
        else:
            response = await agent.chat(message, project, session)
            console.print(Markdown(response))

    asyncio.run(run())


@app.command()
def interactive(
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
):
    """Start interactive chat session."""
    agent = _get_agent()
    session_id = session or f"sess_{__import__('uuid').uuid4().hex[:8]}"

    _print_interactive_header(agent, project, session_id)

    sdd_status = detect_sdd_artifacts()
    if not sdd_status.has_sdd:
        console.print(Panel(
            "[yellow]This project doesn't have SDD artifacts yet.[/yellow]\n"
            "Run [bold]aki sdd-init[/bold] to initialize SDD for this project.",
            title="SDD Detection",
            border_style="yellow",
        ))

    asyncio.run(_async_interactive(agent, project, session_id))


@app.command("mcp")
def mcp_server():
    """Start the Aki stdio MCP server."""
    from agentos.mcp.server import run_mcp_server

    run_mcp_server()


@app.command("mcp-config")
def mcp_config(host: str = typer.Argument("opencode", help="MCP host to print config for")):
    """Print an MCP host configuration snippet."""
    normalized_host = host.strip().lower()
    command = ["uv", "run", "aki", "mcp"]
    snippets = {
        "opencode": {
            "mcp": {
                "aki_memory": {
                    "type": "local",
                    "command": command,
                    "enabled": True,
                }
            }
        },
        "claude-code": {
            "name": "aki_memory",
            "transport": "stdio",
            "command": command[0],
            "args": command[1:],
        },
        "generic-json": {
            "name": "aki_memory",
            "transport": "stdio",
            "command": command[0],
            "args": command[1:],
            "cwd": "/absolute/path/to/aki",
        },
    }
    if normalized_host not in snippets:
        supported = ", ".join(sorted(snippets))
        raise typer.BadParameter(f"Unsupported host '{host}'. Supported hosts: {supported}")
    typer.echo(json.dumps(snippets[normalized_host], indent=2))

@app.command("mcp-setup")
def mcp_setup(
    host: str = typer.Argument(..., help="MCP host to configure (opencode or claude-code)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen without modifying files"),
):
    """Automatically set up Aki MCP config in a host's configuration file."""
    normalized_host = host.strip().lower()
    if normalized_host not in ("opencode", "claude-code"):
        raise typer.BadParameter(f"Unsupported host '{host}'. Supported: opencode, claude-code")

    config_path = _get_host_config_path(normalized_host)
    snippet = _get_mcp_snippet(normalized_host)

    if dry_run:
        console.print(f"[bold]Dry run for {normalized_host}[/bold]")
        console.print(f"Config file: {config_path}")
        if config_path.exists():
            console.print("[yellow]File exists — would create backup and merge[/yellow]")
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
                merged = _merge_mcp_config(existing, snippet)
                console.print("[bold]Merged config would be:[/bold]")
                console.print(json.dumps(merged, indent=2))
            except (json.JSONDecodeError, OSError) as e:
                console.print(f"[red]Cannot parse existing file: {e}[/red]")
        else:
            console.print("[yellow]File does not exist — would create it[/yellow]")
            console.print(json.dumps(snippet, indent=2))
        return

    if config_path.exists():
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        backup_path = config_path.with_suffix(f".backup.{timestamp}")
        shutil.copy2(config_path, backup_path)
        console.print(f"[green]✓[/green] Backup created: {backup_path}")

        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            console.print(f"[red]Cannot parse {config_path}: {e}[/red]")
            raise typer.Exit(1)

        merged = _merge_mcp_config(existing, snippet)
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        merged = snippet

    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]✓[/green] Aki MCP config added to {config_path}")


@app.command()
def doctor():
    """Check Aki installation health."""
    checks: list[tuple[str, bool, str]] = []

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python >= 3.11", py_ok, py_version))

    uv_ok = shutil.which("uv") is not None
    checks.append(("uv installed", uv_ok, shutil.which("uv") or "not found"))

    env_path = Path(".env")
    env_ok = env_path.exists()
    env_detail = str(env_path) if env_ok else "not found"
    if env_ok:
        env_text = env_path.read_text(encoding="utf-8")
        has_qwen = "QWEN_API_KEY=" in env_text and "QWEN_API_KEY=your_" not in env_text
        has_dashscope = "DASHSCOPE_API_KEY=" in env_text and "DASHSCOPE_API_KEY=your_" not in env_text
        has_key = has_qwen or has_dashscope
        detail = "QWEN_API_KEY set" if has_qwen else ("DASHSCOPE_API_KEY set" if has_dashscope else "placeholder or missing")
        checks.append(("API key set", has_key, detail))
    else:
        checks.append(("QWEN_API_KEY set", False, "no .env file"))

    lock_ok = Path("uv.lock").exists()
    checks.append(("uv.lock exists", lock_ok, "uv.lock" if lock_ok else "not found"))

    import_ok = False
    import_detail = ""
    try:
        import agentos
        import agentos.cli.main
        import_ok = True
        import_detail = "ok"
    except ImportError as e:
        import_detail = str(e)
    checks.append(("Import agentos", import_ok, import_detail))

    if py_ok and env_ok:
        api_ok = False
        api_detail = "skipped"
        try:
            env_text = env_path.read_text(encoding="utf-8")
            key = ""
            for line in env_text.splitlines():
                if line.startswith("QWEN_API_KEY="):
                    candidate = line.split("=", 1)[1].strip()
                    if candidate and not candidate.startswith("your_"):
                        key = candidate
                    break
            if not key:
                for line in env_text.splitlines():
                    if line.startswith("DASHSCOPE_API_KEY="):
                        candidate = line.split("=", 1)[1].strip()
                        if candidate and not candidate.startswith("your_"):
                            key = candidate
                        break
            if key:
                import httpx
                base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                for line2 in env_text.splitlines():
                    if line2.startswith("QWEN_BASE_URL="):
                        base_url = line2.split("=", 1)[1].strip()
                        break
                resp = httpx.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                api_ok = resp.status_code == 200
                api_detail = f"HTTP {resp.status_code}"
            else:
                api_detail = "placeholder key"
        except Exception as e:
            api_detail = str(e)
        checks.append(("Qwen API reachable", api_ok, api_detail))

    table = Table(title="Aki Health Check")
    table.add_column("Check", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Detail", style="dim")

    for name, ok, detail in checks:
        status = "[green]✅[/green]" if ok else "[red]❌[/red]"
        table.add_row(name, status, detail)

    console.print(table)

    all_ok = all(ok for _, ok, _ in checks)
    if all_ok:
        console.print("\n[green]All checks passed.[/green]")
    else:
        console.print("\n[yellow]Some checks failed. See above for details.[/yellow]")


@cockpit_app.callback(invoke_without_command=True)
def cockpit_callback(
    ctx: typer.Context,
    path: Optional[Path] = typer.Option(None, "--path", help="Project path to open in the cockpit"),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Open the interactive drill-down navigation loop"
    ),
):
    """Open the cockpit overview for the resolved project."""
    resolved = resolve_project_ref(path)
    ctx.obj = {"project": resolved, "path": path}
    if ctx.invoked_subcommand is None:
        if resolved is None:
            render_projects_browse(
                console,
                current_path=(path or Path.cwd()).resolve(),
                reason="The requested path is not a recognizable project root.",
            )
            return
        if interactive:
            exit_code = run_cockpit_loop(console, resolved)
            raise typer.Exit(exit_code)
        render_cockpit_overview(console, resolved)


def _require_cockpit_project(ctx: typer.Context):
    project = (ctx.obj or {}).get("project")
    if project is None:
        render_projects_browse(
            console,
            current_path=((ctx.obj or {}).get("path") or Path.cwd()).resolve(),
            reason="The requested path is not a recognizable project root.",
        )
        raise typer.Exit(0)
    return project


@cockpit_app.command("action")
def cockpit_action(ctx: typer.Context):
    """Show Action Required drill-down."""
    render_cockpit_detail(console, _require_cockpit_project(ctx), "action")


@cockpit_app.command("health")
def cockpit_health(ctx: typer.Context):
    """Show Project Health drill-down."""
    render_cockpit_detail(console, _require_cockpit_project(ctx), "health")


@cockpit_app.command("memory")
def cockpit_memory(ctx: typer.Context):
    """Show Memory drill-down."""
    render_cockpit_detail(console, _require_cockpit_project(ctx), "memory")


@cockpit_app.command("sdd")
def cockpit_sdd(ctx: typer.Context):
    """Show SDD drill-down."""
    render_cockpit_detail(console, _require_cockpit_project(ctx), "sdd")


@projects_app.command("browse")
def projects_browse(
    filter_query: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter by key or root-path substring"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip the select-to-open prompt"),
):
    """List known projects from the registry, with search/filter and select-to-open."""
    projects = list_projects()

    if not projects:
        console.print(Panel(
            "No known projects yet.\n"
            "Open a project with [cyan]aki cockpit --path /path/to/project[/cyan] "
            "or [cyan]cd[/cyan] into it and run [cyan]aki[/cyan] to register it.",
            title="Projects Browse — Onboarding",
            border_style="yellow",
        ))
        return

    if filter_query:
        needle = filter_query.lower()
        filtered = [
            record for record in projects
            if needle in record.key.lower() or needle in record.root_path.lower()
        ]
    else:
        filtered = projects

    if filter_query and not filtered:
        console.print(f"[yellow]No projects match filter '{filter_query}'.[/yellow]")
        return

    rows = []
    for record in filtered:
        root = Path(record.root_path)
        git_summary = _collect_git_summary(root)
        sdd_summary = _build_sdd_summary(root)
        rows.append((record, git_summary, sdd_summary))

    table = Table(title="Known Projects")
    table.add_column("#", style="dim")
    table.add_column("Key", style="cyan", overflow="fold")
    table.add_column("Root Path", style="white", overflow="fold")
    table.add_column("Branch", style="yellow")
    table.add_column("Git", style="yellow")
    table.add_column("SDD", style="magenta")
    table.add_column("Last Memory Activity", style="dim")
    table.add_column("Last Audit", style="dim")

    for index, (record, git_summary, sdd_summary) in enumerate(rows, start=1):
        dirty_state = (
            "dirty" if git_summary.is_dirty
            else ("clean" if git_summary.is_dirty is False else "unknown")
        )
        table.add_row(
            str(index),
            record.key,
            record.root_path,
            git_summary.branch or "unknown",
            dirty_state,
            sdd_summary.completeness,
            _format_timestamp(record.last_memory_activity_at),
            _format_timestamp(record.last_audit_at),
        )

    console.print(table)

    if no_interactive:
        return

    choice = Prompt.ask("Select a project number to open (or press Enter to skip)", default="")
    if not choice.strip():
        return

    try:
        selected_index = int(choice.strip()) - 1
    except ValueError:
        console.print("[yellow]Invalid selection.[/yellow]")
        return

    if not (0 <= selected_index < len(rows)):
        console.print("[yellow]Invalid selection.[/yellow]")
        return

    selected_record = rows[selected_index][0]
    project_ref = resolve_project_ref(Path(selected_record.root_path))
    if project_ref is None:
        console.print(f"[red]Could not resolve project at {selected_record.root_path}.[/red]")
        return
    render_cockpit_overview(console, project_ref)


def _resolve_audit_project_ref(project: str):
    """Resolve a CLI-supplied project argument (registry key or filesystem path)."""
    for record in list_projects():
        if record.key == project:
            return resolve_project_ref(Path(record.root_path))
    candidate_path = Path(project).expanduser()
    if candidate_path.exists():
        return resolve_project_ref(candidate_path)
    return None


@app.command("audit")
def audit_project(
    project: str = typer.Argument(..., help="Project key (from the registry) or filesystem path to audit"),
):
    """Run the read-only audit engine and generate a durable report (docs/audits/...)."""
    project_ref = _resolve_audit_project_ref(project)
    if project_ref is None:
        console.print(f"[red]project resolution failure: could not resolve project '{project}'[/red]")
        raise typer.Exit(1)

    generated_at = datetime.now()
    ctx = AuditContext(project=project_ref, root_path=project_ref.root_path, generated_at=generated_at)
    pass_results = run_registered_passes(ctx, PASS_REGISTRY)
    findings = merge_findings(pass_results)

    outcome = persist_audit(project_ref.root_path, project_ref.key, generated_at, findings)
    if not outcome.success:
        console.print(f"[red]{outcome.failed_stage}[/red]")
        if outcome.report_path is not None:
            console.print(f"[yellow]Partial artifact preserved at {outcome.report_path}[/yellow]")
        raise typer.Exit(1)

    registry.touch_last_audit(project_ref.root_path)
    console.print(f"[green]✓[/green] Audit report written to {outcome.report_path}")


def _print_interactive_header(agent: "AgentOS", project: str, session_id: str):
    console.print(Panel.fit(
        f"[bold cyan]Aki Interactive[/bold cyan]\n"
        f"Project: [yellow]{project}[/yellow] | Session: [dim]{session_id}[/dim]\n"
        f"Type 'exit' or 'quit' to leave, '/help' for commands",
        border_style="cyan",
    ))

    sdd_status = detect_sdd_artifacts()
    console.print(Panel(
        sdd_status.summary(),
        title="SDD Status",
        border_style="green" if sdd_status.has_sdd else "dim",
    ))

    try:
        context = asyncio.run(agent.recall("", project))
        if context.facts:
            facts_text = "\n".join(
                f"  [cyan]{f.key}[/cyan] = {f.value[:60]}"
                for f in context.facts[:5]
            )
            console.print(Panel(facts_text, title="Memory Context", border_style="blue"))
        else:
            console.print(Panel("[dim]No memories yet[/dim]", title="Memory Context", border_style="dim"))
    except Exception:
        console.print(Panel("[dim]Could not load memory[/dim]", title="Memory Context", border_style="dim"))

    try:
        registry = get_skill_registry()
        enabled_skills = registry.list(enabled_only=True)
        if enabled_skills:
            skills_text = "\n".join(
                f"  [green]{s.name}[/green]: {', '.join(s.functions)}"
                for s in enabled_skills
            )
            console.print(Panel(skills_text, title="Available Skills", border_style="green"))
    except Exception:
        pass


@app.command("sdd-init")
def sdd_init(
    project_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Project directory (default: cwd)"),
):
    """Initialize SDD directory structure for the current project."""
    target = project_dir or Path.cwd()
    sdd_dir, created = init_sdd_project(target)

    console.print(Panel.fit(
        f"[bold green]SDD initialized[/bold green]\n"
        f"Directory: [cyan]{sdd_dir}[/cyan]",
        border_style="green",
    ))

    if created:
        table = Table(title="Created Templates")
        table.add_column("File", style="cyan")
        table.add_column("Status", style="green")
        for f in created:
            table.add_row(f, "created")
        console.print(table)
    else:
        console.print("[dim]All template files already exist.[/dim]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Edit [cyan]docs/sdd/proposal.md[/cyan] with your change intent")
    console.print("  2. Define requirements in [cyan]docs/sdd/spec.md[/cyan]")
    console.print("  3. Document design decisions in [cyan]docs/sdd/design.md[/cyan]")
    console.print("  4. Break work into tasks in [cyan]docs/sdd/tasks.md[/cyan]")


async def _async_interactive(agent, project, session_id):
    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")
            if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                console.print("[dim]Goodbye![/dim]")
                break
            if user_input.lower() in ("/help", "help"):
                _show_help()
                continue
            if user_input.startswith("/"):
                _handle_command(user_input, agent, project, session_id)
                continue

            response = await agent.chat(user_input, project, session_id)
            console.print(Markdown(f"**Agent:** {response}"))

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted[/dim]")
            break
        except EOFError:
            break


@app.command()
def remember(
    content: str = typer.Argument(..., help="Content to remember"),
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    type: str = typer.Option("user_preference", "--type", "-t", help="Event type"),
):
    """Explicitly store a memory."""
    agent = _get_agent()

    async def run():
        event = await agent.remember(content, project, EventType(type))
        console.print(f"[green]✓[/green] Remembered: {event.id}")

    asyncio.run(run())


@app.command()
def recall(
    query: str = typer.Argument(..., help="Search query"),
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
):
    """Search memory."""
    agent = _get_agent()

    async def run():
        context = await agent.recall(query, project)
        _print_context(context, limit)

    asyncio.run(run())


@app.command()
def facts(
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
):
    """List all facts for a project."""
    agent = _get_agent()

    async def run():
        fact_list = await agent.get_facts(project)
        if not fact_list:
            console.print("[dim]No facts found[/dim]")
            return

        table = Table(title=f"Facts for {project}")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        table.add_column("Confidence", style="green")
        table.add_column("Scope", style="dim")

        for fact in fact_list:
            table.add_row(fact.key, fact.value[:80], f"{fact.confidence:.2f}", fact.scope)

        console.print(table)

    asyncio.run(run())


@app.command()
def set_fact(
    key: str = typer.Argument(..., help="Fact key"),
    value: str = typer.Argument(..., help="Fact value"),
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    confidence: float = typer.Option(1.0, "--confidence", "-c", help="Confidence (0-1)"),
):
    """Set a fact manually."""
    agent = _get_agent()

    async def run():
        await agent.set_fact(key, value, project, confidence)
        console.print(f"[green]✓[/green] Fact set: {key} = {value}")

    asyncio.run(run())


@app.command()
def skills(
    enabled_only: bool = typer.Option(True, "--enabled-only/--all", help="Show only enabled skills"),
):
    """List available skills."""
    load_skills()
    registry = get_skill_registry()
    skill_list = registry.list(enabled_only=enabled_only)

    if not skill_list:
        console.print("[dim]No skills registered[/dim]")
        return

    table = Table(title="Available Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Functions", style="green")
    table.add_column("Enabled", style="yellow")

    for skill in skill_list:
        table.add_row(
            skill.name,
            skill.description,
            ", ".join(skill.functions),
            "✓" if skill.enabled else "✗",
        )

    console.print(table)


@app.command()
def config_show():
    """Show current configuration."""
    config = get_config()
    console.print(Markdown(f"""```yaml
qwen:
  model: {config.qwen.model}
  base_url: {config.qwen.base_url}
  embedding_model: {config.qwen.embedding_model}
memory:
  db_path: {config.memory.db_path}
  chroma_path: {config.memory.chroma_path}
  embedding_model: {config.memory.embedding_model}
skills:
  enabled: {config.skills.enabled}
```"""))


def _show_help():
    console.print(Panel("""
[bold]Commands:[/bold]
  /help           - Show this help
  /memory         - Show recent memory
  /facts          - Show facts for current project
  /skills         - List skills
  /sdd            - Show SDD artifact status
  /clear          - Clear screen
  exit/quit       - Exit
""", title="Help", border_style="blue"))


def _handle_command(cmd: str, agent: "AgentOS", project: str, session_id: str):
    if cmd == "/memory":
        asyncio.run(_show_memory(agent, project))
    elif cmd == "/facts":
        asyncio.run(_show_facts(agent, project))
    elif cmd == "/skills":
        asyncio.run(_show_skills())
    elif cmd == "/sdd":
        _show_sdd_status()
    elif cmd == "/clear":
        console.clear()
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")


async def _show_memory(agent: "AgentOS", project: str):
    context = await agent.recall("", project)
    _print_context(context, 20)


async def _show_facts(agent: "AgentOS", project: str):
    facts = await agent.get_facts(project)
    if not facts:
        console.print("[dim]No facts[/dim]")
        return
    table = Table(title=f"Facts: {project}")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Confidence", style="green")
    for f in facts:
        table.add_row(f.key, f.value[:80], f"{f.confidence:.2f}")
    console.print(table)


async def _show_skills():
    registry = get_skill_registry()
    skills = registry.list()
    table = Table(title="Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Functions", style="green")
    for s in skills:
        table.add_row(s.name, s.description, ", ".join(s.functions))
    console.print(table)


def _show_sdd_status():
    status = detect_sdd_artifacts()
    if not status.has_sdd:
        console.print(Panel(
            "[yellow]No SDD artifacts found in this project.[/yellow]\n"
            "Run [bold]aki sdd-init[/bold] to create the SDD structure.",
            title="SDD Status",
            border_style="yellow",
        ))
        return

    table = Table(title=f"SDD Artifacts ({status.sdd_dir})")
    table.add_column("Artifact", style="cyan")
    table.add_column("Status", style="bold")

    for artifact in ("proposal.md", "spec.md", "design.md", "tasks.md"):
        if artifact in status.found_artifacts:
            table.add_row(artifact, "[green]present[/green]")
        else:
            table.add_row(artifact, "[dim]missing[/dim]")

    console.print(table)


def _print_context(context, limit: int):
    if context.facts:
        console.print("\n[bold cyan]Facts:[/bold cyan]")
        for f in context.facts[:limit]:
            console.print(f"  [dim]{f.scope}[/dim] [cyan]{f.key}[/cyan] = {f.value} ([green]{f.confidence:.2f}[/green])")

    if context.events:
        console.print("\n[bold cyan]Recent Events:[/bold cyan]")
        for e in context.events[:limit]:
            console.print(f"  [dim]{e.timestamp:%H:%M}[/dim] [{e.type.value}] {e.project}: {e.content[:100]}")

    if context.skills:
        console.print("\n[bold cyan]Skills:[/bold cyan]")
        for s in context.skills:
            if s.enabled:
                console.print(f"  [green]{s.name}[/green]: {', '.join(s.functions)}")


if __name__ == "__main__":
    app()
