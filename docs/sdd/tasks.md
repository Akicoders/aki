# Tasks: Hackathon MVP — Aki

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900–1,400 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 blockers → PR2 MCP core → PR3 Qwen extraction → PR4 docs/demo |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Green foundation | PR 1 | deps, Ruff, fake embedder, core CI |
| 2 | Local MCP memory server | PR 2 | depends on PR 1; five tools callable directly |
| 3 | Qwen extraction/explain | PR 3 | depends on PR 2; fake Qwen tests |
| 4 | Demo readiness | PR 4 | docs, Docker notes, final smoke checks |

## Phase 1: Blocker fixes — Day 1

- [x] 1.1 Fix `pyproject.toml`: add `mcp` and `beautifulsoup4`, repair Ruff config, add pytest markers. AC: `ruff check` config loads and deps install with `uv sync`.
- [x] 1.2 Update `src/agentos/memory/repository.py` with `Embedder` protocol injection and safe empty-query behavior. AC: repository tests run with `FakeEmbedder`, no sentence-transformers download.
- [x] 1.3 Add/adjust `tests/conftest.py` fake embedder and temp SQLite/Chroma fixtures. AC: save/search/context tests are deterministic.
- [x] 1.4 Document or verify git/GitHub readiness in `README.md` or setup notes. AC: evaluator sees repo setup status and core check command.

## Phase 2: MCP server core — Day 2

- [x] 2.1 Create `src/agentos/mcp/project.py` for project detection from explicit arg, git root basename, cwd name, fallback `default`. AC: parametrized unit tests cover all paths.
- [x] 2.2 Create `src/agentos/memory/capsule.py` for compact English source-tagged capsules. AC: tests prove bounded output, kinds, sources, rendered text.
- [x] 2.3 Create `src/agentos/mcp/{__init__.py,server.py,tools.py}` using official `mcp` SDK. AC: five tool schemas exist and handlers return `{ok, project, errors}`.
- [x] 2.4 Add `agentos mcp` and `agentos mcp-config opencode` in `src/agentos/cli/main.py`. AC: Typer tests assert command registration and OpenCode JSON snippet.

## Phase 3: Qwen extraction + integration — Day 3

- [x] 3.1 Add `structured_json()` to `src/agentos/qwen/client.py`. AC: fake client tests cover valid JSON, invalid JSON, and API failure.
- [x] 3.2 Create `src/agentos/qwen/extraction.py` with `QwenMemoryExtractor` validation for facts, decisions, procedures, confidence, provenance. AC: parser rejects malformed candidates without writes.
- [x] 3.3 Wire `memory_extract` to store extracted memories and report recoverable Qwen errors. AC: direct handler tests prove extracted items become searchable.
- [x] 3.4 Wire `memory_explain` with retrieved memories plus Qwen/deterministic rationale. AC: tests prove explanations do not invent facts.

## Phase 4: Polish + demo + submit — Day 4

- [x] 4.1 Update `Dockerfile` and `docker-compose*.yml` for MCP demo reality, not HTTP health assumptions. AC: docs state stdio path clearly.
- [x] 4.2 Update `README.md` and `docs/` with positioning, setup, five tools, OpenCode config, Claude Code/Antigravity notes, out-of-scope cuts. AC: first-time evaluator can run the happy path.
- [x] 4.3 Add demo script/docs with Qwen fallback path. AC: script proves save/extract/query changes agent context.
- [x] 4.4 Run final checks: `ruff check`, focused `pytest`, CLI config command, direct MCP handler smoke. AC: failures are fixed or explicitly documented as non-blocking.

## Additional work

- [x] Rebrand from agentos to Aki (CLI entry point)
- [x] Add aki CLI command with agentos as alias
- [x] Update Qwen models config (qwen3.7-max, qwen3.7-plus)
- [x] Fix integration test hangs (FakeEmbedder everywhere)
- [x] Add open-source files (LICENSE, CONTRIBUTING, issue templates)

## Status

**READY FOR GITHUB PUSH**

All phases complete. 51 tests passing in <5s. Ruff green. Working tree clean.
