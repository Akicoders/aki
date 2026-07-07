# Aki: Persistent Project Memory for AI Coding Agents

## Tagline

Persistent memory, session continuity, and repo-aware operations for AI coding agents.

## Problem

Most AI coding sessions are stateless.

The agent may be strong, but it forgets project decisions, onboarding steps, prior fixes, and delivery context the moment the session ends. That creates repeated prompts, inconsistent suggestions, and wasted time across real engineering workflows.

## Solution

Aki is a local-first open-source product that gives coding agents durable project memory through MCP.

It combines:

- persistent project memory;
- resumable sessions and checkpoints;
- operational cockpit and audit views;
- specialized agent profiles;
- host bootstrap for OpenCode and Claude Code;
- SDD-aware project context.

The result is simple but powerful: an AI agent can come back to a repository and continue with context instead of starting blind.

## Why it stands out

Most memory products stop at “store some notes.” Aki goes further:

- **Memory that fits engineering work** — facts, decisions, procedures, and events, not generic chat history.
- **Session continuity** — project sessions can resume with stored checkpoints.
- **Operational visibility** — cockpit, project registry, doctor, and structured audit reports.
- **Agent specialization** — planner / builder / reviewer-style profiles with scoped tools and memory.
- **Workflow awareness** — built-in handling for SDD artifacts and repo health.
- **MCP-native integration** — designed for coding-agent hosts, not retrofitted from a chat app.

## Key Features

- **5 MCP memory tools**: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, `memory_explain`
- **Local-first storage**: SQLite + ChromaDB
- **Qwen-powered extraction** when credentials are configured
- **Deterministic fallback** for core memory flows without Qwen credentials
- **Operational cockpit** when running `aki` inside a recognized project
- **Project audit engine** with markdown reports under `docs/audits/`
- **Project registry** for browsing known repos
- **Specialized agent profiles** with tool and memory policies
- **SDD bootstrap and awareness** via `aki sdd-init` and artifact detection
- **MCP bootstrap** through `aki mcp-config` and `aki mcp-setup`

## Technical Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Protocol | MCP over stdio |
| LLM | Qwen Cloud / DashScope-compatible APIs |
| Storage | SQLite + ChromaDB |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| CLI / UX | Typer + Rich |
| CI | GitHub Actions |

## Demo Story

The strongest demo path is:

1. open the cockpit with `uv run aki`;
2. run `uv run aki audit aki`;
3. show `uv run aki agents`;
4. generate host bootstrap with `uv run aki mcp-config opencode`;
5. demonstrate that a stored project decision changes the agent’s next answer.

That sequence tells a credible product story: Aki is not only memory, it is memory plus operating context for real coding workflows.

## Alibaba / Qwen alignment

Aki’s default Qwen configuration targets the DashScope international endpoint:

```text
https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

That gives the project a concrete, repo-level proof of Qwen/Alibaba compatibility while keeping the core product local-first.

## Quick Start

```bash
git clone https://github.com/Akicoders/aki.git
cd aki
uv sync --all-extras
uv run aki doctor
uv run aki
```

## Links

- **GitHub**: https://github.com/Akicoders/aki
- **README**: https://github.com/Akicoders/aki/blob/main/README.md
- **Integration guide**: https://github.com/Akicoders/aki/blob/main/docs/integration.md
- **Evaluator walkthrough**: https://github.com/Akicoders/aki/blob/main/docs/demo.md
- **Agent profiles**: https://github.com/Akicoders/aki/blob/main/docs/agent-profiles.md
