"""Tests for SDD detection and initialization."""

from pathlib import Path

import pytest

from agentos.sdd.detector import detect_sdd_artifacts, load_sdd_artifact, summarize_sdd_context
from agentos.sdd.init import init_sdd_project, TEMPLATES


class TestDetectSDDArtifacts:
    def test_no_sdd_dir_returns_no_artifacts(self, tmp_path):
        status = detect_sdd_artifacts(tmp_path)
        assert status.has_sdd is False
        assert status.sdd_dir is None
        assert status.found_artifacts == []

    def test_detects_docs_sdd_directory(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)

        status = detect_sdd_artifacts(tmp_path)
        assert status.has_sdd is True
        assert status.sdd_dir == "docs/sdd"

    def test_detects_dot_sdd_directory(self, tmp_path):
        sdd_dir = tmp_path / ".sdd"
        sdd_dir.mkdir()

        status = detect_sdd_artifacts(tmp_path)
        assert status.has_sdd is True
        assert status.sdd_dir == ".sdd"

    def test_detects_openspec_directory(self, tmp_path):
        sdd_dir = tmp_path / "openspec"
        sdd_dir.mkdir()

        status = detect_sdd_artifacts(tmp_path)
        assert status.has_sdd is True
        assert status.sdd_dir == "openspec"

    def test_reports_found_and_missing_artifacts(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)
        (sdd_dir / "proposal.md").write_text("# Proposal")
        (sdd_dir / "spec.md").write_text("# Spec")

        status = detect_sdd_artifacts(tmp_path)
        assert status.has_sdd is True
        assert "proposal.md" in status.found_artifacts
        assert "spec.md" in status.found_artifacts
        assert "design.md" in status.missing_artifacts
        assert "tasks.md" in status.missing_artifacts

    def test_summary_when_no_sdd(self, tmp_path):
        status = detect_sdd_artifacts(tmp_path)
        assert status.summary() == "No SDD artifacts found"

    def test_summary_when_sdd_exists(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)
        (sdd_dir / "proposal.md").write_text("# Proposal")

        status = detect_sdd_artifacts(tmp_path)
        summary = status.summary()
        assert "docs/sdd" in summary
        assert "proposal.md" in summary


class TestLoadSDDArtifact:
    def test_loads_existing_artifact(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)
        (sdd_dir / "proposal.md").write_text("# My Proposal")

        content = load_sdd_artifact("proposal.md", tmp_path)
        assert content == "# My Proposal"

    def test_returns_none_for_missing_artifact(self, tmp_path):
        content = load_sdd_artifact("proposal.md", tmp_path)
        assert content is None


class TestSummarizeSDDContext:
    def test_returns_none_when_no_sdd(self, tmp_path):
        result = summarize_sdd_context(tmp_path)
        assert result is None

    def test_returns_summary_when_sdd_exists(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)
        (sdd_dir / "proposal.md").write_text("# My Proposal\nSome content here")

        result = summarize_sdd_context(tmp_path)
        assert result is not None
        assert "SDD Status" in result
        assert "My Proposal" in result


class TestInitSDDProject:
    def test_creates_docs_sdd_directory(self, tmp_path):
        sdd_dir, created = init_sdd_project(tmp_path)
        assert sdd_dir.exists()
        assert sdd_dir == tmp_path / "docs" / "sdd"

    def test_creates_all_template_files(self, tmp_path):
        sdd_dir, created = init_sdd_project(tmp_path)
        assert len(created) == len(TEMPLATES)
        for filename in TEMPLATES:
            assert (sdd_dir / filename).exists()

    def test_does_not_overwrite_existing_files(self, tmp_path):
        sdd_dir = tmp_path / "docs" / "sdd"
        sdd_dir.mkdir(parents=True)
        (sdd_dir / "proposal.md").write_text("# Existing")

        _, created = init_sdd_project(tmp_path)
        assert "proposal.md" not in created
        assert (sdd_dir / "proposal.md").read_text() == "# Existing"

    def test_template_content_is_valid(self, tmp_path):
        sdd_dir, _ = init_sdd_project(tmp_path)
        for filename in TEMPLATES:
            content = (sdd_dir / filename).read_text()
            assert len(content) > 0
            assert content.startswith("#")
