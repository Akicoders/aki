"""Shared task data model for the Aki Cockpit TUI."""
from dataclasses import dataclass, field
from typing import Literal

Priority = Literal["high", "medium", "low"]
Status   = Literal["todo", "in_progress", "done"]

PRIORITY_ICON: dict[Priority, str] = {
    "high":   "🔴",
    "medium": "🟡",
    "low":    "🟢",
}

PRIORITY_COLOR: dict[Priority, str] = {
    "high":   "red",
    "medium": "yellow",
    "low":    "green",
}


@dataclass
class Task:
    title: str
    category: str
    priority: Priority = "medium"
    done: bool = False
    status: Status = "todo"

    def advance(self) -> None:
        """Move to the next kanban column."""
        order: list[Status] = ["todo", "in_progress", "done"]
        idx = order.index(self.status)
        if idx < len(order) - 1:
            self.status = order[idx + 1]
        self.done = self.status == "done"

    def regress(self) -> None:
        """Move to the previous kanban column."""
        order: list[Status] = ["todo", "in_progress", "done"]
        idx = order.index(self.status)
        if idx > 0:
            self.status = order[idx - 1]
        self.done = self.status == "done"


# ─── Default task list ────────────────────────────────────────────────────────
DEFAULT_TASKS: list[Task] = [
    Task("Setup Textual environment",        "Setup",   "high",   done=True,  status="done"),
    Task("Create interactive tabs",           "Setup",   "high",   done=True,  status="done"),
    Task("Fix startup performance",           "Setup",   "medium", done=True,  status="done"),
    Task("Connect agent backend to Chat",     "Backend", "high",   done=False, status="in_progress"),
    Task("Implement persistent task storage", "Backend", "medium", done=False, status="todo"),
    Task("Hook real agent responses",         "Backend", "high",   done=False, status="todo"),
    Task("Add keybinding help overlay",       "UX",      "low",    done=False, status="todo"),
    Task("Polish chat sidebar layout",        "UX",      "medium", done=False, status="in_progress"),
    Task("Write README for the TUI",          "Docs",    "low",    done=False, status="todo"),
]


def get_categories(tasks: list[Task]) -> list[str]:
    seen: list[str] = []
    for t in tasks:
        if t.category not in seen:
            seen.append(t.category)
    return seen


def stats(tasks: list[Task]) -> tuple[int, int]:
    """Return (done_count, total_count)."""
    return sum(1 for t in tasks if t.done), len(tasks)
