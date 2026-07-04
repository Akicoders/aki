from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from agentos.skills.git_ops import GitOpsSkill


def _skill() -> GitOpsSkill:
    return GitOpsSkill()


def _commit_file(repo_dir: Path) -> None:
    (repo_dir / "README.md").write_text("hello\n", encoding="utf-8")
    repo = Repo(repo_dir)
    repo.git.add(A=True)
    repo.index.commit("initial commit")


@pytest.mark.asyncio
async def test_git_status_succeeds_for_existing_repo(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    Repo.init(repo_dir, initial_branch="main")
    _commit_file(repo_dir)

    result = await _skill().status(str(repo_dir))

    assert result.success is True
    assert result.data["branch"] == "main"
    assert result.data["repo_root"] == str(repo_dir.resolve())


@pytest.mark.asyncio
async def test_git_init_bootstraps_missing_repo_and_status_then_succeeds(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    skill = _skill()

    init_result = await skill.init(str(project_dir))
    status_result = await skill.status(str(project_dir))

    assert init_result.success is True
    assert init_result.data["created"] is True
    assert (project_dir / ".git").is_dir()
    assert status_result.success is True
    assert status_result.data["repo_root"] == str(project_dir.resolve())


@pytest.mark.asyncio
async def test_git_init_reports_existing_repo_without_reinitializing(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    Repo.init(repo_dir, initial_branch="main")
    before_git_dir = (repo_dir / ".git").resolve()

    result = await _skill().init(str(repo_dir))

    assert result.success is True
    assert result.data["created"] is False
    assert result.data["git_dir"] == str(before_git_dir)
