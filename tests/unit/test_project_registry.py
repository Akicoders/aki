from __future__ import annotations

from pathlib import Path

import pytest

from agentos.memory.database import Database, init_db
from agentos.memory.models import ProjectRefModel
from agentos.cockpit import registry


@pytest.fixture
def registry_db(tmp_path) -> Database:
    return Database(tmp_path / "registry.db")


def test_init_db_creates_project_refs_table(registry_db):
    with registry_db.session() as session:
        rows = session.query(ProjectRefModel).all()
    assert rows == []


def test_upsert_project_inserts_new_row(registry_db, tmp_path):
    root = tmp_path / "repo-a"
    root.mkdir()

    record = registry.upsert_project("repo-a", root, source="git", database=registry_db)

    assert record.key == "repo-a"
    assert record.root_path == str(root.resolve())
    assert record.last_opened_at is not None

    all_records = registry.list_projects(database=registry_db)
    assert len(all_records) == 1


def test_upsert_project_updates_existing_row_instead_of_duplicating(registry_db, tmp_path):
    root = tmp_path / "repo-b"
    root.mkdir()

    first = registry.upsert_project("repo-b", root, source="git", database=registry_db)
    second = registry.upsert_project("repo-b", root, source="git", database=registry_db)

    assert first.root_path == second.root_path
    all_records = registry.list_projects(database=registry_db)
    assert len(all_records) == 1
    assert second.last_opened_at >= first.last_opened_at


def test_upsert_project_dedups_equivalent_relative_and_absolute_paths(registry_db, tmp_path):
    root = tmp_path / "repo-c"
    root.mkdir()
    relative_equivalent = root / ".." / "repo-c"

    registry.upsert_project("repo-c", root, source="git", database=registry_db)
    registry.upsert_project("repo-c", relative_equivalent, source="git", database=registry_db)

    all_records = registry.list_projects(database=registry_db)
    assert len(all_records) == 1


def test_touch_last_opened_updates_timestamp(registry_db, tmp_path):
    root = tmp_path / "repo-d"
    root.mkdir()
    registry.upsert_project("repo-d", root, source="git", database=registry_db)

    updated = registry.touch_last_opened(root, database=registry_db)

    assert updated is not None
    assert updated.last_opened_at is not None


def test_touch_last_audit_updates_timestamp(registry_db, tmp_path):
    root = tmp_path / "repo-e"
    root.mkdir()
    registry.upsert_project("repo-e", root, source="git", database=registry_db)

    updated = registry.touch_last_audit(root, database=registry_db)

    assert updated is not None
    assert updated.last_audit_at is not None


def test_touch_functions_return_none_for_unknown_project(registry_db, tmp_path):
    unknown = tmp_path / "never-registered"
    unknown.mkdir()

    assert registry.touch_last_opened(unknown, database=registry_db) is None
    assert registry.touch_last_audit(unknown, database=registry_db) is None


def test_delete_project_removes_record(registry_db, tmp_path):
    root = tmp_path / "repo-to-delete"
    root.mkdir()
    registry.upsert_project("repo-to-delete", root, source="git", database=registry_db)

    assert len(registry.list_projects(database=registry_db)) == 1

    # Delete existing
    assert registry.delete_project(root, database=registry_db) is True
    assert len(registry.list_projects(database=registry_db)) == 0

    # Delete non-existing
    assert registry.delete_project(root, database=registry_db) is False

