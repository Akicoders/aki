"""Tests for mcp-setup command merge logic."""

import json
import tempfile
from pathlib import Path

import pytest

from agentos.cli.main import _merge_mcp_config, _get_mcp_snippet, _get_host_config_path


class TestMergeMcpConfig:
    def test_merge_into_empty(self):
        existing = {}
        snippet = {"mcp": {"aki_memory": {"type": "local"}}}
        result = _merge_mcp_config(existing, snippet)
        assert result == snippet

    def test_merge_preserves_existing_servers(self):
        existing = {
            "mcp": {
                "other_server": {"type": "remote", "url": "http://example.com"}
            }
        }
        snippet = {
            "mcp": {
                "aki_memory": {"type": "local", "command": ["uv", "run", "aki", "mcp"]}
            }
        }
        result = _merge_mcp_config(existing, snippet)
        assert "other_server" in result["mcp"]
        assert "aki_memory" in result["mcp"]
        assert result["mcp"]["other_server"]["url"] == "http://example.com"

    def test_merge_does_not_overwrite_existing_aki(self):
        existing = {
            "mcp": {
                "aki_memory": {"type": "remote", "url": "http://old.com"}
            }
        }
        snippet = {
            "mcp": {
                "aki_memory": {"type": "local", "command": ["uv", "run", "aki", "mcp"]}
            }
        }
        result = _merge_mcp_config(existing, snippet)
        assert result["mcp"]["aki_memory"]["type"] == "local"
        assert result["mcp"]["aki_memory"]["command"] == ["uv", "run", "aki", "mcp"]

    def test_merge_nested_dicts(self):
        existing = {"a": {"b": 1, "c": 2}}
        snippet = {"a": {"d": 3}}
        result = _merge_mcp_config(existing, snippet)
        assert result == {"a": {"b": 1, "c": 2, "d": 3}}

    def test_merge_non_dict_values(self):
        existing = {"key": "old_value"}
        snippet = {"key": "new_value"}
        result = _merge_mcp_config(existing, snippet)
        assert result == {"key": "new_value"}


class TestGetMcpSnippet:
    def test_opencode_snippet(self):
        snippet = _get_mcp_snippet("opencode")
        assert "mcp" in snippet
        assert "aki_memory" in snippet["mcp"]
        assert snippet["mcp"]["aki_memory"]["type"] == "local"

    def test_claude_code_snippet(self):
        snippet = _get_mcp_snippet("claude-code")
        assert "mcpServers" in snippet
        assert "aki_memory" in snippet["mcpServers"]

    def test_unknown_host_returns_empty(self):
        snippet = _get_mcp_snippet("unknown")
        assert snippet == {}


class TestGetHostConfigPath:
    def test_opencode_path(self):
        path = _get_host_config_path("opencode")
        assert "opencode" in str(path)
        assert path.name == "opencode.json"

    def test_claude_code_path(self):
        path = _get_host_config_path("claude-code")
        assert "claude" in str(path)
        assert path.name == "claude_desktop_config.json"

    def test_unknown_host_raises(self):
        import typer
        with pytest.raises(typer.BadParameter):
            _get_host_config_path("unknown")
