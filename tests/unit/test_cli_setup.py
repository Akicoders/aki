"""Tests for the `aki setup` command."""

from typer.testing import CliRunner

from agentos.cli.main import app


runner = CliRunner()


class TestSetupCommand:
    def test_setup_runs_and_exits_zero_when_essentials_are_healthy(self, monkeypatch):
        """When Python/uv/import checks pass (as they must to run tests at all),
        `aki setup` should succeed regardless of whether a Qwen key is present."""
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0

    def test_setup_output_includes_summary_sections(self):
        result = runner.invoke(app, ["setup"])
        assert "Aki Setup" in result.output
        assert "Setup summary" in result.output
        assert "Next steps" in result.output
        assert "aki mcp-setup" in result.output
        assert "aki chat" in result.output
        assert "aki cockpit" in result.output

    def test_setup_reuses_doctor_health_check(self):
        """`aki setup` chains doctor's report, not a duplicate implementation."""
        result = runner.invoke(app, ["setup"])
        assert "Aki Health Check" in result.output

    def test_setup_skips_config_init_prompt_when_key_already_configured(self, monkeypatch):
        monkeypatch.setenv("QWEN_API_KEY", "sk-test-key")
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "already configured" in result.output

    def test_setup_warns_but_does_not_hard_fail_without_api_key(self, monkeypatch):
        """Missing Qwen key is a warning, not a hard failure — core memory tools
        still work without it. Force the "no key anywhere" path regardless of
        this machine's own ~/.aki/.env by stubbing the resolver directly."""
        import agentos.cli.main as main_module

        monkeypatch.setattr(
            main_module, "_resolve_global_api_key", lambda: ("", "not set (set QWEN_API_KEY...)")
        )
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert "Qwen configured: no" in result.output
