from __future__ import annotations

import os

from agentos.core.config import _iter_env_search_roots, load_runtime_env
from agentos.core.project_breadcrumb import write_breadcrumb


def test_breadcrumb_root_yielded_last_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    breadcrumb_root = tmp_path / "breadcrumb-project"
    breadcrumb_root.mkdir()
    write_breadcrumb(breadcrumb_root)

    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    roots = _iter_env_search_roots(unrelated_cwd)

    assert roots[-1] == breadcrumb_root.resolve(strict=False)


def test_breadcrumb_not_added_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    roots = _iter_env_search_roots(unrelated_cwd)

    assert all(root != (tmp_path / ".aki") for root in roots)


def test_load_runtime_env_bootstraps_via_breadcrumb_from_unrelated_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "breadcrumb-repo"
    repo.mkdir()
    (repo / ".env").write_text("BREADCRUMB_VAR=from-breadcrumb\n", encoding="utf-8")
    write_breadcrumb(repo)

    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.delenv("BREADCRUMB_VAR", raising=False)

    loaded_path = load_runtime_env()

    assert loaded_path == (repo / ".env").resolve(strict=False)
    assert os.environ.get("BREADCRUMB_VAR") == "from-breadcrumb"


def test_load_runtime_env_prefers_current_context_over_breadcrumb(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    current_repo = tmp_path / "current-repo"
    current_repo.mkdir()
    (current_repo / ".env").write_text("CURRENT_VAR=from-current\n", encoding="utf-8")
    (current_repo / ".git").mkdir()

    other_repo = tmp_path / "other-repo"
    other_repo.mkdir()
    (other_repo / ".env").write_text("CURRENT_VAR=from-breadcrumb\n", encoding="utf-8")
    write_breadcrumb(other_repo)

    monkeypatch.chdir(current_repo)
    monkeypatch.delenv("CURRENT_VAR", raising=False)

    loaded_path = load_runtime_env()

    assert loaded_path == (current_repo / ".env").resolve(strict=False)
    assert os.environ.get("CURRENT_VAR") == "from-current"
