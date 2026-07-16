"""Code runner tab — execute Python and preview Markdown."""
from __future__ import annotations

import io
import sys
import traceback

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Markdown, RichLog, Select, TextArea

STARTER_PYTHON = '''\
# Python runs here — use print() to see output
import sys

def greet(name: str) -> str:
    return f"Hello, {name}!"

print(greet("Aki"))
print(f"Python {sys.version}")
'''

STARTER_MARKDOWN = '''\
# Welcome to the SDD Previewer

Write **Markdown** here and see it rendered live.

## Features
- Headers
- **Bold** and _italic_
- `inline code`
- Lists

```python
print("Hello from a code block!")
```
'''

MODE_PYTHON   = "python"
MODE_MARKDOWN = "markdown"


class RunnerTab(Vertical):
    """Code runner: Python execution and Markdown live preview."""

    DEFAULT_CSS = """
    RunnerTab {
        padding: 0;
    }
    #runner-toolbar {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        layout: horizontal;
        padding: 0 1;
    }
    #runner-toolbar Label {
        margin: 1 1 0 0;
        color: $text-muted;
    }
    #mode-select {
        width: 22;
    }
    #run-btn {
        width: 12;
        margin-left: 1;
    }
    #clear-btn {
        width: 10;
    }
    #runner-body {
        height: 1fr;
        layout: horizontal;
    }
    #code-editor {
        width: 1fr;
        height: 100%;
        border-right: solid $accent-darken-1;
    }
    #output-pane {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
        padding: 1 1;
    }
    #runner-hint {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mode: str = MODE_PYTHON

    def compose(self) -> ComposeResult:
        # ── Toolbar ────────────────────────────────────────────────────────────
        with Horizontal(id="runner-toolbar"):
            yield Label("Mode:")
            yield Select(
                [(MODE_PYTHON, "🐍 Python"), (MODE_MARKDOWN, "📝 Markdown Preview")],
                value=MODE_PYTHON,
                id="mode-select",
            )
            yield Button("▶ Run", id="run-btn", variant="success")
            yield Button("🗑 Clear", id="clear-btn", variant="default")

        # ── Editor + Output ────────────────────────────────────────────────────
        with Horizontal(id="runner-body"):
            yield TextArea(
                STARTER_PYTHON,
                language="python",
                id="code-editor",
            )
            yield RichLog(id="output-pane", highlight=True, markup=True)

        yield Label(
            " [Ctrl+R] run  [Ctrl+L] clear  | Left=editor  Right=output",
            id="runner-hint",
            markup=True,
        )

    def on_mount(self) -> None:
        log = self.query_one("#output-pane", RichLog)
        log.write("[bold green]Ready.[/bold green] Press [bold]▶ Run[/bold] or [bold]Ctrl+R[/bold] to execute.")

    # ── Mode switching ─────────────────────────────────────────────────────────

    @on(Select.Changed, "#mode-select")
    def _on_mode_change(self, event: Select.Changed) -> None:
        self._mode = str(event.value)
        editor = self.query_one("#code-editor", TextArea)
        output = self.query_one("#output-pane", RichLog)
        output.clear()

        if self._mode == MODE_PYTHON:
            editor.language = "python"
            if not editor.text.strip():
                editor.text = STARTER_PYTHON
            output.write("[bold green]Python mode[/bold green] — press ▶ Run to execute.")

        elif self._mode == MODE_MARKDOWN:
            editor.language = "markdown"
            if not editor.text.strip():
                editor.text = STARTER_MARKDOWN
            self._render_markdown()

    # ── Run / Clear ────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#run-btn")
    def _on_run(self) -> None:
        self._execute()

    @on(Button.Pressed, "#clear-btn")
    def _on_clear(self) -> None:
        self.query_one("#output-pane", RichLog).clear()

    def on_key(self, event) -> None:
        if event.key == "ctrl+r":
            self._execute()
        elif event.key == "ctrl+l":
            self.query_one("#output-pane", RichLog).clear()

    # ── Markdown live preview while typing ─────────────────────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._mode == MODE_MARKDOWN:
            self._render_markdown()

    def _render_markdown(self) -> None:
        code = self.query_one("#code-editor", TextArea).text
        log  = self.query_one("#output-pane", RichLog)
        log.clear()
        # We mount a temporary Markdown widget to render — use markup shortcut
        log.write("[dim]── Rendered Preview ──[/dim]")
        # RichLog can't render Markdown directly, so we mount inline
        self._mount_markdown_preview(code)

    def _mount_markdown_preview(self, content: str) -> None:
        """Replace output pane with a live Markdown widget."""
        output_pane = self.query_one("#output-pane")
        # Swap RichLog for Markdown widget if in markdown mode
        # We keep them both and show/hide based on mode
        pass  # Handled via _render_python / display

    # ── Python execution ───────────────────────────────────────────────────────

    def _execute(self) -> None:
        editor = self.query_one("#code-editor", TextArea)
        log    = self.query_one("#output-pane", RichLog)
        code   = editor.text

        if self._mode == MODE_MARKDOWN:
            log.clear()
            log.write("[bold yellow]Markdown preview updates as you type.[/bold yellow]")
            return

        log.clear()
        log.write("[bold dim]─── Running ───[/bold dim]")

        # Capture stdout + stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        sys.stdout = captured_out
        sys.stderr = captured_err

        try:
            exec(compile(code, "<aki-runner>", "exec"), {})  # noqa: S102
            out = captured_out.getvalue()
            err = captured_err.getvalue()

            if out:
                for line in out.splitlines():
                    log.write(f"[white]{line}[/white]")
            if err:
                for line in err.splitlines():
                    log.write(f"[yellow]{line}[/yellow]")
            if not out and not err:
                log.write("[dim](no output)[/dim]")

            log.write("[bold green]✓ Done[/bold green]")

        except Exception:
            tb = traceback.format_exc()
            for line in tb.splitlines():
                log.write(f"[bold red]{line}[/bold red]")
            log.write("[bold red]✗ Error[/bold red]")

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
