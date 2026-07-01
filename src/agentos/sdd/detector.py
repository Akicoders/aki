"""Detect SDD artifacts in a project directory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


SDD_DIRS = ("docs/sdd", ".sdd", "openspec")
SDD_FILES = ("proposal.md", "spec.md", "design.md", "tasks.md")


@dataclass
class SDDStatus:
    has_sdd: bool
    sdd_dir: Optional[str] = None
    found_artifacts: list[str] = field(default_factory=list)
    missing_artifacts: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.has_sdd:
            return "No SDD artifacts found"
        found = ", ".join(self.found_artifacts) if self.found_artifacts else "dir only"
        missing = ", ".join(self.missing_artifacts) if self.missing_artifacts else "none"
        return f"SDD dir: {self.sdd_dir} | Found: {found} | Missing: {missing}"


def detect_sdd_artifacts(project_dir: Optional[Path] = None) -> SDDStatus:
    root = project_dir or Path.cwd()

    for sdd_dir_name in SDD_DIRS:
        candidate = root / sdd_dir_name
        if candidate.is_dir():
            found = []
            missing = []
            for artifact in SDD_FILES:
                if (candidate / artifact).exists():
                    found.append(artifact)
                else:
                    missing.append(artifact)
            return SDDStatus(
                has_sdd=True,
                sdd_dir=sdd_dir_name,
                found_artifacts=found,
                missing_artifacts=missing,
            )

    return SDDStatus(has_sdd=False)


def load_sdd_artifact(artifact_name: str, project_dir: Optional[Path] = None) -> Optional[str]:
    root = project_dir or Path.cwd()
    for sdd_dir_name in SDD_DIRS:
        candidate = root / sdd_dir_name / artifact_name
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def summarize_sdd_context(project_dir: Optional[Path] = None) -> Optional[str]:
    status = detect_sdd_artifacts(project_dir)
    if not status.has_sdd:
        return None

    parts = [f"SDD Status: {status.summary()}"]
    for artifact in status.found_artifacts:
        content = load_sdd_artifact(artifact, project_dir)
        if content:
            preview = content[:500].strip()
            parts.append(f"\n--- {artifact} ---\n{preview}")

    return "\n".join(parts)
