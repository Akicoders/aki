# Contributing to Aki

Thanks for your interest in Aki. Aki is an AI agent for portable project memory, delivered through MCP.

## Development setup

```bash
uv sync --all-extras
cp .env.example .env
```

Qwen credentials are optional for most tests. Do not commit real API keys or local memory databases.

## Checks before a pull request

```bash
uv run ruff check .
uv run pytest tests/ -q
uv run agentos mcp-config opencode
uv run agentos --help
```

## Pull request guidelines

- Keep changes focused and reviewable.
- Update docs when user-facing behavior changes.
- Add or update tests when changing Python behavior.
- Do not add features that imply an HTTP API, hosted service, or integrations outside the current MVP without a design discussion first.

## Security

Never include secrets in issues, pull requests, tests, docs, or committed config files. Use `.env.example` for placeholders only.
