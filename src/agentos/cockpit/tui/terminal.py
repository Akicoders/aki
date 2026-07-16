"""Embedded terminal — real PTY via App.suspend() for interactive programs."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

MAX_HISTORY = 200

# Commands that need a real PTY (interactive, full-screen, etc.)
# Everything else runs inline with captured output.
# We use App.suspend() for these so the real terminal takes over.
INTERACTIVE_PROGRAMS = {
    "nano", "vim", "vi", "nvim", "emacs", "micro",
    "htop", "top", "btop", "bpytop",
    "less", "more", "man",
    "python", "python3", "ipython", "bpython",
    "node", "irb", "pry", "lua", "ghci",
    "ssh", "sftp", "ftp",
    "mysql", "psql", "sqlite3", "redis-cli",
    "bash", "sh", "zsh", "fish",
    "git", "tig",   # tig is interactive; git log/diff are not but add git here
}

def _is_interactive(cmd: str) -> bool:
    """Return True if the command needs a real PTY."""
    base = cmd.strip().split()[0] if cmd.strip() else ""
    return base in INTERACTIVE_PROGRAMS


class TerminalTab(Widget):
    """Full-width terminal: inline output for quick commands, real PTY via suspend() for interactive ones."""

    DEFAULT_CSS = """
    TerminalTab {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }
    #term-header {
        height: 2;
        background: #111111;
        border-bottom: solid $accent;
        padding: 0 2;
        color: $text-muted;
    }
    #term-log {
        height: 1fr;
        background: #0d0d0d;
        color: #e0e0e0;
        overflow-y: auto;
    }
    #term-input-row {
        height: 3;
        background: #111111;
        border-top: solid $accent-darken-2;
        layout: horizontal;
        padding: 0 1;
    }
    #term-prompt {
        width: 3;
        margin: 1 1 0 0;
        color: cyan;
        text-style: bold;
    }
    #term-input {
        width: 1fr;
        background: #111111;
        color: #e0e0e0;
        border: none;
    }
    #term-hint {
        height: 1;
        background: #0a0a0a;
        padding: 0 2;
        color: #555555;
    }
    """

    def __init__(self, cwd: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cwd = cwd
        self._history: list[str] = []
        self._hist_idx: int = 0   # 0 = newest (empty), positive = older

    def compose(self) -> ComposeResult:
        yield Static(
            f"[dim]🖥️  [cyan]{self._cwd}[/cyan][/dim]",
            id="term-header",
            markup=True,
        )
        yield RichLog(id="term-log", highlight=False, markup=False, auto_scroll=True)
        with Horizontal(id="term-input-row"):
            yield Static("❯", id="term-prompt")
            yield Input(placeholder="", id="term-input")
        yield Static(
            " ↑↓ history  |  clear  |  cd <dir>  |  interactive apps (nano/vim/htop…) open in your real terminal and return here when done",
            id="term-hint",
        )

    def on_mount(self) -> None:
        log = self.query_one("#term-log", RichLog)
        log.write(f"Aki Terminal  —  {self._cwd}")
        log.write(f"uname: {os.uname().sysname} {os.uname().machine}")
        log.write("─" * 80)
        log.write("Tip: interactive apps (nano, vim, htop, ssh…) suspend the TUI and open in your real terminal.")
        log.write("")
        self.query_one("#term-input", Input).focus()

    # ── Input handling ─────────────────────────────────────────────────────────

    @on(Input.Submitted, "#term-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""

        if not cmd:
            return

        # History management
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
            if len(self._history) > MAX_HISTORY:
                self._history.pop(0)
        self._hist_idx = 0

        # Built-ins
        if cmd == "clear":
            self.query_one("#term-log", RichLog).clear()
            return

        if cmd.startswith("cd"):
            parts = cmd.split(None, 1)
            target = parts[1] if len(parts) > 1 else str(Path.home())
            self._builtin_cd(target)
            return

        log = self.query_one("#term-log", RichLog)
        log.write(f"❯ {cmd}")

        if _is_interactive(cmd):
            # Run in a real PTY via App.suspend()
            self._run_interactive(cmd)
        else:
            # Run inline with captured output
            self._run_inline(cmd)

    def on_key(self, event) -> None:
        inp = self.query_one("#term-input", Input)

        if event.key == "up":
            if self._history and self._hist_idx < len(self._history):
                self._hist_idx += 1
                inp.value = self._history[-self._hist_idx]
                inp.cursor_position = len(inp.value)

        elif event.key == "down":
            if self._hist_idx > 1:
                self._hist_idx -= 1
                inp.value = self._history[-self._hist_idx]
            else:
                self._hist_idx = 0
                inp.value = ""
            inp.cursor_position = len(inp.value)

        elif event.key == "ctrl+l":
            self.query_one("#term-log", RichLog).clear()

    # ── Interactive: suspend the TUI and give the real terminal ───────────────

    @work
    async def _run_interactive(self, cmd: str) -> None:
        """Suspend Textual, run the command in the real terminal, resume."""
        log = self.query_one("#term-log", RichLog)
        log.write(f"  [suspending cockpit → running in your terminal]")

        async with self.app.suspend():
            subprocess.run(
                cmd,
                shell=True,
                cwd=self._cwd,
                env={**os.environ},
            )

        log.write(f"  [cockpit resumed]")
        log.write("")

    # ── Inline: captured subprocess output ────────────────────────────────────

    @work(thread=True)
    def _run_inline(self, cmd: str) -> None:
        log = self.query_one("#term-log", RichLog)
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self._cwd,
                env={**os.environ, "TERM": "xterm-256color", "FORCE_COLOR": "0"},
            )
            for line in proc.stdout:  # type: ignore[union-attr]
                self.app.call_from_thread(log.write, line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                self.app.call_from_thread(
                    log.write, f"[exit {proc.returncode}]"
                )
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(log.write, "[timeout]")
        except Exception as e:
            self.app.call_from_thread(log.write, f"[error: {e}]")
        self.app.call_from_thread(log.write, "")

    # ── cd built-in ───────────────────────────────────────────────────────────

    def _builtin_cd(self, target: str) -> None:
        log = self.query_one("#term-log", RichLog)
        try:
            if target == "~":
                target = str(Path.home())
            new_cwd = (self._cwd / target).resolve()
            if new_cwd.is_dir():
                self._cwd = new_cwd
                self.query_one("#term-header", Static).update(
                    f"[dim]🖥️  [cyan]{self._cwd}[/cyan][/dim]"
                )
            else:
                log.write(f"cd: {target}: No such directory")
        except Exception as e:
            log.write(f"cd: {e}")
        log.write("")
