from typing import Iterable
from pathlib import Path
from textual.widgets import DirectoryTree

class FilteredDirectoryTree(DirectoryTree):
    """A DirectoryTree that filters out common ignore patterns to improve performance."""

    IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".tox", ".mypy_cache"}
    IGNORE_EXTS = {".pyc", ".pyo", ".pyd", ".so"}

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter the paths before adding them to the tree."""
        return [
            path for path in paths
            if not (path.name in self.IGNORE_DIRS or path.suffix in self.IGNORE_EXTS)
        ]
