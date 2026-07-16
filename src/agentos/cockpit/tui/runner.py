"""Code runner tab — IDE-style file editor with syntax highlighting and Python execution."""
from __future__ import annotations

import io
import sys
import traceback
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Markdown, RichLog, Static, TextArea

from agentos.cockpit.tui.components import FilteredDirectoryTree

# Map file extensions -> TextArea language identifiers
LANG_MAP: dict[str, str] = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "javascript",
    ".jsx":  "javascript",
    ".tsx":  "javascript",
    ".css":  "css",
    ".html": "html",
    ".json": "json",
    ".md":   "markdown",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".toml": "toml",
    ".sh":   "bash",
    ".bash": "bash",
    ".sql":  "sql",
}

# IDE-style theme for TextArea
IDE_THEME = "vscode_dark"


class RunnerTab(Widget):
    """Select a .py or .md file — Python runs, Markdown renders live."""

    DEFAULT_CSS = """
    RunnerTab {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    #runner-tree {
        width: 28;
        height: 1fr;
        border-right: solid $accent-darken-1;
    }
    #runner-right {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }
    #runner-toolbar {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        layout: horizontal;
        padding: 0 1;
    }
    #file-label {
        width: 1fr;
        margin: 1 0 0 0;
        color: $text-muted;
    }
    #run-btn { width: 12; }
    #editor-pane {
        height: 1fr;
        border-bottom: solid $accent-darken-1;
    }
    #output-log { height: 1fr; }
    #preview-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    #md-preview { height: auto; }
    #runner-hint {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def __init__(self, root_path: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._root_path = root_path
        self._current_file: Path | None = None
        self._mode: str = "none"

    def compose(self) -> ComposeResult:
        yield FilteredDirectoryTree(self._root_path, id="runner-tree")
        with Vertical(id="runner-right"):
            with Horizontal(id="runner-toolbar"):
                yield Static("Select a [bold].py[/bold] or [bold].md[/bold] file from the tree →", id="file-label", markup=True)
                yield Button("▶ Run", id="run-btn", variant="success", disabled=True)
            yield TextArea(
                "",
                id="editor-pane",
                language="python",
                theme=IDE_THEME,
                show_line_numbers=True,
            )
            yield RichLog(id="output-log", highlight=True, markup=True)
            with ScrollableContainer(id="preview-scroll"):
                yield Markdown("", id="md-preview")
            yield Static(
                " [Ctrl+R] run python  |  .md previews automatically as you type",
                id="runner-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._set_output_mode("log")
        log = self.query_one("#output-log", RichLog)
        log.write("[dim]Select a [bold].py[/bold] or [bold].md[/bold] file from the tree on the left.[/dim]")

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            self.app.notify(f"Cannot read: {e}", severity="error")
            return

        self._current_file = path
        editor = self.query_one("#editor-pane", TextArea)
        label  = self.query_one("#file-label", Static)
        ext    = path.suffix.lower()
        lang   = LANG_MAP.get(ext, "")

        # Apply language — only set if tree-sitter supports it
        try:
            editor.language = lang or None  # type: ignore[assignment]
        except Exception:
            editor.language = None  # type: ignore[assignment]

        editor.text  = content
        editor.theme = IDE_THEME

        if ext == ".py":
            self._mode = "python"
            self._set_output_mode("log")
            label.update(f"[bold cyan]🐍 {path.name}[/bold cyan]  [dim]Ctrl+R to run[/dim]")
            log = self.query_one("#output-log", RichLog)
            log.clear()
            log.write(f"[dim]Loaded [bold]{path.name}[/bold] — press ▶ Run or Ctrl+R.[/dim]")
            self.query_one("#run-btn", Button).disabled = False

        elif ext == ".md":
            self._mode = "markdown"
            self._set_output_mode("preview")
            label.update(f"[bold magenta]📝 {path.name}[/bold magenta]  [dim]live preview[/dim]")
            self.query_one("#md-preview", Markdown).update(content)
            self.query_one("#run-btn", Button).disabled = True

        else:
            self._mode = "other"
            self._set_output_mode("log")
            label.update(f"[bold]{path.name}[/bold]  [dim]{lang or 'plain text'}[/dim]")
            self.query_one("#run-btn", Button).disabled = True

        self.app.notify(f"Opened {path.name}  [{lang or 'text'}]")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._mode == "markdown":
            self.query_one("#md-preview", Markdown).update(
                self.query_one("#editor-pane", TextArea).text
            )

    @on(Button.Pressed, "#run-btn")
    def _on_run_btn(self) -> None:
        self._run_python()

    def on_key(self, event) -> None:
        if event.key == "ctrl+r":
            self._run_python()

    def _run_python(self) -> None:
        if self._mode != "python":
            return
        code = self.query_one("#editor-pane", TextArea).text
        log  = self.query_one("#output-log", RichLog)
        log.clear()
        name = self._current_file.name if self._current_file else "<buffer>"
        log.write(f"[bold dim]─── Running {name} ───[/bold dim]")

        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            exec(compile(code, name, "exec"), {"__file__": str(self._current_file)})  # noqa: S102
            out = sys.stdout.getvalue()
            err = sys.stderr.getvalue()
            for line in out.splitlines():
                log.write(f"[white]{line}[/white]")
            for line in err.splitlines():
                log.write(f"[yellow]{line}[/yellow]")
            if not out and not err:
                log.write("[dim](no output)[/dim]")
            log.write("[bold green]✓ Done[/bold green]")
        except Exception:
            for line in traceback.format_exc().splitlines():
                log.write(f"[bold red]{line}[/bold red]")
            log.write("[bold red]✗ Error[/bold red]")
        finally:
            sys.stdout = old_out
            sys.stderr = old_err

    def _set_output_mode(self, mode: str) -> None:
        self.query_one("#output-log", RichLog).display   = (mode == "log")
        self.query_one("#preview-scroll").display         = (mode == "preview")
