# Troubleshooting

## OpenCode cannot start the MCP server

Verify the command works from the repository root:

```bash
uv run agentos mcp-config opencode
uv run agentos --help
```

If your host cannot resolve `uv`, use an absolute path to `uv` in the host configuration.

## Do not configure an HTTP URL

The MVP does not expose REST or `/health`. Use local stdio MCP:

```bash
uv run agentos mcp
```

Docker and compose are development helpers, not the runtime path for coding hosts.

## Qwen extraction fails

Check that these variables are visible to the MCP process:

```bash
QWEN_API_KEY
QWEN_BASE_URL
QWEN_MODEL
```

If credentials are absent, this is non-blocking for the core demo. Use `memory_save`, `memory_search`, and `memory_context` manually. `memory_extract` specifically requires Qwen.

## First handler call downloads embedding models

The default repository uses `sentence-transformers/all-MiniLM-L6-v2`. The first local run may download model files. Tests avoid network dependency by injecting a fake embedder.

## Smoke checks

Run:

```bash
uv run ruff check .
uv run pytest tests/ -q
uv run agentos mcp-config opencode
```

Direct handler smoke test:

```bash
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory

from agentos.mcp.tools import MemoryToolHandlers
from agentos.memory.repository import MemoryRepository

class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

with TemporaryDirectory() as tmp:
    repo = MemoryRepository(
        db_path=Path(tmp) / "agentos.db",
        chroma_path=Path(tmp) / "chroma_db",
        embedder=FakeEmbedder(),
    )
    handlers = MemoryToolHandlers(repository=repo, qwen_client=None)
    assert handlers.memory_context(project="demo", query="package manager")["ok"] is True
    assert handlers.memory_save("decision", "Package manager", "We use pnpm.", project="demo")["ok"] is True
    result = handlers.memory_search("pnpm", project="demo")
    assert result["ok"] is True
    assert result["items"]
    print("direct handler smoke ok")
PY
```
