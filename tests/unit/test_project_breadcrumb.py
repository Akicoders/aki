from __future__ import annotations

import json
from pathlib import Path

from agentos.core.project_breadcrumb import read_breadcrumb, write_breadcrumb


def test_write_then_read_round_trips_to_resolved_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "my-project"
    project_root.mkdir()

    write_breadcrumb(project_root)

    assert read_breadcrumb() == project_root.resolve(strict=False)


def test_read_returns_none_when_no_file_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert read_breadcrumb() is None


def test_read_returns_none_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    breadcrumb_dir = tmp_path / ".aki"
    breadcrumb_dir.mkdir()
    (breadcrumb_dir / "last-project.json").write_text("not valid json{", encoding="utf-8")

    assert read_breadcrumb() is None


def test_read_returns_none_when_stored_root_path_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    breadcrumb_dir = tmp_path / ".aki"
    breadcrumb_dir.mkdir()
    payload = {
        "root_path": str(tmp_path / "does-not-exist"),
        "updated_at": "2026-07-02T14:03:21.512+00:00",
    }
    (breadcrumb_dir / "last-project.json").write_text(json.dumps(payload), encoding="utf-8")

    assert read_breadcrumb() is None


def test_write_creates_aki_directory_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "my-project"
    project_root.mkdir()
    assert not (tmp_path / ".aki").exists()

    write_breadcrumb(project_root)

    assert (tmp_path / ".aki").is_dir()
    assert (tmp_path / ".aki" / "last-project.json").is_file()


def test_write_is_best_effort_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "my-project"
    project_root.mkdir()

    def _raise_mkdir(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _raise_mkdir)

    write_breadcrumb(project_root)  # must not raise


def test_updated_at_field_present_and_iso8601(tmp_path, monkeypatch):
    from datetime import datetime

    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "my-project"
    project_root.mkdir()

    write_breadcrumb(project_root)

    raw = json.loads((tmp_path / ".aki" / "last-project.json").read_text(encoding="utf-8"))
    assert "updated_at" in raw
    datetime.fromisoformat(raw["updated_at"])
