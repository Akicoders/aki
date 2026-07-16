from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, TextArea, TabbedContent, TabPane
from agentos.cockpit.tui.components import FilteredDirectoryTree
from agentos.cli.cockpit import ProjectRef

from agentos.cockpit.tui.chat import ChatTab
from agentos.cockpit.tui.kanban import KanbanTab
from agentos.cockpit.tui.runner import RunnerTab, IDE_THEME
from agentos.cockpit.tui.sdd import SDDHubTab
from agentos.cockpit.tui.doctor import DoctorTab

# Default tab order — user can reorder with [ and ]
DEFAULT_TABS: list[tuple[str, str]] = [
    ("tab-explorer", "Explorer"),
    ("tab-chat",     "Chat"),
    ("tab-kanban",   "Kanban"),
    ("tab-runner",   "Runner"),
    ("tab-sdd",      "SDD Hub"),
    ("tab-doctor",   "🩺 Doctor"),
]


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
        ("q",       "quit",          "Quit"),
        ("ctrl+s",  "save",          "Save File"),
        ("[",       "move_tab_left", "Move Tab ←"),
        ("]",       "move_tab_right","Move Tab →"),
        ("1",       "goto_tab('1')", "Tab 1"),
        ("2",       "goto_tab('2')", "Tab 2"),
        ("3",       "goto_tab('3')", "Tab 3"),
        ("4",       "goto_tab('4')", "Tab 4"),
        ("5",       "goto_tab('5')", "Tab 5"),
    ]

    def __init__(self, project: ProjectRef, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.current_file: Path | None = None
        # Live tab order (tab_id, label) — user can reorder
        self._tab_order: list[tuple[str, str]] = list(DEFAULT_TABS)

    # ── Compose ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs"):
            for tab_id, _ in self._tab_order:
                yield from self._build_tab_pane(tab_id)
        yield Footer()

    def _build_tab_pane(self, tab_id: str):
        """Yield the correct TabPane for the given tab_id."""
        labels = dict(self._tab_order)
        label  = labels.get(tab_id, tab_id)

        if tab_id == "tab-explorer":
            with TabPane(label, id=tab_id):
                with Horizontal():
                    yield FilteredDirectoryTree(self.project.root_path, id="tree-view")
                    with Vertical(id="editor-view"):
                        yield TextArea(
                            language="markdown",
                            read_only=False,
                            theme=IDE_THEME,
                            show_line_numbers=True,
                        )

        elif tab_id == "tab-chat":
            with TabPane(label, id=tab_id):
                yield ChatTab()

        elif tab_id == "tab-kanban":
            with TabPane(label, id=tab_id):
                yield KanbanTab()

        elif tab_id == "tab-runner":
            with TabPane(label, id=tab_id):
                yield RunnerTab(root_path=self.project.root_path)

        elif tab_id == "tab-sdd":
            with TabPane(label, id=tab_id):
                yield SDDHubTab(root_path=self.project.root_path)

        elif tab_id == "tab-doctor":
            with TabPane(label, id=tab_id):
                yield DoctorTab(root_path=self.project.root_path)

    # ── Tab reordering ────────────────────────────────────────────────────────

    def action_move_tab_left(self) -> None:
        """Shift the active tab one position to the left."""
        tc = self.query_one("#main-tabs", TabbedContent)
        active = str(tc.active)
        ids = [t[0] for t in self._tab_order]
        idx = ids.index(active) if active in ids else -1
        if idx > 0:
            self._tab_order[idx], self._tab_order[idx - 1] = (
                self._tab_order[idx - 1], self._tab_order[idx]
            )
            self._rebuild_tabs(active)
            self.notify(f"Moved '{self._tab_order[idx - 1][1]}' ←")

    def action_move_tab_right(self) -> None:
        """Shift the active tab one position to the right."""
        tc = self.query_one("#main-tabs", TabbedContent)
        active = str(tc.active)
        ids = [t[0] for t in self._tab_order]
        idx = ids.index(active) if active in ids else -1
        if idx >= 0 and idx < len(self._tab_order) - 1:
            self._tab_order[idx], self._tab_order[idx + 1] = (
                self._tab_order[idx + 1], self._tab_order[idx]
            )
            self._rebuild_tabs(active)
            self.notify(f"Moved '{self._tab_order[idx + 1][1]}' →")

    def action_goto_tab(self, n: str) -> None:
        """Jump to tab by number (1-based)."""
        idx = int(n) - 1
        if 0 <= idx < len(self._tab_order):
            tc = self.query_one("#main-tabs", TabbedContent)
            tc.active = self._tab_order[idx][0]

    def _rebuild_tabs(self, restore_active: str) -> None:
        """Rebuild TabbedContent in the new order."""
        tc = self.query_one("#main-tabs", TabbedContent)
        tc.clear_panes()
        for tab_id, _ in self._tab_order:
            for pane in self._build_tab_pane(tab_id):
                tc.add_pane(pane)
        try:
            tc.active = restore_active
        except Exception:
            pass

    # ── File handling ─────────────────────────────────────────────────────────

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
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
        if self.current_file:
            try:
                editor = self.query_one(TextArea)
                self.current_file.write_text(editor.text, encoding="utf-8")
                self.notify(f"Saved {self.current_file.name}", severity="information")
            except Exception as e:
                self.notify(f"Failed to save: {e}", severity="error")
        else:
            self.notify("No file open to save.", severity="warning")
