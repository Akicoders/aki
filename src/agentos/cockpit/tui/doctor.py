"""Doctor tab — async project health checks."""
from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual import on, work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input, Label, RichLog, Select, Static

from agentos.qwen.client import KNOWN_QWEN_MODELS
from agentos.cockpit.tui.chat import get_active_model, set_active_model

Status = Literal["ok", "warn", "fail", "info", "running"]

STATUS_ICON: dict[Status, str] = {
    "ok":      "[bold green]✅[/bold green]",
    "warn":    "[bold yellow]⚠️ [/bold yellow]",
    "fail":    "[bold red]❌[/bold red]",
    "info":    "[bold cyan]ℹ️ [/bold cyan]",
    "running": "[bold dim]⏳[/bold dim]",
}


@dataclass
class Check:
    name: str
    status: Status
    detail: str


class DoctorTab(Widget):
    """Runs health checks on the project and displays results."""

    DEFAULT_CSS = """
    DoctorTab {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }
    #doctor-header {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        layout: horizontal;
        padding: 0 2;
    }
    #doctor-title {
        width: 1fr;
        margin: 1 0 0 0;
        text-style: bold;
        color: cyan;
    }
    #doctor-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    #doctor-log {
        height: auto;
    }
    #doctor-hint {
        height: 1;
        background: $panel-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    #model-section {
        height: auto;
        background: $panel;
        border-bottom: solid $accent-darken-1;
        padding: 1 2;
        layout: vertical;
    }
    #model-title {
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }
    #model-row {
        height: 3;
        layout: horizontal;
    }
    #model-select { width: 30; margin-right: 1; }
    #model-custom-input { width: 24; margin-right: 1; }
    #model-apply-btn { width: 12; }
    #model-current {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, root_path: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._root_path = root_path

    def compose(self) -> ComposeResult:
        with Horizontal(id="doctor-header"):
            yield Static("🩺 Project Doctor", id="doctor-title", markup=True)
            yield Button("🔄 Run Checks", id="run-checks-btn", variant="primary")

        current = get_active_model()
        with Vertical(id="model-section"):
            yield Static("🧠 Qwen Model", id="model-title", markup=True)
            with Horizontal(id="model-row"):
                yield Select(
                    [(m, m) for m in KNOWN_QWEN_MODELS] + [("Custom…", "__custom__")],
                    value=current if current in KNOWN_QWEN_MODELS else "__custom__",
                    id="model-select",
                    allow_blank=False,
                )
                yield Input(
                    placeholder="custom model id",
                    value=current if current not in KNOWN_QWEN_MODELS and current else "",
                    id="model-custom-input",
                )
                yield Button("Apply", id="model-apply-btn", variant="success")
            yield Static(
                f"Active: [bold]{current or '(config default)'}[/bold]",
                id="model-current",
                markup=True,
            )

        with ScrollableContainer(id="doctor-scroll"):
            yield RichLog(id="doctor-log", highlight=True, markup=True)

        yield Static(
            " Press [bold]🔄 Run Checks[/bold] to diagnose your project",
            id="doctor-hint",
            markup=True,
        )

    def on_mount(self) -> None:
        log = self.query_one("#doctor-log", RichLog)
        log.write("[dim]Press [bold]🔄 Run Checks[/bold] to run diagnostics.[/dim]")

    @on(Select.Changed, "#model-select")
    def _on_model_select_changed(self, event: Select.Changed) -> None:
        custom_input = self.query_one("#model-custom-input", Input)
        custom_input.disabled = event.value != "__custom__"

    @on(Button.Pressed, "#model-apply-btn")
    def _on_apply_model(self) -> None:
        select = self.query_one("#model-select", Select)
        custom_input = self.query_one("#model-custom-input", Input)

        if select.value == "__custom__":
            model = custom_input.value.strip()
            if not model:
                self.app.notify("Enter a custom model id first.", severity="warning")
                return
        else:
            model = str(select.value)

        set_active_model(model)
        self.query_one("#model-current", Static).update(
            f"Active: [bold]{model}[/bold]"
        )
        self.app.notify(f"Qwen model set to {model}")

    @on(Button.Pressed, "#run-checks-btn")
    def _on_run(self) -> None:
        self._run_checks()

    @work(thread=True)
    def _run_checks(self) -> None:
        log = self.query_one("#doctor-log", RichLog)
        self.app.call_from_thread(log.clear)
        self.app.call_from_thread(
            log.write, "[bold cyan]🩺 Running project health checks…[/bold cyan]\n"
        )

        checks = [
            *self._check_structure(),
            *self._check_python(),
            *self._check_deps(),
            *self._check_tests(),
            *self._check_git(),
        ]

        # Print section headers and results
        sections: dict[str, list[Check]] = {}
        for c in checks:
            section = c.name.split("/")[0]
            sections.setdefault(section, []).append(c)

        for section, items in sections.items():
            self.app.call_from_thread(
                log.write, f"\n[bold white]── {section} ──────────────────────────[/bold white]"
            )
            for item in items:
                icon   = STATUS_ICON[item.status]
                label  = item.name.split("/", 1)[-1] if "/" in item.name else item.name
                detail = f"  [dim]{item.detail}[/dim]" if item.detail else ""
                self.app.call_from_thread(
                    log.write, f"  {icon} {label}{detail}"
                )

        # Summary
        oks   = sum(1 for c in checks if c.status == "ok")
        warns = sum(1 for c in checks if c.status == "warn")
        fails = sum(1 for c in checks if c.status == "fail")
        self.app.call_from_thread(
            log.write,
            f"\n[bold]Summary:[/bold] "
            f"[green]{oks} passed[/green]  "
            f"[yellow]{warns} warnings[/yellow]  "
            f"[red]{fails} failed[/red]",
        )
        self.app.call_from_thread(
            self.app.notify,
            f"Doctor done — {oks}✅ {warns}⚠️  {fails}❌",
        )

    # ── Check implementations ──────────────────────────────────────────────────

    def _check_structure(self) -> list[Check]:
        """Verify expected project files exist."""
        root = self._root_path
        checks = []
        required = [
            ("pyproject.toml",       "Python project config"),
            ("README.md",            "Project README"),
            (".env.example",         "Environment variables template"),
            ("src",                  "Source directory"),
            ("tests",                "Test directory"),
        ]
        for fname, desc in required:
            path = root / fname
            status: Status = "ok" if path.exists() else "warn"
            detail = f"Found at {path.name}" if path.exists() else f"Missing — {desc}"
            checks.append(Check(f"Structure/{fname}", status, detail))
        return checks

    def _check_python(self) -> list[Check]:
        """Try to compile key Python files."""
        checks: list[Check] = []
        py_files = list((self._root_path / "src").rglob("*.py"))[:20]  # limit to 20

        errors = 0
        for f in py_files:
            try:
                source = f.read_text(encoding="utf-8")
                compile(source, str(f), "exec")
            except SyntaxError as e:
                checks.append(Check(f"Syntax/{f.name}", "fail", f"Line {e.lineno}: {e.msg}"))
                errors += 1

        if not errors:
            checks.append(Check(
                "Syntax/All files",
                "ok",
                f"No syntax errors in {len(py_files)} files checked",
            ))
        return checks

    def _check_deps(self) -> list[Check]:
        """Check if dependencies are installed."""
        checks: list[Check] = []
        key_deps = ["textual", "fastapi", "httpx", "pydantic", "pytest"]

        for dep in key_deps:
            try:
                result = subprocess.run(
                    [sys.executable, "-c", f"import {dep}; print({dep}.__version__)"],
                    capture_output=True, text=True, timeout=5,
                    cwd=self._root_path,
                )
                if result.returncode == 0:
                    ver = result.stdout.strip()
                    checks.append(Check(f"Dependencies/{dep}", "ok", f"v{ver}"))
                else:
                    checks.append(Check(f"Dependencies/{dep}", "warn", "Not installed"))
            except Exception:
                checks.append(Check(f"Dependencies/{dep}", "warn", "Could not check"))

        return checks

    def _check_tests(self) -> list[Check]:
        """Count and optionally collect tests."""
        checks: list[Check] = []
        test_dir = self._root_path / "tests"

        if not test_dir.exists():
            checks.append(Check("Tests/Directory", "warn", "tests/ not found"))
            return checks

        test_files = list(test_dir.rglob("test_*.py"))
        checks.append(Check(
            "Tests/Files",
            "ok" if test_files else "warn",
            f"{len(test_files)} test file(s) found",
        ))

        # Try to collect tests with pytest
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_dir)],
                capture_output=True, text=True, timeout=15,
                cwd=self._root_path,
            )
            lines  = result.stdout.strip().splitlines()
            # Last line usually has "X tests collected"
            summary = next((l for l in reversed(lines) if "selected" in l or "collected" in l), "")
            if summary:
                checks.append(Check("Tests/Collection", "ok", summary.strip()))
            elif result.returncode != 0:
                err = (result.stderr or result.stdout).strip().splitlines()
                msg = err[-1] if err else "Unknown error"
                checks.append(Check("Tests/Collection", "warn", msg[:80]))
        except Exception as e:
            checks.append(Check("Tests/Collection", "warn", str(e)[:80]))

        return checks

    def _check_git(self) -> list[Check]:
        """Check git status and recent activity."""
        checks: list[Check] = []

        # Current branch
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
                cwd=self._root_path,
            ).stdout.strip()
            checks.append(Check("Git/Branch", "ok", branch or "detached HEAD"))
        except Exception:
            checks.append(Check("Git/Status", "fail", "Not a git repository"))
            return checks

        # Uncommitted changes
        try:
            status = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, timeout=5,
                cwd=self._root_path,
            ).stdout.strip()
            changed = len(status.splitlines()) if status else 0
            s: Status = "warn" if changed > 0 else "ok"
            msg = f"{changed} uncommitted file(s)" if changed else "Working tree clean"
            checks.append(Check("Git/Changes", s, msg))
        except Exception:
            pass

        # Last commit
        try:
            last = subprocess.run(
                ["git", "log", "-1", "--format=%h %s (%ar)"],
                capture_output=True, text=True, timeout=5,
                cwd=self._root_path,
            ).stdout.strip()
            checks.append(Check("Git/Last Commit", "info", last[:80]))
        except Exception:
            pass

        return checks
