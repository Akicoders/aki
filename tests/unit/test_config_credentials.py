"""Tests for QwenConfig credential fallback."""

import os
import pytest

from agentos.core.config import QwenConfig, reset_config, Config


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
