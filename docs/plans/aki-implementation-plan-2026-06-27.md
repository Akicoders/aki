# Aki Implementation Plan — Shareability, SDD, and Qwen Efficiency

## Objective
Turn the current hackathon MVP into a cleaner public-facing Aki release by implementing the highest-leverage improvements in three areas:
1. Shareability and onboarding
2. Living SDD structure
3. Token-efficient Qwen extraction and memory context handling

## Non-goals
- Do not publish to PyPI in this pass.
- Do not redesign the whole architecture.
- Do not remove backward compatibility for `agentos` commands.
- Do not introduce speculative features beyond the scope below.

## Constraints
- Keep the project working.
- Preserve `agentos` as a compatibility alias while making `aki` the preferred public path.
- Update tests alongside behavior changes.
- Run lint and full test suite before finishing.

## Phase 1 — Public entrypoint, neutral defaults, and MCP ergonomics

### Task 1.1 — Make Aki the public-first CLI path
Files:
- `src/agentos/cli/main.py`
- `README.md`
- `docs/integration.md`
- `docs/demo.md`
- `docs/troubleshooting.md`
- `pyproject.toml`

Changes:
- Keep the Typer app functional, but make output/help consistently describe Aki as the primary product.
- Keep `agentos` compatibility, but update docs and config snippets to prefer `aki`.
- Ensure examples and host snippets use `aki mcp` instead of `uv run agentos mcp` where possible.
- If the package already exposes both scripts, keep both; do not break existing tests/users.

Acceptance:
- `uv run aki --help` works.
- Public docs consistently present Aki as the primary command.

### Task 1.2 — Improve `mcp-config` for real host ergonomics
Files:
- `src/agentos/cli/main.py`
- `tests/unit/test_mcp_cli.py`
- docs if needed

Changes:
- Expand `mcp-config` to support at least:
  - `opencode`
  - `claude-code`
  - `generic-json`
- Prefer snippets that invoke `aki mcp`.
- Include a clean error message for unsupported hosts.
- Keep output JSON/snippet deterministic and testable.

Acceptance:
- Tests cover the new supported hosts.
- `uv run aki mcp-config opencode` works.
- `uv run aki mcp-config claude-code` works.

### Task 1.3 — Remove personal defaults and placeholders from public-facing config/prompting
Files:
- `config.yaml`
- `src/agentos/agent/core.py`
- `pyproject.toml`
- possibly `README.md`

Changes:
- Replace personal/project-specific default prompt text with neutral public-safe defaults.
- Remove placeholder author/email metadata that look unprofessional for open source.
- Keep product framing around persistent memory for coding agents.

Acceptance:
- No public-facing default mentions Paul or private project names.
- Config remains valid.

## Phase 2 — Fix context budgeting and memory assembly correctness

### Task 2.1 — Separate result count from token budget in MCP memory context
Files:
- `src/agentos/mcp/tools.py`
- `tests/unit/test_mcp_tools.py`
- any related tests

Changes:
- `memory_context()` should not pass `limit` as `max_tokens`.
- Introduce a real token budget parameter internally or use a safe default from config while `limit` remains item-count oriented.
- Keep backward-compatible tool interface unless absolutely necessary.

Acceptance:
- Tests verify item count control is distinct from token budgeting.
- No regression in MCP tool behavior.

### Task 2.2 — Implement real token estimation and truncation in memory context assembly
Files:
- `src/agentos/memory/repository.py`
- `src/agentos/memory/models.py`
- relevant tests

Changes:
- Add a lightweight token estimation strategy (heuristic is acceptable; do not overengineer).
- Make `assemble_context()` respect `max_tokens` instead of always returning `total_tokens=0`.
- Make `MemoryContext.format_for_prompt(max_tokens=...)` actually honor the budget.
- Prefer stable deterministic truncation over cleverness.

Acceptance:
- `total_tokens` is non-zero when context exists.
- Context formatting truncates to budget-aware output.
- Tests cover token-budget behavior.

## Phase 3 — Qwen extraction pipeline with Plus/Max routing

### Task 3.1 — Add chunked extraction pipeline
Files:
- `src/agentos/qwen/extraction.py`
- `tests/unit/test_qwen_extraction.py`
- maybe `tests/unit/test_mcp_extract.py`

Changes:
- Refactor extraction so large text can be processed in semantic or size-bounded chunks.
- Run per-chunk extraction and merge validated candidates.
- Deduplicate candidates deterministically.
- Keep API surface simple.

Acceptance:
- Extraction still works for small text.
- Large input path is covered by tests.

### Task 3.2 — Add explicit model routing for cheaper extraction vs stronger consolidation
Files:
- `src/agentos/core/config.py`
- `config.yaml`
- `src/agentos/qwen/client.py`
- `src/agentos/qwen/extraction.py`
- tests

Changes:
- Support separate models/config entries for extraction and consolidation, e.g. Plus for chunk extraction and Max for final consolidation.
- Preserve sensible defaults so existing behavior still works without extra config.
- Use the cheaper model for chunk extraction and stronger model only for final merge/conflict resolution.

Acceptance:
- Config supports separate extraction/consolidation model settings.
- Tests cover fallback/default behavior.

## Phase 4 — Revive SDD as a living project structure

### Task 4.1 — Add a lightweight SDD documentation skeleton
Files to create/update:
- `docs/sdd/vision.md`
- `docs/sdd/features/README.md`
- `docs/adr/README.md`
- `CONTRIBUTING.md`
- `.github/PULL_REQUEST_TEMPLATE.md`

Changes:
- Add a minimal SDD structure that matches the repo’s current maturity.
- Add guidance for feature specs, ADRs, and evidence in PRs.
- Keep it lightweight and credible, not bloated.

Acceptance:
- Repo contains a real, simple SDD path for future work.
- PR template asks for problem, decision, trade-offs, tests/evidence.

## Implementation order
1. Phase 1.1
2. Phase 1.2
3. Phase 1.3
4. Phase 2.1
5. Phase 2.2
6. Phase 3.1
7. Phase 3.2
8. Phase 4.1
9. Run lint + tests
10. Summarize what changed and any remaining gaps

## Mandatory verification
Before finishing:
- `uv run ruff check .`
- `uv run pytest tests/ -q`
- If a test needs updating because behavior improved, update it deliberately rather than deleting coverage.

## Delivery notes
- Prefer small, coherent commits if practical, but completing the implementation correctly matters more than commit count.
- Do not stop after planning; implement the changes in code and docs.
- If one sub-part is blocked, complete the rest and report the blocker explicitly.
