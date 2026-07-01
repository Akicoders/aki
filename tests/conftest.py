import tempfile
from pathlib import Path

import pytest

from agentos.core.config import reset_config
from agentos.memory.database import get_database, reset_database
from agentos.memory.repository import MemoryRepository, reset_embedder_cache


class FakeEmbedder:
    """Deterministic embedder for repository tests."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        seed = sum((index + 1) * ord(char) for index, char in enumerate(text.strip().lower()))
        values = [((seed + index * 31) % 997) / 997 for index in range(self.dimensions)]
        magnitude = sum(value * value for value in values) ** 0.5 or 1.0
        return [value / magnitude for value in values]


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state before each test."""
    reset_database()
    reset_config()
    reset_embedder_cache()
    yield
    reset_database()
    reset_config()
    reset_embedder_cache()


@pytest.fixture
def fake_embedder():
    """Create a deterministic embedder without model downloads."""
    return FakeEmbedder()


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", dir=tmp_path, delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def temp_chroma():
    """Create a temporary ChromaDB directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def memory_repo(temp_db, temp_chroma, fake_embedder):
    """Create a MemoryRepository with temporary storage."""
    return MemoryRepository(
        db_path=temp_db,
        chroma_path=temp_chroma,
        embedder=fake_embedder,
    )
