from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Input, Label, ListItem, ListView, RichLog

# Shared task state — used by both ChatTab and TaskBoardTab
INITIAL_TASKS: list[tuple[bool, str]] = [
    (True,  "Setup Textual environment"),
    (True,  "Create interactive tabs"),
    (False, "Connect agent backend to Chat Tab"),
    (False, "Implement persistent task storage"),
]


class ChatTab(Vertical):
    """The Agent Chat tab with a task summary panel."""

    DEFAULT_CSS = """
    ChatTab {
        layout: horizontal;
    }
    #chat-main {
        width: 1fr;
        height: 100%;
    }
    #chat-sidebar {
        width: 26;
        height: 100%;
        border-left: solid cyan;
        padding: 1 1;
    }
    #sidebar-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    #chat-log {
        height: 1fr;
        border: solid $accent;
        margin-bottom: 1;
    }
    #chat-input {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-main"):
            yield RichLog(id="chat-log", highlight=True, markup=True)
            yield Input(placeholder="Message the agent...", id="chat-input")

        with Vertical(id="chat-sidebar"):
            yield Label("📋 Tasks", id="sidebar-title")
            yield self._build_task_list()

    def _build_task_list(self) -> Label:
        lines = []
        for done, name in INITIAL_TASKS:
            icon = "✅" if done else "⬜"
            lines.append(f"{icon} {name}")
        return Label("\n".join(lines), id="task-summary")

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("[bold green]Agent:[/bold green] Hello! I am Aki. How can I help you today?")
        log.write("[dim]Tip: Open the [bold]Tasks[/bold] tab to manage your full task list.[/dim]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            log = self.query_one(RichLog)
            log.write(f"[bold cyan]You:[/bold cyan] {event.value}")
            event.input.value = ""
            # Placeholder — real agent connection will go here
            log.write("[bold green]Agent:[/bold green] Got it! (Backend integration coming soon 🚀)")
