"""Tests for doctor command."""

import pytest
from typer.testing import CliRunner

from agentos.cli.main import app


runner = CliRunner()


class TestDoctorCommand:
    def test_doctor_runs_without_error(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_shows_health_check_table(self):
        result = runner.invoke(app, ["doctor"])
        assert "Aki Health Check" in result.output
        assert "Python" in result.output
        assert "uv" in result.output
