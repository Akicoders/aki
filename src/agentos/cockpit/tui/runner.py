"""Code runner tab — select a .py or .md file from the tree and run/preview it."""
from __future__ import annotations

import io
import sys
import traceback
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Label, Markdown, RichLog, Static, TextArea

from agentos.cockpit.tui.components import FilteredDirectoryTree


class RunnerTab(Horizontal):
    """Select a .py or .md file — Python runs, Markdown renders."""

    DEFAULT_CSS = """
    RunnerTab {
        height: 100%;
    }
    #runner-tree {
        width: 28;
        border-right: solid $accent-darken-1;
    }
    #runner-right {
        width: 1fr;
        height: 100%;
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
    #run-btn {
        width: 12;
    }
    #editor-pane {
        height: 1fr;
        border-bottom: solid $accent-darken-1;
    }
    #preview-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    #md-preview {
        height: auto;
    }
    #output-log {
        height: 1fr;
        overflow-y: auto;
    }
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
        self._mode: str = "none"  # "python" | "markdown" | "none"

    def compose(self) -> ComposeResult:
        yield FilteredDirectoryTree(self._root_path, id="runner-tree")

        with Vertical(id="runner-right"):
            # Toolbar
            with Horizontal(id="runner-toolbar"):
                yield Static("Select a .py or .md file from the tree", id="file-label", markup=True)
                yield Button("▶ Run", id="run-btn", variant="success", disabled=True)

            # Editor (always visible, shows file content)
            yield TextArea("", id="editor-pane", language="python")

            # Output: either RichLog (Python) or Markdown preview
            yield RichLog(id="output-log", highlight=True, markup=True)
            with ScrollableContainer(id="preview-scroll"):
                yield Markdown("", id="md-preview")

            yield Static(
                " [Ctrl+R] run python  |  .md files preview automatically",
                id="runner-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        # Start with preview hidden, log visible
        self._set_mode("none")

    # ── File selection ─────────────────────────────────────────────────────────

    def on_directory_tree_file_selected(self, event: FilteredDirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            self.app.notify(f"Cannot read file: {e}", severity="error")
            return

        self._current_file = path
        editor = self.query_one("#editor-pane", TextArea)
        editor.text = content

        label = self.query_one("#file-label", Static)

        if path.suffix == ".py":
            self._set_mode("python")
            editor.language = "python"
            label.update(f"[bold cyan]🐍 {path.name}[/bold cyan]  [dim](Ctrl+R to run)[/dim]")
            log = self.query_one("#output-log", RichLog)
            log.clear()
            log.write(f"[dim]Loaded [bold]{path.name}[/bold] — press [bold]▶ Run[/bold] or Ctrl+R to execute.[/dim]")

        elif path.suffix == ".md":
            self._set_mode("markdown")
            editor.language = "markdown"
            label.update(f"[bold magenta]📝 {path.name}[/bold magenta]  [dim](live preview)[/dim]")
            self.query_one("#md-preview", Markdown).update(content)

        else:
            self._set_mode("other")
            editor.language = "python"  # fallback syntax
            label.update(f"[dim]{path.name}[/dim]")

        self.app.notify(f"Opened {path.name}")

    # ── Live Markdown preview while editing ────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._mode == "markdown":
            content = self.query_one("#editor-pane", TextArea).text
            self.query_one("#md-preview", Markdown).update(content)

    # ── Run Python ─────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#run-btn")
    def _on_run_btn(self) -> None:
        self._run_python()

    def on_key(self, event) -> None:
        if event.key == "ctrl+r" and self._mode == "python":
            self._run_python()

    def _run_python(self) -> None:
        if self._mode != "python":
            return
        code = self.query_one("#editor-pane", TextArea).text
        log  = self.query_one("#output-log", RichLog)
        log.clear()

        name = self._current_file.name if self._current_file else "<buffer>"
        log.write(f"[bold dim]─── Running {name} ───[/bold dim]")

        old_stdout, old_stderr = sys.stdout, sys.stderr
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
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    # ── Layout helpers ─────────────────────────────────────────────────────────

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        run_btn      = self.query_one("#run-btn", Button)
        output_log   = self.query_one("#output-log", RichLog)
        preview_wrap = self.query_one("#preview-scroll")

        run_btn.disabled = (mode != "python")

        if mode == "python":
            output_log.display  = True
            preview_wrap.display = False
        elif mode == "markdown":
            output_log.display  = False
            preview_wrap.display = True
        else:
            output_log.display  = True
            preview_wrap.display = False
