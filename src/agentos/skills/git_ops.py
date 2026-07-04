"""Git operations skill."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, cast

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from agentos.skills.base import Skill, SkillResult

logger = logging.getLogger(__name__)


class GitOpsSkill(Skill):
    name = "git_ops"
    description = "Git operations: status, init, diff, commit, push, create PR, log"
    destructive_functions = frozenset({"init"})

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.default_branch = config.get("default_branch", "main") if config else "main"
        self.auto_commit = config.get("auto_commit", False) if config else False

    def _get_repo(self, path: str) -> Repo:
        repo_path = Path(path).expanduser().resolve()
        if not repo_path.exists():
            raise ValueError(f"Path does not exist: {repo_path}")
        try:
            return Repo(repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError):
            raise ValueError(f"Not a git repository: {repo_path}")

    def _get_branch_name(self, repo: Repo) -> Optional[str]:
        try:
            if repo.head.is_detached:
                return None
            return repo.active_branch.name
        except (TypeError, ValueError):
            try:
                return repo.head.reference.name
            except (TypeError, ValueError):
                return None

    def _get_staged_files(self, repo: Repo) -> list[str]:
        if repo.head.is_valid():
            return [path for item in repo.index.diff("HEAD") if (path := item.a_path or item.b_path)]
        return [line for line in cast(str, repo.git.diff("--cached", "--name-only")).splitlines() if line]

    async def status(self, path: str = ".") -> SkillResult:
        """Get git status."""
        try:
            repo = self._get_repo(path)
            status = {
                "branch": self._get_branch_name(repo),
                "repo_root": str(Path(repo.working_tree_dir or path).resolve()),
                "git_dir": str(Path(repo.git_dir).resolve()),
                "has_commits": repo.head.is_valid(),
                "is_dirty": repo.is_dirty(),
                "untracked_files": repo.untracked_files,
                "modified_files": [item.a_path for item in repo.index.diff(None)],
                "staged_files": self._get_staged_files(repo),
            }
            return SkillResult(success=True, data=status)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def init(self, path: str, initial_branch: str = "main") -> SkillResult:
        """Initialize git version control for an existing project folder."""
        try:
            repo_path = Path(path).expanduser().resolve()
            if not repo_path.exists():
                return SkillResult(success=False, error=f"Path does not exist: {repo_path}")
            if not repo_path.is_dir():
                return SkillResult(success=False, error=f"Not a directory: {repo_path}")

            try:
                repo = self._get_repo(str(repo_path))
                return SkillResult(success=True, data={
                    "path": str(repo_path),
                    "git_dir": str(Path(repo.git_dir).resolve()),
                    "repo_root": str(Path(repo.working_tree_dir or repo_path).resolve()),
                    "created": False,
                    "branch": self._get_branch_name(repo),
                })
            except ValueError:
                repo = Repo.init(repo_path, initial_branch=initial_branch)
                return SkillResult(success=True, data={
                    "path": str(repo_path),
                    "git_dir": str(Path(repo.git_dir).resolve()),
                    "repo_root": str(Path(repo.working_tree_dir or repo_path).resolve()),
                    "created": True,
                    "branch": self._get_branch_name(repo),
                })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def diff(self, path: str = ".", staged: bool = False) -> SkillResult:
        """Get git diff."""
        try:
            repo = self._get_repo(path)
            if staged:
                diff = repo.index.diff("HEAD")
            else:
                diff = repo.index.diff(None)
            result = {
                "files": [
                    {
                        "path": item.a_path,
                        "diff": (
                            item.diff.decode("utf-8", errors="replace")
                            if isinstance(item.diff, bytes)
                            else item.diff or ""
                        ),
                    }
                    for item in diff
                ]
            }
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def commit(self, path: str = ".", message: str = "", add_all: bool = True) -> SkillResult:
        """Create a commit."""
        try:
            repo = self._get_repo(path)
            if add_all:
                repo.git.add(A=True)
            if not message:
                return SkillResult(success=False, error="Commit message required")
            commit = repo.index.commit(message)
            return SkillResult(success=True, data={"commit": commit.hexsha, "message": message})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def push(self, path: str = ".", remote: str = "origin", branch: Optional[str] = None) -> SkillResult:
        """Push to remote."""
        try:
            repo = self._get_repo(path)
            branch = branch or repo.active_branch.name
            repo.remotes[remote].push(refspec=f"{branch}:{branch}")
            return SkillResult(success=True, data={"remote": remote, "branch": branch})
        except GitCommandError as e:
            return SkillResult(success=False, error=f"Push failed: {e}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def log(self, path: str = ".", limit: int = 10, oneline: bool = True) -> SkillResult:
        """Get recent commits."""
        try:
            repo = self._get_repo(path)
            commits = list(repo.iter_commits(max_count=limit))
            result = {
                "commits": [
                    {
                        "sha": c.hexsha[:8],
                        "message": c.message.strip(),
                        "author": str(c.author),
                        "date": c.committed_datetime.isoformat(),
                    }
                    for c in commits
                ]
            }
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def create_branch(self, path: str = ".", name: str = "", base: Optional[str] = None) -> SkillResult:
        """Create and checkout a new branch."""
        try:
            repo = self._get_repo(path)
            base_branch = base or self.default_branch
            new_branch = repo.create_head(name, repo.refs[base_branch])
            new_branch.checkout()
            return SkillResult(success=True, data={"branch": name, "base": base_branch})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def get_remote_url(self, path: str = ".", remote: str = "origin") -> SkillResult:
        """Get remote URL."""
        try:
            repo = self._get_repo(path)
            url = repo.remotes[remote].url
            return SkillResult(success=True, data={"remote": remote, "url": url})
        except Exception as e:
            return SkillResult(success=False, error=str(e))
