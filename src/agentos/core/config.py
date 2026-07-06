"""Configuration management for Aki."""

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentos.agents.registry import AgentProfilesConfig
from agentos.core.project_breadcrumb import read_breadcrumb


def _find_git_root(path: Path) -> Optional[Path]:
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _iter_env_search_roots(start: Optional[Path] = None) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    def add_root(root: Path) -> None:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)

    if start is not None:
        anchor = start if start.is_dir() else start.parent
        for candidate in (anchor, *anchor.parents):
            add_root(candidate)

    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        add_root(candidate)

    git_root = _find_git_root(cwd)
    if git_root is not None:
        add_root(git_root)

    breadcrumb_root = read_breadcrumb()        # NEW: last-resort candidate
    if breadcrumb_root is not None:            # NEW
        add_root(breadcrumb_root)              # NEW

    return roots


def _global_home() -> Path:
    """The global Aki config home, independent of cwd."""
    return Path.home() / ".aki"


def _load_project_env(start: Optional[Path] = None) -> Optional[Path]:
    """Load the nearest project-local .env (cwd/parent/git-root/breadcrumb search)."""
    for root in _iter_env_search_roots(start):
        env_path = root / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            return env_path
    return None


def _load_global_env() -> Optional[Path]:
    """Load ~/.aki/.env, independent of cwd."""
    global_env_path = _global_home() / ".env"
    if global_env_path.is_file():
        load_dotenv(global_env_path, override=False)
        return global_env_path
    return None


def _find_project_config_yaml(start: Optional[Path] = None) -> Optional[Path]:
    """Find the nearest project-local config.yaml (same search order as .env)."""
    for root in _iter_env_search_roots(start):
        candidate = root / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_runtime_env(start: Optional[Path] = None) -> Optional[Path]:
    """Load project-local then global (~/.aki/.env) env files into os.environ.

    Both loads use override=False (first-writer-wins), so real process env
    vars set before this call are never clobbered, and project-local values
    win over global values for the same key. Returns the project-local .env
    path if one was found (for backward-compatible callers), or None.
    """
    project_path = _load_project_env(start)
    _load_global_env()
    return project_path


def _load_yaml_dict(path: Path) -> dict:
    """Parse a YAML file with ${VAR}/${VAR:-default} interpolation into a dict."""
    import re

    if not path.is_file():
        return {}

    content = path.read_text(encoding="utf-8")

    def replace_env(match: re.Match) -> str:
        full = match.group(0)
        var_expr = match.group(1)
        if ":-" in var_expr:
            var, default = var_expr.split(":-", 1)
            return os.getenv(var.strip(), default.strip())
        return os.getenv(var_expr, full)

    content = re.sub(r"\$\{([^}]+)\}", replace_env, content)
    data = yaml.safe_load(content)
    return data or {}


def _deep_merge(
    base: dict,
    over: dict,
    tier: int,
    leaf_tier: dict[tuple[str, ...], int],
    path: tuple[str, ...] = (),
) -> dict:
    """Merge `over` onto `base`, recording the origin tier of every leaf that
    `over` contributes (overwriting any previously recorded tier for that leaf,
    since callers apply tiers in ascending precedence order)."""
    result = dict(base)
    for key, value in over.items():
        cur_path = path + (key,)
        if isinstance(value, dict):
            base_child = result.get(key)
            base_child = base_child if isinstance(base_child, dict) else {}
            result[key] = _deep_merge(base_child, value, tier, leaf_tier, cur_path)
        else:
            result[key] = value
            leaf_tier[cur_path] = tier
    return result


def _build_field_env_map() -> dict[tuple[str, ...], str]:
    """Map every leaf field path in Config to the env var name pydantic-settings
    would use for it, by recursively introspecting nested BaseSettings
    env_prefix values (each nested BaseSettings uses its own prefix; prefixes
    are not compounded across nesting levels)."""
    field_map: dict[tuple[str, ...], str] = {}

    def walk(model_cls: type[BaseSettings], path: tuple[str, ...]) -> None:
        prefix = model_cls.model_config.get("env_prefix", "")
        for name, field in model_cls.model_fields.items():
            cur_path = path + (name,)
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
                walk(annotation, cur_path)
            else:
                field_map[cur_path] = f"{prefix}{name}".upper()

    walk(Config, ())
    return field_map


def _prune_merged(
    merged: dict,
    leaf_tier: dict[tuple[str, ...], int],
    field_env_map: dict[tuple[str, ...], str],
    real_env_keys: frozenset[str],
    proj_env_keys: frozenset[str],
    glob_env_keys: frozenset[str],
    path: tuple[str, ...] = (),
) -> dict:
    """Drop YAML-derived leaves that an equal-or-higher env tier already set,
    so the surviving kwargs never defeat pydantic's env_settings for that key."""
    result: dict = {}
    for key, value in merged.items():
        cur_path = path + (key,)
        if isinstance(value, dict):
            pruned_child = _prune_merged(
                value, leaf_tier, field_env_map, real_env_keys, proj_env_keys, glob_env_keys, cur_path
            )
            if pruned_child:
                result[key] = pruned_child
            continue

        env_var = field_env_map.get(cur_path)
        tier = leaf_tier.get(cur_path)
        if env_var is not None and tier != 1:
            if env_var in real_env_keys:
                continue  # real process env (tier 2) always wins, except tier-1 --config
            if tier == 4 and env_var in proj_env_keys:
                continue  # project .env (tier 3) beats global YAML (tier 4)
        result[key] = value
    return result


class QwenConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QWEN_")

    api_key: str = Field(default="", description="Qwen Cloud API key")
    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-max"
    extraction_model: str = ""
    consolidation_model: str = ""
    embedding_model: str = "text-embedding-v3"
    timeout: int = 60
    max_retries: int = 3

    @model_validator(mode="after")
    def _fallback_dashscope_key(self) -> "QwenConfig":
        if not self.api_key:
            self.api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        return self


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

    max_iterations: int = Field(default=20, gt=0, le=100)
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
    agent_profiles: AgentProfilesConfig = Field(default_factory=AgentProfilesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load config from YAML file with environment variable interpolation."""
        import re

        load_runtime_env(path)
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


def resolve_config(config_path: Optional[Path] = None) -> Config:
    """Resolve the effective Config per the tiered precedence chain (highest
    first): explicit --config file > real process env var > project-local
    file (./config.yaml, ./.env) > global file (~/.aki/config.yaml,
    ~/.aki/.env) > internal default.
    """
    # (1) Snapshot BEFORE any dotenv load: the only keys that count as real
    # tier-2 process env. Anything a dotenv load adds afterward is file-tier.
    real_env_keys = frozenset(os.environ)

    before_project = frozenset(os.environ)
    _load_project_env(config_path)
    after_project = frozenset(os.environ)
    proj_env_keys = after_project - before_project

    _load_global_env()
    after_global = frozenset(os.environ)
    glob_env_keys = after_global - after_project

    # (2) Deep-merge YAML tiers, recording per-leaf origin tier.
    leaf_tier: dict[tuple[str, ...], int] = {}
    merged: dict = {}

    global_yaml = _load_yaml_dict(_global_home() / "config.yaml")
    merged = _deep_merge(merged, global_yaml, 4, leaf_tier)

    project_yaml_path = _find_project_config_yaml(config_path)
    if project_yaml_path is not None:
        merged = _deep_merge(merged, _load_yaml_dict(project_yaml_path), 3, leaf_tier)

    if config_path is not None and config_path.is_file():
        merged = _deep_merge(merged, _load_yaml_dict(config_path), 1, leaf_tier)

    # (3) Prune leaves that an equal-or-higher env tier already set, then
    # construct with the second, built-in dotenv mechanism disabled so only
    # our snapshot-ordered os.environ feeds env_settings.
    field_env_map = _build_field_env_map()
    pruned = _prune_merged(merged, leaf_tier, field_env_map, real_env_keys, proj_env_keys, glob_env_keys)

    global _env_provenance
    _env_provenance = {"real": real_env_keys, "project": proj_env_keys, "global": glob_env_keys}

    return Config(**pruned, _env_file=None)


_config: Optional[Config] = None

# Populated by the most recent resolve_config() call: real_env_keys are keys
# that existed in os.environ BEFORE any dotenv load in that call (i.e. genuine
# shell/process env vars), as opposed to keys that load_dotenv(override=False)
# wrote into os.environ as a side effect while loading project/global .env
# files. Callers that need to label a key's true origin (e.g. `aki doctor`)
# should consult this instead of trusting raw `os.environ` membership, since
# the Typer callback always runs resolve_config() before any command body.
_env_provenance: Optional[dict[str, frozenset[str]]] = None


def get_env_provenance() -> Optional[dict[str, frozenset[str]]]:
    """Return {"real", "project", "global"} env-key frozensets captured by the
    most recent resolve_config() call, or None if it hasn't run yet in this
    process."""
    return _env_provenance


def get_config(config_path: Optional[Path] = None) -> Config:
    """Get global config instance, resolving the full precedence chain."""
    global _config
    if _config is None:
        _config = resolve_config(config_path)
    return _config


def reset_config() -> None:
    """Reset global config (for testing)."""
    global _config
    _config = None


def reset_env_provenance() -> None:
    """Reset the cached env provenance snapshot (for testing).

    `_env_provenance` is only ever refreshed by `resolve_config()`; nothing
    invalidates it in between. In a long-lived process (or a pytest session
    that runs many tests without recreating the process), a stale snapshot
    from an earlier `resolve_config()` call can silently mislabel a
    genuinely-real env var as dotenv-sourced if it wasn't present at the time
    of that earlier snapshot. Callers that need a guaranteed-fresh read
    should call `resolve_config()`/`get_config()` again rather than relying
    on a cached snapshot; this function exists so tests (and any other code
    that wants a clean slate) can explicitly discard the stale cache instead
    of trusting whatever the last `resolve_config()` call happened to leave
    behind.
    """
    global _env_provenance
    _env_provenance = None
