# Aki Hackathon MVP Plan

This document records the public MVP plan for Aki, an AI agent with portable project memory for AI coding agents.

## Completed MVP scope

- Local stdio MCP server via `uv run agentos mcp`.
- Five MCP memory tools: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`.
- SQLite and ChromaDB-backed local memory storage.
- Qwen-powered structured memory extraction.
- Deterministic fallback for core memory operations when Qwen credentials are absent.
- OpenCode, Claude Code, and Antigravity-style integration documentation.

## Remaining publish tasks

- Create the public GitHub repository and set the real remote.
- Replace placeholder repository URLs with final coordinates.
- Decide whether to keep `agentos` as the long-term CLI command or migrate fully to `aki` in a later breaking release.
- Publish package/container artifacts only after final repository naming is confirmed.

## Out of scope for MVP

- REST API or `/health` endpoint.
- Hosted production deployment.
- WhatsApp, Telegram, or voice integrations.
- Multi-user or team tenancy.

The MVP is intentionally narrow so the hackathon demo stays focused on the coding-agent memory loop.
