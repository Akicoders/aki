import json

from typer.testing import CliRunner

from agentos.cli.main import app


def test_mcp_command_is_registered():
    command_names = {command.name for command in app.registered_commands}

    assert "mcp" in command_names
    assert "mcp-config" in command_names


def test_mcp_config_opencode_prints_json_snippet():
    result = CliRunner().invoke(app, ["mcp-config", "opencode"])

    assert result.exit_code == 0
    snippet = json.loads(result.stdout)

    assert snippet == {
        "mcp": {
            "aki_memory": {
                "type": "local",
                "command": ["uv", "run", "agentos", "mcp"],
                "enabled": True,
            }
        }
    }
