# Host integration guide

`agentos-memory` is delivered to coding agents as a local stdio MCP server. The supported MVP command is:

```bash
uv run agentos mcp
```

Run host commands from the repository root unless your host lets you set an explicit working directory.

## OpenCode

Generate the configuration snippet:

```bash
uv run agentos mcp-config opencode
```

Expected JSON:

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

Add the `agentos_memory` entry to your OpenCode MCP configuration. Then restart OpenCode so it spawns the local stdio server.

Recommended agent behavior:

- Call `memory_context` before editing code.
- Call `memory_search` for specific past decisions.
- Call `memory_save` after important decisions, bug fixes, and procedures.
- Call `memory_extract` when a paragraph should become structured memory and Qwen credentials are configured.
- Call `memory_explain` when the agent needs to justify why a memory is relevant.

## Claude Code

Claude Code can use the same stdio process shape. Register a local MCP server named `agentos_memory` with:

```text
command: uv
args: run agentos mcp
transport: stdio
```

Start Claude Code from the project root to make implicit project detection useful. If your Claude Code setup supports fixed environment variables, set `QWEN_API_KEY` there or source `.env` before launching the host.

## Antigravity-style MCP hosts

For hosts that use a JSON shape with command and args:

```json
{
  "name": "agentos_memory",
  "transport": "stdio",
  "command": "uv",
  "args": ["run", "agentos", "mcp"],
  "cwd": "/absolute/path/to/qwen-hackathon-memory-agent"
}
```

If the host does not support `cwd`, launch it from this repository or wrap the command in a small script that changes into the repository first.

## Qwen Cloud configuration

Set these variables in the environment visible to the MCP process:

```bash
QWEN_API_KEY=your_qwen_api_key_here
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-max
QWEN_EMBEDDING_MODEL=text-embedding-v3
```

Qwen is required for `memory_extract` and enriches `memory_explain`. Without Qwen credentials:

- `memory_save`, `memory_search`, and `memory_context` continue to work.
- `memory_explain` returns deterministic keyword explanations and records the Qwen failure in `errors`.
- `memory_extract` returns a clear extraction error; use `memory_save` manually instead.

## Docker and compose alignment

Docker is not the normal runtime path for coding hosts. MCP stdio must be attached to the host process, so OpenCode and Claude Code should launch `uv run agentos mcp` locally.

Use Docker only for development parity or container smoke checks:

```bash
docker build -t agentos-memory .
docker compose run --rm agentos agentos --help
```

There are intentionally no compose ports and no `/health` checks. A broken HTTP health check would imply an API surface that the MVP does not provide.
