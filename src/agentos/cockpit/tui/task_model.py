"""Shared task data model for the Aki Cockpit TUI."""
import re
from dataclasses import dataclass, field
from pathlib import Path
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
# Historically this held hand-written example tasks that were shown whenever
# no persisted kanban board existed — which made the board look "populated"
# even on a fresh project with no real work tracked. It is now empty; the
# real default comes from parsing the project's actual SDD tasks.md (see
# `discover_sdd_tasks_file` / `parse_sdd_tasks` below). If neither a
# persisted board nor an SDD tasks.md exists, the board starts empty.
DEFAULT_TASKS: list[Task] = []

_CHECKBOX_RE = re.compile(r"^-\s*\[( |x|X)\]\s*(?:\*\*)?(?:\d+(?:\.\d+)*\.?\s*)?(.+)$")
_PHASE_HEADING_RE = re.compile(r"^#{1,3}\s*(?:Phase\s+\S+\s*[—:-]?\s*)?(.+)$", re.IGNORECASE)


def discover_sdd_tasks_file(root: Path | None = None) -> Path | None:
    """Find the project's real SDD tasks.md, if any.

    Checks the conventional `docs/sdd/tasks.md` location first, then falls
    back to the most recently modified `tasks.md` under an active
    `openspec/changes/<change>/` directory (excluding the archive).
    """
    base = Path(root) if root is not None else Path.cwd()

    docs_tasks = base / "docs" / "sdd" / "tasks.md"
    if docs_tasks.exists():
        return docs_tasks

    changes_dir = base / "openspec" / "changes"
    if changes_dir.is_dir():
        candidates = [
            p
            for p in changes_dir.glob("*/tasks.md")
            if "archive" not in p.parts
        ]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)

    return None


def _priority_for(status: Status) -> Priority:
    return "low" if status == "done" else "medium"


def parse_sdd_tasks(path: Path) -> list[Task]:
    """Parse a Spec-Driven-Development `tasks.md` checklist into Tasks.

    Recognizes lines like `- [x] 1.2 Do the thing` (with optional Markdown
    bold around the numbering) grouped under the nearest preceding
    Markdown heading (used as the task category, e.g. "Phase 2: ...").
    Non-checklist content (tables, prose) is ignored.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    tasks: list[Task] = []
    category = "General"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = _PHASE_HEADING_RE.match(line)
            if heading:
                cleaned = re.sub(r"\s*\(PR[^)]*\)\s*$", "", heading.group(1).strip())
                category = cleaned or "General"
            continue
        m = _CHECKBOX_RE.match(line)
        if not m:
            continue
        checked = m.group(1).lower() == "x"
        title = m.group(2).strip()
        # Strip a leading Markdown bold marker on the task title, if any.
        title = title.lstrip("*").strip()
        if not title:
            continue
        status: Status = "done" if checked else "todo"
        tasks.append(
            Task(
                title=title,
                category=category,
                priority=_priority_for(status),
                done=checked,
                status=status,
            )
        )
    return tasks


def get_categories(tasks: list[Task]) -> list[str]:
    seen: list[str] = []
    for t in tasks:
        if t.category not in seen:
            seen.append(t.category)
    return seen


def stats(tasks: list[Task]) -> tuple[int, int]:
    """Return (done_count, total_count)."""
    return sum(1 for t in tasks if t.done), len(tasks)


import json

def get_tasks_file_path() -> Path:
    path = Path("data/kanban_tasks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def load_tasks() -> list[Task]:
    """Load the kanban board.

    Precedence:
    1. A previously persisted board (`data/kanban_tasks.json`) — the user's
       own edits always win once they exist.
    2. The project's real SDD `tasks.md` (see `discover_sdd_tasks_file`),
       parsed into cards — this is the real source of truth for project
       work, shared with the SDD Hub tab and `agentos sdd` commands.
    3. An empty board. No hardcoded example tasks are shown.
    """
    path = get_tasks_file_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [
                    Task(
                        title=item["title"],
                        category=item["category"],
                        priority=item.get("priority", "medium"),
                        done=item.get("done", False),
                        status=item.get("status", "todo")
                    )
                    for item in data
                ]
        except Exception:
            pass

    sdd_tasks_file = discover_sdd_tasks_file()
    if sdd_tasks_file is not None:
        parsed = parse_sdd_tasks(sdd_tasks_file)
        if parsed:
            return parsed

    return list(DEFAULT_TASKS)

def save_tasks(tasks: list[Task]) -> None:
    path = get_tasks_file_path()
    try:
        data = [
            {
                "title": t.title,
                "category": t.category,
                "priority": t.priority,
                "done": t.done,
                "status": t.status
            }
            for t in tasks
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
