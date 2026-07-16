"""Kanban board tab — three columns: Todo / In Progress / Done."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from agentos.cockpit.tui.task_model import (
    DEFAULT_TASKS,
    PRIORITY_COLOR,
    PRIORITY_ICON,
    Task,
    stats,
)

_tasks: list[Task] = list(DEFAULT_TASKS)

COLUMNS: list[tuple[str, str]] = [
    ("todo",        "📥 Todo"),
    ("in_progress", "⚡ In Progress"),
    ("done",        "✅ Done"),
]


def get_tasks() -> list[Task]:
    return _tasks


class KanbanCard(ListItem):
    """A task card inside a kanban column."""

    def __init__(self, aki_task: Task) -> None:
        super().__init__()
        self._aki_task = aki_task

    def compose(self) -> ComposeResult:
        icon  = PRIORITY_ICON[self._aki_task.priority]
        color = PRIORITY_COLOR[self._aki_task.priority]
        yield Label(
            f"{icon} [{color}]{self._aki_task.title}[/{color}]\n[dim]{self._aki_task.category}[/dim]",
            markup=True,
        )

    def refresh_card(self) -> None:
        icon  = PRIORITY_ICON[self._aki_task.priority]
        color = PRIORITY_COLOR[self._aki_task.priority]
        self.query_one(Label).update(
            f"{icon} [{color}]{self._aki_task.title}[/{color}]\n[dim]{self._aki_task.category}[/dim]"
        )


class KanbanColumn(Widget):
    """A single kanban column."""

    DEFAULT_CSS = """
    KanbanColumn {
        width: 1fr;
        height: 1fr;
        border: solid $accent-darken-1;
        margin: 0 1;
        layout: vertical;
    }
    KanbanColumn > .col-header {
        height: 3;
        width: 1fr;
        content-align: center middle;
        text-style: bold;
        background: $panel-lighten-1;
        color: $text;
        border-bottom: solid $accent;
        padding: 0 1;
    }
    KanbanColumn > ScrollableContainer {
        height: 1fr;
        overflow-y: auto;
    }
    KanbanCard {
        margin: 0 0 1 0;
        padding: 1 1;
        border: solid $panel-lighten-1;
    }
    KanbanCard.-highlighted {
        border: solid yellow;
    }
    """

    def __init__(self, status: str, title: str) -> None:
        super().__init__()
        self._status = status
        self._title  = title

    def compose(self) -> ComposeResult:
        count = sum(1 for t in _tasks if t.status == self._status)
        yield Static(f"{self._title} ({count})", classes="col-header")
        with ScrollableContainer():
            yield ListView(
                *[KanbanCard(t) for t in _tasks if t.status == self._status],
                id=f"col-{self._status}",
            )

    def refresh_column(self) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        count = 0
        for t in _tasks:
            if t.status == self._status:
                lv.append(KanbanCard(t))
                count += 1
        self.query_one(".col-header").update(f"{self._title} ({count})")


class KanbanTab(Widget):
    """Interactive Kanban board."""

    DEFAULT_CSS = """
    KanbanTab {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }
    #kanban-stats {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 2;
        color: $text;
    }
    #kanban-body {
        height: 1fr;
        layout: horizontal;
    }
    #kanban-add {
        height: 3;
        background: $panel;
        border-top: solid $accent;
        layout: horizontal;
        padding: 0 1;
    }
    #kanban-add Input { width: 1fr; }
    #cat-input { width: 18; margin-left: 1; }
    #kanban-add Button { width: 10; margin-left: 1; }
    #kanban-hint {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        done, total = stats(_tasks)
        yield Static(
            f"[bold]🗂 Kanban[/bold]  [green]{done}[/green]/[white]{total}[/white] done",
            id="kanban-stats",
            markup=True,
        )
        with Horizontal(id="kanban-body"):
            for status, title in COLUMNS:
                yield KanbanColumn(status, title)

        with Horizontal(id="kanban-add"):
            yield Input(placeholder="Card title…", id="kanban-input")
            yield Input(placeholder="Category", id="cat-input")
            yield Button("+ Add", id="kanban-btn", variant="success")

        yield Static(
            " [→] promote  [←] demote  [D] delete",
            id="kanban-hint",
            markup=True,
        )

    def on_key(self, event) -> None:
        focused = self.app.focused
        if not isinstance(focused, ListView):
            return
        card = focused.highlighted_child
        if not isinstance(card, KanbanCard):
            return

        if event.key == "right":
            card._aki_task.advance()
            self._full_refresh()
            self.app.notify(f"→ {card._aki_task.status.replace('_', ' ').title()}")
        elif event.key == "left":
            card._aki_task.regress()
            self._full_refresh()
            self.app.notify(f"← {card._aki_task.status.replace('_', ' ').title()}")
        elif event.key.lower() == "d":
            _tasks.remove(card._aki_task)
            self._full_refresh()
            self.app.notify(f"Deleted: {card._aki_task.title}", severity="warning")

    @on(Button.Pressed, "#kanban-btn")
    def _on_add(self) -> None:
        self._add_card()

    @on(Input.Submitted, "#kanban-input")
    @on(Input.Submitted, "#cat-input")
    def _on_input(self) -> None:
        self._add_card()

    def _add_card(self) -> None:
        title_inp = self.query_one("#kanban-input", Input)
        cat_inp   = self.query_one("#cat-input", Input)
        title = title_inp.value.strip()
        if not title:
            return
        cat = cat_inp.value.strip() or "General"
        _tasks.append(Task(title=title, category=cat, priority="medium", status="todo"))
        title_inp.value = ""
        cat_inp.value   = ""
        self._full_refresh()
        self.app.notify(f"Added: {title} [{cat}]")

    def _full_refresh(self) -> None:
        for col in self.query(KanbanColumn):
            col.refresh_column()
        done, total = stats(_tasks)
        self.query_one("#kanban-stats", Static).update(
            f"[bold]🗂 Kanban[/bold]  [green]{done}[/green]/[white]{total}[/white] done"
        )
