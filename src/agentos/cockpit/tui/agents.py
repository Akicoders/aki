"""Agents tab — view, create, and edit AI agent profiles.

List + detail pattern, matching the conventions of `kanban.py` / `sdd.py`.
Profiles are `AgentProfile` (see `agentos.agents.profiles`), merged from
static config and the Cockpit-local JSON store (see
`agentos.agents.profile_store`) so edits made here never touch config.yaml
and never break the production `AgentOS` wiring that still loads profiles
straight from config.
"""
from __future__ import annotations

from typing import Optional

from pydantic import ValidationError
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from agentos.agents.profiles import AgentProfile, DelegationMetadata, MemoryPolicy, ToolPolicy
from agentos.agents.profile_store import delete_profile, load_merged_profiles, upsert_profile

ROLE_OPTIONS = [("planner", "planner"), ("builder", "builder"), ("reviewer", "reviewer"), ("custom", "custom")]
MEMORY_OPTIONS = [
    ("project", "project"),
    ("session", "session"),
    ("global", "global"),
    ("disabled", "disabled"),
]

ROLE_ICON = {"planner": "🧭", "builder": "🛠️", "reviewer": "🔍", "custom": "✨"}


def _config_profiles() -> list[AgentProfile]:
    """Best-effort read of config-declared profiles (may be empty/unavailable)."""
    try:
        from agentos.core.config import get_config

        return list(get_config().agent_profiles.profiles)
    except Exception:
        return []


class AgentCard(ListItem):
    """A profile row in the agents list."""

    def __init__(self, profile: AgentProfile) -> None:
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        icon = ROLE_ICON.get(self.profile.role, "🤖")
        model = self.profile.model or "default"
        yield Label(
            f"{icon} [bold]{self.profile.name}[/bold]\n"
            f"[dim]{self.profile.role} · {model}[/dim]",
            markup=True,
        )


class AgentsTab(Widget):
    """Interactive agent-profile manager: list on the left, form on the right."""

    DEFAULT_CSS = """
    AgentsTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    #agents-left-panel {
        width: 34;
        height: 1fr;
        border-right: solid $accent-darken-1;
        background: $panel;
        layout: vertical;
    }
    #agents-header-area {
        padding: 1 1;
        border-bottom: solid $accent-darken-2;
    }
    #agents-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    #agents-list {
        height: 1fr;
    }
    #new-agent-btn {
        width: 1fr;
        margin-top: 1;
    }
    #agents-right-panel {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }
    #agents-form-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 3;
    }
    #agents-form-scroll Label {
        margin-top: 1;
    }
    #agents-form-scroll Input, #agents-form-scroll Select {
        width: 1fr;
    }
    #agents-form-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    #agents-toolbar {
        height: 3;
        background: $panel;
        border-top: solid $accent;
        layout: horizontal;
        padding: 0 2;
    }
    #agents-toolbar Button {
        margin-right: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._profiles: list[AgentProfile] = load_merged_profiles(_config_profiles())
        self._selected_id: Optional[str] = None

    # ── Compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="agents-left-panel"):
            with Vertical(id="agents-header-area"):
                yield Static("🤖 Agent Profiles", id="agents-title")
                yield Button("+ New Profile", id="new-agent-btn", variant="success")
            yield ListView(*[AgentCard(p) for p in self._profiles], id="agents-list")

        with Vertical(id="agents-right-panel"):
            with ScrollableContainer(id="agents-form-scroll"):
                yield Static("Select a profile or create a new one", id="agents-form-title")

                yield Label("Id (lowercase, digits, - or _)")
                yield Input(placeholder="my-agent", id="f-id")

                yield Label("Name")
                yield Input(placeholder="My Agent", id="f-name")

                yield Label("Description")
                yield Input(placeholder="What this agent does", id="f-description")

                yield Label("Role")
                yield Select(ROLE_OPTIONS, value="custom", id="f-role", allow_blank=False)

                yield Label("Prompt template")
                yield Input(placeholder="System prompt / instructions", id="f-prompt")

                yield Label("Model (optional)")
                yield Input(placeholder="qwen-max, gpt-4o, …", id="f-model")

                yield Label("Temperature (optional)")
                yield Input(placeholder="0.0 - 2.0", id="f-temperature")

                yield Label("Max iterations (optional)")
                yield Input(placeholder="e.g. 10", id="f-max-iterations")

                yield Label("Allowed tools (comma-separated)")
                yield Input(placeholder="fs.read, fs.write, shell.exec", id="f-tools")
                yield Checkbox("Deny all tools", id="f-deny-all")

                yield Label("Memory scope")
                yield Select(MEMORY_OPTIONS, value="session", id="f-memory", allow_blank=False)

                yield Checkbox("Delegation enabled", id="f-delegation-enabled")
                yield Label("Delegation strategy (optional)")
                yield Input(placeholder="round-robin, …", id="f-delegation-strategy")

            with Horizontal(id="agents-toolbar"):
                yield Button("💾 Save", id="save-agent-btn", variant="primary")
                yield Button("🗑 Delete", id="delete-agent-btn", variant="error", disabled=True)
                yield Button("✖ Clear", id="clear-agent-btn")

    # ── Selection ────────────────────────────────────────────────────────

    @on(ListView.Selected, "#agents-list")
    def _on_select(self, event: ListView.Selected) -> None:
        card = event.item
        if isinstance(card, AgentCard):
            self._load_into_form(card.profile)

    def _load_into_form(self, profile: AgentProfile) -> None:
        self._selected_id = profile.id
        self.query_one("#agents-form-title", Static).update(f"Editing: {profile.name}")
        self.query_one("#f-id", Input).value = profile.id
        self.query_one("#f-id", Input).disabled = True
        self.query_one("#f-name", Input).value = profile.name
        self.query_one("#f-description", Input).value = profile.description
        self.query_one("#f-role", Select).value = profile.role
        self.query_one("#f-prompt", Input).value = profile.prompt_template
        self.query_one("#f-model", Input).value = profile.model or ""
        self.query_one("#f-temperature", Input).value = (
            "" if profile.temperature is None else str(profile.temperature)
        )
        self.query_one("#f-max-iterations", Input).value = (
            "" if profile.max_iterations is None else str(profile.max_iterations)
        )
        self.query_one("#f-tools", Input).value = ", ".join(profile.tools.allowed)
        self.query_one("#f-deny-all", Checkbox).value = profile.tools.deny_all
        self.query_one("#f-memory", Select).value = profile.memory.scope
        self.query_one("#f-delegation-enabled", Checkbox).value = profile.delegation.enabled
        self.query_one("#f-delegation-strategy", Input).value = profile.delegation.strategy or ""
        self.query_one("#delete-agent-btn", Button).disabled = False

    # ── Toolbar actions ──────────────────────────────────────────────────

    @on(Button.Pressed, "#new-agent-btn")
    @on(Button.Pressed, "#clear-agent-btn")
    def _on_clear(self) -> None:
        self._selected_id = None
        self.query_one("#agents-form-title", Static).update("New profile")
        for field_id in ("#f-id", "#f-name", "#f-description", "#f-prompt", "#f-model",
                          "#f-temperature", "#f-max-iterations", "#f-tools", "#f-delegation-strategy"):
            self.query_one(field_id, Input).value = ""
        self.query_one("#f-id", Input).disabled = False
        self.query_one("#f-role", Select).value = "custom"
        self.query_one("#f-memory", Select).value = "session"
        self.query_one("#f-deny-all", Checkbox).value = False
        self.query_one("#f-delegation-enabled", Checkbox).value = False
        self.query_one("#delete-agent-btn", Button).disabled = True

    @on(Button.Pressed, "#save-agent-btn")
    def _on_save(self) -> None:
        allowed_raw = self.query_one("#f-tools", Input).value
        allowed = [t.strip() for t in allowed_raw.split(",") if t.strip()]
        deny_all = self.query_one("#f-deny-all", Checkbox).value

        temp_raw = self.query_one("#f-temperature", Input).value.strip()
        iter_raw = self.query_one("#f-max-iterations", Input).value.strip()

        try:
            temperature = float(temp_raw) if temp_raw else None
        except ValueError:
            self.app.notify("Temperature must be a number", severity="error")
            return
        try:
            max_iterations = int(iter_raw) if iter_raw else None
        except ValueError:
            self.app.notify("Max iterations must be an integer", severity="error")
            return

        strategy = self.query_one("#f-delegation-strategy", Input).value.strip() or None

        try:
            profile = AgentProfile(
                id=self.query_one("#f-id", Input).value.strip(),
                name=self.query_one("#f-name", Input).value.strip(),
                description=self.query_one("#f-description", Input).value.strip(),
                role=self.query_one("#f-role", Select).value,
                prompt_template=self.query_one("#f-prompt", Input).value.strip(),
                model=self.query_one("#f-model", Input).value.strip() or None,
                temperature=temperature,
                max_iterations=max_iterations,
                tools=ToolPolicy(allowed=allowed, deny_all=deny_all),
                memory=MemoryPolicy(scope=self.query_one("#f-memory", Select).value),
                delegation=DelegationMetadata(
                    enabled=self.query_one("#f-delegation-enabled", Checkbox).value,
                    strategy=strategy,
                ),
            )
        except ValidationError as e:
            self.app.notify(f"Invalid profile: {e.errors()[0]['msg']}", severity="error")
            return

        upsert_profile(profile)
        self._selected_id = profile.id
        self._refresh_list()
        self.app.notify(f"Saved profile: {profile.name}")

    @on(Button.Pressed, "#delete-agent-btn")
    def _on_delete(self) -> None:
        if not self._selected_id:
            return
        deleted_id = self._selected_id
        delete_profile(deleted_id, _config_profiles())
        self._selected_id = None
        self._refresh_list()
        self._on_clear()
        self.app.notify(f"Deleted profile: {deleted_id}", severity="warning")

    def _refresh_list(self) -> None:
        self._profiles = load_merged_profiles(_config_profiles())
        lv = self.query_one("#agents-list", ListView)
        lv.clear()
        for p in self._profiles:
            lv.append(AgentCard(p))
