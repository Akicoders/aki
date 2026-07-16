"""Shared task data model for the Aki Cockpit TUI."""
from dataclasses import dataclass, field
from typing import Literal

Priority = Literal["high", "medium", "low"]

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


# ─── Default task list ────────────────────────────────────────────────────────
DEFAULT_TASKS: list[Task] = [
    Task("Setup Textual environment",       "Setup",   "high",   done=True),
    Task("Create interactive tabs",          "Setup",   "high",   done=True),
    Task("Fix startup performance",          "Setup",   "medium", done=True),
    Task("Connect agent backend to Chat",    "Backend", "high",   done=False),
    Task("Implement persistent task storage","Backend", "medium", done=False),
    Task("Hook real agent responses",        "Backend", "high",   done=False),
    Task("Add keybinding help overlay",      "UX",      "low",    done=False),
    Task("Polish chat sidebar layout",       "UX",      "medium", done=False),
    Task("Write README for the TUI",         "Docs",    "low",    done=False),
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
