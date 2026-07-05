# Aki

Portable project memory for AI coding agents — powered by Qwen, delivered through MCP.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-136%20passing-brightgreen)
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

- **Local stdio MCP server**: primary runtime is `uv run aki mcp`.
- **Five MCP memory tools**: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`.
- **Qwen extraction**: turns prose into structured memory candidates when Qwen Cloud credentials are configured.
- **Deterministic fallback**: manual save/search/context and keyword explanations remain available without Qwen credentials.
- **Episodic, semantic, and procedural memory**: stores recent events, durable facts/decisions, and repeatable procedures.
- **Project-aware context**: uses explicit project names or current-directory detection.
- **Host integration docs**: includes setup notes for OpenCode, Claude Code, and Antigravity-style MCP hosts.
- **SDD-aware chat**: detects Spec-Driven Development artifacts and injects them into chat context when relevant.
- **SDD initialization**: `aki sdd-init` bootstraps `docs/sdd/` with proposal, spec, design, and tasks templates.
- **Sectioned interactive UI**: `aki interactive` shows memory context, skills, and SDD status at startup.
- **Operational cockpit**: default view shows project health, action items, memory posture, and SDD status when `aki` runs with no subcommand inside a recognized project.
- **Project registry**: `aki projects browse` lists known projects with persistent SQLite-backed storage, search/filter, and one-click cockpit access.
- **Read-only project audit**: `aki audit <project>` runs specialized passes (tests, SDD completeness, git hygiene, env/config, MCP readiness, memory posture) and produces structured markdown reports in `docs/audits/`.

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

The public CLI entry point is `aki`. The legacy `agentos` command remains available as a compatibility alias during the MVP transition.

## Development Methodology

Aki was built using **Spec-Driven Development (SDD)**, a structured approach that ensures architectural clarity and incremental delivery:

1. **Explore** — Analyzed memory agent landscape, MCP ecosystem, and differentiation opportunities
2. **Propose** — Defined scope, capabilities, risks, and success criteria
3. **Specify** — Wrote testable requirements with Given/When/Then scenarios
4. **Design** — Made architectural decisions with documented tradeoffs
5. **Implement** — Executed in 4 phases with continuous verification

All SDD artifacts are available in [`docs/sdd/`](docs/sdd/):
- [Exploration](docs/sdd/explore.md) and [Ecosystem Analysis](docs/sdd/explore-ecosystem.md)
- [Proposal](docs/sdd/proposal.md) with scope and risks
- [Specification](docs/sdd/spec.md) with testable scenarios
- [Design](docs/sdd/design.md) with architecture decisions
- [Tasks](docs/sdd/tasks.md) and [Progress](docs/sdd/apply-progress.md)

**Result**: 136 tests passing in <25 seconds, with operational cockpit, audit engine, and project registry delivered across phases 2–4.

## Installation

### Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Optional: Qwen Cloud/DashScope-compatible API key for extraction and enriched explanations

### One-command installer

```bash
sh install.sh
```

The installer runs on Linux and macOS, checks for Python 3.11+, installs `uv` with Astral's installer if needed, runs `uv sync --all-extras`, and creates `.env` from `.env.example` only when `.env` does not already exist.

It does not modify OpenCode, Claude Code, or any other MCP host configuration files. Use `uv run aki mcp-config <host>` to print a snippet and add it to your host config manually, or use `uv run aki mcp-setup <host>` for automatic setup.

### Updating Aki

For source-based installs, `aki update` is the recommended update path:

```bash
aki update
```

This pulls the latest changes from the cloned repository, runs `uv sync --all-extras`, refreshes the global editable `aki` tool install, and confirms the update.

The legacy installer path still exists if you need it:

```bash
sh install.sh --update
```

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

If you used `install.sh`, `.env` is created automatically when missing. For manual setup, create a local environment file:

```bash
cp .env.example .env
```

Qwen configuration:

```bash
QWEN_API_KEY=your_qwen_api_key_here
# Or use DASHSCOPE_API_KEY as an alternative:
# DASHSCOPE_API_KEY=your_dashscope_api_key_here
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-max
QWEN_EXTRACTION_MODEL=qwen3.7-plus
QWEN_CONSOLIDATION_MODEL=qwen3.7-max
QWEN_EMBEDDING_MODEL=text-embedding-v3
```

Aki accepts either `QWEN_API_KEY` or `DASHSCOPE_API_KEY`. If both are set, `QWEN_API_KEY` takes precedence.

Memory storage defaults:

```bash
MEMORY_DB_PATH=data/agentos.db
MEMORY_CHROMA_PATH=data/chroma_db
MEMORY_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
MEMORY_MAX_CONTEXT_TOKENS=8000
```

Agent behaviour:

```bash
AGENT_MAX_ITERATIONS=20
```

`AGENT_MAX_ITERATIONS` caps how many reasoning iterations the agent may take
before it stops and reports exhaustion; one iteration is one model
round-trip, so higher values allow more tool-heavy tasks at the cost of more
round-trips. Default is `20`, and the value must be between `1` and `100`
(inclusive) — values outside that range fail config construction.

`config.yaml` contains the same defaults for local development. Do not commit real API keys.

## Usage

### Operational Cockpit

When run with no subcommand inside a recognized project, Aki displays an operational cockpit overview:

```bash
uv run aki
```

The cockpit shows:
- **Project Health** — test status, git state, environment configuration
- **Action Items** — pending tasks and checks requiring attention
- **Memory Posture** — recent decisions and procedural memories
- **SDD Status** — current Spec-Driven Development artifacts and progress

This is the default entry point for understanding project state at a glance.

### Project Registry and Browse

List known projects and navigate to their cockpits:

```bash
uv run aki projects browse
```

The registry:
- Maintains a persistent SQLite-backed project database
- Supports search and filter by name or path
- Allows one-click selection to open the cockpit for any registered project
- Auto-detects projects when running `aki` inside a git repository

### Cockpit Navigation

For interactive drill-down navigation within the cockpit:

```bash
uv run aki cockpit --interactive
# or
uv run aki cockpit -i
```

Keyboard shortcuts:
- `Tab` / Arrow keys — move between panels
- `j` / `k` — move within a panel list
- `Enter` — open detail view
- `b` — go back to previous view
- `g` — return to overview
- `r` — refresh data
- `/` — filter or search
- `q` — quit

### Audit

Run a read-only audit on a project to assess posture across multiple dimensions:

```bash
uv run aki audit <project>
```

The audit runs specialized passes:
- **Tests posture** — test coverage and passing status
- **SDD completeness** — presence and quality of specification artifacts
- **Git hygiene** — branch state, commit history, and upstream sync
- **Environment & config** — secrets, credentials, and configuration validation
- **MCP readiness** — integration status with MCP hosts
- **Memory posture** — project memory retention and structure

Results are saved as structured markdown reports in `docs/audits/` for later retrieval. The audit is read-only; no automatic fixes are applied.

### Primary MCP runtime

```bash
uv run aki mcp
```

Generate MCP snippets for supported hosts:

```bash
uv run aki mcp-config opencode
uv run aki mcp-config claude-code
uv run aki mcp-config generic-json
```

Other available CLI commands:

```bash
uv run aki --help
uv run aki chat "remember that we use pnpm" --project my-project
uv run aki recall "package manager" --project my-project
uv run aki remember "The MVP runtime is MCP stdio, not HTTP" --project my-project
uv run aki facts --project my-project
uv run aki skills
uv run aki doctor
```

### Automatic MCP setup

To automatically configure Aki in your host's MCP configuration:

```bash
uv run aki mcp-setup opencode
uv run aki mcp-setup claude-code
```

This creates a backup of the existing config file (if present) and merges the Aki MCP configuration without overwriting other MCP servers. Use `--dry-run` to preview changes:

```bash
uv run aki mcp-setup opencode --dry-run
```

### Health check

To verify your Aki installation:

```bash
uv run aki doctor
```

This checks Python version, uv installation, environment variables, dependencies, and Qwen API connectivity.

### Listing skills

To see available skills:

```bash
uv run aki skills
```

Example output:

```
┌─────────────────────────────────────────────────────────────────┐
│                      Available Skills                           │
├──────────────┬─────────────────────┬──────────────────┬─────────┤
│ Name         │ Description         │ Functions        │ Enabled │
├──────────────┼─────────────────────┼──────────────────┼─────────┤
│ git_ops      │ Git operations      │ status, diff...  │ ✓       │
│ filesystem   │ File operations     │ read, write...   │ ✓       │
│ web_search   │ Web search          │ search           │ ✓       │
│ n8n_trigger  │ n8n workflow        │ trigger          │ ✓       │
│ scheduler    │ Task scheduling     │ schedule         │ ✓       │
│ code_intel   │ Code intelligence   │ lint, test       │ ✓       │
└──────────────┴─────────────────────┴──────────────────┴─────────┘
```

The `agentos` command is retained for compatibility. A matching `aki` console script is available after installing the package.

### Interactive chat with SDD awareness

```bash
uv run aki interactive --project my-project
```

The interactive mode shows a sectioned UI on startup:
- **SDD Status** — whether the project has SDD artifacts (proposal, spec, design, tasks)
- **Memory Context** — recent facts and decisions for the project
- **Available Skills** — enabled skills and their functions

Inside the chat, use `/sdd` to check SDD artifact status, or ask questions like "what's the spec?" to get SDD context injected into the response.

### SDD initialization

```bash
uv run aki sdd-init
```

Creates `docs/sdd/` with template files: `proposal.md`, `spec.md`, `design.md`, `tasks.md`. Use this to bootstrap Spec-Driven Development for any project.

## MCP Integration

### OpenCode

```bash
uv run aki mcp-config opencode
```

Expected output:

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

Add `aki_memory` to your OpenCode MCP configuration and restart OpenCode from the repository root.

### Claude Code

```bash
uv run aki mcp-config claude-code
```

Expected output:

```json
{
  "name": "aki_memory",
  "transport": "stdio",
  "command": "uv",
  "args": ["run", "aki", "mcp"]
}
```

### Generic stdio JSON hosts

```bash
uv run aki mcp-config generic-json
```

See [`docs/integration.md`](docs/integration.md) for host-specific notes.

## Demo walkthrough

The evaluator walkthrough is in [`docs/demo.md`](docs/demo.md). It shows how to:

1. start `aki mcp` as an OpenCode local MCP server;
2. save a project decision such as “we use pnpm”;
3. extract structured memories from an architecture paragraph;
4. query `memory_context` and show it changing agent behavior;
5. demonstrate fallback behavior when Qwen credentials are absent.

## Docker and compose

Docker is a development helper, not the normal runtime path for coding hosts. MCP stdio must remain attached to the host process.

```bash
docker build -t aki-memory .
docker compose run --rm aki aki --help
```

There are intentionally no compose ports and no `/health` checks. Aki's MVP interface is stdio MCP, not HTTP.

## Development

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest tests/ -q
uv run aki mcp-config opencode
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
