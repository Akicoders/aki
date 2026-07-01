"""Helpers for the `aki update` command."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


PROJECT_NAME_MARKERS = (
    'name = "aki-memory"',
    'name = "agentos"',
)
EXPECTED_PROJECT_PATHS = (
    "install.sh",
    "pyproject.toml",
    "README.md",
    "src/agentos/cli/main.py",
)


class UpdateError(RuntimeError):
    """Raised when `aki update` cannot safely update the current install."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _is_expected_source_dir(candidate: Path) -> bool:
    if not all(
        (candidate / relative_path).exists() for relative_path in EXPECTED_PROJECT_PATHS
    ):
        return False

    pyproject_text = _read_text(candidate / "pyproject.toml")
    return any(marker in pyproject_text for marker in PROJECT_NAME_MARKERS)


def find_install_source_dir(start: Path) -> Path | None:
    """Walk up from `start` looking for the Aki source checkout root."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if _is_expected_source_dir(candidate):
            return candidate
    return None


def locate_installed_source_dir() -> Path | None:
    """Locate the source checkout that backs the current Aki install."""
    import agentos

    package_file = agentos.__file__
    if package_file is None:
        return None
    return find_install_source_dir(Path(package_file))


def validate_source_checkout(source_dir: Path) -> Path:
    """Ensure the detected install source is the expected Aki git checkout."""
    resolved = source_dir.resolve()
    if not _is_expected_source_dir(resolved):
        expected = ", ".join(EXPECTED_PROJECT_PATHS)
        raise UpdateError(
            "The detected Aki install source is missing expected project files "
            f"({expected}). `aki update` only works for installs backed by a cloned "
            "Aki source checkout."
        )

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=resolved,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpdateError("git is required to update Aki but was not found in PATH.") from exc

    if result.returncode != 0:
        raise UpdateError(
            "The detected Aki install source is not a git checkout. `aki update` only "
            "works for source installs created from a cloned repository."
        )

    git_root_text = result.stdout.strip()
    if not git_root_text:
        raise UpdateError("git rev-parse did not return a repository root for this install.")

    git_root = Path(git_root_text).resolve()
    if git_root != resolved:
        raise UpdateError(
            f"Expected the Aki source checkout at {resolved}, but git reported {git_root}. "
            "Reinstall Aki from the repository root and try again."
        )

    return resolved


def resolve_uv_binary() -> str:
    """Resolve the uv binary in the same way as the source installer."""
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    local_uv = Path.home() / ".local" / "bin" / "uv"
    if local_uv.is_file() and os.access(local_uv, os.X_OK):
        return str(local_uv)

    raise UpdateError(
        "uv is required to update Aki but was not found in PATH or at ~/.local/bin/uv."
    )


def run_update_command(
    command: Sequence[str],
    *,
    cwd: Path,
    missing_message: str,
    failure_message: str,
) -> None:
    """Run an update step and raise a user-friendly error if it fails."""
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpdateError(missing_message) from exc

    if result.returncode == 0:
        return

    details: list[str] = []
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        details.append(f"stdout:\n{stdout}")
    if stderr:
        details.append(f"stderr:\n{stderr}")

    message = f"{failure_message} (exit code {result.returncode})."
    if details:
        message = f"{message}\n\n" + "\n\n".join(details)
    raise UpdateError(message)
