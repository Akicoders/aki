"""SDD Hub tab — interactive architectural document viewer and initializer."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Label, ListItem, ListView, Markdown, Static

from agentos.cockpit.tui.components import FilteredDirectoryTree
from agentos.sdd.init import init_sdd_project, TEMPLATES
from agentos.sdd.detector import detect_sdd_artifacts


class SDDHubTab(Widget):
    """SDD Hub — view and initialize architectural templates."""

    DEFAULT_CSS = """
    SDDHubTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    #sdd-left-panel {
        width: 32;
        height: 1fr;
        border-right: solid $accent-darken-1;
        background: $panel;
        layout: vertical;
    }
    #sdd-header-area {
        padding: 1 1;
        border-bottom: solid $accent-darken-2;
    }
    #sdd-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    #init-sdd-btn {
        width: 1fr;
        margin-top: 1;
    }
    #sdd-status-list {
        background: transparent;
        padding: 0 1;
        margin: 1 0;
    }
    .sdd-status-item {
        padding: 1 1;
        margin-bottom: 0;
    }
    #sdd-tree-area {
        height: 1fr;
        border-top: solid $accent-darken-2;
    }
    #sdd-right-panel {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }
    #sdd-toolbar {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        layout: horizontal;
        padding: 0 2;
    }
    #sdd-file-title {
        width: 1fr;
        margin: 1 0 0 0;
        text-style: bold;
    }
    #edit-sdd-btn {
        width: 16;
        margin-top: 0;
    }
    #sdd-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 4;
    }
    #sdd-viewer { height: auto; }
    """

    def __init__(self, root_path: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root_path = root_path
        self._selected_file: Optional[Path] = None

    def compose(self) -> ComposeResult:
        sdd_path = self.root_path / "docs" / "sdd"
        if not sdd_path.exists():
            sdd_path = self.root_path

        with Vertical(id="sdd-left-panel"):
            with Vertical(id="sdd-header-area"):
                yield Static("📖 SDD Hub", id="sdd-title")
                yield Button("⚡ Initialize SDD Templates", id="init-sdd-btn", variant="primary")
            
            yield ListView(id="sdd-status-list")
            
            with Vertical(id="sdd-tree-area"):
                yield FilteredDirectoryTree(sdd_path, id="sdd-tree")

        with Vertical(id="sdd-right-panel"):
            with Horizontal(id="sdd-toolbar"):
                yield Static("Select a document to read", id="sdd-file-title")
                yield Button("✏️ Edit File", id="edit-sdd-btn", variant="success", disabled=True)
            with ScrollableContainer(id="sdd-scroll"):
                yield Markdown(
                    "# Software Design Documents\n"
                    "SDD provides a structured design methodology:\n\n"
                    "1. **Proposal**: Problem, intent, high-level approach.\n"
                    "2. **Spec**: Functional requirements and scenarios.\n"
                    "3. **Design**: Architecture details and data schemas.\n"
                    "4. **Tasks**: Actionable milestones.",
                    id="sdd-viewer",
                )

    def on_mount(self) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Scan docs/sdd and populate status list."""
        status = detect_sdd_artifacts(self.root_path)
        lv = self.query_one("#sdd-status-list", ListView)
        lv.clear()

        # Render status indicators for templates
        for artifact in ["proposal.md", "spec.md", "design.md", "tasks.md"]:
            found = artifact in status.found_artifacts
            pill = "[green]🟢 Found[/green]" if found else "[red]🔴 Missing[/red]"
            item = ListItem(
                Label(f"{pill} {artifact.split('.')[0].title()}"),
                classes="sdd-status-item"
            )
            # Store metadata
            item.artifact_name = artifact  # type: ignore[attr-defined]
            item.found = found             # type: ignore[attr-defined]
            lv.append(item)

    @on(ListView.Selected, "#sdd-status-list")
    def _on_status_selected(self, event: ListView.Selected) -> None:
        artifact = getattr(event.item, "artifact_name", None)
        found = getattr(event.item, "found", False)
        if not artifact:
            return

        target_path = self.root_path / "docs" / "sdd" / artifact
        if found and target_path.exists():
            self._view_file(target_path)
        else:
            self.query_one("#sdd-file-title", Static).update(f"[red]Missing: {artifact}[/red]", markup=True)
            self.query_one("#sdd-viewer", Markdown).update(
                f"# Missing Document: {artifact}\n\n"
                "This SDD template does not exist yet. Click the **⚡ Initialize SDD Templates** button to create all template files."
            )
            self._selected_file = None
            self.query_one("#edit-sdd-btn", Button).disabled = True

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
        if event.control.id == "sdd-tree":
            self._view_file(Path(event.path))

    def _view_file(self, path: Path) -> None:
        if path.suffix == ".md":
            try:
                content = path.read_text(encoding="utf-8")
                self.query_one(Markdown).update(content)
                self.query_one(ScrollableContainer).scroll_home(animate=False)
                
                self._selected_file = path
                self.query_one("#sdd-file-title", Static).update(f"[cyan]📖 {path.name}[/cyan]", markup=True)
                self.query_one("#edit-sdd-btn", Button).disabled = False
                self.app.notify(f"Viewing {path.name}")
            except Exception as e:
                self.app.notify(f"Could not open: {e}", severity="error")

    @on(Button.Pressed, "#init-sdd-btn")
    def _on_init_sdd(self) -> None:
        sdd_dir, created = init_sdd_project(self.root_path)
        self._refresh_status()
        
        # Refresh tree view
        try:
            tree = self.query_one("#sdd-tree", FilteredDirectoryTree)
            tree.reload()
        except Exception:
            pass

        if created:
            self.app.notify(f"Initialized SDD templates in {sdd_dir.name}: {', '.join(created)}")
        else:
            self.app.notify("All SDD templates are already initialized!")

    @on(Button.Pressed, "#edit-sdd-btn")
    def _on_edit_sdd(self) -> None:
        if self._selected_file and self._selected_file.exists():
            self.app.open_file_in_editor(self._selected_file)  # type: ignore[attr-defined]
