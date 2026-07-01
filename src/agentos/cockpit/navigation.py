"""Interactive prompt-loop drill-down navigation for the Aki cockpit.

This intentionally reuses the existing Rich render helpers in
`agentos.cli.cockpit` (`_render_header`, `_render_*_panel`,
`_render_*_detail`) rather than introducing a new TUI framework. Each
iteration reads one line of text input (via `rich.prompt.Prompt.ask` by
default) and re-renders the current view, per the "lightweight interactive
prompt loop" design decision (spec: "Prompt-Loop Navigation Mechanism").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from agentos.cli.cockpit import (
    CockpitSnapshot,
    ProjectRef,
    _render_action_detail,
    _render_action_required_panel,
    _render_footer,
    _render_header,
    _render_health_detail,
    _render_health_panel,
    _render_memory_detail,
    _render_memory_panel,
    _render_sdd_detail,
    _render_sdd_panel,
    build_cockpit_snapshot,
)

CockpitView = Literal["overview", "panel_detail", "item_detail"]

PANEL_IDS: tuple[str, ...] = ("action", "health", "memory", "sdd")
PANEL_TITLES: dict[str, str] = {
    "action": "Action Required",
    "health": "Project Health",
    "memory": "Memory",
    "sdd": "SDD Status",
}


@dataclass
class CockpitUIState:
    """Navigation state for the interactive cockpit prompt loop."""

    current_view: CockpitView = "overview"
    selected_panel: int = 0
    selected_index: int = 0
    filter_query: str = ""
    refresh_in_progress: bool = False


def _panel_item_count(snapshot: CockpitSnapshot, panel_id: str) -> int:
    if panel_id == "action":
        return len(snapshot.action_items)
    if panel_id == "health":
        return len(snapshot.health_checks)
    if panel_id == "memory":
        return len(snapshot.memory_summary.recent_facts)
    if panel_id == "sdd":
        return len(snapshot.sdd_summary.found_artifacts) + len(snapshot.sdd_summary.missing_artifacts)
    return 0


def _render_panel_summary(snapshot: CockpitSnapshot, panel_id: str) -> str:
    if panel_id == "action":
        return _render_action_required_panel(snapshot)
    if panel_id == "health":
        return _render_health_panel(snapshot)
    if panel_id == "memory":
        return _render_memory_panel(snapshot)
    if panel_id == "sdd":
        return _render_sdd_panel(snapshot)
    raise ValueError(f"Unknown panel id: {panel_id}")


def _render_panel_detail(snapshot: CockpitSnapshot, panel_id: str) -> Panel:
    if panel_id == "action":
        return _render_action_detail(snapshot)
    if panel_id == "health":
        return _render_health_detail(snapshot)
    if panel_id == "memory":
        return _render_memory_detail(snapshot)
    if panel_id == "sdd":
        return _render_sdd_detail(snapshot)
    raise ValueError(f"Unknown panel id: {panel_id}")


def _render_item_detail(snapshot: CockpitSnapshot, panel_id: str, index: int) -> Panel:
    title = f"{PANEL_TITLES[panel_id]} Item Detail"

    if panel_id == "action":
        items = snapshot.action_items
        if not items:
            return Panel("No action items to inspect.", title=title, border_style="red")
        item = items[min(index, len(items) - 1)]
        body = f"[bold]{item.severity.upper()}[/bold] {item.title}\n{item.evidence}\n[dim]{item.command}[/dim]"
        return Panel(body, title=title, border_style="red")

    if panel_id == "health":
        checks = snapshot.health_checks
        if not checks:
            return Panel("No health checks to inspect.", title=title, border_style="green")
        check = checks[min(index, len(checks) - 1)]
        body = f"[bold]{check.id}[/bold]: {check.status}\n{check.detail}\nSource: {check.source}"
        return Panel(body, title=title, border_style="green")

    if panel_id == "memory":
        facts = snapshot.memory_summary.recent_facts
        if not facts:
            return Panel("No durable facts to inspect.", title=title, border_style="blue")
        fact = facts[min(index, len(facts) - 1)]
        body = f"[cyan]{fact.key}[/cyan]\n{fact.value}"
        return Panel(body, title=title, border_style="blue")

    if panel_id == "sdd":
        artifacts = snapshot.sdd_summary.found_artifacts + snapshot.sdd_summary.missing_artifacts
        if not artifacts:
            return Panel("No SDD artifacts to inspect.", title=title, border_style="magenta")
        artifact = artifacts[min(index, len(artifacts) - 1)]
        status = "present" if artifact in snapshot.sdd_summary.found_artifacts else "missing"
        return Panel(f"[cyan]{artifact}[/cyan]: {status}", title=title, border_style="magenta")

    return Panel("Unknown panel.", title=title, border_style="red")


def _render_state(console: Console, snapshot: CockpitSnapshot, state: CockpitUIState) -> None:
    console.print(_render_header(snapshot))
    panel_id = PANEL_IDS[state.selected_panel]

    if state.current_view == "overview":
        panels = [
            Panel(_render_action_required_panel(snapshot), title="Action Required", border_style="red"),
            Panel(_render_health_panel(snapshot), title="Project Health", border_style="green"),
            Panel(_render_memory_panel(snapshot), title="Memory", border_style="blue"),
            Panel(_render_sdd_panel(snapshot), title="SDD Status", border_style="magenta"),
        ]
        console.print(Columns(panels, equal=True, expand=True))
        console.print(f"[dim]Focused panel: {PANEL_TITLES[panel_id]}[/dim]")
    elif state.current_view == "panel_detail":
        console.print(_render_panel_detail(snapshot, panel_id))
    elif state.current_view == "item_detail":
        console.print(_render_item_detail(snapshot, panel_id, state.selected_index))

    if state.filter_query:
        console.print(f"[yellow]Filter: {state.filter_query}[/yellow]")

    console.print(_render_footer())
    console.print(
        "[dim]Keys: Tab/arrows panels | j/k list | Enter drill | b back | g overview | "
        "r refresh | / filter | q quit[/dim]"
    )


def run_cockpit_loop(
    console: Console,
    project: ProjectRef,
    input_func: Optional[Callable[[str], str]] = None,
) -> int:
    """Run the interactive prompt-loop drill-down navigation for a project.

    Each iteration re-renders the current view then reads one line of input.
    Returns a process exit code (0 on clean quit via `q`).
    """
    ask = input_func or (lambda prompt: Prompt.ask(prompt, default=""))
    state = CockpitUIState()
    snapshot = build_cockpit_snapshot(project)

    while True:
        _render_state(console, snapshot, state)
        key = ask("cockpit> ").strip().lower()

        if key in ("q", "quit", "exit"):
            return 0

        if key in ("tab", "right", "l"):
            state.selected_panel = (state.selected_panel + 1) % len(PANEL_IDS)
            continue
        if key in ("left", "h"):
            state.selected_panel = (state.selected_panel - 1) % len(PANEL_IDS)
            continue

        if key == "j":
            panel_id = PANEL_IDS[state.selected_panel]
            count = _panel_item_count(snapshot, panel_id)
            if count:
                state.selected_index = (state.selected_index + 1) % count
            continue

        if key == "k":
            panel_id = PANEL_IDS[state.selected_panel]
            count = _panel_item_count(snapshot, panel_id)
            if count:
                state.selected_index = (state.selected_index - 1) % count
            continue

        if key in ("", "enter"):
            if state.current_view == "overview":
                state.current_view = "panel_detail"
                state.selected_index = 0
            elif state.current_view == "panel_detail":
                state.current_view = "item_detail"
            continue

        if key == "b":
            if state.current_view == "item_detail":
                state.current_view = "panel_detail"
            elif state.current_view == "panel_detail":
                state.current_view = "overview"
            continue

        if key == "g":
            state.current_view = "overview"
            state.selected_index = 0
            continue

        if key == "r":
            state.refresh_in_progress = True
            snapshot = build_cockpit_snapshot(project)
            state.refresh_in_progress = False
            continue

        if key == "/":
            state.filter_query = ask("filter> ").strip()
            continue

        # Unknown key: ignore and redraw the same state.
        continue
