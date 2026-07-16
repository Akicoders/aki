"""Logic for diagnosing chaos and salvaging project health."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


class ChaosReport:
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.generated_at = datetime.now()
        
        # Git checks
        self.is_git_repo = False
        self.git_dirty = False
        self.git_untracked = []
        self.git_modified = []
        
        # SDD checks
        self.sdd_dir: Optional[str] = None
        self.found_artifacts = []
        self.missing_artifacts = []
        
        # Test checks
        self.has_tests_dir = False
        self.test_files_count = 0
        
        # Config checks
        self.has_config_yaml = False
        self.has_env = False
        self.has_env_example = False
        
        # Credentials checks
        self.has_qwen_key = False
        self.qwen_key_source = "missing"
        
        # Conflict marker checks
        self.files_with_conflicts = []

    def run_diagnosis(self) -> None:
        # 1. Git
        self.is_git_repo = (self.root_path / ".git").is_dir()
        if self.is_git_repo:
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=self.root_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                for line in res.stdout.splitlines():
                    if line.startswith("?? "):
                        self.git_untracked.append(line[3:])
                    elif line.startswith(" M ") or line.startswith("M "):
                        self.git_modified.append(line[3:])
                self.git_dirty = len(self.git_untracked) > 0 or len(self.git_modified) > 0
            except Exception:
                pass

        # 2. SDD
        for candidate in (".sdd", "docs/sdd", "openspec"):
            if (self.root_path / candidate).is_dir():
                self.sdd_dir = candidate
                break
        
        expected_artifacts = ("proposal.md", "spec.md", "design.md", "tasks.md")
        if self.sdd_dir:
            sdd_path = self.root_path / self.sdd_dir
            for art in expected_artifacts:
                if (sdd_path / art).is_file():
                    self.found_artifacts.append(art)
                else:
                    self.missing_artifacts.append(art)
        else:
            self.missing_artifacts = list(expected_artifacts)

        # 3. Tests
        self.has_tests_dir = (self.root_path / "tests").is_dir() or (self.root_path / "test").is_dir()
        # count test files
        for p in self.root_path.glob("**/test_*.py"):
            if ".venv" not in p.parts and ".git" not in p.parts:
                self.test_files_count += 1

        # 4. Configs
        self.has_config_yaml = (self.root_path / "config.yaml").is_file()
        self.has_env = (self.root_path / ".env").is_file()
        self.has_env_example = (self.root_path / ".env.example").is_file()

        # 5. Credentials
        # check os.environ
        if "QWEN_API_KEY" in os.environ or "DASHSCOPE_API_KEY" in os.environ:
            self.has_qwen_key = True
            self.qwen_key_source = "environment"
        elif self.has_env:
            # check inside .env
            try:
                content = (self.root_path / ".env").read_text(encoding="utf-8")
                if "QWEN_API_KEY" in content or "DASHSCOPE_API_KEY" in content:
                    self.has_qwen_key = True
                    self.qwen_key_source = ".env file"
            except Exception:
                pass

        # 6. Conflict markers (<<<<<<<, =======, >>>>>>>)
        # Search source files, excluding binary files, git directory, and virtual envs
        exclude_dirs = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules"}
        valid_extensions = {".py", ".md", ".json", ".yaml", ".yml", ".html", ".css", ".js", ".toml"}
        
        for root, dirs, files in os.walk(self.root_path):
            # filter directories in place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in valid_extensions:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if "<<<<<<<" in content and "=======" in content and ">>>>>>>" in content:
                            self.files_with_conflicts.append(str(file_path.relative_to(self.root_path)))
                    except Exception:
                        pass

    def generate_markdown_report(self) -> str:
        report = []
        report.append("# Aki Salvage Diagnosis")
        report.append(f"Generated at: `{self.generated_at.isoformat()}`")
        report.append(f"Project root: `{self.root_path.resolve()}`")
        report.append("")
        
        # Summary table
        report.append("## Chaos Diagnosis Summary")
        report.append("| Check | Status | Info |")
        report.append("| :--- | :--- | :--- |")
        
        # Git Status
        git_status = "✅ OK" if self.is_git_repo and not self.git_dirty else ("⚠️ DIRTY" if self.is_git_repo else "❌ MISSING")
        git_info = "Clean repo" if git_status == "✅ OK" else (f"{len(self.git_modified)} modified, {len(self.git_untracked)} untracked files" if self.is_git_repo else "Not a Git repository")
        report.append(f"| Git Repository | {git_status} | {git_info} |")

        # SDD Status
        sdd_status = "✅ COMPLETE" if len(self.missing_artifacts) == 0 else ("⚠️ PARTIAL" if self.sdd_dir else "❌ MISSING")
        sdd_info = f"Found in '{self.sdd_dir}'" if self.sdd_dir else "No SDD artifacts found"
        report.append(f"| SDD Artifacts | {sdd_status} | {sdd_info} (Missing: {', '.join(self.missing_artifacts) or 'none'}) |")

        # Tests Status
        test_status = "✅ OK" if self.has_tests_dir and self.test_files_count > 0 else "❌ MISSING"
        test_info = f"{self.test_files_count} test files found" if self.test_files_count > 0 else "No test suite found"
        report.append(f"| Test Suite | {test_status} | {test_info} |")

        # Config Status
        config_status = "✅ OK" if self.has_config_yaml and self.has_env else "⚠️ INCOMPLETE"
        config_info = []
        if self.has_config_yaml: config_info.append("config.yaml found")
        else: config_info.append("config.yaml missing")
        if self.has_env: config_info.append(".env found")
        else: config_info.append(".env missing")
        report.append(f"| Config Files | {config_status} | {', '.join(config_info)} |")

        # Credentials
        cred_status = "✅ OK" if self.has_qwen_key else "❌ MISSING"
        cred_info = f"Configured via {self.qwen_key_source}" if self.has_qwen_key else "QWEN_API_KEY/DASHSCOPE_API_KEY not found"
        report.append(f"| API Credentials | {cred_status} | {cred_info} |")

        # Conflicts
        conflict_status = "✅ OK" if len(self.files_with_conflicts) == 0 else "❌ CONFLICTS DETECTED"
        conflict_info = "No git conflict markers found" if len(self.files_with_conflicts) == 0 else f"{len(self.files_with_conflicts)} files have conflict markers"
        report.append(f"| Code Conflicts | {conflict_status} | {conflict_info} |")
        
        report.append("")

        # Detailed Findings
        if self.files_with_conflicts:
            report.append("## ❌ Git Conflict Details")
            report.append("The following files contain git merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`):")
            for f in self.files_with_conflicts:
                report.append(f"- `{f}`")
            report.append("")

        if self.missing_artifacts:
            report.append("## ⚠️ SDD Completeness Details")
            report.append(f"The project is missing the following core SDD/OpenSpec files:")
            for art in self.missing_artifacts:
                report.append(f"- `{art}`")
            report.append("")

        # Remediation
        report.append("## Recommended Remediation Plan")
        step = 1
        
        if self.files_with_conflicts:
            report.append(f"{step}. **Resolve Git Conflicts**: Open the conflict files list above, clean up the conflict markers, and commit the resolved files.")
            step += 1
            
        if not self.has_env and self.has_env_example:
            report.append(f"{step}. **Restore Environment Configuration**: Copy `.env.example` to `.env` and fill in the required API keys.")
            step += 1
        elif not self.has_env:
            report.append(f"{step}. **Create Environment Configuration**: Create a `.env` file with `QWEN_API_KEY` configuration.")
            step += 1

        if not self.has_config_yaml:
            report.append(f"{step}. **Create config.yaml**: Write a default `config.yaml` for project-local configurations.")
            step += 1

        if not self.sdd_dir:
            report.append(f"{step}. **Initialize SDD**: Run `aki sdd-init` inside the project to bootstrap the planning structure.")
            step += 1

        if not self.has_tests_dir:
            report.append(f"{step}. **Set Up Test Suite**: Create a `tests/` directory with base tests to safeguard development.")
            step += 1

        if step == 1:
            report.append("Everything looks healthy and orderly! No recovery steps required.")

        return "\n".join(report)

    def write_report_file(self) -> Path:
        content = self.generate_markdown_report()
        report_file = self.root_path / "aki_diagnose.md"
        report_file.write_text(content, encoding="utf-8")
        return report_file


def perform_salvage_fixes(report: ChaosReport) -> list[str]:
    """Execute automated fixes for repairable chaos."""
    fixed_items = []
    
    # 1. Restore missing .env from .env.example
    if not report.has_env and report.has_env_example:
        try:
            example_content = (report.root_path / ".env.example").read_text(encoding="utf-8")
            (report.root_path / ".env").write_text(example_content, encoding="utf-8")
            fixed_items.append("Restored missing .env file from .env.example template.")
        except Exception as e:
            fixed_items.append(f"Failed to restore .env: {str(e)}")

    # 2. Write a default config.yaml if missing
    if not report.has_config_yaml:
        try:
            default_config = (
                "# Aki project configuration\n"
                "project:\n"
                f"  name: {report.root_path.name}\n"
                "  version: 0.1.0\n"
            )
            (report.root_path / "config.yaml").write_text(default_config, encoding="utf-8")
            fixed_items.append("Created default config.yaml file.")
        except Exception as e:
            fixed_items.append(f"Failed to create config.yaml: {str(e)}")

    # 3. Create basic .gitignore if missing
    if report.is_git_repo and not (report.root_path / ".gitignore").is_file():
        try:
            default_gitignore = (
                "__pycache__/\n"
                "*.py[cod]\n"
                ".venv/\n"
                ".env\n"
                ".mypy_cache/\n"
                ".pytest_cache/\n"
            )
            (report.root_path / ".gitignore").write_text(default_gitignore, encoding="utf-8")
            fixed_items.append("Created default .gitignore file.")
        except Exception as e:
            fixed_items.append(f"Failed to create .gitignore: {str(e)}")

    return fixed_items
