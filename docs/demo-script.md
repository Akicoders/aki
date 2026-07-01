# Aki Demo Script (2-3 minutes)

## Pre-flight checklist (do before recording)

```bash
cd /path/to/aki
uv sync --all-extras
cp .env.example .env
# Edit .env and set QWEN_API_KEY if you want extraction demo
# Verify MCP tools work:
uv run python -c "
from pathlib import Path; from tempfile import TemporaryDirectory
from agentos.mcp.tools import MemoryToolHandlers; from agentos.memory.repository import MemoryRepository
class FakeEmbedder:
    def embed(self, text): return [1.0, 0.0, 0.0]
with TemporaryDirectory() as tmp:
    repo = MemoryRepository(db_path=Path(tmp)/'a.db', chroma_path=Path(tmp)/'c', embedder=FakeEmbedder())
    h = MemoryToolHandlers(repository=repo, qwen_client=None)
    print(h.memory_save('decision', 'Test', 'It works', project='smoke'))
"
```

---

## Scene 1: Intro (15 seconds)

**Screen**: Terminal with project README visible

**Say**:
> "This is Aki — an AI agent that gives coding assistants portable project memory. It runs as a local MCP server, so any MCP-compatible tool like OpenCode or Claude Code can save and retrieve project decisions automatically."

---

## Scene 2: Setup (30 seconds)

**Screen**: Terminal

**Type and say**:
> "First, let's generate the MCP configuration for OpenCode:"

```bash
uv run aki mcp-config opencode
```

**Show** the JSON output:
```json
{
  "mcp": {
    "aki_memory": {
      "type": "local",
      "command": ["uv", "run", "aki", "mcp"],
      "enabled": true
    }
  }
}
```

**Say**:
> "This tells OpenCode to spawn Aki as a local stdio MCP server. Five tools become available: memory_context, memory_search, memory_save, memory_extract, and memory_explain."

---

## Scene 3: Save a decision (20 seconds)

**Screen**: OpenCode session (or Python REPL as fallback)

**Option A — via OpenCode** (if MCP is connected):

Type in OpenCode:
```
Save this decision in Aki memory for project aki:
we use pnpm in this project.
```

**Option B — via Python REPL** (fallback if OpenCode MCP not connected):

```bash
uv run python -c "
from agentos.mcp.tools import MemoryToolHandlers
h = MemoryToolHandlers()
result = h.memory_save('decision', 'Package manager', 'We use pnpm for dependency management.', project='aki-demo')
import json; print(json.dumps(result, indent=2))
"
```

**Say**:
> "I'm saving a project decision: we use pnpm. Aki stores this as a structured memory with type, confidence, and project scope."

**Show** the result:
```json
{
  "ok": true,
  "project": "aki-demo",
  "memory": {
    "id": "evt_...",
    "title": "Package manager",
    "kind": "decision",
    "summary": "We use pnpm for dependency management."
  }
}
```

---

## Scene 4: Extract memories from prose (25 seconds)

**Screen**: Same session

**Type**:
```bash
uv run python -c "
from agentos.mcp.tools import MemoryToolHandlers
h = MemoryToolHandlers()
result = h.memory_extract(
    text='The architecture uses a local stdio MCP server. Memory is persisted in SQLite for facts and ChromaDB for vector search. The MVP excludes REST API, WhatsApp, and multi-user features. Agents should call memory_context before editing code.',
    project='aki-demo'
)
import json; print(json.dumps(result, indent=2))
"
```

**Say**:
> "Now I'm passing a paragraph about our architecture. Qwen extracts structured memory candidates — facts, decisions, and procedures — and Aki stores them automatically."

**Fallback** (if Qwen API fails):
> "Qwen extraction requires API credentials. Without them, you can still save memories manually with memory_save — which is what we just did."

---

## Scene 5: Query memory and show behavior change (30 seconds)

**Screen**: Same session

**Type**:
```bash
uv run python -c "
from agentos.mcp.tools import MemoryToolHandlers
h = MemoryToolHandlers()
result = h.memory_context(project='aki-demo', query='how to install dependencies')
import json; print(json.dumps(result, indent=2))
"
```

**Say**:
> "Now I query memory_context with 'how to install dependencies'. Aki returns a memory capsule that includes our earlier decision: we use pnpm."

**Show** the capsule output with the decision visible.

**Say**:
> "Without Aki, an AI agent would guess npm or pip. With Aki, it knows the project uses pnpm because the decision was persisted. This is the key moment: memory changes agent behavior."

---

## Scene 6: Show the five MCP tools (15 seconds)

**Screen**: Quick scroll through the tool list or `docs/integration.md`

**Say**:
> "Aki exposes five MCP tools: memory_context for retrieving project context, memory_search for specific queries, memory_save for storing decisions and facts, memory_extract for Qwen-powered structured extraction, and memory_explain for understanding why a memory is relevant."

---

## Scene 7: Outro (15 seconds)

**Screen**: Terminal with `uv run aki --help` output

**Say**:
> "Aki makes AI agents remember your project. It's local-first, works without cloud dependencies, and integrates with any MCP-compatible coding tool. The code is open source — link in the description."

---

## Fallback plan

If anything breaks during recording:

1. **MCP server won't start**: Use the Python REPL approach (Option B) for all demos
2. **Qwen API fails**: Skip Scene 4, mention deterministic fallback in Scene 5
3. **Sentence-transformers slow to load**: Pre-run any command once before recording to warm the cache
4. **CLI commands crash**: Known issue with `aki remember`/`recall`/`facts` (abstract method bug). Use MCP tools via Python or OpenCode MCP integration instead

## Timing summary

| Scene | Duration | Cumulative |
|-------|----------|------------|
| Intro | 15s | 0:15 |
| Setup | 30s | 0:45 |
| Save decision | 20s | 1:05 |
| Extract memories | 25s | 1:30 |
| Query + behavior change | 30s | 2:00 |
| Five tools overview | 15s | 2:15 |
| Outro | 15s | 2:30 |
