# Proposal: Hackathon MVP

## Intent

Pivot `agentos-memory` into **Qwen Memory Bridge**: portable project memory for AI coding agents, powered by Qwen and delivered through a local stdio MCP server. The goal is a credible July 1 hackathon demo for developers using OpenCode first, with Claude Code and Antigravity documented as secondary hosts.

## Scope

### In Scope
- Fix repo blockers: initial git/GitHub readiness, Ruff config, missing deps, mypy/pytest path to credible CI.
- Implement local MCP stdio server exposing five memory tools.
- Add Qwen-powered extraction for facts, decisions, procedures, and compact memory capsules.
- Provide OpenCode integration config/docs and a demo script.
- Update README/submission assets around the MCP developer-memory positioning.

### Out of Scope
- WhatsApp, Telegram, voice, REST dashboard, full MCP aggregation, Composio OAuth.
- Autonomous skill creation, production scheduler, multi-user/team memory, observability stack.

## Capabilities

### New Capabilities
- `mcp-memory-server`: Local stdio MCP server exposing memory tools to coding agents.
- `qwen-memory-extraction`: Qwen extracts structured project facts, decisions, procedures, and relevance explanations.
- `coding-agent-integration`: OpenCode setup plus documented Claude Code/Antigravity configuration.
- `hackathon-readiness`: CI, docs, demo, and Devpost-ready repository polish.

### Modified Capabilities
- None; no existing OpenSpec capabilities are present.

## Approach

Keep the MVP narrow: make memory useful inside existing coding agents instead of building another chatbot. Add `agentos mcp`, implement tools `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`, reuse SQLite/Chroma memory, fake Qwen/embedder in tests, and avoid API/channel scope unless core demo is green.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | Fix tooling config; add MCP/runtime deps. |
| `src/agentos/cli/main.py` | Modified | Add MCP entrypoint/config helper. |
| `src/agentos/mcp/server.py` | New | MCP stdio server and tool registration. |
| `src/agentos/memory/*` | Modified | Retrieval capsules, provenance, testable embedder injection. |
| `src/agentos/qwen/client.py` | Modified | Extraction/summarization/classification support. |
| `tests/*` | Modified | Fast fakes; CI-safe coverage for MCP/extraction. |
| `README.md`, `docs/*` | Modified | Positioning, integration docs, demo script. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope explosion into channels/API/aggregator | High | Enforce MCP-only MVP cut line. |
| MCP tool/context bloat | Med | Five compact tools; capsule output limits. |
| Qwen/API instability | Med | Fake clients for tests; recorded demo fallback. |
| CI blockers consume demo time | High | Fix tooling first before feature polish. |

## Rollback Plan

Revert MCP/extraction files and docs, keep blocker fixes if green. If MCP fails late, ship CLI-only memory demo with the same Qwen extraction narrative.

## Dependencies

- Qwen API credentials for real extraction demo.
- MCP Python SDK or equivalent stdio JSON-RPC implementation.
- Public GitHub repo and green-enough CI.

## Success Criteria

- [x] OpenCode can call the local MCP server via documented config.
- [x] All five memory tools work against local project memory.
- [x] Qwen extracts decisions/facts/procedures from text into stored memory.
- [x] Tests/CI are credible and do not hang on sentence-transformers.
- [x] README/demo clearly show memory changing coding-agent behavior.
