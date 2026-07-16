"""SDD Hub tab — read-only architectural document viewer."""
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Markdown

from agentos.cockpit.tui.components import FilteredDirectoryTree


class SDDHubTab(Widget):
    """SDD Hub — read-only architectural document viewer."""

    DEFAULT_CSS = """
    SDDHubTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    #sdd-tree {
        width: 30;
        height: 1fr;
        border-right: solid $accent-darken-1;
    }
    #sdd-scroll {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    #sdd-viewer { height: auto; }
    """

    def __init__(self, root_path: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root_path = root_path

    def compose(self) -> ComposeResult:
        sdd_path = self.root_path / "docs" / "sdd"
        if not sdd_path.exists():
            sdd_path = self.root_path

        yield FilteredDirectoryTree(sdd_path, id="sdd-tree")
        with ScrollableContainer(id="sdd-scroll"):
            yield Markdown(
                "# SDD Hub\nSelect a **markdown** file from the tree to view its contents.",
                id="sdd-viewer",
            )

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        if path.suffix == ".md":
            try:
                content = path.read_text(encoding="utf-8")
                self.query_one(Markdown).update(content)
                self.query_one(ScrollableContainer).scroll_home(animate=False)
                self.app.notify(f"Loaded {path.name}")
            except Exception as e:
                self.app.notify(f"Could not open: {e}", severity="error")
