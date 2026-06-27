# Aki MVP Technical Specification

Aki is an AI agent that provides portable project memory for AI coding agents through a local stdio MCP server.

## Scope

The MVP focuses on one runtime path:

```bash
uv run agentos mcp
```

The Python package and historical CLI command remain `agentos` for compatibility, but the user-facing agent name is **Aki**.

## Supported MCP tools

- `memory_context`: returns a compact memory capsule for a project.
- `memory_search`: searches stored facts and events.
- `memory_save`: stores a durable fact, decision, or procedure.
- `memory_extract`: uses Qwen to extract structured memories from prose.
- `memory_explain`: explains why memories are relevant to a query.

## Storage

- SQLite stores durable facts and events.
- ChromaDB supports vector-backed event retrieval.
- Local paths default to `data/agentos.db` and `data/chroma_db`.

## Qwen behavior

Qwen credentials are required for `memory_extract` and can enrich `memory_explain`.
Without Qwen credentials, manual `memory_save`, `memory_search`, and `memory_context` continue to work.

## Non-goals

- REST API or web dashboard
- WhatsApp, Telegram, or voice ingestion
- multi-user/team tenancy
- hosted production deployment
- HTTP health checks

These items are intentionally out of scope for the hackathon MVP.
