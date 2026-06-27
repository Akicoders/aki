"""Configuration management for Aki."""

from pathlib import Path
from typing import Any, Optional
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QwenConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QWEN_")

    api_key: str = Field(default="", description="Qwen Cloud API key")
    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-max"
    embedding_model: str = "text-embedding-v3"
    timeout: int = 60
    max_retries: int = 3


class MemoryConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_")

    db_path: Path = Path("data/agentos.db")
    chroma_path: Path = Path("data/chroma_db")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_context_tokens: int = 8000
    consolidation_interval_hours: int = 24
    max_episodic_per_project: int = 10000


class GitOpsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GITOPS_")

    default_branch: str = "main"
    auto_commit: bool = False


class FilesystemConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FS_")

    allowed_roots: list[Path] = Field(default_factory=lambda: [Path.home() / "proyects", Path.home() / "Documents"])


class WebSearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEBSEARCH_")

    default_limit: int = 5
    timeout: int = 15


class N8nConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="N8N_")

    base_url: str = "http://localhost:5678"
    api_key: str = ""
    timeout: int = 30


class SchedulerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHED_")

    default_timezone: str = "America/Lima"


class CodeIntelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODEINTEL_")

    test_command: str = "pytest -v"
    lint_command: str = "ruff check ."


class SkillsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLS_")

    enabled: list[str] = Field(default_factory=lambda: [
        "git_ops", "filesystem", "web_search", "n8n_trigger", "scheduler", "code_intel"
    ])
    git_ops: GitOpsConfig = Field(default_factory=GitOpsConfig)
    filesystem: FilesystemConfig = Field(default_factory=FilesystemConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    n8n_trigger: N8nConfig = Field(default_factory=N8nConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    code_intel: CodeIntelConfig = Field(default_factory=CodeIntelConfig)


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    max_iterations: int = 5
    temperature: float = 0.3
    system_prompt_template: str = ""
    memory_injection_template: str = ""
    skill_injection_template: str = ""


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = "INFO"
    format: str = "json"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qwen: QwenConfig = Field(default_factory=QwenConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load config from YAML file with environment variable interpolation."""
        import os
        import re

        content = path.read_text(encoding="utf-8")

        # Replace ${VAR} or ${VAR:-default} with environment values
        def replace_env(match: re.Match) -> str:
            full = match.group(0)
            var_expr = match.group(1)
            if ":-" in var_expr:
                var, default = var_expr.split(":-", 1)
                return os.getenv(var.strip(), default.strip())
            return os.getenv(var_expr, full)

        content = re.sub(r"\$\{([^}]+)\}", replace_env, content)
        data = yaml.safe_load(content)
        return cls(**data)


_config: Optional[Config] = None


def get_config(config_path: Optional[Path] = None) -> Config:
    """Get global config instance, loading from YAML if path provided."""
    global _config
    if _config is None:
        if config_path and config_path.exists():
            _config = Config.from_yaml(config_path)
        else:
            _config = Config()
    return _config


def reset_config() -> None:
    """Reset global config (for testing)."""
    global _config
    _config = None
