"""Database layer for Aki memory."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, MemoryEventModel, MemoryFactModel, ProjectRefModel, SkillModel


def get_engine(db_path: Path) -> Engine:
    """Create SQLite engine with WAL mode and foreign keys."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    # Enable WAL mode and foreign keys
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-32768")  # 32MB cache
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create all tables."""
    Base.metadata.create_all(engine)


class Database:
    """Database wrapper with session management."""

    def __init__(self, db_path: Path):
        self.engine = get_engine(db_path)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        init_db(self.engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        self.engine.dispose()


# Global instance
_db: Optional[Database] = None


def get_database(db_path: Optional[Path] = None) -> Database:
    global _db
    if _db is None:
        if db_path is None:
            from agentos.core.config import get_config
            db_path = get_config().memory.db_path
        _db = Database(db_path)
    return _db


def reset_database() -> None:
    global _db
    if _db:
        _db.close()
        _db = None
