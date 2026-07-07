"""Code intelligence skill."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from agentos.skills.base import Skill, SkillResult
from agentos.core.config import get_config

logger = logging.getLogger(__name__)


RIPGREP_TYPE_MAP = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "typescript": "ts",
    "js": "js",
    "ts": "ts",
    "json": "json",
    "html": "html",
    "css": "css",
    "rust": "rust",
    "rs": "rs",
    "go": "go",
    "yaml": "yaml",
    "yml": "yaml",
    "markdown": "md",
    "md": "md",
}


class CodeIntelSkill(Skill):
    name = "code_intel"
    description = "Code analysis: find symbols, grep AST, run tests, get coverage"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.test_command = config.get("test_command", "pytest -v") if config else "pytest -v"
        self.lint_command = config.get("lint_command", "ruff check .") if config else "ruff check ."

    def _resolve_path(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    async def find_symbol(self, path: str, symbol: str, language: str = "python") -> SkillResult:
        """Find a symbol definition using ripgrep."""
        try:
            target = self._resolve_path(path)
            if language == "python":
                pattern = rf"^(def|class|async def)\s+{symbol}\b"
            elif language in ("javascript", "typescript"):
                pattern = rf"^(function|const|let|var|class)\s+{symbol}\b"
            else:
                pattern = symbol

            cleaned_lang = language.strip().lower()
            rg_type = RIPGREP_TYPE_MAP.get(cleaned_lang)
            
            if rg_type:
                cmd = ["rg", "-n", "--type", rg_type, pattern, str(target)]
            else:
                cmd = ["rg", "-n", "--glob", f"*.{cleaned_lang}", pattern, str(target)]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode >= 2:
                return SkillResult(success=False, error=f"ripgrep failed: {result.stderr.strip()}")
                
            lines = result.stdout.strip().split("\n") if result.stdout else []
            matches = []
            for line in lines:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({"file": parts[0], "line": int(parts[1]), "content": parts[2]})
            return SkillResult(success=True, data={"symbol": symbol, "matches": matches})
        except FileNotFoundError:
            return SkillResult(success=False, error="ripgrep (rg) not installed")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def grep_ast(self, path: str, pattern: str, language: str = "python") -> SkillResult:
        """Search code using AST-aware patterns (via ripgrep)."""
        try:
            target = self._resolve_path(path)
            
            cleaned_lang = language.strip().lower()
            rg_type = RIPGREP_TYPE_MAP.get(cleaned_lang)
            
            if rg_type:
                cmd = ["rg", "-n", "--type", rg_type, pattern, str(target)]
            else:
                cmd = ["rg", "-n", "--glob", f"*.{cleaned_lang}", pattern, str(target)]
                
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode >= 2:
                return SkillResult(success=False, error=f"ripgrep failed: {result.stderr.strip()}")
                
            lines = result.stdout.strip().split("\n") if result.stdout else []
            matches = []
            for line in lines[:100]:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({"file": parts[0], "line": int(parts[1]), "content": parts[2]})
            return SkillResult(success=True, data={"pattern": pattern, "matches": matches})
        except FileNotFoundError:
            return SkillResult(success=False, error="ripgrep (rg) not installed")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def run_tests(self, path: str = ".", extra_args: str = "") -> SkillResult:
        """Run test suite."""
        try:
            target = self._resolve_path(path)
            cmd = f"{self.test_command} {extra_args}".strip()
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=target,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return SkillResult(success=result.returncode == 0, data={
                "command": cmd,
                "returncode": result.returncode,
                "stdout": result.stdout[-5000:],  # Last 5k chars
                "stderr": result.stderr[-2000:],
            })
        except subprocess.TimeoutExpired:
            return SkillResult(success=False, error="Tests timed out")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def run_lint(self, path: str = ".") -> SkillResult:
        """Run linter."""
        try:
            target = self._resolve_path(path)
            result = subprocess.run(
                self.lint_command,
                shell=True,
                cwd=target,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return SkillResult(success=result.returncode == 0, data={
                "command": self.lint_command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def get_coverage(self, path: str = ".") -> SkillResult:
        """Get test coverage."""
        try:
            target = self._resolve_path(path)
            result = subprocess.run(
                "pytest --cov=. --cov-report=term-missing",
                shell=True,
                cwd=target,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return SkillResult(success=result.returncode == 0, data={
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def get_project_structure(self, path: str = ".", max_depth: int = 3) -> SkillResult:
        """Get project directory structure."""
        try:
            target = self._resolve_path(path)
            structure = []
            for item in target.rglob("*"):
                depth = len(item.relative_to(target).parts)
                if depth > max_depth:
                    continue
                if item.name.startswith(".") or item.name in {"__pycache__", "node_modules", "venv", ".git"}:
                    continue
                structure.append({
                    "path": str(item.relative_to(target)),
                    "type": "dir" if item.is_dir() else "file",
                    "depth": depth,
                })
            return SkillResult(success=True, data={"structure": structure})
        except Exception as e:
            return SkillResult(success=False, error=str(e))