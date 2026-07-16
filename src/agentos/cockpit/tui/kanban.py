"""Kanban board tab — three columns: Todo / In Progress / Done."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
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
    """A draggable-style task card inside a column."""

    def __init__(self, aki_task: Task) -> None:
        super().__init__()
        self._aki_task = aki_task

    def compose(self) -> ComposeResult:
        icon  = PRIORITY_ICON[self._aki_task.priority]
        color = PRIORITY_COLOR[self._aki_task.priority]
        yield Label(
            f"{icon} [{color}]{self._aki_task.title}[/{color}]\n"
            f"[dim]{self._aki_task.category}[/dim]",
            markup=True,
        )

    def refresh_card(self) -> None:
        icon  = PRIORITY_ICON[self._aki_task.priority]
        color = PRIORITY_COLOR[self._aki_task.priority]
        self.query_one(Label).update(
            f"{icon} [{color}]{self._aki_task.title}[/{color}]\n"
            f"[dim]{self._aki_task.category}[/dim]",
        )


class KanbanColumn(Vertical):
    """A single kanban column with header and scrollable card list."""

    DEFAULT_CSS = """
    KanbanColumn {
        width: 1fr;
        height: 100%;
        border: solid $accent-darken-1;
        margin: 0 1;
        padding: 0;
    }
    .col-header {
        height: 3;
        text-align: center;
        text-style: bold;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 1;
    }
    .col-scroll {
        height: 1fr;
        overflow-y: auto;
    }
    .col-list {
        height: auto;
    }
    KanbanCard {
        margin: 0 0 1 0;
        padding: 1 1;
        border: solid $panel-lighten-1;
    }
    KanbanCard:hover {
        border: solid $accent;
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
        yield Label(f"{self._title}  [dim]({count})[/dim]", classes="col-header", markup=True)
        with ScrollableContainer(classes="col-scroll"):
            yield ListView(
                *[KanbanCard(t) for t in _tasks if t.status == self._status],
                classes="col-list",
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
        self.query_one(Label).update(
            f"{self._title}  [dim]({count})[/dim]"
        )


class KanbanTab(Vertical):
    """Interactive Kanban board with three columns."""

    DEFAULT_CSS = """
    KanbanTab {
        padding: 0;
    }
    #kanban-header {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 2;
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
        with Horizontal(id="kanban-header"):
            yield Static(
                f"[bold]🗂 Kanban Board[/bold]  "
                f"[green]{done}[/green]/[white]{total}[/white] done",
                markup=True,
            )

        with Horizontal(id="kanban-body"):
            for status, title in COLUMNS:
                yield KanbanColumn(status, title)

        with Horizontal(id="kanban-add"):
            yield Input(placeholder="New card title…", id="kanban-input")
            yield Button("+ Add", id="kanban-btn", variant="success")

        yield Static(
            " [→] promote  [←] demote  [D] delete  [Tab] focus input",
            id="kanban-hint",
            markup=True,
        )

    def on_key(self, event) -> None:
        key = event.key

        # Find the currently focused ListView and its highlighted card
        focused = self.app.focused
        if not isinstance(focused, ListView):
            return
        card = focused.highlighted_child
        if not isinstance(card, KanbanCard):
            return

        if key == "right":
            card._aki_task.advance()
            self._full_refresh()
            self.app.notify(f"→ {card._aki_task.status.replace('_', ' ').title()}")

        elif key == "left":
            card._aki_task.regress()
            self._full_refresh()
            self.app.notify(f"← {card._aki_task.status.replace('_', ' ').title()}")

        elif key.lower() == "d":
            _tasks.remove(card._aki_task)
            self._full_refresh()
            self.app.notify(f"Deleted: {card._aki_task.title}", severity="warning")

    @on(Button.Pressed, "#kanban-btn")
    def _on_add(self) -> None:
        self._add_card()

    @on(Input.Submitted, "#kanban-input")
    def _on_input(self) -> None:
        self._add_card()

    def _add_card(self) -> None:
        inp = self.query_one("#kanban-input", Input)
        title = inp.value.strip()
        if not title:
            return
        new_task = Task(title=title, category="General", priority="medium", status="todo")
        _tasks.append(new_task)
        inp.value = ""
        self._full_refresh()
        self.app.notify(f"Added: {title}")

    def _full_refresh(self) -> None:
        """Rebuild all three columns and update the header stats."""
        for col in self.query(KanbanColumn):
            col.refresh_column()
        done, total = stats(_tasks)
        self.query_one("#kanban-header Static", Static).update(
            f"[bold]🗂 Kanban Board[/bold]  "
            f"[green]{done}[/green]/[white]{total}[/white] done",
        )
