# Aki demo script

This walkthrough proves the MVP claim: Aki is an AI agent whose project memory changes coding-agent behavior across interactions.

## 0. Prepare the repository

```bash
uv sync --all-extras
cp .env.example .env
```

Optional for Qwen extraction:

```bash
export QWEN_API_KEY=your_qwen_api_key_here
export QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export QWEN_MODEL=qwen-max
```

## 1. Start `agentos mcp` as an OpenCode local MCP server

Generate the OpenCode snippet:

```bash
uv run agentos mcp-config opencode
```

Copy the JSON into OpenCode MCP configuration:

```json
{
  "mcp": {
    "aki_memory": {
      "type": "local",
      "command": ["uv", "run", "agentos", "mcp"],
      "enabled": true
    }
  }
}
```

Restart OpenCode from the repository root. The host should start `uv run agentos mcp` over stdio.

## 2. Save a project decision

Ask the coding agent to call `memory_save`:

```text
Save this decision in Aki memory for project aki:
we use pnpm in this project.
```

Expected MCP call shape:

```json
{
  "kind": "decision",
  "title": "Package manager",
  "content": "We use pnpm in this project.",
  "project": "aki",
  "confidence": 1.0
}
```

Expected result: `ok: true` with a stored memory item.

## 3. Extract structured memories from architecture prose

With Qwen credentials configured, ask the agent to call `memory_extract`:

```text
Extract durable memories for aki from this paragraph:

The architecture uses a local stdio MCP server so coding hosts can attach without a REST API.
Memory is persisted in SQLite for facts and events, with ChromaDB used for vector-backed event retrieval.
The project decision is to keep WhatsApp, Telegram, voice, REST, and multi-user features out of the MVP.
Agents should call memory_context before editing and memory_save after important decisions or bug fixes.
```

Expected result: Qwen returns structured candidates grouped as facts, decisions, and procedures; the handler stores them and returns a refreshed memory capsule.

## 4. Query `memory_context` and show behavior change

Now ask the coding agent:

```text
Before suggesting install commands for this repository, read project memory.
How should dependencies be installed?
```

Expected MCP call:

```json
{
  "project": "aki",
  "query": "install dependencies package manager",
  "limit": 10
}
```

Expected behavior change:

- Without memory, the agent may suggest `npm install`, `pip install`, or generic commands.
- With memory, the agent should mention the stored decision: `pnpm` is the chosen package manager for this project.

This is the demo moment: the answer changes because the agent consulted durable project memory instead of guessing from the prompt alone.

## 5. Fallback path when Qwen credentials are absent

Unset Qwen credentials:

```bash
unset QWEN_API_KEY
```

Then run the same project with manual memory operations:

```text
Save a decision: The MVP runtime is local MCP stdio, not HTTP.
Search memory for: runtime MCP HTTP.
Read memory_context for: runtime path.
```

Expected fallback behavior:

- `memory_save` works because it does not require Qwen.
- `memory_search` works against stored facts/events.
- `memory_context` returns a memory capsule.
- `memory_explain` can still produce deterministic keyword explanations and include the Qwen error in `errors`.
- `memory_extract` reports a clear Qwen extraction failure; use `memory_save` to store important items manually.

## Optional direct smoke test outside a host

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
    print(handlers.memory_context(project="demo", query="package manager"))
    print(handlers.memory_save("decision", "Package manager", "We use pnpm.", project="demo"))
    print(handlers.memory_search("pnpm", project="demo"))
PY
```

The final `memory_search` output should include the saved `Package manager` decision.
