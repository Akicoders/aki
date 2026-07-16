from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, TextArea, TabbedContent, TabPane
from agentos.cockpit.tui.components import FilteredDirectoryTree
from agentos.cli.cockpit import ProjectRef

from agentos.cockpit.tui.chat import ChatTab
from agentos.cockpit.tui.kanban import KanbanTab
from agentos.cockpit.tui.runner import RunnerTab
from agentos.cockpit.tui.sdd import SDDHubTab

class AkiCockpitApp(App):
    """The interactive Aki Cockpit built with Textual."""

    CSS = """
    #tree-view {
        width: 30%;
        border-right: solid cyan;
    }
    #editor-view {
        width: 70%;
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+s", "save", "Save File"),
    ]

    def __init__(self, project: ProjectRef, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.current_file: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with TabbedContent():
            with TabPane("Explorer", id="tab-explorer"):
                with Horizontal():
                    yield FilteredDirectoryTree(self.project.root_path, id="tree-view")
                    with Vertical(id="editor-view"):
                        editor = TextArea(language="markdown", read_only=False)
                        yield editor
            
            with TabPane("Chat", id="tab-chat"):
                yield ChatTab()

            with TabPane("Kanban", id="tab-kanban"):
                yield KanbanTab()

            with TabPane("Runner", id="tab-runner"):
                yield RunnerTab()

            with TabPane("SDD Hub", id="tab-sdd"):
                yield SDDHubTab(root_path=self.project.root_path)
                
        yield Footer()

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
        """Handle file selection from the main interactive tree."""
        # Only handle if it's the main tree, SDD Hub has its own handler
        if event.control.id == "tree-view":
            try:
                path = Path(event.path)
                content = path.read_text(encoding="utf-8")
                editor = self.query_one(TextArea)
                editor.text = content
                self.current_file = path
                editor.focus()
                self.notify(f"Opened {path.name}")
            except Exception as e:
                self.notify(f"Could not open file: {e}", severity="error")

    def action_save(self) -> None:
        """Save the current editor content to the file."""
        if self.current_file:
            try:
                editor = self.query_one(TextArea)
                self.current_file.write_text(editor.text, encoding="utf-8")
                self.notify(f"Saved {self.current_file.name}", severity="information")
            except Exception as e:
                self.notify(f"Failed to save: {e}", severity="error")
        else:
            self.notify("No file currently open to save.", severity="warning")
