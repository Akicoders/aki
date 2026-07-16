"""Persistent project registry backed by the Aki memory SQLite database."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from agentos.memory.database import Database, get_database
from agentos.memory.models import ProjectRefModel, ProjectRefRecord


def _canonical_root(root_path: Path) -> str:
    return str(Path(root_path).expanduser().resolve())


def upsert_project(
    key: str,
    root_path: Path,
    source: str = "detected",
    database: Optional[Database] = None,
) -> ProjectRefRecord:
    """Insert or update the ProjectRef row for the given canonical root path."""
    db = database or get_database()
    canonical = _canonical_root(root_path)
    now = datetime.utcnow()

    with db.session() as session:
        model = session.get(ProjectRefModel, canonical)
        if model is None:
            model = ProjectRefModel(
                root_path=canonical,
                key=key,
                source=source,
                last_opened_at=now,
            )
            session.add(model)
        else:
            model.key = key
            model.source = source
            model.last_opened_at = now
        session.flush()
        record = ProjectRefRecord.from_model(model)

    return record


def list_projects(database: Optional[Database] = None) -> list[ProjectRefRecord]:
    """Return all known ProjectRef records, most recently opened first."""
    db = database or get_database()
    with db.session() as session:
        models = session.execute(
            select(ProjectRefModel).order_by(ProjectRefModel.last_opened_at.desc())
        ).scalars().all()
        return [ProjectRefRecord.from_model(model) for model in models]


def touch_last_opened(root_path: Path, database: Optional[Database] = None) -> Optional[ProjectRefRecord]:
    """Update last_opened_at for an existing ProjectRef. Returns None if unknown."""
    db = database or get_database()
    canonical = _canonical_root(root_path)
    with db.session() as session:
        model = session.get(ProjectRefModel, canonical)
        if model is None:
            return None
        model.last_opened_at = datetime.utcnow()
        session.flush()
        return ProjectRefRecord.from_model(model)


def touch_last_audit(root_path: Path, database: Optional[Database] = None) -> Optional[ProjectRefRecord]:
    """Update last_audit_at for an existing ProjectRef. Returns None if unknown."""
    db = database or get_database()
    canonical = _canonical_root(root_path)
    with db.session() as session:
        model = session.get(ProjectRefModel, canonical)
        if model is None:
            return None
        model.last_audit_at = datetime.utcnow()
        session.flush()
        return ProjectRefRecord.from_model(model)


def delete_project(root_path: Path | str, database: Optional[Database] = None) -> bool:
    """Delete a ProjectRef from the DB registry by root path. Returns True if deleted, False if not found."""
    db = database or get_database()
    canonical = _canonical_root(Path(root_path))
    with db.session() as session:
        model = session.get(ProjectRefModel, canonical)
        if model is None:
            return False
        session.delete(model)
        session.flush()
        return True

