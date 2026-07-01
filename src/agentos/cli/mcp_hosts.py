"""Shared MCP host configuration helpers for Aki CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer


def _get_mcp_snippet(host: str) -> dict:
    command = ["uv", "run", "aki", "mcp"]
    snippets = {
        "opencode": {
            "mcp": {
                "aki_memory": {
                    "type": "local",
                    "command": command,
                    "enabled": True,
                }
            }
        },
        "claude-code": {
            "mcpServers": {
                "aki_memory": {
                    "command": command[0],
                    "args": command[1:],
                }
            }
        },
    }
    return snippets.get(host, {})


def _get_host_config_path(host: str) -> Path:
    paths = {
        "opencode": Path.home() / ".config" / "opencode" / "opencode.json",
        "claude-code": Path.home() / ".claude" / "claude_desktop_config.json",
    }
    if host not in paths:
        supported = ", ".join(sorted(paths))
        raise typer.BadParameter(f"Unsupported host '{host}'. Supported hosts: {supported}")
    return paths[host]


def _merge_mcp_config(existing: dict, snippet: dict) -> dict:
    result = dict(existing)
    for key, value in snippet.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result
