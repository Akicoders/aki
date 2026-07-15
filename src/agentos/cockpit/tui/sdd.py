from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import DirectoryTree, Markdown

class SDDHubTab(Horizontal):
    """The SDD Hub tab."""
    
    def __init__(self, root_path: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root_path = root_path
        
    def compose(self) -> ComposeResult:
        # We can point this specifically to docs/sdd or just use the project root
        sdd_path = self.root_path / "docs" / "sdd"
        if not sdd_path.exists():
            sdd_path = self.root_path
            
        yield DirectoryTree(sdd_path, id="sdd-tree")
        yield Markdown("# SDD Hub\nSelect a markdown file from the tree to view its contents.", id="sdd-viewer")
        
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Load markdown files into the viewer."""
        path = Path(event.path)
        if path.suffix == ".md":
            try:
                content = path.read_text(encoding="utf-8")
                viewer = self.query_one(Markdown)
                viewer.update(content)
                self.app.notify(f"Loaded {path.name}")
            except Exception as e:
                self.app.notify(f"Could not open file: {e}", severity="error")
