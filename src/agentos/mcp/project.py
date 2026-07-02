"""Project detection helpers for MCP tool calls."""

from __future__ import annotations

from pathlib import Path

from agentos.core.project_breadcrumb import write_breadcrumb

_USE_PROCESS_CWD = object()


def detect_project(
    explicit_project: str | None = None,
    cwd: Path | None | object = _USE_PROCESS_CWD,
) -> str:
    """Resolve a project name from explicit input, git root, cwd, or a default."""
    if explicit_project and explicit_project.strip():
        return explicit_project.strip()

    if cwd is _USE_PROCESS_CWD:
        cwd = Path.cwd()

    if cwd is None:
        return "default"

    if not isinstance(cwd, Path):
        cwd = Path(cwd)

    current = cwd.resolve()
    git_root = _find_git_root(current)
    if git_root and git_root.name:
        write_breadcrumb(git_root)
        return git_root.name

    if current.name:
        return current.name
    return "default"


def _find_git_root(path: Path) -> Path | None:
    """Walk upward until a directory containing .git is found."""
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None
