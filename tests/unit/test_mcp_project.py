from pathlib import Path

import pytest

from agentos.mcp.project import detect_project


def test_detect_project_prefers_explicit_value(tmp_path):
    assert detect_project("manual-project", cwd=tmp_path) == "manual-project"


def test_detect_project_uses_git_root_basename(tmp_path):
    git_root = tmp_path / "repo-name"
    nested = git_root / "src" / "package"
    nested.mkdir(parents=True)
    (git_root / ".git").mkdir()

    assert detect_project(cwd=nested) == "repo-name"


def test_detect_project_uses_cwd_name_without_git_root(tmp_path):
    project_dir = tmp_path / "plain-directory"
    project_dir.mkdir()

    assert detect_project(cwd=project_dir) == "plain-directory"


def test_detect_project_uses_process_cwd_when_omitted(tmp_path, monkeypatch):
    project_dir = tmp_path / "current-project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    assert detect_project() == "current-project"


@pytest.mark.parametrize("cwd", [None, Path("/")])
def test_detect_project_falls_back_to_default(cwd):
    assert detect_project(cwd=cwd) == "default"
