# Exploration: Hackathon MVP target ecosystem — MCP memory agent for AI coding tools

## Current State

The project currently positions itself as `agentos-memory`: a Qwen Cloud hackathon MemoryAgent with CLI-first persistent memory, a three-tier memory model, Qwen client, SQLite/ChromaDB storage, and built-in local skills. That original framing is too generic after the new information. The stronger ecosystem target is developers already using AI coding assistants — OpenCode, Claude Code, Antigravity, Qwen Code, Cursor-like tools — who need portable project memory and curated MCP access inside their existing tool, not a separate chatbot.

The existing codebase already has useful raw material: episodic/semantic/procedural memory models, a Typer/Rich CLI, Qwen Cloud integration, and skills for git/files/web/n8n/code intelligence. It does not yet expose an MCP server, does not consume MCP servers, and does not have a working API package despite README/Docker references.

## Gentle-ai analysis

Reference analyzed from `https://github.com/Gentleman-Programming/gentle-ai`.

Gentle-AI is a Go CLI/TUI ecosystem configurator for AI coding agents. It supercharges existing agents with persistent memory, SDD workflows, curated skills, MCP servers, AI provider switching, persona/permission rules, and per-phase model routing. It supports Claude Code, OpenCode, Antigravity, Qwen Code, Cursor, VS Code Copilot, Codex, Windsurf, Kiro, and others.

Architecture patterns:

- `internal/agents/<agent>/` centralizes per-agent config paths and MCP strategies.
- `internal/components/engram/` wires Engram without owning the memory store.
- `internal/components/mcp/` wires Context7 and other MCP config.
- `docs/codebase/memory-core.md` clearly separates installer/config ownership from actual memory ownership.

Reusable lessons:

1. Adapter strategy per AI host is mandatory because config schemas differ.
2. OpenCode uses strict `mcp` entries with `type: local|remote`; Claude-like clients commonly use `mcpServers`; Antigravity has its own shape.
3. Engram is local command-based (`engram mcp --tools=agent`); Context7 is remote HTTP (`https://mcp.context7.com/mcp`).
4. Memory should be a protocol capability inside the developer's existing AI tool, not a separate chat destination.
5. A one-command setup/config experience is valuable, but should not eclipse the MemoryAgent itself.

## OpenCode analysis

Reference analyzed from `https://github.com/anomalyco/opencode` and official docs from `https://opencode.ai/docs`.

OpenCode is an open-source AI coding agent with terminal UI, CLI, desktop app, server mode, GitHub action, agents, commands, permissions, tool execution, session history, context compaction, plugins, and MCP support. It includes built-in `build` and `plan` agents plus a `general` subagent.

OpenCode has strong internal context handling: durable session history, typed system context sources, context epochs, mid-conversation system messages, context snapshots, compaction, and bounded tool output. This solves transient runtime context, but not portable cross-tool project memory.

MCP support:

- Configured under `mcp` in `opencode.json` / `opencode.jsonc`.
- Local: `{ "type": "local", "command": ["..."] }`.
- Remote: `{ "type": "remote", "url": "https://...", "headers": {...}, "oauth": ... }`.
- CLI supports `opencode mcp list`, `add`, `auth`, `logout`, and `debug`.
- OAuth is supported for remote MCP servers; tokens are stored under `~/.local/share/opencode/mcp-auth.json`.
- MCP tools are available alongside built-in tools, but OpenCode warns that too many MCP tools consume context.

## MCP landscape and architecture

MCP is an open protocol for connecting AI applications to external systems. It uses:

- **Host**: AI app such as OpenCode, Claude Code, Claude Desktop, VS Code, Cursor.
- **Client**: one connection manager inside the host per server.
- **Server**: exposes capabilities.

MCP has a JSON-RPC 2.0 data layer and stdio/Streamable HTTP transport layer. Servers expose tools, resources, and prompts. Local stdio is the safest MVP path; remote HTTP is better for hosted/team setups later.

Composio MCP is a toolkit/action gateway. Current docs emphasize `composio.create(user_id)`, `session.tools()` for native tools, and `session.mcp.url`/headers for MCP. It is valuable for GitHub/Jira/Slack/etc., but OAuth/toolkit setup is risky for this 4-day MVP.

Context7 MCP provides up-to-date code docs. Remote endpoint: `https://mcp.context7.com/mcp`; optional `CONTEXT7_API_KEY` header. Tools include `resolve-library-id` and `query-docs`. It is a high-value adjacent integration for developer memory.

Engram MCP provides persistent memory via local command, commonly `engram mcp --tools=agent`. Tools include `mem_save`, `mem_search`, `mem_context`, `mem_get_observation`, `mem_session_summary`, and related memory lifecycle/update tools. Engram is both reference and potential interoperability target.

## New positioning statement

**Qwen Memory Bridge is a Qwen-powered MCP memory agent for developers using AI coding assistants. It gives OpenCode, Claude Code, Antigravity, and similar tools a shared project memory that remembers decisions, bugs, conventions, and workflow procedures — then retrieves the right memory and documentation at the moment the coding agent needs it.**

Short tagline:

> Portable project memory for AI coding agents — powered by Qwen, delivered through MCP.

Differentiation:

- Targets AI coding tools, not generic chat.
- Stores project decisions, bugs, commands, stack choices, and architecture constraints.
- Returns compact memory capsules suitable for LLM context.
- Uses Qwen for extraction, classification, summarization, and relevance scoring.
- Coexists with Context7, Engram, and Composio through MCP.

## Integration architecture recommendation

Build this primarily as a **local stdio MCP server** that AI coding tools connect to.

```text
OpenCode / Claude Code / Antigravity
  -> MCP client connection
  -> agentos-memory MCP server (local stdio for MVP)
       -> Qwen extraction/summarization
       -> SQLite + Chroma memory store
       -> optional Engram import/export bridge
       -> optional Context7 docs augmentation
       -> Composio action gateway later
```

Do not build a full MCP aggregator/host in the MVP. Consuming Composio, Context7, and Engram as MCP clients multiplies auth, routing, error handling, and context-budget risk. For 4 days, document coexistence and optionally add a small Context7 docs helper only if the core server is stable.

MVP tool surface should be tiny:

- `memory_context(project?: string)` — concise project memory capsule.
- `memory_search(query: string, project?: string, limit?: int)` — semantic/fact search.
- `memory_save(kind, title, content, project?, confidence?)` — structured save.
- `memory_extract(text, project?)` — Qwen extracts decisions/facts/procedures.
- Optional `memory_explain(query)` — explain relevance of retrieved memories.

## Approaches

1. **MCP memory server only** — expose local stdio MCP server with Qwen-powered extraction and local memory.
   - Pros: strongest ecosystem fit, demoable inside OpenCode, narrow enough for 4 days.
   - Cons: needs MCP SDK correctness and polished demo.
   - Effort: Medium.

2. **MCP aggregator/host** — expose one server that internally consumes Composio, Context7, and Engram MCP servers.
   - Pros: ambitious, strong integration story.
   - Cons: too risky in 4 days due to auth/tool routing/context budgets.
   - Effort: High.

3. **Gentle-AI-style installer/configurator** — write config for multiple clients.
   - Pros: high onboarding value.
   - Cons: may become installer project instead of MemoryAgent.
   - Effort: Medium/High.

4. **Original generic CLI/chat agent** — keep terminal/WhatsApp/Telegram direction.
   - Pros: aligned with current docs.
   - Cons: generic and misses the new ecosystem insight.
   - Effort: High.

## Recommendation

Build Approach 1 plus a tiny slice of Approach 3: `agentos mcp`, OpenCode config snippet/helper, and docs for Claude Code/Antigravity. Treat Context7/Engram/Composio as ecosystem integrations, not required runtime dependencies.
