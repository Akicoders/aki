"""Multi-session Agent Chat tab with persistent per-session history."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, ListItem, ListView, RichLog, Static

from agentos.cockpit.tui.task_model import PRIORITY_ICON, get_categories, stats


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    role: str  # "user" | "agent"
    text: str


@dataclass
class ChatSession:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    messages: list[ChatMessage] = field(default_factory=list)


# Global session store
_sessions: list[ChatSession] = [
    ChatSession(name="Session 1"),
]
_active_id: str = _sessions[0].id


def get_sessions() -> list[ChatSession]:
    return _sessions


def get_active() -> ChatSession:
    for s in _sessions:
        if s.id == _active_id:
            return s
    return _sessions[0]


# ── Task summary for the sidebar ──────────────────────────────────────────────

def _build_summary_text() -> str:
    try:
        from agentos.cockpit.tui.kanban import get_tasks
        tasks = get_tasks()
        done, total = stats(tasks)
        pct = int(done / total * 100) if total else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines = [
            f"[bold cyan]Tasks[/bold cyan] [green]{done}[/green]/[white]{total}[/white]",
            f"[cyan]{bar}[/cyan] {pct}%",
            "",
        ]
        for cat in get_categories(tasks):
            cat_tasks = [t for t in tasks if t.category == cat]
            done_cat = sum(1 for t in cat_tasks if t.done)
            lines.append(f"[bold]{cat}[/bold] {done_cat}/{len(cat_tasks)}")
        return "\n".join(lines)
    except Exception:
        return "[dim]Tasks unavailable[/dim]"


# ── Session list item ─────────────────────────────────────────────────────────

class SessionItem(ListItem):
    def __init__(self, session: ChatSession) -> None:
        super().__init__()
        self._session = session

    def compose(self) -> ComposeResult:
        yield Label(f"💬 {self._session.name}")

    def refresh_label(self, active_id: str) -> None:
        prefix = "▶ " if self._session.id == active_id else "  "
        count  = len(self._session.messages)
        suffix = f" [dim]({count})[/dim]" if count else ""
        self.query_one(Label).update(f"{prefix}💬 {self._session.name}{suffix}")


# ── Main Chat Tab ─────────────────────────────────────────────────────────────

class ChatTab(Widget):
    """Multi-session Agent Chat tab."""

    DEFAULT_CSS = """
    ChatTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    /* ── Session sidebar ── */
    #session-panel {
        width: 22;
        height: 1fr;
        layout: vertical;
        border-right: solid $accent-darken-1;
    }
    #session-panel-header {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 1;
        text-style: bold;
        color: cyan;
    }
    #session-list {
        height: 1fr;
    }
    #session-btn-row {
        height: 3;
        layout: horizontal;
        border-top: solid $accent-darken-1;
        background: $panel;
    }
    #new-session-btn  { width: 1fr; }
    #del-session-btn  { width: 1fr; }

    /* ── Chat area ── */
    #chat-area {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }
    #chat-header {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 2;
        color: $text;
    }
    #chat-log {
        height: 1fr;
        border-bottom: solid $accent-darken-1;
    }
    #chat-input { dock: bottom; }

    /* ── Task sidebar ── */
    #task-panel {
        width: 24;
        height: 1fr;
        layout: vertical;
        border-left: solid $accent-darken-1;
        padding: 1 1;
        overflow-y: auto;
    }
    #task-panel-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._active_id = _sessions[0].id

    def compose(self) -> ComposeResult:
        active = self._get_active()

        # ── Session sidebar ────────────────────────────────────────────────────
        with Vertical(id="session-panel"):
            yield Static("💬 Chats", id="session-panel-header", markup=True)
            yield ListView(
                *[SessionItem(s) for s in _sessions],
                id="session-list",
            )
            with Horizontal(id="session-btn-row"):
                yield Button("+ New", id="new-session-btn", variant="success")
                yield Button("🗑 Del", id="del-session-btn", variant="error")

        # ── Chat messages area ─────────────────────────────────────────────────
        with Vertical(id="chat-area"):
            yield Static(f"[bold]{active.name}[/bold]", id="chat-header", markup=True)
            yield RichLog(id="chat-log", highlight=True, markup=True)
            yield Input(placeholder="Message the agent… (Enter to send)", id="chat-input")

        # ── Task summary sidebar ───────────────────────────────────────────────
        with Vertical(id="task-panel"):
            yield Label("📋 Tasks", id="task-panel-title")
            yield Static(_build_summary_text(), id="task-summary", markup=True)

    def on_mount(self) -> None:
        self._load_session(self._get_active())
        self._refresh_session_list()

    # ── Session switching ──────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.control.id == "session-list" and isinstance(event.item, SessionItem):
            self._switch_to(event.item._session)

    def _switch_to(self, session: ChatSession) -> None:
        self._active_id = session.id
        header = self.query_one("#chat-header", Static)
        header.update(f"[bold]{session.name}[/bold]")
        self._load_session(session)
        self._refresh_session_list()

    def _load_session(self, session: ChatSession) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        if not session.messages:
            log.write(f"[bold green]Agent:[/bold green] Hello! This is [bold]{session.name}[/bold]. How can I help?")
        else:
            for msg in session.messages:
                if msg.role == "user":
                    log.write(f"[bold cyan]You:[/bold cyan] {msg.text}")
                else:
                    log.write(f"[bold green]Agent:[/bold green] {msg.text}")

    def _refresh_session_list(self) -> None:
        lv = self.query_one("#session-list", ListView)
        for item in lv.query(SessionItem):
            item.refresh_label(self._active_id)

    # ── New / Delete session ──────────────────────────────────────────────────

    @on(Button.Pressed, "#new-session-btn")
    def _on_new_session(self) -> None:
        n = len(_sessions) + 1
        new_s = ChatSession(name=f"Session {n}")
        _sessions.append(new_s)
        lv = self.query_one("#session-list", ListView)
        lv.append(SessionItem(new_s))
        self._switch_to(new_s)
        self.app.notify(f"Created {new_s.name}")

    @on(Button.Pressed, "#del-session-btn")
    def _on_del_session(self) -> None:
        if len(_sessions) <= 1:
            self.app.notify("Cannot delete the only session.", severity="warning")
            return
        active = self._get_active()
        _sessions.remove(active)
        # Switch to first remaining session
        lv = self.query_one("#session-list", ListView)
        for item in list(lv.query(SessionItem)):
            if item._session.id == active.id:
                item.remove()
                break
        self._switch_to(_sessions[0])
        self.app.notify(f"Deleted {active.name}", severity="warning")

    # ── Sending messages ──────────────────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    def _on_send(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        session = self._get_active()
        log     = self.query_one("#chat-log", RichLog)

        # Save and display user message
        session.messages.append(ChatMessage(role="user", text=text))
        log.write(f"[bold cyan]You:[/bold cyan] {text}")

        # Placeholder agent response — hook real agent here
        reply = f"Got it! (Connecting to Aki agent backend soon 🚀)"
        session.messages.append(ChatMessage(role="agent", text=reply))
        log.write(f"[bold green]Agent:[/bold green] {reply}")

        self._refresh_session_list()

    # ── Tab focus refresh ─────────────────────────────────────────────────────

    def on_focus(self) -> None:
        try:
            self.query_one("#task-summary", Static).update(_build_summary_text())
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_active(self) -> ChatSession:
        for s in _sessions:
            if s.id == self._active_id:
                return s
        return _sessions[0]
