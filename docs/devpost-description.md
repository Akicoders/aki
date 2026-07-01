# Aki: Portable Project Memory for AI Coding Agents

## Tagline

AI agents that remember your project decisions and apply them automatically.

## Problem

Every time you start a new session with an AI coding assistant, it forgets everything. Your package manager choice, your architecture decisions, your setup procedures — gone. You repeat yourself constantly, and the agent makes the same mistakes every time. Existing memory solutions are either cloud-dependent, tied to a single vendor, or designed for chat conversations rather than developer workflows.

## Solution

Aki is a local-first AI agent that gives coding assistants durable project memory through MCP (Model Context Protocol). It stores decisions, facts, and procedures in SQLite and ChromaDB, uses Qwen for structured extraction from prose, and exposes everything through five MCP tools that any compatible coding assistant can call. When your AI agent starts a new session, it queries Aki first — and the response changes because it knows your project history.

## Key Features

- **5 MCP tools**: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, `memory_explain` — the full memory lifecycle in one protocol
- **Qwen-powered extraction**: turns architecture prose into structured memory candidates (facts, decisions, procedures) using Qwen Cloud APIs
- **OpenCode + Claude Code integration**: one command generates the MCP config, restart your editor, done
- **Episodic, semantic, and procedural memory**: not just a key-value store — events, facts, and repeatable procedures with confidence scores
- **Deterministic fallback**: all core operations work without Qwen credentials — save, search, and context assembly never depend on external APIs
- **Local-first**: SQLite + ChromaDB on your machine, no cloud storage required, your project data stays private

## Technical Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| LLM | Qwen Cloud (qwen3.7-max, qwen3.7-plus) |
| Protocol | MCP (Model Context Protocol) over stdio |
| Storage | SQLite (SQLAlchemy) + ChromaDB (vector search) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (local) |
| CLI | Typer + Rich |
| Testing | pytest (51 tests passing) |

## What Makes It Different

Most memory agents are built for chat — they remember what you said last Tuesday. Aki is built for developer workflow. It understands the difference between a fact ("we use pnpm"), a decision ("the MVP runtime is MCP stdio, not HTTP"), and a procedure ("run uv sync before testing"). It stores these with project scope, confidence scores, and vector embeddings so agents can retrieve exactly what they need before editing code.

The MCP-first design means Aki works with any compatible host — OpenCode, Claude Code, or any tool that speaks MCP stdio. No vendor lock-in, no REST API, no cloud dependency for core operations.

## Demo Video

[Video will be uploaded here]

## Installation

```bash
git clone https://github.com/Akicoders/aki
cd aki
uv sync --all-extras
uv run aki --help
```

### Quick start

```bash
# Generate MCP config for OpenCode
uv run aki mcp-config opencode

# Start the MCP server
uv run aki mcp

# Or use the CLI directly
uv run aki remember "We use pnpm" --project my-project
uv run aki recall "package manager" --project my-project
```

### Optional: Qwen extraction

```bash
cp .env.example .env
# Edit .env and set QWEN_API_KEY
uv run aki mcp  # memory_extract now uses Qwen for structured extraction
```

## Links

- **GitHub**: https://github.com/Akicoders/aki
- **Docs**: https://github.com/Akicoders/aki/tree/main/docs
- **Integration guide**: https://github.com/Akicoders/aki/blob/main/docs/integration.md
- **Demo walkthrough**: https://github.com/Akicoders/aki/blob/main/docs/demo.md

## Built with

- [Qwen Cloud](https://qwen.ai/) — LLM for extraction and explanation
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol for tool delivery
- [ChromaDB](https://www.trychroma.com/) — vector search for semantic memory retrieval
- [SQLite](https://www.sqlite.org/) — durable local storage
