"""Tests for packaging and tool configuration."""

import tomllib
from pathlib import Path


def load_pyproject() -> dict:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return tomllib.loads(pyproject_path.read_text())


def test_runtime_dependencies_include_mcp_and_beautifulsoup() -> None:
    pyproject = load_pyproject()

    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.startswith("mcp") for dependency in dependencies)
    assert any(dependency.startswith("beautifulsoup4") for dependency in dependencies)


def test_ruff_selectors_are_supported_rule_prefixes() -> None:
    pyproject = load_pyproject()
    ruff = pyproject["tool"]["ruff"]
    lint = pyproject["tool"]["ruff"]["lint"]

    selectors = set(lint["select"] + lint.get("extend-select", []))

    assert "C91" not in selectors
    assert "C90" in selectors
    assert "C4" in selectors
    assert "select" not in ruff
    assert "lint-select" not in ruff


def test_integration_pytest_marker_is_declared() -> None:
    pyproject = load_pyproject()

    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]

    assert "integration: Integration tests" in markers
