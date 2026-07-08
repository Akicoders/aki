"""Interactive prompt-loop drill-down navigation for the Aki cockpit.

This incorporates tabs, a parsed task list, a file tree view, scrollable markdown
visualizers, and dynamic Change Creation (/new) tab options.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.tree import Tree
from rich.markdown import Markdown

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

CockpitView = Literal["overview", "panel_detail", "item_detail", "tasks", "file_tree", "sdd_docs", "new_sdd"]

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

    # Tabs integration
    active_tab: int = 0  # 0: Overview, 1: Tasks, 2: File Tree, 3: SDD Docs, 4: Memory, 5: Health, 6: New SDD
    sdd_selected_file: int = 0  # 0: proposal, 1: spec, 2: design, 3: tasks
    sdd_scroll_offset: int = 0  # Line scroll offset
    new_sdd_state: dict = field(default_factory=dict)


def parse_tasks(project_root: Path) -> list[dict]:
    """Parse tasks.md from SDD directory into list of task dicts."""
    from agentos.sdd.detector import detect_sdd_artifacts
    status = detect_sdd_artifacts(project_root)
    if not status.has_sdd or not status.sdd_dir:
        return []

    tasks_path = project_root / status.sdd_dir / "tasks.md"
    if not tasks_path.exists():
        return []

    try:
        content = tasks_path.read_text(encoding="utf-8")
    except Exception:
        return []

    tasks = []
    current_section = "General"

    for line in content.splitlines():
        line_str = line.strip()
        if not line_str:
            continue

        # Match section headers
        header_match = re.match(r'^(#+)\s+(.*)$', line_str)
        if header_match:
            level, text = header_match.groups()
            if level in ("##", "###"):
                current_section = text.strip()
            continue

        # Match checkboxes
        cb_match = re.search(r'\[([ xX/])\]\s*(.*)$', line_str)
        if cb_match:
            status_char, desc = cb_match.groups()
            status = "pending"
            if status_char == "/":
                status = "in_progress"
            elif status_char in ("x", "X"):
                status = "completed"

            tasks.append({
                "section": current_section,
                "desc": desc.strip(),
                "status": status
            })

    return tasks


def build_file_tree(dir_path: Path, max_depth: int = 2) -> Tree:
    """Build a rich visual Tree representing project directories."""
    tree = Tree(f"[bold cyan]📁 {dir_path.name}[/bold cyan]")

    def add_node(path: Path, current_tree: Tree, depth: int):
        if depth > max_depth:
            return

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return

        for item in items:
            # Exclude common meta dirs to keep tree clean
            if item.name.startswith((".", "__pycache__", "node_modules", "venv", ".venv")):
                continue
            if item.is_dir():
                branch = current_tree.add(f"[bold yellow]📁 {item.name}[/bold yellow]")
                add_node(item, branch, depth + 1)
            else:
                ext = item.suffix.lower()
                color = "white"
                icon = "📄"
                if ext in (".py", ".pyw"):
                    color = "green"
                    icon = "🐍"
                elif ext in (".md", ".txt"):
                    color = "magenta"
                    icon = "📝"
                elif ext in (".json", ".yaml", ".yml", ".toml"):
                    color = "cyan"
                    icon = "⚙️"
                elif ext in (".lock",):
                    color = "red"
                    icon = "🔒"
                current_tree.add(f"[{color}]{icon} {item.name}[/{color}]")

    add_node(dir_path, tree, 1)
    return tree


def render_markdown_to_lines(console: Console, text: str, width: int) -> list[str]:
    """Capture rich rendered markdown as list of formatted ANSI lines."""
    temp_console = Console(width=width, force_terminal=True, color_system="auto")
    with temp_console.capture() as capture:
        temp_console.print(Markdown(text))
    return capture.get().splitlines()


def make_progress_bar(completed: int, total: int, width: int = 40) -> str:
    """Return a styled text progress bar."""
    if total == 0:
        return ""
    ratio = completed / total
    filled_len = int(width * ratio)
    empty_len = width - filled_len
    bar = "[green]█[/green]" * filled_len + "[dim]░[/dim]" * empty_len
    percentage = int(ratio * 100)
    return f"{bar} [bold green]{percentage}%[/bold green] ({completed}/{total})"


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


def _render_tabs_header(state: CockpitUIState) -> Panel:
    """Render horizontal navigation tabs row."""
    tabs = [
        "Overview",
        "Tasks",
        "File Tree",
        "SDD Docs",
        "Memory Detail",
        "Health Detail",
    ]

    tab_strs = []
    for i, tab in enumerate(tabs):
        is_active = (state.active_tab == i)
        shortcut = f"[{i+1}]"
        if is_active:
            tab_strs.append(f"[bold yellow reverse] ▶ {shortcut} {tab} [/bold yellow reverse]")
        else:
            tab_strs.append(f"[dim]   {shortcut} {tab}   [/dim]")

    # If dynamic new SDD tab is active, append it
    if state.active_tab == 6:
        tab_strs.append("[bold red reverse] ▶ [7] New SDD [/bold red reverse]")
    else:
        tab_strs.append("[dim]   /new Create Change   [/dim]")

    return Panel(" | ".join(tab_strs), border_style="cyan", title="[bold cyan]Navigation Tabs[/bold cyan]")


def _render_state(console: Console, snapshot: CockpitSnapshot, state: CockpitUIState) -> None:
    # 1. Print Header con AKI
    console.print(_render_header(snapshot))

    # 2. Print Navigation Tabs
    console.print(_render_tabs_header(state))

    # 3. Print Active View
    if state.active_tab == 0:  # Overview
        panel_id = PANEL_IDS[state.selected_panel]
        if state.current_view == "overview":
            panels = [
                Panel(_render_action_required_panel(snapshot), title="Action Required", border_style="red"),
                Panel(_render_health_panel(snapshot), title="Project Health", border_style="green"),
                Panel(_render_memory_panel(snapshot), title="Memory", border_style="blue"),
                Panel(_render_sdd_panel(snapshot), title="SDD Status", border_style="magenta"),
            ]
            console.print(Columns(panels, equal=True, expand=True))
            console.print(f"[dim]Focused panel: {PANEL_TITLES[panel_id]} (Press Enter to drill down)[/dim]")
        elif state.current_view == "panel_detail":
            console.print(_render_panel_detail(snapshot, panel_id))
        elif state.current_view == "item_detail":
            console.print(_render_item_detail(snapshot, panel_id, state.selected_index))

    elif state.active_tab == 1:  # Tasks Checklist
        tasks = parse_tasks(snapshot.project.root_path)
        if not tasks:
            console.print(Panel(
                "[yellow]No SDD tasks checklist detected.[/yellow]\n"
                "Initialize SDD for this project by running [bold]aki sdd-init[/bold] or typing [bold]/new[/bold].",
                title="Tasks Checklist",
                border_style="yellow"
            ))
        else:
            completed_tasks = sum(1 for t in tasks if t["status"] == "completed")
            in_progress_tasks = sum(1 for t in tasks if t["status"] == "in_progress")
            total_tasks = len(tasks)

            # Progress Bar panel
            progress_bar = make_progress_bar(completed_tasks, total_tasks)
            summary_lines = [
                f"Total: {total_tasks} | Completed: {completed_tasks} | In Progress: {in_progress_tasks}",
                f"Progress: {progress_bar}"
            ]
            console.print(Panel("\n".join(summary_lines), title="[bold green]Task Progress[/bold green]", border_style="green"))

            # Render Table of Tasks
            table = Table(expand=True)
            table.add_column("Status", width=12, justify="center")
            table.add_column("Section", style="cyan", width=25)
            table.add_column("Task Description", style="white")

            for t in tasks:
                status_str = "[dim]⏳ Pending[/dim]"
                if t["status"] == "completed":
                    status_str = "[bold green]✓ Done[/bold green]"
                elif t["status"] == "in_progress":
                    status_str = "[bold yellow]🔄 Doing[/bold yellow]"

                table.add_row(status_str, t["section"], t["desc"])

            console.print(Panel(table, title="[bold green]Active Change Task List[/bold green]", border_style="green"))

    elif state.active_tab == 2:  # File Tree
        tree = build_file_tree(snapshot.project.root_path)
        console.print(Panel(tree, title="[bold yellow]Project Directory Tree[/bold yellow]", border_style="yellow"))

    elif state.active_tab == 3:  # SDD Docs Markdown Visualizer
        sdd_files = ["proposal.md", "spec.md", "design.md", "tasks.md"]
        from agentos.sdd.detector import load_sdd_artifact
        active_filename = sdd_files[state.sdd_selected_file]
        content = load_sdd_artifact(active_filename, snapshot.project.root_path)

        # Left file-list selector layout
        file_list_lines = []
        for idx, filename in enumerate(sdd_files):
            exists = snapshot.sdd_summary.has_sdd and (filename in snapshot.sdd_summary.found_artifacts)
            exists_marker = "✓" if exists else "✗"
            exists_color = "green" if exists else "red"

            if idx == state.sdd_selected_file:
                file_list_lines.append(f"[bold cyan reverse] ▶ [{exists_color}]{exists_marker}[/{exists_color}] {filename} [/bold cyan reverse]")
            else:
                file_list_lines.append(f"  [{exists_color}]{exists_marker}[/{exists_color}] {filename}")

        file_list_panel = Panel(
            "\n".join(file_list_lines),
            title="[bold cyan]SDD Artifacts[/bold cyan]",
            border_style="cyan"
        )

        # Right markdown visualizer layout
        if not content:
            md_panel = Panel(
                f"[yellow]File {active_filename} does not exist or is empty.[/yellow]\n"
                "Run `aki sdd-init` or create this file in the SDD directory.",
                title=f"[bold red]{active_filename} (Missing)[/bold red]",
                border_style="red"
            )
        else:
            # Render and slice content for scrolling
            lines = render_markdown_to_lines(console, content, width=70)
            max_lines = len(lines)
            height = 20  # Show 20 lines at a time
            state.sdd_scroll_offset = max(0, min(state.sdd_scroll_offset, max_lines - height))
            visible_lines = lines[state.sdd_scroll_offset: state.sdd_scroll_offset + height]

            scroll_info = f"Lines {state.sdd_scroll_offset + 1}-{min(state.sdd_scroll_offset + height, max_lines)} of {max_lines}"
            scroll_hint = "[dim](w/s or up/down to scroll, u/d for page)[/dim]"

            md_content = "\n".join(visible_lines)
            md_panel = Panel(
                md_content,
                title=f"[bold green]📄 {active_filename}[/bold green] - {scroll_info}",
                subtitle=scroll_hint,
                border_style="green"
            )

        # Put columns side by side
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=3)
        grid.add_row(file_list_panel, md_panel)
        console.print(Panel(grid, title="[bold green]Markdown SDD Visualizer[/bold green]", border_style="green"))

    elif state.active_tab == 4:  # Memory Detail
        console.print(_render_panel_detail(snapshot, "memory"))

    elif state.active_tab == 5:  # Health Detail
        console.print(_render_panel_detail(snapshot, "health"))

    elif state.active_tab == 6:  # New SDD assistant wizard
        console.print(Panel(
            "[bold cyan]🆕 Create a New SDD Change[/bold cyan]\n\n"
            "This wizard will bootstrap a new Change Specification under `docs/sdd`.\n"
            "Please follow the boxed prompts below to set the Change Title and Intent.\n\n"
            "Type [bold red]exit[/bold red] at the prompts to cancel and return to overview.",
            title="[bold cyan]Change Scaffolding Wizard[/bold cyan]",
            border_style="cyan"
        ))

    if state.filter_query:
        console.print(f"[yellow]Filter: {state.filter_query}[/yellow]")

    console.print(_render_footer())


def run_cockpit_loop(
    console: Console,
    project: ProjectRef,
    input_func: Optional[Callable[[str], str]] = None,
) -> int:
    """Run the interactive prompt-loop drill-down navigation for a project."""
    ask = input_func or (lambda prompt: Prompt.ask(prompt, default=""))
    state = CockpitUIState()
    snapshot = build_cockpit_snapshot(project)

    while True:
        _render_state(console, snapshot, state)

        # Visual advice panel for input (Boxed Input Helper)
        tips = (
            "[dim]"
            "Tabs: [bold]1-6[/bold] select tab | [bold]tab/arrows[/bold] cycle tabs | [bold]q[/bold] quit\n"
            "View: [bold]j/k[/bold] move item | [bold]Enter[/bold] details | [bold]b[/bold] back\n"
            "SDD Docs: [bold]p/s/d/t[/bold] choose file | [bold]w/s[/bold] (or up/down) scroll doc\n"
            "Commands: [bold]/new[/bold] create new change"
            "[/dim]"
        )
        console.print(Panel(
            tips,
            title="[bold magenta]🎮 Cockpit Controls[/bold magenta]",
            border_style="magenta",
            expand=True
        ))

        key = ask("cockpit> ").strip().lower()

        if key in ("q", "quit", "exit"):
            if state.active_tab == 6:  # If in /new tab, exit returns to overview
                state.active_tab = 0
                state.current_view = "overview"
                continue
            return 0

        # Command shortcuts
        if key == "/new":
            state.active_tab = 6
            state.current_view = "new_sdd"
            continue

        # Tab direct keys
        if key == "1":
            state.active_tab = 0
            state.current_view = "overview"
            continue
        if key == "2":
            state.active_tab = 1
            state.current_view = "tasks"
            continue
        if key == "3":
            state.active_tab = 2
            state.current_view = "file_tree"
            continue
        if key == "4":
            state.active_tab = 3
            state.current_view = "sdd_docs"
            state.sdd_scroll_offset = 0
            continue
        if key == "5":
            state.active_tab = 4
            state.current_view = "panel_detail"
            state.selected_panel = 2  # memory
            continue
        if key == "6":
            state.active_tab = 5
            state.current_view = "panel_detail"
            state.selected_panel = 1  # health
            continue

        # Wizard flow for new change
        if state.active_tab == 6:
            if key == "exit":
                state.active_tab = 0
                state.current_view = "overview"
                continue

            # Run interactive helper
            from agentos.sdd.init import init_sdd_project
            console.print()
            console.print("[bold cyan]Prompting in interactive wizard...[/bold cyan]")

            # We can run inline inputs
            console.print(Panel("[dim]Enter the unique change ID (e.g. login-auth)[/dim]", title="Step 1: Change Slug", border_style="cyan"))
            slug = ask("Slug: ").strip()
            if not slug or slug.lower() == "exit":
                state.active_tab = 0
                state.current_view = "overview"
                continue

            console.print(Panel("[dim]Describe the intent of the change (What is being solved?)[/dim]", title="Step 2: Change Intent", border_style="cyan"))
            intent = ask("Intent: ").strip()
            if intent.lower() == "exit":
                state.active_tab = 0
                state.current_view = "overview"
                continue

            sdd_dir, created = init_sdd_project(project.root_path)
            from agentos.sdd.init import TEMPLATES
            for filename, content in TEMPLATES.items():
                filepath = sdd_dir / filename
                if filename == "proposal.md" and intent:
                    content = content.replace("[What problem are you solving and why?]", intent)
                content = content.replace("[Change Name]", slug)

                if not filepath.exists():
                    filepath.write_text(content, encoding="utf-8")

            console.print(Panel(
                f"[green]✓ SDD Change folder initialized at {sdd_dir}[/green]\n"
                f"Slug: [cyan]{slug}[/cyan]\n"
                "Press Enter to return to Overview.",
                title="Success",
                border_style="green"
            ))
            ask("")
            state.active_tab = 0
            state.current_view = "overview"
            snapshot = build_cockpit_snapshot(project)
            continue

        # Tab/Arrow Cycling
        if key in ("tab", "right", "l"):
            if state.current_view == "overview":
                # compatibility with original overview panel selection
                state.selected_panel = (state.selected_panel + 1) % len(PANEL_IDS)
            else:
                state.active_tab = (state.active_tab + 1) % 6
                # Sync views
                if state.active_tab == 0:
                    state.current_view = "overview"
                elif state.active_tab == 1:
                    state.current_view = "tasks"
                elif state.active_tab == 2:
                    state.current_view = "file_tree"
                elif state.active_tab == 3:
                    state.current_view = "sdd_docs"
                elif state.active_tab == 4:
                    state.current_view = "panel_detail"
                    state.selected_panel = 2
                elif state.active_tab == 5:
                    state.current_view = "panel_detail"
                    state.selected_panel = 1
            continue

        if key in ("left", "h"):
            if state.current_view == "overview":
                state.selected_panel = (state.selected_panel - 1) % len(PANEL_IDS)
            else:
                state.active_tab = (state.active_tab - 1) % 6
                # Sync views
                if state.active_tab == 0:
                    state.current_view = "overview"
                elif state.active_tab == 1:
                    state.current_view = "tasks"
                elif state.active_tab == 2:
                    state.current_view = "file_tree"
                elif state.active_tab == 3:
                    state.current_view = "sdd_docs"
                elif state.active_tab == 4:
                    state.current_view = "panel_detail"
                    state.selected_panel = 2
                elif state.active_tab == 5:
                    state.active_tab = 5
                    state.current_view = "panel_detail"
                    state.selected_panel = 1
            continue

        # Scroll controls for SDD Docs tab (Tab 3)
        if state.active_tab == 3:
            if key in ("w", "up"):
                state.sdd_scroll_offset = max(0, state.sdd_scroll_offset - 1)
                continue
            if key in ("s", "down"):
                state.sdd_scroll_offset += 1
                continue
            if key == "u":  # page up
                state.sdd_scroll_offset = max(0, state.sdd_scroll_offset - 10)
                continue
            if key == "d":  # page down
                state.sdd_scroll_offset += 10
                continue
            # Select specific file
            if key == "p":
                state.sdd_selected_file = 0
                state.sdd_scroll_offset = 0
                continue
            if key == "s":
                state.sdd_selected_file = 1
                state.sdd_scroll_offset = 0
                continue
            if key == "d":
                state.sdd_selected_file = 2
                state.sdd_scroll_offset = 0
                continue
            if key == "t":
                state.sdd_selected_file = 3
                state.sdd_scroll_offset = 0
                continue

        # Item vertical movement
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
            state.active_tab = 0
            continue

        if key == "r":
            state.refresh_in_progress = True
            snapshot = build_cockpit_snapshot(project)
            state.refresh_in_progress = False
            continue

        if key == "/":
            state.filter_query = ask("filter> ").strip()
            continue

        # Unknown key: ignore and redraw
        continue
