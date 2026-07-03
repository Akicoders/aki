"""Filesystem operations skill."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from agentos.skills.base import Skill, SkillResult

logger = logging.getLogger(__name__)


class FilesystemSkill(Skill):
    name = "filesystem"
    description = "File operations: read, write, search, glob, list"
    destructive_functions = frozenset({"write", "append", "delete"})

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.allowed_roots = [
            Path(r).expanduser().resolve()
            for r in (config.get("allowed_roots", ["~/proyects", "~/Documents"]) if config else ["~/proyects", "~/Documents"])
        ]

    def _resolve_path(self, path: str) -> Path:
        """Resolve path and check it's within allowed roots."""
        target = Path(path).expanduser().resolve()
        for root in self.allowed_roots:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue
        raise PermissionError(f"Path {target} not within allowed roots: {self.allowed_roots}")

    async def read(self, path: str, offset: int = 0, limit: int = 2000) -> SkillResult:
        """Read file content with pagination."""
        try:
            target = self._resolve_path(path)
            if not target.exists():
                return SkillResult(success=False, error=f"File not found: {path}")
            if not target.is_file():
                return SkillResult(success=False, error=f"Not a file: {path}")

            content = target.read_text(encoding="utf-8")
            lines = content.splitlines()
            total = len(lines)
            start = max(0, offset)
            end = min(total, offset + limit)
            return SkillResult(success=True, data={
                "path": str(target),
                "content": "\n".join(lines[start:end]),
                "total_lines": total,
                "offset": start,
                "limit": limit,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def write(self, path: str, content: str, create_dirs: bool = True) -> SkillResult:
        """Write content to file."""
        try:
            target = self._resolve_path(path)
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return SkillResult(success=True, data={"path": str(target), "size": len(content)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def append(self, path: str, content: str) -> SkillResult:
        """Append content to file."""
        try:
            target = self._resolve_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as f:
                f.write(content)
            return SkillResult(success=True, data={"path": str(target), "appended": len(content)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def delete(self, path: str) -> SkillResult:
        """Delete a file."""
        try:
            target = self._resolve_path(path)
            if not target.exists():
                return SkillResult(success=False, error=f"File not found: {path}")
            target.unlink()
            return SkillResult(success=True, data={"path": str(target)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def list(self, path: str = ".", recursive: bool = False) -> SkillResult:
        """List directory contents."""
        try:
            target = self._resolve_path(path)
            if not target.exists():
                return SkillResult(success=False, error=f"Path not found: {path}")
            if not target.is_dir():
                return SkillResult(success=False, error=f"Not a directory: {path}")

            if recursive:
                items = [p for p in target.rglob("*")]
            else:
                items = list(target.iterdir())

            return SkillResult(success=True, data={
                "path": str(target),
                "items": [
                    {
                        "name": p.name,
                        "path": str(p.relative_to(target)),
                        "type": "directory" if p.is_dir() else "file",
                        "size": p.stat().st_size if p.is_file() else None,
                    }
                    for p in items
                ],
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def glob(self, path: str = ".", pattern: str = "**/*") -> SkillResult:
        """Find files matching glob pattern."""
        try:
            target = self._resolve_path(path)
            matches = list(target.glob(pattern))
            return SkillResult(success=True, data={
                "path": str(target),
                "pattern": pattern,
                "matches": [str(p.relative_to(target)) for p in matches],
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def search(self, path: str = ".", query: str = "", file_pattern: str = "*.py", limit: int = 50) -> SkillResult:
        """Search file contents (grep-like)."""
        try:
            target = self._resolve_path(path)
            import subprocess
            result = subprocess.run(
                ["rg", "-n", "--type", file_pattern.replace("*.", ""), query, str(target)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = result.stdout.strip().split("\n") if result.stdout else []
            matches = []
            for line in lines[:limit]:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0],
                        "line": int(parts[1]),
                        "content": parts[2],
                    })
            return SkillResult(success=True, data={"query": query, "matches": matches})
        except FileNotFoundError:
            return SkillResult(success=False, error="ripgrep (rg) not installed")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def exists(self, path: str) -> SkillResult:
        """Check if path exists."""
        try:
            target = self._resolve_path(path)
            return SkillResult(success=True, data={
                "path": str(target),
                "exists": target.exists(),
                "is_file": target.is_file() if target.exists() else False,
                "is_dir": target.is_dir() if target.exists() else False,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))