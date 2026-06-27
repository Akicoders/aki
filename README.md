# agentos-memory — MemoryAgent for Qwen Cloud Hackathon

Personal AI agent with persistent cross-session memory, running on terminal, WhatsApp, and Telegram.

## Quick Start

```bash
# Install
uv sync --all-extras

# Configure
cp .env.example .env
# Edit .env with your Qwen Cloud API key

# Run
uv run agentos --help
uv run agentos chat "recordá que en ERP-AI usamos pnpm"
uv run agentos chat "cómo instalamos deps en ERP-AI?"
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Ingestion  │────▶│   Memory    │────▶│  Retrieval  │
│  (voice/txt)│     │  (Engram +  │     │  (vector +  │
│  WhatsApp/  │     │   ChromaDB) │     │   keyword)  │
│  Telegram)  │     └─────────────┘     └──────┬──────┘
└─────────────┘                                │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Execution  │◀───│  Reasoning  │◀───│   Context   │
│  (skills)   │     │  (Qwen API) │     │  Assembly   │
└──────┬──────┘     └─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  Memorize   │
│  (decisions,│
│   prefs,    │
│   outcomes) │
└─────────────┘
```

## Core Components

| Module | Responsibility |
|--------|----------------|
| `agentos.memory` | Persistent memory: episodic (events), semantic (facts), procedural (skills) |
| `agentos.qwen` | Qwen Cloud API client: chat, function calling, streaming, embeddings |
| `agentos.skills` | Tool registry: git, fs, web, n8n, scheduler, code_intel |
| `agentos.agent` | Core loop: ingest → retrieve → reason → act → memorize |
| `agentos.api` | REST API for web dashboard / webhooks |
| `agentos.cli` | Typer CLI: chat, memory, skills, config |

## Memory Model

```python
# Episodic: "what happened"
MemoryEvent(
    id="evt_abc123",
    type="user_preference",
    content="En ERP-AI usamos pnpm",
    project="ERP-AI",
    timestamp=datetime(...),
    embedding=[...]
)

# Semantic: "what we know"
MemoryFact(
    id="fact_xyz789",
    key="package_manager",
    value="pnpm",
    scope="project:ERP-AI",
    confidence=0.95,
    updated_at=datetime(...)
)

# Procedural: "how to do things"
Skill(
    name="git_ops",
    description="Git operations: status, diff, commit, push, PR",
    functions=["status", "diff", "commit", "push", "create_pr"]
)
```

## Skills (MVP)

| Skill | Functions |
|-------|-----------|
| `git_ops` | status, diff, commit, push, create_pr, log |
| `filesystem` | read, write, search, glob, list |
| `web_search` | search, extract, summarize |
| `n8n_trigger` | trigger_workflow, get_status, list_workflows |
| `scheduler` | add_reminder, list_reminders, cancel, cron |
| `code_intel` | find_symbol, grep_ast, run_tests, get_coverage |

## Configuration

```yaml
# config.yaml
qwen:
  api_key: "${QWEN_API_KEY}"
  base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
  model: "qwen-max"
  embedding_model: "text-embedding-v3"

memory:
  db_path: "data/agentos.db"
  chroma_path: "data/chroma_db"
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
  max_context_tokens: 8000

skills:
  enabled: ["git_ops", "filesystem", "web_search", "n8n_trigger", "scheduler", "code_intel"]
  git_ops:
    default_branch: "main"
  n8n_trigger:
    base_url: "${N8N_BASE_URL}"
    api_key: "${N8N_API_KEY}"
```

## Development

```bash
# Install dependencies
uv sync --all-extras

# Lint + typecheck
uv run ruff check .
uv run mypy src/

# Test
uv run pytest -v

# Format
uv run ruff format .
uv run ruff check --fix .
```

## Repository Readiness

This repository is prepared for local-first hackathon evaluation:

- Runtime data (`data/`, ChromaDB files, SQLite databases), local SDD cache (`.atl/`), virtualenvs, and tool caches are ignored.
- Core blocker checks are:
  - `uv sync --all-extras`
  - `uv run ruff check .`
  - `uv run pytest tests/unit tests/integration -q`
- No GitHub remote is required for local validation yet. The maintainer will create and attach the remote manually before public submission.

## Deploy

```bash
# Build image
docker build -t agentos-memory .

# Run locally
docker compose up -d

# Production
docker compose -f docker-compose.prod.yml up -d
```

## Hackathon Submission

- **Track**: MemoryAgent
- **Repo**: https://github.com/your-org/qwen-hackathon-memory-agent
- **Demo**: Video (5 min) showing cross-session memory across terminal + WhatsApp
- **Deploy**: Alibaba Cloud ECS + Container Registry

## License

MIT
