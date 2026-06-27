"""CLI entry point for Aki."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentos.agent.core import AgentOS, get_agent
from agentos.core.config import get_config, reset_config
from agentos.mcp.server import run_mcp_server
from agentos.memory.repository import MemoryRepository
from agentos.memory.models import EventType
from agentos.skills.base import get_skill_registry

app = typer.Typer(
    name="agentos",
    help="Aki - AI agent with portable project memory",
    add_completion=False,
)
console = Console()


@app.callback()
def callback(
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


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send"),
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
    stream: bool = typer.Option(False, "--stream", help="Stream response"),
):
    """Chat with Aki."""
    agent = get_agent()

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
    agent = get_agent()
    session_id = session or f"sess_{__import__('uuid').uuid4().hex[:8]}"

    console.print(Panel.fit(
        f"[bold cyan]Aki Interactive[/bold cyan]\n"
        f"Project: [yellow]{project}[/yellow] | Session: [dim]{session_id}[/dim]\n"
        f"Type 'exit' or 'quit' to leave, '/help' for commands",
        border_style="cyan",
    ))

    asyncio.run(_async_interactive(agent, project, session_id))


@app.command("mcp")
def mcp_server():
    """Start the Aki stdio MCP server."""
    run_mcp_server()


@app.command("mcp-config")
def mcp_config(host: str = typer.Argument("opencode", help="MCP host to print config for")):
    """Print an MCP host configuration snippet."""
    if host != "opencode":
        raise typer.BadParameter("Only 'opencode' is supported in the MVP")
    snippet = {
        "mcp": {
            "aki_memory": {
                "type": "local",
                "command": ["uv", "run", "agentos", "mcp"],
                "enabled": True,
            }
        }
    }
    typer.echo(json.dumps(snippet, indent=2))


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
    agent = get_agent()

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
    agent = get_agent()

    async def run():
        context = await agent.recall(query, project)
        _print_context(context, limit)

    asyncio.run(run())


@app.command()
def facts(
    project: str = typer.Option("default", "--project", "-p", help="Project name"),
):
    """List all facts for a project."""
    agent = get_agent()

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
    agent = get_agent()

    async def run():
        await agent.set_fact(key, value, project, confidence)
        console.print(f"[green]✓[/green] Fact set: {key} = {value}")

    asyncio.run(run())


@app.command()
def skills(
    enabled_only: bool = typer.Option(True, "--enabled-only/--all", help="Show only enabled skills"),
):
    """List available skills."""
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
  /clear          - Clear screen
  exit/quit       - Exit
""", title="Help", border_style="blue"))


def _handle_command(cmd: str, agent: AgentOS, project: str, session_id: str):
    if cmd == "/memory":
        asyncio.run(_show_memory(agent, project))
    elif cmd == "/facts":
        asyncio.run(_show_facts(agent, project))
    elif cmd == "/skills":
        asyncio.run(_show_skills())
    elif cmd == "/clear":
        console.clear()
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")


async def _show_memory(agent: AgentOS, project: str):
    context = await agent.recall("", project)
    _print_context(context, 20)


async def _show_facts(agent: AgentOS, project: str):
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
