"""CLI entry point for Aki."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentos.agents import ProfileNotFoundError
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
from agentos.mcp.project import detect_project
from agentos.cli.update import (
    UpdateError,
    locate_installed_source_dir,
    resolve_uv_binary,
    run_update_command,
    validate_source_checkout,
)
from agentos.cockpit.navigation import run_cockpit_loop
from agentos.cockpit import registry
from agentos.cockpit.registry import list_projects

try:
    from agentos.cockpit.web.app import run_server
    from agentos.cockpit.web.settings import WebServerSettings
except ImportError:  # pragma: no cover - exercised only without `web` extras installed
    run_server = None  # type: ignore[assignment]
    WebServerSettings = None  # type: ignore[assignment,misc]
from agentos.cockpit.audit.base import AuditContext, merge_findings, run_registered_passes
from agentos.cockpit.audit.passes import PASS_REGISTRY
from agentos.cockpit.audit.report import persist_audit
from agentos.core.config import (
    _find_project_config_yaml,
    _global_home,
    get_config,
    get_env_provenance,
    reset_config,
)
from agentos.memory.models import EventType
from agentos.skills.base import get_skill_registry
from agentos.skills import load_skills
from agentos.sdd.detector import detect_sdd_artifacts, summarize_sdd_context
from agentos.sdd.init import init_sdd_project

if TYPE_CHECKING:
    from agentos.agent.core import AgentOS
    from agentos.agents import AgentProfile

def run_async_cmd(coro):
    async def wrapper():
        try:
            return await coro
        finally:
            from agentos.qwen.client import close_qwen_client
            await close_qwen_client()
    return asyncio.run(wrapper())


app = typer.Typer(
    name="aki",
    help="Aki - AI agent with portable project memory",
    add_completion=False,
)
cockpit_app = typer.Typer(help="Open the operational cockpit for a project.")
projects_app = typer.Typer(help="Browse projects when current context is unclear.")
config_app = typer.Typer(help="Manage the global Aki config home (~/.aki/).")
app.add_typer(cockpit_app, name="cockpit")
app.add_typer(projects_app, name="projects")
app.add_typer(config_app, name="config")
console = Console()
logger = logging.getLogger(__name__)


class LazyFileHandler(logging.FileHandler):
    """FileHandler that delays directory and file creation until the first write."""
    def __init__(self, filename: Path | str, mode: str = "a", encoding: Optional[str] = "utf-8", delay: bool = True):
        super().__init__(filename, mode, encoding, delay=True)

    def _open(self):
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        return super()._open()


def _configure_logging(verbose: bool) -> None:
    """Route logs to a file by default so tracebacks never leak to the terminal."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    log_dir = _global_home() / "logs"
    file_handler = LazyFileHandler(log_dir / "aki.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.handlers.clear()
    root.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        root.addHandler(stream_handler)


def _friendly_turn_error(exc: Exception) -> str:
    """Map low-level exceptions to a short, actionable message for the user."""
    import httpx

    if isinstance(exc, httpx.TimeoutException) or type(exc).__name__ == "APITimeoutError":
        return "Qwen no respondió a tiempo (timeout). Probá de nuevo o revisá tu conexión."
    if isinstance(exc, httpx.ConnectError):
        return "No se pudo conectar con Qwen. Verificá tu conexión a internet o el estado del servicio."
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "Qwen rechazó la API key (401). Revisá QWEN_API_KEY / DASHSCOPE_API_KEY."
        if status == 429:
            return "Límite de uso de Qwen alcanzado (429). Esperá un momento y reintentá."
        return f"Qwen devolvió un error HTTP {status}."
    return str(exc)


def _format_status(message: str) -> str:
    return f"[bold cyan]{message}...[/bold cyan]"


def safe_status(console_obj, message: str, spinner: str = "dots"):
    try:
        return console_obj.status(message, spinner=spinner)
    except TypeError:
        return console_obj.status(message)


def ask_selection(question: str, options: list[str], default: str = "") -> str:
    """Display options in a beautiful Panel and ask user to choose."""
    lines = []
    for i, opt in enumerate(options, 1):
        indicator = "▶" if (opt == default or str(i) == default) else " "
        lines.append(f"  {indicator} [[bold cyan]{i}[/bold cyan]] {opt}")

    panel = Panel(
        "\n".join(lines),
        title=f"[bold magenta]{question}[/bold magenta]",
        border_style="cyan",
        expand=False
    )
    console.print(panel)

    valid_choices = [str(i) for i in range(1, len(options) + 1)]
    if default is not None:
        valid_choices.append("")

    while True:
        choice = Prompt.ask(f"Select option [1-{len(options)}] (or press Enter to skip)", default=default or "")
        if choice.strip() in valid_choices:
            return choice.strip()
        console.print("[red]Invalid choice. Please select a valid option.[/red]")


def _get_agent():
    from agentos.agent.core import get_agent

    return get_agent()


def _resolve_cli_profile(agent: "AgentOS", profile_id: Optional[str]) -> "AgentProfile | None":
    """Resolve a CLI-selected profile before starting an agent turn."""
    if profile_id is None:
        return None
    try:
        return agent.agent_registry.resolve(profile_id)
    except ProfileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def _profile_summary(profile: "AgentProfile | None") -> str:
    if profile is None:
        return "[dim]default[/dim]"
    return f"[cyan]{profile.name}[/cyan] ([dim]{profile.id}[/dim])"


def _print_profile_header(profile: "AgentProfile | None") -> None:
    if profile is not None:
        console.print(f"[bold]Agent profile:[/bold] {_profile_summary(profile)}")


def _memory():
    """Return a memory accessor usable for session resolution (last_session reads)."""
    from agentos.memory.repository import MemoryRepository

    return MemoryRepository()


def _resolve_session_id(
    project: str,
    memory,
    session: Optional[str],
    new_session: bool,
) -> str:
    """Resolve the session_id per the design.md section 5 resolution order.

    1. Explicit `session` wins unconditionally.
    2. `new_session=True` mints a fresh id, ignoring any stored pointer.
    3. Otherwise, resume the durable `session:last` fact if present.
    4. Otherwise, mint a fresh id.

    NOTE: this CLI-side helper only READS `session:last` (via
    `MemoryRepository.get_last_session`). The WRITE authority lives in
    `AgentOS.chat()` (Phase 2 / PR #2), which upserts `session:last` on every
    turn via `touch_last_session`. Phase 1 ships read-only resolution here so
    the flag/escape-hatch behavior is fully correct even before the write
    path exists.
    """
    if session:
        return session
    if not new_session:
        last = memory.get_last_session(project)
        if last:
            return last
    return f"sess_{__import__('uuid').uuid4().hex[:8]}"


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Aki is an AI agent with persistent cross-session project memory."""
    reset_config()
    get_config(config_path)
    _configure_logging(verbose)
    if ctx.invoked_subcommand is None:
        render_default_entry(console)


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Specialized agent profile id"),
    new_session: bool = typer.Option(
        False, "--new-session", help="Start a fresh session, bypassing auto-resume"
    ),
    stream: bool = typer.Option(False, "--stream", help="Stream response"),
):
    """Chat with Aki."""
    project = detect_project(project)
    session = _resolve_session_id(project, _memory(), session, new_session)
    with safe_status(console, _format_status("Loading memory engine"), spinner="clock"):
        agent = _get_agent()
    selected_profile = _resolve_cli_profile(agent, profile)
    _print_profile_header(selected_profile)

    async def run():
        response = ""

        with safe_status(console, _format_status("Collecting project context"), spinner="earth") as status:
            def update_status(message: str) -> None:
                status.update(_format_status(message))

            if stream:
                async for chunk in agent.stream_chat(
                    message,
                    project,
                    session,
                    status_callback=update_status,
                    profile_id=profile,
                ):
                    console.print(chunk, end="")
            else:
                response = await agent.chat(
                    message,
                    project,
                    session,
                    status_callback=update_status,
                    profile_id=profile,
                )

        if stream:
            console.print()
        else:
            console.print(Markdown(response))

    run_async_cmd(run())


@app.command()
def interactive(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Specialized agent profile id"),
    new_session: bool = typer.Option(
        False, "--new-session", help="Start a fresh session, bypassing auto-resume"
    ),
):
    """Start interactive chat session."""
    project = detect_project(project)
    with safe_status(console, _format_status("Loading memory engine"), spinner="clock"):
        agent = _get_agent()
    selected_profile = _resolve_cli_profile(agent, profile)
    session_id = _resolve_session_id(project, _memory(), session, new_session)

    _print_interactive_header(agent, project, session_id, selected_profile)

    sdd_status = detect_sdd_artifacts()
    if not sdd_status.has_sdd:
        console.print(Panel(
            "[yellow]This project doesn't have SDD artifacts yet.[/yellow]\n"
            "Run [bold]aki sdd-init[/bold] to initialize SDD for this project.",
            title="SDD Detection",
            border_style="yellow",
        ))

    run_async_cmd(_async_interactive(agent, project, session_id, profile_id=profile))


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


def _is_real_key(candidate: str) -> bool:
    candidate = candidate.strip()
    return bool(candidate) and not candidate.startswith("your_")


def _resolve_global_api_key() -> tuple[str, str]:
    """Resolve the Qwen API key: process env -> ~/.aki/.env -> project .env.

    Returns (key, detail). Precedence per var source: QWEN_API_KEY then
    DASHSCOPE_API_KEY. Placeholder values (empty or prefixed with "your_")
    are ignored. The detail never contains the key value.

    NOTE: the Typer callback always calls resolve_config()/get_config() before
    any command body runs, which loads project/global .env files via
    load_dotenv(override=False) — this WRITES previously-unset keys into
    os.environ as a side effect even though override=False. So a key that
    lives only in ~/.aki/.env (never exported by the user's shell) shows up
    in os.environ by the time this function runs. We consult
    get_env_provenance()'s "real" snapshot (captured BEFORE any dotenv load
    in the most recent resolve_config() call) to tell a genuine shell env var
    apart from one merely populated by dotenv loading, so the reported source
    label is accurate.
    """
    from dotenv import dotenv_values

    provenance = get_env_provenance()
    real_keys = provenance["real"] if provenance is not None else None
    dotenv_keys = (
        (provenance["project"] | provenance["global"]) if provenance is not None else frozenset()
    )

    for var_name in ("QWEN_API_KEY", "DASHSCOPE_API_KEY"):
        candidate = os.environ.get(var_name, "")
        if not _is_real_key(candidate):
            continue
        # Provenance can go stale relative to the *current* os.environ (e.g. a
        # caller mutates os.environ after the last resolve_config() call, or
        # calls this function directly without ever calling resolve_config()
        # in this process). We must not let a stale snapshot cause us to
        # silently drop a genuinely real key, so the unsafe direction (real
        # key -> reported as absent) is avoided: a var only gets treated as
        # dotenv-sourced when it is positively known to have been written by
        # a project/global .env load in the most recent resolve_config()
        # call. If the snapshot doesn't know about this var at all (no
        # provenance captured yet, or the var predates/postdates that
        # snapshot), we default to trusting it as a real shell env var
        # instead of guessing it came from a file.
        if real_keys is not None and var_name not in real_keys and var_name in dotenv_keys:
            # Positively known to have been written into os.environ only by
            # dotenv loading in the most recent resolve_config() call. Fall
            # through to file-based checks below so the source is
            # attributed correctly.
            continue
        return candidate.strip(), f"{var_name} set in shell env"

    global_env_path = _global_home() / ".env"
    if global_env_path.is_file():
        values = dotenv_values(global_env_path)
        for var_name in ("QWEN_API_KEY", "DASHSCOPE_API_KEY"):
            candidate = values.get(var_name) or ""
            if _is_real_key(candidate):
                return candidate.strip(), f"found in {global_env_path}"

    project_env_path = _find_project_env_path()
    if project_env_path is not None:
        values = dotenv_values(project_env_path)
        for var_name in ("QWEN_API_KEY", "DASHSCOPE_API_KEY"):
            candidate = values.get(var_name) or ""
            if _is_real_key(candidate):
                return candidate.strip(), f"found in {project_env_path}"

    return "", "not set (set QWEN_API_KEY or DASHSCOPE_API_KEY, or run `aki config init`)"


def _find_project_env_path() -> Optional[Path]:
    from agentos.core.config import _iter_env_search_roots

    for root in _iter_env_search_roots():
        candidate = root / ".env"
        if candidate.is_file():
            return candidate
    return None


def _do_doctor() -> list[tuple[str, bool, str]]:
    """Run all health checks, print the report, and return the raw checks.

    Shared by `aki doctor` and `aki setup` so both present identical output.
    """
    checks: list[tuple[str, bool, str]] = []

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python >= 3.11", py_ok, py_version))

    uv_ok = shutil.which("uv") is not None
    checks.append(("uv installed", uv_ok, shutil.which("uv") or "not found"))

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

    key, key_detail = _resolve_global_api_key()
    checks.append(("API key configured", bool(key), key_detail))

    if py_ok and key:
        api_ok = False
        api_detail = "skipped"
        try:
            import httpx

            base_url = os.environ.get("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
            resp = httpx.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            api_ok = resp.status_code == 200
            api_detail = f"HTTP {resp.status_code}"
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

    if not Path("uv.lock").exists():
        console.print(
            "[dim]Project context not detected "
            "(run inside the Aki repo for project checks — see `aki audit`).[/dim]"
        )

    project_config_path = _find_project_config_yaml()
    if project_config_path is not None:
        console.print(f"[dim]Project-local config detected: {project_config_path}[/dim]")

    return checks


@app.command()
def doctor():
    """Check Aki installation health (global-only; independent of CWD)."""
    _do_doctor()


def _do_config_init(
    qwen_api_key: Optional[str] = None,
    dashscope_api_key: Optional[str] = None,
    model: Optional[str] = None,
    embedding_model: Optional[str] = None,
    base_url: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Bootstrap the global Aki config home at ~/.aki/ (.env + config.yaml).

    Shared by `aki config init` and `aki setup`. Raises `typer.Exit(1)` when
    no API key was provided and stdin is not interactive.
    """
    home = _global_home()

    if qwen_api_key is None and dashscope_api_key is None:
        if sys.stdin.isatty():
            qwen_api_key = Prompt.ask("Qwen API key (QWEN_API_KEY)", default="")
        else:
            console.print(
                "[red]Missing required value: --qwen-api-key (or --dashscope-api-key), "
                "and stdin is not interactive.[/red]"
            )
            raise typer.Exit(1)

    env_lines: list[str] = []
    if qwen_api_key:
        env_lines.append(f"QWEN_API_KEY={qwen_api_key}")
    if dashscope_api_key:
        env_lines.append(f"DASHSCOPE_API_KEY={dashscope_api_key}")

    yaml_data: dict = {}
    qwen_yaml: dict = {}
    if model:
        qwen_yaml["model"] = model
    if embedding_model:
        qwen_yaml["embedding_model"] = embedding_model
    if base_url:
        qwen_yaml["base_url"] = base_url
    if qwen_yaml:
        yaml_data["qwen"] = qwen_yaml

    env_path = home / ".env"
    yaml_path = home / "config.yaml"

    if dry_run:
        console.print(f"[bold]Dry run — global config home: {home}[/bold]")
        if env_lines:
            console.print(f"Would write {env_path}:")
            console.print("\n".join(env_lines))
        if yaml_data:
            console.print(f"Would write {yaml_path}:")
            console.print(yaml.safe_dump(yaml_data, default_flow_style=False))
        return

    home.mkdir(parents=True, exist_ok=True)

    if env_lines:
        if env_path.exists():
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            backup_path = env_path.parent / f".env.backup.{timestamp}"
            shutil.copy2(env_path, backup_path)
            console.print(f"[green]✓[/green] Backup created: {backup_path}")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        console.print(f"[green]✓[/green] Wrote {env_path}")

    if yaml_data:
        if yaml_path.exists():
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            backup_path = yaml_path.with_suffix(f".backup.{timestamp}")
            shutil.copy2(yaml_path, backup_path)
            console.print(f"[green]✓[/green] Backup created: {backup_path}")
        yaml_path.write_text(yaml.safe_dump(yaml_data, default_flow_style=False), encoding="utf-8")
        console.print(f"[green]✓[/green] Wrote {yaml_path}")

    console.print(f"[green]✓[/green] Global config initialized at {home}")


@config_app.command("init")
def config_init(
    qwen_api_key: Optional[str] = typer.Option(None, "--qwen-api-key", help="Qwen Cloud API key"),
    dashscope_api_key: Optional[str] = typer.Option(None, "--dashscope-api-key", help="DashScope API key"),
    model: Optional[str] = typer.Option(None, "--model", help="Default Qwen model"),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model", help="Default embedding model"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Qwen-compatible API base URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen without writing files"),
):
    """Bootstrap the global Aki config home at ~/.aki/ (.env + config.yaml)."""
    _do_config_init(
        qwen_api_key=qwen_api_key,
        dashscope_api_key=dashscope_api_key,
        model=model,
        embedding_model=embedding_model,
        base_url=base_url,
        dry_run=dry_run,
    )


_ESSENTIAL_DOCTOR_CHECKS = {"Python >= 3.11", "uv installed", "Import agentos"}


@app.command("setup")
def setup():
    """One command to go from a fresh clone to a working Aki install.

    Chains `config init` (writes ~/.aki/.env + config.yaml, idempotent with
    backups) and `doctor` (verifies the result). Safe to re-run.
    """
    console.print(
        Panel.fit(
            "[bold cyan]Aki Setup[/bold cyan]\n"
            "Bootstrapping your global config and verifying the install.",
            border_style="cyan",
        )
    )

    key, _ = _resolve_global_api_key()
    if key:
        console.print("[green]✓[/green] Qwen API key already configured — skipping `config init` prompt.")
    else:
        console.print("[cyan]No Qwen API key found — running `config init`...[/cyan]")
        try:
            _do_config_init()
        except typer.Exit as exc:
            if exc.exit_code != 0:
                console.print(
                    "[yellow]⚠[/yellow] Skipped Qwen API key setup (no interactive terminal and no key "
                    "provided).\n[dim]Core memory/agent tools still work without it. Run "
                    "`aki config init --qwen-api-key <key>` later to enable Qwen features.[/dim]"
                )

    console.print("\n[bold]Verifying installation...[/bold]")
    checks = _do_doctor()

    key, key_detail = _resolve_global_api_key()
    qwen_configured = bool(key)
    essential_ok = all(ok for name, ok, _ in checks if name in _ESSENTIAL_DOCTOR_CHECKS)

    console.print("\n[bold]Setup summary[/bold]")
    console.print(f"  Global config home: [cyan]{_global_home()}[/cyan]")
    if qwen_configured:
        console.print("  Qwen configured: [green]yes[/green]")
    else:
        console.print(f"  Qwen configured: [yellow]no[/yellow] ({key_detail})")
    console.print(
        f"  Install healthy: {'[green]yes[/green]' if essential_ok else '[red]no — see checks above[/red]'}"
    )

    console.print(
        "\n[bold]Next steps[/bold]\n"
        "  • Register Aki with your coding host's MCP config: "
        "[cyan]aki mcp-setup <claude-code|opencode>[/cyan]\n"
        "  • Start chatting: [cyan]aki chat[/cyan]\n"
        "  • Open the cockpit: [cyan]aki cockpit[/cyan]"
    )

    if not essential_ok:
        raise typer.Exit(1)


@app.command()
def update():
    """Update the Aki installation from its source checkout."""
    source_dir = locate_installed_source_dir()
    if source_dir is None:
        console.print(
            "[red]Aki does not appear to be installed from a source checkout.[/red]\n"
            "[yellow]`aki update` only works for Linux/macOS installs backed by a cloned "
            "repository. Re-clone the repo and install from source if you need this command.[/yellow]"
        )
        raise typer.Exit(1)

    try:
        source_dir = validate_source_checkout(source_dir)
        uv_bin = resolve_uv_binary()

        console.print(f"[cyan]Updating Aki from {source_dir}[/cyan]")

        console.print("[cyan]Pulling latest changes with git pull...[/cyan]")
        run_update_command(
            ["git", "pull"],
            cwd=source_dir,
            missing_message="git is required to update Aki but was not found in PATH.",
            failure_message="git pull failed",
        )

        console.print("[cyan]Syncing dependencies with uv sync --all-extras...[/cyan]")
        run_update_command(
            [uv_bin, "sync", "--all-extras"],
            cwd=source_dir,
            missing_message="uv is required to update Aki but was not found.",
            failure_message="uv sync --all-extras failed",
        )

        console.print("[cyan]Refreshing the global aki tool shim...[/cyan]")
        run_update_command(
            [uv_bin, "tool", "install", "--editable", ".[web]", "--force"],
            cwd=source_dir,
            missing_message="uv is required to refresh the Aki tool install but was not found.",
            failure_message="uv tool install --editable .[web] --force failed",
        )
    except UpdateError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print("[green]✓[/green] Aki updated successfully.")


@cockpit_app.callback(invoke_without_command=True)
def cockpit_callback(
    ctx: typer.Context,
    path: Optional[Path] = typer.Option(None, "--path", help="Project path to open in the cockpit"),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Open the interactive drill-down navigation loop"
    ),
    web: bool = typer.Option(False, "--web", help="Serve a read-only cockpit over HTTP"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the web cockpit server"),
    port: int = typer.Option(8420, "--port", help="Port for the web cockpit server"),
):
    """Open the cockpit overview for the resolved project."""
    resolved = resolve_project_ref(path)
    ctx.obj = {"project": resolved, "path": path}
    if ctx.invoked_subcommand is None:
        if web:
            if run_server is None or WebServerSettings is None:
                console.print(
                    "[red]The web cockpit requires the `web` extras. "
                    "Install with `pip install '.[web]'` or `uv sync --extra web`.[/red]"
                )
                raise typer.Exit(1)
            try:
                run_server(WebServerSettings(host=host, port=port))
            except OSError as exc:
                console.print(
                    f"[red]Could not start the web cockpit on {host}:{port} — {exc}. "
                    f"Try a different port with --port.[/red]"
                )
                raise typer.Exit(1) from exc
            return
        if resolved is None:
            render_projects_browse(
                console,
                current_path=(path or Path.cwd()).resolve(),
                reason="The requested path is not a recognizable project root.",
            )
            return
        if interactive:
            from agentos.cockpit.tui.app import AkiCockpitApp
            app = AkiCockpitApp(resolved)
            app.run()
            raise typer.Exit(0)
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

    project_options = [f"{record.key} ({record.root_path})" for record, _, _ in rows]
    choice = ask_selection("Select a project to open", project_options, default="")
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
    deep: bool = typer.Option(
        False, "--deep", help="Also run a model-backed deep audit pass (uses tokens, can be slow)"
    ),
):
    """Run the read-only audit engine and generate a durable report (docs/audits/...).

    By default this is fast, local, and deterministic -- no model calls. Pass --deep
    to additionally run a model-backed pass for architectural/semantic findings that
    static checks can't catch. --deep uses API tokens and may take noticeably longer.
    """
    project_ref = _resolve_audit_project_ref(project)
    if project_ref is None:
        console.print(f"[red]project resolution failure: could not resolve project '{project}'[/red]")
        raise typer.Exit(1)

    passes = list(PASS_REGISTRY)
    if deep:
        from agentos.cockpit.audit.deep import DeepAuditPass

        console.print(
            "[yellow]--deep uses the Qwen model (consumes API tokens) and may be noticeably "
            "slower than the standard audit.[/yellow]"
        )
        passes.append(DeepAuditPass())

    generated_at = datetime.now()
    ctx = AuditContext(project=project_ref, root_path=project_ref.root_path, generated_at=generated_at)
    status_cm = safe_status(console, _format_status("Running deep audit pass..."), spinner="aesthetic") if deep else nullcontext()
    with status_cm:
        pass_results = run_registered_passes(ctx, passes)
    findings = merge_findings(pass_results)

    outcome = persist_audit(project_ref.root_path, project_ref.key, generated_at, findings)
    if not outcome.success:
        console.print(f"[red]{outcome.failed_stage}[/red]")
        if outcome.report_path is not None:
            console.print(f"[yellow]Partial artifact preserved at {outcome.report_path}[/yellow]")
        raise typer.Exit(1)

    registry.touch_last_audit(project_ref.root_path)
    console.print(f"[green]✓[/green] Audit report written to {outcome.report_path}")


def _print_interactive_header(
    agent: "AgentOS",
    project: str,
    session_id: str,
    profile: "AgentProfile | None" = None,
):
    console.print(Panel.fit(
        f"[bold cyan]Aki Interactive[/bold cyan]\n"
        f"Project: [yellow]{project}[/yellow] | Session: [dim]{session_id}[/dim]\n"
        f"Profile: {_profile_summary(profile)}\n"
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
        with safe_status(console, _format_status("Collecting project context"), spinner="earth"):
            context = run_async_cmd(agent.recall("", project))
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

    try:
        events = agent.memory.get_session_conversation(session_id)
        if events:
            console.print("\n[bold cyan]— Session Conversation History —[/bold cyan]")
            for event in events:
                role = "[bold green]You:[/bold green]" if event.source == "user" else "[bold cyan]Agent:[/bold cyan]"
                console.print(f"{role} {event.content}")
            console.print("[bold cyan]———————————————————————————————[/bold cyan]\n")
    except Exception as e:
        logger.warning(f"Could not load session conversation history: {e}")


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


@app.command("salvage")
def salvage_project(
    project_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Project directory (default: cwd)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run diagnostics without performing fixes"),
):
    """Diagnose chaos and restore project health.

    This command runs checks for missing config/env files, Git repo state,
    SDD artifacts, test files, and merge conflict markers. It generates
    an 'aki_diagnose.md' report in the project root.
    """
    target = project_dir or Path.cwd()
    
    from agentos.cockpit.salvage.logic import ChaosReport, perform_salvage_fixes
    
    console.print(f"[cyan]Running salvage diagnostics on {target.resolve()}...[/cyan]")
    
    report = ChaosReport(target)
    report.run_diagnosis()
    
    # Render report summary using Rich
    console.print()
    console.print(Panel(
        f"[bold]Aki Salvage Diagnostics Summary[/bold]\n\n"
        f"Git repository: {'[green]Yes[/green]' if report.is_git_repo else '[red]No[/red]'}\n"
        f"SDD directory: {'[green]' + report.sdd_dir + '[/green]' if report.sdd_dir else '[red]Missing[/red]'}\n"
        f"Tests directory: {'[green]Yes[/green]' if report.has_tests_dir else '[red]No[/red]'}\n"
        f"Test files: [cyan]{report.test_files_count}[/cyan]\n"
        f"Config files: config.yaml ({'[green]Yes[/green]' if report.has_config_yaml else '[red]No[/red]'}), .env ({'[green]Yes[/green]' if report.has_env else '[red]No[/red]'})\n"
        f"Conflict markers: {'[red]Yes[/red]' if report.files_with_conflicts else '[green]None[/green]'}",
        title="Diagnostic Check",
        border_style="cyan" if not report.files_with_conflicts else "red",
    ))
    
    # Warn about conflicts immediately if any exist
    if report.files_with_conflicts:
        console.print("\n[bold red]CRITICAL: Git conflict markers detected in the following files:[/bold red]")
        for file in report.files_with_conflicts:
            console.print(f"  - [red]{file}[/red]")
        console.print("[yellow]Please resolve these conflict markers manually.[/yellow]")

    # Write markdown report
    report_file = report.write_report_file()
    console.print(f"\n[green]✓[/green] Written detailed diagnosis report to [cyan]{report_file.name}[/cyan]")
    
    if dry_run:
        console.print("\n[yellow]Dry-run mode: no repairs attempted.[/yellow]")
        return
        
    # Check if there are fixable issues
    has_fixes = not report.has_env or not report.has_config_yaml or (report.is_git_repo and not (target / ".gitignore").is_file())
    if not has_fixes:
        console.print("\n[green]No fixable configuration issues detected.[/green]")
        return
        
    # Ask for confirmation
    confirm = typer.confirm("\nDo you want to automatically apply recommended fixes (e.g. restoring missing configs/gitignore)?", default=True)
    if not confirm:
        console.print("\n[yellow]Salvage fixes cancelled by user.[/yellow]")
        return
        
    fixes = perform_salvage_fixes(report)
    if fixes:
        console.print("\n[bold green]Applied fixes:[/bold green]")
        for fix in fixes:
            console.print(f"  [green]✓[/green] {fix}")
    else:
        console.print("\n[yellow]No fixes were applied.[/yellow]")


async def _async_interactive(agent, project, session_id, profile_id: Optional[str] = None):
    from agentos.skills.scheduler import run_task_dispatcher
    from agentos.memory.repository import MemoryRepository

    async def background_dispatcher():
        repo = MemoryRepository()
        while True:
            try:
                fired = await run_task_dispatcher(repo, print_callback=lambda msg: console.print(f"\n{msg}"))
                if fired > 0:
                    console.print("[bold green]You[/bold green]: ", end="")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background task dispatcher: {e}")
            await asyncio.sleep(5)

    dispatcher_task = asyncio.create_task(background_dispatcher())
    try:
        while True:
            try:
                console.print()
                console.print(Panel(
                    "[dim]Type your message / command and press Enter. To exit type [bold]quit[/bold].[/dim]",
                    title="[bold green]⌨️ You (Aki Chat Input)[/bold green]",
                    border_style="green",
                    expand=True,
                ))
                user_input = Prompt.ask("❯ ")
                if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                if user_input.lower() in ("/help", "help"):
                    _show_help(agent, project, session_id)
                    continue
                if user_input.startswith("/"):
                    await _handle_command(user_input, agent, project, session_id)
                    continue

                with safe_status(console, _format_status("Starting turn"), spinner="dots12") as status:
                    def update_status(message: str) -> None:
                        status.update(_format_status(message))

                    stream = agent.stream_chat(
                        user_input,
                        project,
                        session_id,
                        status_callback=update_status,
                        profile_id=profile_id,
                    )

                    if hasattr(stream, "__aiter__"):
                        started_printing = False
                        async for token in stream:
                            if not started_printing:
                                if hasattr(status, "stop"):
                                    status.stop()
                                console.print("[bold cyan]Agent:[/bold cyan] ", end="")
                                started_printing = True
                            console.print(token, end="")

                        if started_printing:
                            console.print()
                        else:
                            if hasattr(status, "stop"):
                                status.stop()
                            console.print("[bold cyan]Agent:[/bold cyan] (sin respuesta)")
                    else:
                        if hasattr(status, "stop"):
                            status.stop()
                        response = await agent.chat(
                            user_input,
                            project,
                            session_id,
                            status_callback=update_status,
                            profile_id=profile_id,
                        )
                        console.print(Markdown(f"**Agent:** {response}"))

            except KeyboardInterrupt:
                console.print("\n[dim]Interrupted[/dim]")
                break
            except EOFError:
                break
            except Exception as exc:
                logger.exception("Interactive turn failed")
                console.print(f"[red]Turn failed:[/red] {_friendly_turn_error(exc)}")
                console.print("[dim]Tip: run `aki sdd-init` to structure this as a spec-driven change.[/dim]")
                continue
    finally:
        dispatcher_task.cancel()
        try:
            await dispatcher_task
        except asyncio.CancelledError:
            pass


@app.command()
def remember(
    content: str = typer.Argument(..., help="Content to remember"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    type: str = typer.Option("user_preference", "--type", "-t", help="Event type"),
):
    """Explicitly store a memory."""
    project = detect_project(project)
    agent = _get_agent()

    async def run():
        event = await agent.remember(content, project, EventType(type))
        console.print(f"[green]✓[/green] Remembered: {event.id}")

    run_async_cmd(run())


@app.command()
def recall(
    query: Optional[str] = typer.Argument(None, help="Search query"),
    event_id: Optional[str] = typer.Option(None, "--id", help="Fetch one event by exact ID"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
):
    """Search memory, or fetch a single event by exact ID with --id."""
    if event_id and query:
        console.print("[red]--id and a free-text query are mutually exclusive[/red]")
        raise typer.Exit(1)

    agent = _get_agent()

    if event_id:
        async def run_by_id():
            event = await asyncio.to_thread(agent.memory.get_event, event_id)
            if event is None:
                console.print(f"[yellow]No event with id {event_id}[/yellow]")
                raise typer.Exit(1)
            console.print(f"Event {event.id}")
            console.print(
                f"  time: {event.timestamp}  type: {event.type.value}  "
                f"project: {event.project}  source: {event.source}"
            )
            console.print(f"  {event.content}")

        run_async_cmd(run_by_id())
        return

    if not query:
        console.print("[red]Provide a search query or --id[/red]")
        raise typer.Exit(1)

    project = detect_project(project)

    async def run():
        context = await agent.recall(query, project)
        _print_context(context, limit)

    run_async_cmd(run())


@app.command()
def facts(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
):
    """List all facts for a project."""
    project = detect_project(project)
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

    run_async_cmd(run())


@app.command()
def set_fact(
    key: str = typer.Argument(..., help="Fact key"),
    value: str = typer.Argument(..., help="Fact value"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name"),
    confidence: float = typer.Option(1.0, "--confidence", "-c", help="Confidence (0-1)"),
):
    """Set a fact manually."""
    project = detect_project(project)
    agent = _get_agent()

    async def run():
        await agent.set_fact(key, value, project, confidence)
        console.print(f"[green]✓[/green] Fact set: {key} = {value}")

    run_async_cmd(run())


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


@app.command("agents")
def agents():
    """List configured specialized agent profiles."""
    agent = _get_agent()
    profiles = agent.agent_registry.list_profiles()

    if not profiles:
        console.print("[dim]No specialized agent profiles configured[/dim]")
        return

    table = Table(title="Agent Profiles")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Role", style="green")
    table.add_column("Tools", style="yellow")
    table.add_column("Memory", style="magenta")
    table.add_column("Delegation", style="dim")

    for profile in profiles:
        tools = "deny-all" if profile.tools.deny_all else ", ".join(profile.tools.allowed)
        delegation = "on" if profile.delegation.enabled else "off"
        table.add_row(
            profile.id,
            profile.name,
            profile.role,
            tools,
            profile.memory.scope,
            delegation,
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


def _show_help(agent: "AgentOS", project: str, session_id: str):
    try:
        checkpoint = agent.memory.read_checkpoint(project, session_id)
    except Exception:
        checkpoint = None

    if checkpoint and checkpoint.get("goal"):
        state = (
            f"[green]Resuming[/green] session [cyan]{session_id}[/cyan]\n"
            f"Last goal: {checkpoint['goal'][:80]}"
        )
    else:
        state = f"[yellow]New[/yellow] session [cyan]{session_id}[/cyan] — no history yet"

    console.print(Panel(f"""{state}

[bold]Commands:[/bold]
  /help           - Show this help
  /memory         - Show recent memory
  /facts          - Show facts for current project
  /skills         - List skills
  /sessions       - List past sessions for this project
  /sdd            - Show SDD artifact status
  /clear          - Clear screen
  exit/quit       - Exit
""", title="Help", border_style="blue"))


async def _handle_command(cmd: str, agent: "AgentOS", project: str, session_id: str):
    if cmd == "/memory":
        await _show_memory(agent, project)
    elif cmd == "/facts":
        await _show_facts(agent, project)
    elif cmd == "/skills":
        await _show_skills()
    elif cmd == "/sessions":
        await _show_sessions(agent, project)
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


async def _show_sessions(agent: "AgentOS", project: str):
    sessions = agent.memory.list_sessions(project)
    if not sessions:
        console.print("[dim]No sessions yet for this project[/dim]")
        return
    table = Table(title=f"Sessions: {project}")
    table.add_column("Session", style="cyan")
    table.add_column("Goal", style="white")
    table.add_column("Updated", style="green")
    for s in sessions:
        label = s.goal.strip()[:60] if s.goal.strip() else f"(no goal) {s.session_id}"
        table.add_row(s.session_id, label, s.updated_at.strftime("%Y-%m-%d %H:%M"))
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
