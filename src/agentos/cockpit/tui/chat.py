"""Multi-session Agent Chat tab — connected to the real Aki agent via stream_chat."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Label, ListItem, ListView, RichLog, Static

from agentos.cockpit.tui.task_model import get_categories, stats


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    role: str   # "user" | "agent"
    text: str


@dataclass
class ChatSession:
    name: str
    project: str = "cockpit"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    messages: list[ChatMessage] = field(default_factory=list)


_sessions: list[ChatSession] = [ChatSession(name="Session 1")]


def get_sessions() -> list[ChatSession]:
    return _sessions


# ── Agent singleton (lazy) ─────────────────────────────────────────────────────

_agent = None

def _get_agent():
    global _agent
    if _agent is None:
        try:
            from agentos.agent.core import get_agent
            _agent = get_agent()
        except Exception as e:
            return None, str(e)
    return _agent, None


# ── Task summary ───────────────────────────────────────────────────────────────

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
    """Multi-session chat tab connected to the Aki agent via stream_chat."""

    DEFAULT_CSS = """
    ChatTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
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
    #session-list { height: 1fr; }
    #session-btn-row {
        height: 3;
        layout: horizontal;
        border-top: solid $accent-darken-1;
        background: $panel;
    }
    #new-session-btn { width: 1fr; }
    #del-session-btn { width: 1fr; }

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
        layout: horizontal;
    }
    #chat-header-title { width: 1fr; }
    #agent-status {
        width: 16;
        color: $text-muted;
        margin: 0 1 0 0;
    }
    #chat-log { height: 1fr; }
    #chat-input-row {
        height: 3;
        layout: horizontal;
        border-top: solid $accent-darken-1;
        background: $panel;
        padding: 0 1;
    }
    #chat-input { width: 1fr; }
    #send-btn   { width: 8; }

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
        self._streaming  = False

    def compose(self) -> ComposeResult:
        active = self._get_active()

        with Vertical(id="session-panel"):
            yield Static("💬 Chats", id="session-panel-header", markup=True)
            yield ListView(*[SessionItem(s) for s in _sessions], id="session-list")
            with Horizontal(id="session-btn-row"):
                yield Button("+ New", id="new-session-btn", variant="success")
                yield Button("🗑 Del", id="del-session-btn", variant="error")

        with Vertical(id="chat-area"):
            with Horizontal(id="chat-header"):
                yield Static(f"[bold]{active.name}[/bold]", id="chat-header-title", markup=True)
                yield Static("● ready", id="agent-status", markup=True)
            yield RichLog(id="chat-log", highlight=True, markup=True, auto_scroll=True)
            with Horizontal(id="chat-input-row"):
                yield Input(placeholder="Message Aki… (Enter to send)", id="chat-input")
                yield Button("Send", id="send-btn", variant="primary")

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
        self.query_one("#chat-header-title", Static).update(f"[bold]{session.name}[/bold]")
        self._load_session(session)
        self._refresh_session_list()

    def _load_session(self, session: ChatSession) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        if not session.messages:
            log.write("[bold green]Aki:[/bold green] Hello! I'm ready. How can I help you today?")
            log.write(f"[dim]Session: {session.session_id} | Project: {session.project}[/dim]")
        else:
            for msg in session.messages:
                if msg.role == "user":
                    log.write(f"[bold cyan]You:[/bold cyan] {msg.text}")
                else:
                    log.write(f"[bold green]Aki:[/bold green] {msg.text}")

    def _refresh_session_list(self) -> None:
        for item in self.query(SessionItem):
            item.refresh_label(self._active_id)

    # ── New / Delete session ──────────────────────────────────────────────────

    @on(Button.Pressed, "#new-session-btn")
    def _on_new_session(self) -> None:
        n = len(_sessions) + 1
        new_s = ChatSession(name=f"Session {n}")
        _sessions.append(new_s)
        self.query_one("#session-list", ListView).append(SessionItem(new_s))
        self._switch_to(new_s)
        self.app.notify(f"Created {new_s.name}")

    @on(Button.Pressed, "#del-session-btn")
    def _on_del_session(self) -> None:
        if len(_sessions) <= 1:
            self.app.notify("Cannot delete the only session.", severity="warning")
            return
        active = self._get_active()
        _sessions.remove(active)
        lv = self.query_one("#session-list", ListView)
        for item in list(lv.query(SessionItem)):
            if item._session.id == active.id:
                item.remove()
                break
        self._switch_to(_sessions[0])
        self.app.notify(f"Deleted {active.name}", severity="warning")

    # ── Sending messages ──────────────────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    @on(Button.Pressed, "#send-btn")
    def _on_send(self, event) -> None:
        if self._streaming:
            return
        inp  = self.query_one("#chat-input", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""

        session = self._get_active()
        log     = self.query_one("#chat-log", RichLog)

        session.messages.append(ChatMessage(role="user", text=text))
        log.write(f"[bold cyan]You:[/bold cyan] {text}")
        self._refresh_session_list()

        self._stream_agent_response(text, session)

    @work(thread=True)
    def _stream_agent_response(self, user_input: str, session: ChatSession) -> None:
        """Call the real agent and stream tokens back to the RichLog."""
        log    = self.query_one("#chat-log", RichLog)
        status = self.query_one("#agent-status", Static)

        self._streaming = True
        self.app.call_from_thread(
            status.update, "[bold yellow]● thinking…[/bold yellow]"
        )

        agent, err = _get_agent()

        if agent is None:
            msg = f"Agent unavailable: {err}"
            self.app.call_from_thread(
                log.write, f"[bold red]Aki:[/bold red] [dim]{msg}[/dim]"
            )
            session.messages.append(ChatMessage(role="agent", text=msg))
            self.app.call_from_thread(status.update, "[dim]● offline[/dim]")
            self._streaming = False
            return

        # Collect the full response by running the async generator in a new event loop
        full_response = []

        async def _collect():
            self.app.call_from_thread(
                log.write, "[bold green]Aki:[/bold green] "
            )
            token_buf = []
            try:
                async for token in agent.stream_chat(
                    user_input=user_input,
                    project=session.project,
                    session_id=session.session_id,
                ):
                    token_buf.append(token)
                    full_response.append(token)
                    # Flush to UI every ~50 chars for smooth streaming
                    combined = "".join(token_buf)
                    if len(combined) >= 50 or "\n" in combined:
                        self.app.call_from_thread(log.write, combined)
                        token_buf.clear()
                # Flush remaining
                if token_buf:
                    self.app.call_from_thread(log.write, "".join(token_buf))
            except Exception as e:
                self.app.call_from_thread(
                    log.write, f"[red][error: {e}][/red]"
                )

        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_collect())
        finally:
            loop.close()

        complete = "".join(full_response)
        session.messages.append(ChatMessage(role="agent", text=complete))
        self._streaming = False
        self.app.call_from_thread(status.update, "[bold green]● ready[/bold green]")
        self.app.call_from_thread(self._refresh_session_list)

        # Refresh task summary in case agent added tasks
        try:
            self.app.call_from_thread(
                self.query_one("#task-summary", Static).update,
                _build_summary_text()
            )
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_active(self) -> ChatSession:
        for s in _sessions:
            if s.id == self._active_id:
                return s
        return _sessions[0]

    def on_focus(self) -> None:
        try:
            self.query_one("#task-summary", Static).update(_build_summary_text())
        except Exception:
            pass
