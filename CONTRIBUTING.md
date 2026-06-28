# Contributing

Thanks for helping improve Aki.

## Development flow

1. Sync dependencies: `uv sync --all-extras`
2. Run lint: `uv run ruff check .`
3. Run tests: `uv run pytest tests/ -q`
4. Smoke-check MCP config output: `uv run aki mcp-config opencode`

## Conventions

- Prefer `aki` in public-facing docs and examples.
- Keep `agentos` only where compatibility matters.
- Do not commit real API keys, local memory databases, or generated Chroma data.
- When touching extraction behavior, cover both deterministic fallback and Qwen-assisted paths.
- Keep docs aligned with the `proposal/spec/design/tasks/apply-log/verify-report` vocabulary.
