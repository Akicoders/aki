"""Tests for QwenConfig credential fallback."""

import os

from agentos.core.config import Config, QwenConfig, get_config


def test_qwen_config_reads_qwen_prefix():
    os.environ["QWEN_API_KEY"] = "sk-qwen-test"
    try:
        config = QwenConfig()
        assert config.api_key == "sk-qwen-test"
    finally:
        del os.environ["QWEN_API_KEY"]


def test_qwen_config_falls_back_to_dashscope_key():
    os.environ.pop("QWEN_API_KEY", None)
    os.environ["DASHSCOPE_API_KEY"] = "sk-dashscope-test"
    try:
        config = QwenConfig()
        assert config.api_key == "sk-dashscope-test"
    finally:
        del os.environ["DASHSCOPE_API_KEY"]


def test_qwen_config_prefers_qwen_key_over_dashscope():
    os.environ["QWEN_API_KEY"] = "sk-qwen-primary"
    os.environ["DASHSCOPE_API_KEY"] = "sk-dashscope-fallback"
    try:
        config = QwenConfig()
        assert config.api_key == "sk-qwen-primary"
    finally:
        del os.environ["QWEN_API_KEY"]
        del os.environ["DASHSCOPE_API_KEY"]


def test_qwen_config_empty_when_no_keys_set():
    os.environ.pop("QWEN_API_KEY", None)
    os.environ.pop("DASHSCOPE_API_KEY", None)
    config = QwenConfig()
    assert config.api_key == ""


def test_get_config_loads_dashscope_key_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DASHSCOPE_API_KEY=sk-dotenv-dashscope\n", encoding="utf-8")

    config = get_config()

    assert config.qwen.api_key == "sk-dotenv-dashscope"


def test_get_config_prefers_qwen_key_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "QWEN_API_KEY=sk-dotenv-qwen\nDASHSCOPE_API_KEY=sk-dotenv-dashscope\n",
        encoding="utf-8",
    )

    config = get_config()

    assert config.qwen.api_key == "sk-dotenv-qwen"


def test_config_from_yaml_loads_dotenv_for_interpolation(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = project_root / "aki.yaml"
    config_path.write_text("qwen:\n  api_key: ${QWEN_API_KEY}\n", encoding="utf-8")
    (project_root / ".env").write_text("QWEN_API_KEY=sk-yaml-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    config = Config.from_yaml(config_path)

    assert config.qwen.api_key == "sk-yaml-dotenv"
