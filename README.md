# Aki

Portable project memory for AI coding agents — powered by Qwen, delivered through MCP.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-49%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

Aki is an AI agent that gives coding assistants durable project memory. It runs locally as a stdio MCP server so hosts such as OpenCode, Claude Code, and other MCP-compatible agents can retrieve project context before editing code and save new decisions after useful work.

## What is Aki?

Aki is a hackathon MVP for portable memory across AI coding sessions. Instead of forcing every agent session to rediscover repository conventions, architecture choices, and setup procedures, Aki stores those memories locally and exposes them through MCP tools.

Use Aki when you want an AI coding agent to:

- remember project decisions across sessions;
- search prior implementation notes before changing code;
- keep procedural setup knowledge close to the repository;
- extract structured memories from architecture prose with Qwen;
- keep working locally when Qwen credentials are unavailable.

## Features

- **Local stdio MCP server**: primary runtime is `uv run agentos mcp`.
- **Five MCP memory tools**: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`.
- **Qwen extraction**: turns prose into structured memory candidates when Qwen Cloud credentials are configured.
- **Deterministic fallback**: manual save/search/context and keyword explanations remain available without Qwen credentials.
- **Episodic, semantic, and procedural memory**: stores recent events, durable facts/decisions, and repeatable procedures.
- **Project-aware context**: uses explicit project names or current-directory detection.
- **Host integration docs**: includes setup notes for OpenCode, Claude Code, and Antigravity-style MCP hosts.

## Architecture

```text
┌────────────────────┐       stdio MCP        ┌────────────────────┐
│ AI coding host      │ ─────────────────────▶ │ Aki MCP server      │
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

The Python package and CLI entry point are currently named `agentos` for MVP compatibility. The user-facing agent name is **Aki**.

## Installation

### Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Optional: Qwen Cloud/DashScope-compatible API key for extraction and enriched explanations

### From source with uv

```bash
git clone https://github.com/Akicoders/aki.git
cd aki
uv sync --all-extras
```

### Local editable install

```bash
uv pip install -e .
```

### pip install

The package is not published to PyPI yet. Until a release is published, install from source.

## Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Qwen configuration:

```bash
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-max
QWEN_EMBEDDING_MODEL=text-embedding-v3
```

Memory storage defaults:

```bash
MEMORY_DB_PATH=data/agentos.db
MEMORY_CHROMA_PATH=data/chroma_db
MEMORY_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

`config.yaml` contains the same defaults for local development. Do not commit real API keys.

## Usage

Primary MCP runtime:

```bash
uv run agentos mcp
```

Generate an OpenCode MCP snippet:

```bash
uv run agentos mcp-config opencode
```

Other available CLI commands:

```bash
uv run agentos --help
uv run agentos chat "remember that we use pnpm" --project my-project
uv run agentos recall "package manager" --project my-project
uv run agentos remember "The MVP runtime is MCP stdio, not HTTP" --project my-project
uv run agentos facts --project my-project
```

The `agentos` command is retained for compatibility. A matching `aki` console script is also available after installing the package.

## MCP Integration

### OpenCode

```bash
uv run agentos mcp-config opencode
```

Expected output:

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

Add `aki_memory` to your OpenCode MCP configuration and restart OpenCode from the repository root.

### Claude Code

Register a local stdio MCP server with the same process shape:

```text
command: uv
args: run agentos mcp
transport: stdio
```

### Antigravity-style MCP hosts

```json
{
  "name": "aki_memory",
  "transport": "stdio",
  "command": "uv",
  "args": ["run", "agentos", "mcp"],
  "cwd": "/absolute/path/to/aki"
}
```

See [`docs/integration.md`](docs/integration.md) for host-specific notes.

## Demo walkthrough

The evaluator walkthrough is in [`docs/demo.md`](docs/demo.md). It shows how to:

1. start `agentos mcp` as an OpenCode local MCP server;
2. save a project decision such as “we use pnpm”;
3. extract structured memories from an architecture paragraph;
4. query `memory_context` and show it changing agent behavior;
5. demonstrate fallback behavior when Qwen credentials are absent.

## Docker and compose

Docker is a development helper, not the normal runtime path for coding hosts. MCP stdio must remain attached to the host process.

```bash
docker build -t aki-memory .
docker compose run --rm aki agentos --help
```

There are intentionally no compose ports and no `/health` checks. Aki's MVP interface is stdio MCP, not HTTP.

## Development

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest tests/ -q
uv run agentos mcp-config opencode
```

## Project Status

Aki is an MVP built for the Qwen hackathon. It is useful for local agent memory workflows, but it is not a hosted production service.

Out of scope for this MVP:

- REST API or web dashboard
- multi-user/team tenancy
- WhatsApp, Telegram, or voice ingestion
- hosted production deployment
- HTTP health checks

## Roadmap

- Publish the package and container image under final repository coordinates.
- Add more host-specific MCP examples after real-world testing.
- Improve structured extraction prompts and memory ranking.
- Add release automation once the public repository is created.

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md), run the test suite, and avoid committing credentials or local memory data.

## License

MIT. See [`LICENSE`](LICENSE).

## Credits

Built for the Qwen hackathon using Qwen Cloud-compatible APIs, MCP, SQLite, and ChromaDB.
