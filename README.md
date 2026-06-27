# agentos-memory

Portable project memory for AI coding agents — powered by Qwen, delivered through MCP.

`agentos-memory` gives coding agents a durable memory layer for project decisions, conventions, procedures, and architecture notes. It runs locally as a stdio MCP server, so hosts such as OpenCode can retrieve context before editing code and save new knowledge after useful work.

## Vision

AI coding sessions should not start from zero every time. This project turns project knowledge into a portable memory capsule that can follow the repository across agent hosts without requiring a hosted REST API, chatbot bridge, or multi-user backend.

For the hackathon MVP, the core loop is intentionally focused:

1. A coding agent connects to `agentos-memory` through MCP stdio.
2. The agent asks for project context before acting.
3. The agent saves durable decisions and procedures after work.
4. Qwen Cloud can extract structured memories from prose.
5. Deterministic fallbacks keep local save/search/context flows useful when Qwen credentials are absent.

## Features

- **MCP stdio server** for local coding-agent integration.
- **Five memory tools**: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`.
- **Project-aware memory** using explicit project names or current-directory detection.
- **Persistent storage** with SQLite for facts/events and ChromaDB for vector-backed event search.
- **Qwen-powered extraction** for turning paragraphs into facts, decisions, and procedures.
- **Graceful local operation** for manual save/search/context when Qwen credentials are not configured.
- **Host-ready docs** for OpenCode, Claude Code, and Antigravity-style MCP hosts.

## Architecture

```text
┌────────────────────┐       stdio MCP        ┌────────────────────┐
│ AI coding host      │ ─────────────────────▶ │ agentos mcp         │
│ OpenCode / Claude   │ ◀───────────────────── │ FastMCP tools       │
└────────────────────┘                         └─────────┬──────────┘
                                                          │
                         ┌────────────────────────────────┼──────────────────────────────┐
                         ▼                                ▼                              ▼
              ┌──────────────────┐             ┌──────────────────┐          ┌──────────────────┐
              │ Memory handlers  │             │ Qwen extraction  │          │ Project detector │
              │ context/search   │             │ structured JSON  │          │ cwd/name aware   │
              │ save/explain     │             └──────────────────┘          └──────────────────┘
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ Memory store     │
              │ SQLite + Chroma  │
              └──────────────────┘
```

Primary runtime path:

```bash
uv run agentos mcp
```

Docker and compose files are development helpers only. They do not expose an HTTP service and do not define `/health` checks because the MVP interface is stdio MCP, not REST.

## Setup

### Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Optional: Qwen Cloud/DashScope-compatible API key for extraction and explanation enrichment

### Install

```bash
git clone <your-repo-url>
cd qwen-hackathon-memory-agent
uv sync --all-extras
```

### Configure environment

```bash
cp .env.example .env
```

For local save/search/context smoke checks, Qwen credentials are optional. For Qwen extraction, set:

```bash
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-max
QWEN_EMBEDDING_MODEL=text-embedding-v3
```

Memory defaults:

```bash
MEMORY_DB_PATH=data/agentos.db
MEMORY_CHROMA_PATH=data/chroma_db
MEMORY_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Validate the CLI

```bash
uv run agentos --help
uv run agentos mcp-config opencode
```

## OpenCode configuration

Generate the snippet:

```bash
uv run agentos mcp-config opencode
```

Expected output:

```json
{
  "mcp": {
    "agentos_memory": {
      "type": "local",
      "command": ["uv", "run", "agentos", "mcp"],
      "enabled": true
    }
  }
}
```

Add the `agentos_memory` entry to your OpenCode MCP configuration from the repository root. See [`docs/integration.md`](docs/integration.md) for host-specific notes.

## Claude Code notes

Claude Code MCP configuration is host-managed. Use the same local process shape:

```bash
uv run agentos mcp
```

Register it as a local stdio MCP server named `agentos_memory`. Start Claude Code from the project root when you want project auto-detection to resolve to this repository.

## Antigravity notes

Antigravity-style agent hosts that support local MCP stdio should use the same command array:

```json
{
  "name": "agentos_memory",
  "transport": "stdio",
  "command": "uv",
  "args": ["run", "agentos", "mcp"]
}
```

If your host requires an absolute working directory, point it at this repository. Do not configure an HTTP URL; there is no REST server in the MVP.

## Tool reference

### `memory_context`

Returns a compact memory capsule for a project.

Inputs:

- `project` optional project name. If omitted, the server attempts current-directory detection.
- `query` optional focus query.
- `limit` optional max number of facts/events, clamped to a safe range.

Use before coding to let the agent adapt to stored conventions.

### `memory_search`

Searches stored facts and events.

Inputs:

- `query` required search text.
- `project` optional project name.
- `limit` optional result count.

Use when the agent needs a specific past decision or procedure.

### `memory_save`

Stores a durable memory.

Inputs:

- `kind`: `fact`, `decision`, or `procedure`.
- `title`: concise searchable title.
- `content`: durable memory body.
- `project` optional project name.
- `confidence` optional score from `0` to `1`.

Use after decisions, bug fixes, setup discoveries, and repeatable procedures.

### `memory_extract`

Uses Qwen to extract structured memories from prose and stores them.

Inputs:

- `text` required source paragraph.
- `project` optional project name.
- `source` optional provenance label.

Requires Qwen credentials. Without them, the tool returns a clear Qwen extraction error; manual `memory_save` remains available.

### `memory_explain`

Searches memory and explains why returned memories are relevant.

Inputs:

- `query` required search text.
- `project` optional project name.

Qwen can enrich explanations when configured. If Qwen is unavailable, deterministic keyword-based explanations are returned with the Qwen error included in `errors`.

## Demo walkthrough

The full evaluator script is in [`docs/demo.md`](docs/demo.md). It shows:

1. OpenCode launching `agentos mcp` as a local MCP server.
2. Saving the decision “we use pnpm in this project.”
3. Extracting structured memories from an architecture paragraph.
4. Calling `memory_context` so the coding agent changes behavior based on memory.
5. Demonstrating the no-Qwen fallback path.

## Docker and compose

Build the image for development parity:

```bash
docker build -t agentos-memory .
```

Run the compose helper only when you intentionally want a containerized stdio process for manual development:

```bash
docker compose run --rm agentos agentos --help
```

Do not use compose as the normal runtime for OpenCode or Claude Code. Coding hosts should launch the local command directly so stdio remains attached to the host process.

## Development

```bash
uv sync --all-extras
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
    print(handlers.memory_context(project="demo", query="package manager"))
    print(handlers.memory_save("decision", "Package manager", "We use pnpm.", project="demo"))
    print(handlers.memory_search("pnpm", project="demo"))
PY
```

## Out of scope for the MVP

- WhatsApp integration
- Telegram integration
- Voice ingestion
- REST API or web dashboard
- Multi-user/team tenancy
- Hosted production service
- Long-running HTTP health checks

These are deliberately excluded so the submission stays focused on the coding-agent memory loop.

## Troubleshooting

See [`docs/troubleshooting.md`](docs/troubleshooting.md) for common setup and smoke-check issues.

## License

MIT
