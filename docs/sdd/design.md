# Design: Hackathon MVP — Qwen Memory Bridge

## Technical Approach

Implement a local stdio MCP server as a thin adapter over the existing `MemoryRepository` and `QwenClient`. Keep the existing Typer CLI and add `agentos mcp` for host integration. The MVP optimizes for OpenCode first: five compact MCP tools return bounded, provenance-rich memory capsules and never require real Qwen or sentence-transformers in tests.

## Architecture Decisions

| Decision | Choice | Alternatives / Tradeoff | Rationale |
|---|---|---|---|
| MCP runtime | Use the official `mcp` Python SDK | Raw JSON-RPC is fewer deps but higher protocol risk | Four-day deadline favors correct stdio handshake, schemas, and host compatibility. |
| CLI integration | Add `agentos mcp` and `agentos mcp-config opencode` in `src/agentos/cli/main.py` | Separate binary is cleaner but more packaging work | Reuses existing `agentos` script and config callback. |
| Memory output | Add `MemoryCapsule` formatter separate from Spanish `MemoryContext.format_for_prompt()` | Reusing prompt formatter is faster but too chat-oriented | Coding agents need English, compact, source-tagged capsules. |
| Extraction | Add `QwenMemoryExtractor` using Qwen chat JSON output, with deterministic fallback validation | Direct free-form chat is simpler but brittle | Structured facts/decisions/procedures are the demo differentiator. |
| Embeddings | Inject an `Embedder` protocol into `MemoryRepository` | Keep direct `SentenceTransformer` construction | Fixes slow/flaky CI and allows fake embeddings. |
| Project detection | `project` argument optional; default from cwd git root basename, else cwd name, else `default` | Require explicit project | MCP hosts call from project directories; useful defaults improve demo UX. |
| Host config | Document OpenCode local MCP config; print snippet via CLI | Auto-edit host config | Safer for MVP; avoids corrupting user configs. |

## Data Flow

```text
OpenCode / Claude Code
  -> stdio MCP request
  -> agentos.mcp.server tool handler
  -> ProjectResolver(cwd, optional project)
  -> MemoryService
       -> MemoryRepository(SQLite + Chroma)
       -> QwenMemoryExtractor/Explainer when requested
  -> MemoryCapsule JSON/text response
```

`memory_extract` flow:

```text
text -> Qwen structured JSON -> validate items -> add source event
     -> upsert facts / add decision events / add procedure events -> capsule summary
```

## File Changes

| File | Action | Description |
|---|---|---|
| `pyproject.toml` | Modified | Add `mcp`, fix Ruff config, add `beautifulsoup4`; keep dev deps. |
| `src/agentos/cli/main.py` | Modified | Add `mcp` stdio command and `mcp_config(host="opencode")` snippet command. |
| `src/agentos/mcp/__init__.py` | Created | MCP package export. |
| `src/agentos/mcp/server.py` | Created | MCP app, stdio entrypoint, tool registration. |
| `src/agentos/mcp/tools.py` | Created | Tool schemas and handlers for five tools. |
| `src/agentos/mcp/project.py` | Created | cwd/git-root project detection. |
| `src/agentos/memory/capsule.py` | Created | Bounded capsule formatter and response models. |
| `src/agentos/memory/repository.py` | Modified | Inject embedder; add safe empty-query handling; remove global repo use from create helper or accept repo. |
| `src/agentos/memory/models.py` | Modified | Add optional capsule/extraction Pydantic models if not kept in new modules. |
| `src/agentos/qwen/client.py` | Modified | Add `structured_json()` helper for extraction/explanation. |
| `src/agentos/qwen/extraction.py` | Created | Extraction prompt, validation, mapping to memory writes. |
| `tests/*` | Modified/Created | Fake embedder/Qwen fixtures plus MCP tool tests. |
| `Dockerfile`, `docker-compose*.yml` | Modified | For MCP demo, remove HTTP health assumptions or make explicit that compose is not the stdio path. |

## Interfaces / Contracts

MCP tools return JSON-serializable dicts with `ok`, `project`, `capsule` or `items`, and `errors`.

```python
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...

class MemoryCapsule(BaseModel):
    project: str
    facts: list[MemoryFact]
    decisions: list[MemoryEvent]
    procedures: list[MemoryEvent]
    recent: list[MemoryEvent]
    sources: list[str]
    rendered: str
```

Tool contracts:
- `memory_context(project?: str, query?: str, limit?: int=10)` returns capsule.
- `memory_search(query: str, project?: str, limit?: int=10)` returns ranked facts/events.
- `memory_save(kind: "fact"|"decision"|"procedure"|"event", title: str, content: str, project?: str, confidence?: float)` stores memory.
- `memory_extract(text: str, project?: str, source?: str)` extracts and stores structured memories.
- `memory_explain(query: str, project?: str)` returns retrieved items plus Qwen or deterministic relevance explanation.

## Error Handling Strategy

Validate tool inputs at MCP boundary; return structured tool errors for user mistakes. Let startup/config errors fail fast on stderr. Qwen failures degrade gracefully: store raw event and return extraction error metadata. Repository failures preserve exception context and never silently swallow writes.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | project detection, capsule formatting, extraction parsing, validation errors | pytest parametrized tests; fake Qwen JSON. |
| Repository | save/search/context without real embeddings | `FakeEmbedder` fixture; temp SQLite/Chroma; no sentence-transformers in CI. |
| MCP | all five tool handlers and schema shape | call handlers directly; optional SDK stdio smoke test marked integration. |
| CLI | `agentos mcp-config opencode` output | Typer runner snapshot/string assertions. |

## Integration Points

OpenCode config:

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

Claude Code/Antigravity docs use the same command with host-specific config keys. No migration required; existing SQLite tables are reused.
