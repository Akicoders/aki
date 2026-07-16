"""Multi-session Agent Chat tab — connected to the real Aki agent via stream_chat."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RichLog,
    Static,
)

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
    group: str = "General"


# ── Persistence ─────────────────────────────────────────────────────────────

def get_sessions_file_path() -> Path:
    path = Path("data/chat_sessions.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_sessions() -> list[ChatSession]:
    """Load persisted chat sessions from disk.

    If no saved file exists yet, fall back to a single empty default
    session — never fabricate historical data.
    """
    path = get_sessions_file_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions = []
            for item in data:
                sessions.append(
                    ChatSession(
                        name=item["name"],
                        project=item.get("project", "cockpit"),
                        id=item.get("id") or str(uuid.uuid4())[:8],
                        session_id=item.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}",
                        messages=[
                            ChatMessage(role=m["role"], text=m["text"])
                            for m in item.get("messages", [])
                        ],
                        group=item.get("group", "General"),
                    )
                )
            if sessions:
                return sessions
        except Exception:
            pass
    return [ChatSession(name="Session 1")]


def save_sessions(sessions: list[ChatSession]) -> None:
    path = get_sessions_file_path()
    try:
        data = [
            {
                "name": s.name,
                "project": s.project,
                "id": s.id,
                "session_id": s.session_id,
                "group": s.group,
                "messages": [
                    {"role": m.role, "text": m.text} for m in s.messages
                ],
            }
            for s in sessions
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


_sessions: list[ChatSession] = load_sessions()


def get_sessions() -> list[ChatSession]:
    return _sessions


# ── Model selection persistence ────────────────────────────────────────────────

def get_model_settings_file_path() -> Path:
    path = Path("data/cockpit_settings.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_selected_model() -> str | None:
    """Load the persisted Qwen model override, or None to use config defaults."""
    path = get_model_settings_file_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            model = data.get("qwen_model")
            return model or None
        except Exception:
            pass
    return None


def save_selected_model(model: str | None) -> None:
    path = get_model_settings_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"qwen_model": model}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def set_active_model(model: str | None) -> None:
    """Apply `model` as the agent's active Qwen model override and persist it."""
    save_selected_model(model)
    agent, _ = _get_agent()
    if agent is not None:
        agent.active_model = model


def get_active_model() -> str | None:
    agent, _ = _get_agent()
    if agent is not None:
        return agent.active_model
    return load_selected_model()


# ── Agent singleton (lazy) ─────────────────────────────────────────────────────

_agent = None

def _get_agent():
    global _agent
    if _agent is None:
        try:
            from agentos.agent.core import get_agent
            _agent = get_agent()
            _agent.active_model = load_selected_model()
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
            f"[bold]{done}[/bold][dim]/{total}[/dim]  "
            f"[cyan]{bar}[/cyan] [dim]{pct}%[/dim]",
            "[dim]" + "─" * 20 + "[/dim]",
        ]
        for cat in get_categories(tasks):
            cat_tasks = [t for t in tasks if t.category == cat]
            done_cat = sum(1 for t in cat_tasks if t.done)
            cat_total = len(cat_tasks)
            complete = cat_total > 0 and done_cat == cat_total
            mark = "✓" if complete else "•"
            mark_color = "green" if complete else "cyan"
            count_color = "green" if complete else "dim"
            lines.append(
                f"[{mark_color}]{mark}[/{mark_color}] {cat}"
                f"  [{count_color}]{done_cat}/{cat_total}[/{count_color}]"
            )
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


class GroupHeader(ListItem):
    """Non-selectable header row grouping sessions by folder/group."""

    def __init__(self, group: str) -> None:
        super().__init__(disabled=True)
        self._group = group

    def compose(self) -> ComposeResult:
        yield Label(f"[bold dim]── {self._group} ──[/bold dim]", markup=True)


# ── Main Chat Tab ─────────────────────────────────────────────────────────────

class ChatTab(Widget):
    """Multi-session chat tab connected to the Aki agent via stream_chat."""

    can_focus = True

    # Resizable panel widths (cells). Adjusted via keybindings below.
    SIDEBAR_MIN, SIDEBAR_MAX, SIDEBAR_STEP = 16, 48, 4
    TASKS_MIN, TASKS_MAX, TASKS_STEP = 16, 48, 4

    sidebar_width = reactive(22)
    tasks_width   = reactive(24)

    BINDINGS = [
        Binding("ctrl+left",  "resize_sidebar(-1)", "Sidebar −", show=False),
        Binding("ctrl+right", "resize_sidebar(1)",  "Sidebar +", show=False),
        Binding("ctrl+up",    "resize_tasks(1)",     "Tasks +",   show=False),
        Binding("ctrl+down",  "resize_tasks(-1)",    "Tasks −",   show=False),
    ]

    DEFAULT_CSS = """
    ChatTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    #session-panel {
        width: 22;
        min-width: 16;
        max-width: 48;
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
    #chat-loading {
        width: 3;
        height: 1;
        display: none;
        color: yellow;
    }
    #chat-loading.-visible { display: block; }

    #task-panel {
        width: 24;
        min-width: 16;
        max-width: 48;
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
    #resize-hint {
        color: $text-muted;
        text-style: dim;
        margin-bottom: 1;
    }
    #task-summary {
        padding: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._active_id = _sessions[0].id
        self._streaming  = False
        self._renaming   = False

    def _grouped_session_items(self) -> list:
        """Build ListItem widgets grouped by session.group, preserving the
        order in which each group first appears."""
        groups: dict[str, list[ChatSession]] = {}
        for s in _sessions:
            groups.setdefault(s.group, []).append(s)
        items = []
        for group_name, group_sessions in groups.items():
            if len(groups) > 1:
                items.append(GroupHeader(group_name))
            items.extend(SessionItem(s) for s in group_sessions)
        return items

    def _rebuild_session_list(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        for item in self._grouped_session_items():
            lv.append(item)
        self._refresh_session_list()

    def compose(self) -> ComposeResult:
        active = self._get_active()

        with Vertical(id="session-panel"):
            yield Static("💬 Chats", id="session-panel-header", markup=True)
            yield ListView(*self._grouped_session_items(), id="session-list")
            with Horizontal(id="session-btn-row"):
                yield Button("+ New", id="new-session-btn", variant="success")
                yield Button("✎ Ren", id="ren-session-btn")
                yield Button("🗑 Del", id="del-session-btn", variant="error")

        with Vertical(id="chat-area"):
            with Horizontal(id="chat-header"):
                yield Static(f"[bold]{active.name}[/bold]", id="chat-header-title", markup=True)
                yield Static("● ready", id="agent-status", markup=True)
            yield RichLog(id="chat-log", highlight=True, markup=True, auto_scroll=True)
            with Horizontal(id="chat-input-row"):
                yield Input(placeholder="Message Aki… (Enter to send)", id="chat-input")
                yield LoadingIndicator(id="chat-loading")
                yield Button("Send", id="send-btn", variant="primary")

        with Vertical(id="task-panel"):
            yield Label("📋 Tasks", id="task-panel-title")
            yield Static(
                "[dim]ctrl+←/→ sidebar · ctrl+↑/↓ tasks[/dim]",
                id="resize-hint",
                markup=True,
            )
            yield Static(_build_summary_text(), id="task-summary", markup=True)

    def on_mount(self) -> None:
        self._load_session(self._get_active())
        self._refresh_session_list()
        self.query_one("#session-panel").styles.width = self.sidebar_width
        self.query_one("#task-panel").styles.width = self.tasks_width

    # ── Resizable panels ────────────────────────────────────────────────────────

    def watch_sidebar_width(self, width: int) -> None:
        try:
            self.query_one("#session-panel").styles.width = width
        except Exception:
            pass

    def watch_tasks_width(self, width: int) -> None:
        try:
            self.query_one("#task-panel").styles.width = width
        except Exception:
            pass

    def action_resize_sidebar(self, direction: int) -> None:
        new_width = self.sidebar_width + direction * self.SIDEBAR_STEP
        self.sidebar_width = max(self.SIDEBAR_MIN, min(self.SIDEBAR_MAX, new_width))

    def action_resize_tasks(self, direction: int) -> None:
        new_width = self.tasks_width + direction * self.TASKS_STEP
        self.tasks_width = max(self.TASKS_MIN, min(self.TASKS_MAX, new_width))

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
        self._rebuild_session_list()
        self._switch_to(new_s)
        save_sessions(_sessions)
        self.app.notify(f"Created {new_s.name}")

    @on(Button.Pressed, "#del-session-btn")
    def _on_del_session(self) -> None:
        if len(_sessions) <= 1:
            self.app.notify("Cannot delete the only session.", severity="warning")
            return
        active = self._get_active()
        _sessions.remove(active)
        self._rebuild_session_list()
        self._switch_to(_sessions[0])
        save_sessions(_sessions)
        self.app.notify(f"Deleted {active.name}", severity="warning")

    @on(Button.Pressed, "#ren-session-btn")
    def _on_rename_session(self) -> None:
        """Enter rename mode: repurpose the chat input to edit the active
        session's 'name' or 'name / group' (e.g. 'Backend API / BACKEND')."""
        active = self._get_active()
        inp = self.query_one("#chat-input", Input)
        current = active.name if active.group == "General" else f"{active.name} / {active.group}"
        inp.value = current
        inp.placeholder = "New name, or 'Name / Group' — Enter to confirm"
        self._renaming = True
        inp.focus()

    # ── Sending messages ──────────────────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    @on(Button.Pressed, "#send-btn")
    def _on_send(self, event) -> None:
        inp = self.query_one("#chat-input", Input)

        if self._renaming:
            text = inp.value.strip()
            inp.value = ""
            inp.placeholder = "Message Aki… (Enter to send)"
            self._renaming = False
            if text:
                session = self._get_active()
                if "/" in text:
                    name_part, group_part = text.split("/", 1)
                    session.name = name_part.strip() or session.name
                    session.group = group_part.strip() or "General"
                else:
                    session.name = text
                self.query_one("#chat-header-title", Static).update(
                    f"[bold]{session.name}[/bold]"
                )
                self._rebuild_session_list()
                save_sessions(_sessions)
                self.app.notify(f"Renamed to {session.name} ({session.group})")
            return

        if self._streaming:
            return
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""

        session = self._get_active()
        log     = self.query_one("#chat-log", RichLog)

        session.messages.append(ChatMessage(role="user", text=text))
        log.write(f"[bold cyan]You:[/bold cyan] {text}")
        self._refresh_session_list()
        save_sessions(_sessions)

        inp.disabled = True
        self.query_one("#send-btn", Button).disabled = True
        self.query_one("#chat-loading", LoadingIndicator).add_class("-visible")
        self.query_one("#agent-status", Static).update("[bold yellow]● thinking…[/bold yellow]")

        self._stream_agent_response(text, session)

    @work(thread=True)
    def _stream_agent_response(self, user_input: str, session: ChatSession) -> None:
        """Call the real agent and stream tokens back to the RichLog."""
        log    = self.query_one("#chat-log", RichLog)
        status = self.query_one("#agent-status", Static)
        inp    = self.query_one("#chat-input", Input)
        send_btn = self.query_one("#send-btn", Button)
        loading  = self.query_one("#chat-loading", LoadingIndicator)

        self._streaming = True
        full_response = []
        final_status = "[bold green]● ready[/bold green]"

        def _clear_busy_state(status_text: str) -> None:
            status.update(status_text)
            loading.remove_class("-visible")
            inp.disabled = False
            send_btn.disabled = False

        try:
            agent, err = _get_agent()

            if agent is None:
                msg = f"Agent unavailable: {err}"
                self.app.call_from_thread(
                    log.write, f"[bold red]Aki:[/bold red] [dim]{msg}[/dim]"
                )
                session.messages.append(ChatMessage(role="agent", text=msg))
                final_status = "[dim]● offline[/dim]"
                return

            # Collect the full response by running the async generator in a new event loop
            first_token_seen = False

            async def _collect():
                nonlocal first_token_seen
                token_buf = []
                try:
                    async for token in agent.stream_chat(
                        user_input=user_input,
                        project=session.project,
                        session_id=session.session_id,
                    ):
                        if not first_token_seen:
                            first_token_seen = True
                            self.app.call_from_thread(
                                log.write, "[bold green]Aki:[/bold green] "
                            )
                            self.app.call_from_thread(
                                status.update, "[bold yellow]● streaming…[/bold yellow]"
                            )
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
                    if not first_token_seen:
                        self.app.call_from_thread(
                            log.write, "[bold green]Aki:[/bold green] "
                        )
                    self.app.call_from_thread(
                        log.write, f"[red][error: {e}][/red]"
                    )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_collect())
            finally:
                loop.close()

            complete = "".join(full_response)
            session.messages.append(ChatMessage(role="agent", text=complete))
            self.app.call_from_thread(self._refresh_session_list)

            # Refresh task summary in case agent added tasks
            try:
                self.app.call_from_thread(
                    self.query_one("#task-summary", Static).update,
                    _build_summary_text()
                )
            except Exception:
                pass

            save_sessions(_sessions)
        except Exception as e:
            self.app.call_from_thread(
                log.write, f"[bold red]Error: {e}[/bold red]"
            )
            final_status = "[bold red]● error[/bold red]"
        finally:
            self._streaming = False
            self.app.call_from_thread(_clear_busy_state, final_status)

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
