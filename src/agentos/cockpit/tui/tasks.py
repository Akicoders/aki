"""Full-featured interactive Task Board for the Aki Cockpit."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from agentos.cockpit.tui.task_model import (
    DEFAULT_TASKS,
    PRIORITY_COLOR,
    PRIORITY_ICON,
    Task,
    get_categories,
    stats,
)

# Session-scoped mutable task list (shared with Chat sidebar)
_tasks: list[Task] = list(DEFAULT_TASKS)


def get_tasks() -> list[Task]:
    return _tasks


class TaskItem(ListItem):
    """A single task row inside the ListView."""

    def __init__(self, task: Task) -> None:
        super().__init__()
        self.task = task

    def compose(self) -> ComposeResult:
        check = "✅" if self.task.done else "⬜"
        icon  = PRIORITY_ICON[self.task.priority]
        color = PRIORITY_COLOR[self.task.priority]
        text  = f"{check} {icon}  [{color}]{self.task.title}[/{color}]"
        yield Label(text, markup=True)

    def refresh_label(self) -> None:
        check = "✅" if self.task.done else "⬜"
        icon  = PRIORITY_ICON[self.task.priority]
        color = PRIORITY_COLOR[self.task.priority]
        text  = f"{check} {icon}  [{color}]{self.task.title}[/{color}]"
        self.query_one(Label).update(text)

    def toggle(self) -> None:
        self.task.done = not self.task.done
        self.refresh_label()


class CategoryHeader(ListItem):
    """Non-interactive section header separating task categories."""

    DISABLED = True

    def __init__(self, category: str) -> None:
        super().__init__(disabled=True)
        self.category = category

    def compose(self) -> ComposeResult:
        yield Label(f"[bold cyan]── {self.category} ──[/bold cyan]", markup=True)


class TaskBoardTab(Vertical):
    """Full-featured interactive task board."""

    DEFAULT_CSS = """
    TaskBoardTab {
        padding: 0;
    }
    #stats-bar {
        height: 3;
        background: $panel;
        padding: 1 2;
        border-bottom: solid $accent;
        color: $text;
    }
    #filter-label {
        margin-left: 2;
        color: $text-muted;
    }
    #board-body {
        height: 1fr;
    }
    #category-panel {
        width: 20;
        border-right: solid $accent-darken-2;
        padding: 1 1;
    }
    #category-list {
        height: 1fr;
    }
    #task-scroll {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
    }
    #task-list {
        height: auto;
    }
    #add-bar {
        height: 3;
        background: $panel;
        border-top: solid $accent;
        padding: 0 1;
        layout: horizontal;
    }
    #add-input {
        width: 1fr;
    }
    #add-btn {
        width: 10;
        margin-left: 1;
    }
    #hint-bar {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    CategoryHeader {
        background: transparent;
    }
    """

    filter_pending: reactive[bool] = reactive(False)
    active_category: reactive[str] = reactive("All")

    def compose(self) -> ComposeResult:
        # ── Stats bar ──────────────────────────────────────────────────────────
        done, total = stats(_tasks)
        pct = int(done / total * 100) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        with Horizontal(id="stats-bar"):
            yield Static(
                f"[bold]📋 Tasks[/bold]  [green]{done}[/green]/[white]{total}[/white]  "
                f"[cyan]{bar}[/cyan]  [yellow]{pct}%[/yellow]",
                markup=True,
            )
            yield Static("", id="filter-label")

        # ── Board body ─────────────────────────────────────────────────────────
        with Horizontal(id="board-body"):
            # Category sidebar
            with Vertical(id="category-panel"):
                yield Label("[bold]Filter[/bold]", markup=True)
                cats = ["All"] + get_categories(_tasks)
                yield ListView(
                    *[ListItem(Label(c)) for c in cats],
                    id="category-list",
                )

            # Tasks scroll area
            with ScrollableContainer(id="task-scroll"):
                yield ListView(id="task-list")

        # ── Add task bar ────────────────────────────────────────────────────────
        with Horizontal(id="add-bar"):
            yield Input(placeholder="Add a new task… (press Enter)", id="add-input")
            yield Button("+ Add", id="add-btn", variant="success")

        # ── Hint bar ────────────────────────────────────────────────────────────
        yield Static(
            " [Enter/Space] toggle  [D] delete  [F] filter pending  [Tab] focus input",
            id="hint-bar",
            markup=True,
        )

    def on_mount(self) -> None:
        self._refresh_task_list()

    # ── Keybindings ────────────────────────────────────────────────────────────

    def on_key(self, event) -> None:
        key = event.key.lower()
        if key == "f":
            self.filter_pending = not self.filter_pending
            label = self.query_one("#filter-label", Static)
            label.update("[yellow][ Pending only ][/yellow]" if self.filter_pending else "")
            self._refresh_task_list()

        elif key == "d":
            task_list = self.query_one("#task-list", ListView)
            if task_list.highlighted_child and isinstance(task_list.highlighted_child, TaskItem):
                t = task_list.highlighted_child.task
                _tasks.remove(t)
                self._refresh_task_list()
                self.app.notify(f"Deleted: {t.title}", severity="warning")

    # ── Events ────────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Toggle a task or switch category filter."""
        if event.control.id == "task-list":
            if isinstance(event.item, TaskItem):
                event.item.toggle()
                self._update_stats()

        elif event.control.id == "category-list":
            if isinstance(event.item, ListItem):
                label = event.item.query_one(Label)
                self.active_category = str(label.renderable)
                self._refresh_task_list()

    @on(Button.Pressed, "#add-btn")
    def _on_add_button(self) -> None:
        self._add_task()

    @on(Input.Submitted, "#add-input")
    def _on_add_input(self, event: Input.Submitted) -> None:
        self._add_task()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add_task(self) -> None:
        inp = self.query_one("#add-input", Input)
        title = inp.value.strip()
        if not title:
            return
        cat = self.active_category if self.active_category != "All" else "General"
        new_task = Task(title=title, category=cat, priority="medium")
        _tasks.append(new_task)
        inp.value = ""
        self._refresh_task_list()
        self.app.notify(f"Added: {new_task.title}")

    def _refresh_task_list(self) -> None:
        """Rebuild the task list based on active filters."""
        task_list = self.query_one("#task-list", ListView)
        task_list.clear()

        visible = [
            t for t in _tasks
            if (self.active_category == "All" or t.category == self.active_category)
            and (not self.filter_pending or not t.done)
        ]

        # Group by category
        shown_cats: list[str] = []
        for task in visible:
            if task.category not in shown_cats:
                shown_cats.append(task.category)
                if self.active_category == "All":
                    task_list.append(CategoryHeader(task.category))
            task_list.append(TaskItem(task))

        self._update_stats()

    def _update_stats(self) -> None:
        done, total = stats(_tasks)
        pct = int(done / total * 100) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        self.query_one("#stats-bar Static", Static).update(
            f"[bold]📋 Tasks[/bold]  [green]{done}[/green]/[white]{total}[/white]  "
            f"[cyan]{bar}[/cyan]  [yellow]{pct}%[/yellow]",
        )
