"""Agent Chat tab with a live task summary sidebar."""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, RichLog, Static

from agentos.cockpit.tui.task_model import PRIORITY_ICON, get_categories, stats


def _build_summary_text() -> str:
    """Build the sidebar summary text from current task state."""
    from agentos.cockpit.tui.tasks import get_tasks
    tasks = get_tasks()

    done, total = stats(tasks)
    pct = int(done / total * 100) if total else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)

    lines = [
        f"[bold cyan]Progress[/bold cyan]",
        f"[green]{done}[/green]/[white]{total}[/white]  {pct}%",
        f"[cyan]{bar}[/cyan]",
        "",
    ]

    for cat in get_categories(tasks):
        cat_tasks = [t for t in tasks if t.category == cat]
        done_cat = sum(1 for t in cat_tasks if t.done)
        lines.append(f"[bold]{cat}[/bold] ({done_cat}/{len(cat_tasks)})")
        for t in cat_tasks:
            icon = PRIORITY_ICON[t.priority]
            check = "✅" if t.done else "⬜"
            name = t.title[:16] + "…" if len(t.title) > 16 else t.title
            lines.append(f"  {check}{icon} {name}")
        lines.append("")

    return "\n".join(lines)


class ChatTab(Horizontal):
    """Agent Chat tab with a task summary sidebar on the right."""

    DEFAULT_CSS = """
    ChatTab {
        height: 100%;
    }
    #chat-main {
        width: 1fr;
        height: 100%;
    }
    #chat-log {
        height: 1fr;
        border: solid $accent;
        margin-bottom: 1;
    }
    #chat-input {
        dock: bottom;
    }
    #chat-sidebar {
        width: 28;
        height: 100%;
        border-left: solid $accent-darken-1;
        padding: 1 1;
        overflow-y: auto;
    }
    #sidebar-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-main"):
            yield RichLog(id="chat-log", highlight=True, markup=True)
            yield Input(placeholder="Message the agent…", id="chat-input")

        with Vertical(id="chat-sidebar"):
            yield Label("📋 Task Status", id="sidebar-title")
            yield Static(_build_summary_text(), id="task-summary", markup=True)

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("[bold green]Agent:[/bold green] Hello! I'm Aki. How can I help you today?")
        log.write("[dim]Tip: See the [bold]Tasks[/bold] tab to manage your full task list.[/dim]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            log = self.query_one(RichLog)
            log.write(f"[bold cyan]You:[/bold cyan] {event.value}")
            event.input.value = ""
            log.write("[bold green]Agent:[/bold green] Got it! (Backend integration coming soon 🚀)")

    def on_focus(self) -> None:
        """Refresh task summary when the user switches to this tab."""
        summary = self.query_one("#task-summary", Static)
        summary.update(_build_summary_text())
