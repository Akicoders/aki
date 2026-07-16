from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ListView, ListItem, Label
from agentos.cockpit.tui.chat import INITIAL_TASKS


class TaskItem(ListItem):
    """A single toggleable task item."""

    def __init__(self, done: bool, description: str) -> None:
        super().__init__()
        self._done = done
        self._description = description

    def compose(self) -> ComposeResult:
        icon = "✅" if self._done else "⬜"
        yield Label(f"{icon} {self._description}", id=f"lbl-{id(self)}")

    def toggle(self) -> None:
        self._done = not self._done
        icon = "✅" if self._done else "⬜"
        self.query_one(Label).update(f"{icon} {self._description}")


class TaskBoardTab(Vertical):
    """The interactive Task Board tab."""

    DEFAULT_CSS = """
    TaskBoardTab {
        padding: 1 2;
    }
    #task-list {
        height: 100%;
        border: solid green;
    }
    """

    def compose(self) -> ComposeResult:
        yield ListView(
            *[TaskItem(done, name) for done, name in INITIAL_TASKS],
            id="task-list",
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Toggle a task when selected with Enter or Space."""
        if isinstance(event.item, TaskItem):
            event.item.toggle()
