"""Embedded terminal tab — run commands with full output and history."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

MAX_HISTORY = 100


class TerminalTab(Widget):
    """A terminal emulator: run any shell command and see its output."""

    DEFAULT_CSS = """
    TerminalTab {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }
    #term-header {
        height: 2;
        background: $panel;
        border-bottom: solid $accent;
        padding: 0 2;
        color: $text-muted;
    }
    #term-log {
        height: 1fr;
        background: #0d0d0d;
        color: #e0e0e0;
        scrollbar-gutter: stable;
    }
    #term-input-row {
        height: 3;
        background: #111111;
        border-top: solid $accent-darken-1;
        layout: horizontal;
        padding: 0 1;
    }
    #term-prompt {
        width: 4;
        margin: 1 0 0 0;
        color: cyan;
        text-style: bold;
    }
    #term-input {
        width: 1fr;
        background: #111111;
    }
    #term-hint {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    def __init__(self, cwd: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cwd   = cwd
        self._history: list[str] = []
        self._hist_idx: int = -1

    def compose(self) -> ComposeResult:
        yield Static(
            f"[dim]Terminal — [cyan]{self._cwd}[/cyan][/dim]",
            id="term-header",
            markup=True,
        )
        yield RichLog(id="term-log", highlight=True, markup=False, auto_scroll=True)
        with Vertical(id="term-input-row"):
            yield Static("❯", id="term-prompt")
            yield Input(placeholder="Enter command…", id="term-input")
        yield Static(
            " [↑/↓] history  [Ctrl+L] clear  [Ctrl+C] interrupt",
            id="term-hint",
            markup=True,
        )

    def on_mount(self) -> None:
        log = self.query_one("#term-log", RichLog)
        log.write(f"Aki Terminal — {self._cwd}")
        log.write(f"Python: {os.sys.version.split()[0]}  |  Shell: bash")
        log.write("─" * 60)
        self.query_one("#term-input", Input).focus()

    @on(Input.Submitted, "#term-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        if not cmd:
            return
        event.input.value = ""

        # History
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
            if len(self._history) > MAX_HISTORY:
                self._history.pop(0)
        self._hist_idx = -1

        # Built-in: cd
        if cmd.startswith("cd "):
            target = cmd[3:].strip()
            self._builtin_cd(target)
            return

        if cmd == "clear":
            self.query_one("#term-log", RichLog).clear()
            return

        log = self.query_one("#term-log", RichLog)
        log.write(f"❯ {cmd}")
        self._run_command(cmd)

    def on_key(self, event) -> None:
        inp = self.query_one("#term-input", Input)
        if event.key == "up":
            if self._history:
                self._hist_idx = max(-len(self._history), self._hist_idx - 1)
                inp.value = self._history[self._hist_idx]
                inp.cursor_position = len(inp.value)
        elif event.key == "down":
            if self._hist_idx < -1:
                self._hist_idx += 1
                inp.value = self._history[self._hist_idx] if self._hist_idx < 0 else ""
            else:
                inp.value = ""
                self._hist_idx = -1
        elif event.key == "ctrl+l":
            self.query_one("#term-log", RichLog).clear()

    @work(thread=True)
    def _run_command(self, cmd: str) -> None:
        log = self.query_one("#term-log", RichLog)
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=30,
                env={**os.environ, "TERM": "xterm-256color"},
            )
            stdout = result.stdout
            stderr = result.stderr

            if stdout:
                for line in stdout.splitlines():
                    self.app.call_from_thread(log.write, line)
            if stderr:
                for line in stderr.splitlines():
                    self.app.call_from_thread(log.write, f"[ERR] {line}")
            if result.returncode != 0 and not stderr and not stdout:
                self.app.call_from_thread(
                    log.write, f"[exit {result.returncode}]"
                )

        except subprocess.TimeoutExpired:
            self.app.call_from_thread(log.write, "[timeout after 30s]")
        except Exception as e:
            self.app.call_from_thread(log.write, f"[error: {e}]")

    def _builtin_cd(self, target: str) -> None:
        log = self.query_one("#term-log", RichLog)
        try:
            new_cwd = (self._cwd / target).resolve()
            if new_cwd.is_dir():
                self._cwd = new_cwd
                log.write(f"❯ cd {target}")
                self.query_one("#term-header", Static).update(
                    f"[dim]Terminal — [cyan]{self._cwd}[/cyan][/dim]"
                )
            else:
                log.write(f"cd: no such directory: {target}")
        except Exception as e:
            log.write(f"cd: {e}")
