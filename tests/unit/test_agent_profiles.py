"""Unit tests for specialized agent profile contracts and registry behavior."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos.agents import (
    AgentProfile,
    AgentRegistry,
    DelegationMetadata,
    MemoryPolicy,
    ProfileNotFoundError,
    ToolPolicy,
)
from agentos.agents.registry import DuplicateAgentProfileError
from agentos.core.config import Config


def _profile(profile_id: str = "reviewer") -> AgentProfile:
    return AgentProfile(
        id=profile_id,
        name="Reviewer",
        description="Reviews code for correctness",
        role="reviewer",
        prompt_template="Review this change carefully.",
        tools=ToolPolicy(allowed=["filesystem.read", "git.diff"]),
        memory=MemoryPolicy(scope="project"),
    )


def test_agent_profile_docs_show_config_policies_and_inert_delegation_metadata():
    docs = Path("docs/agent-profiles.md").read_text(encoding="utf-8")

    assert "agent_profiles:" in docs
    assert "allowed:" in docs
    assert "scope: session" in docs
    assert "delegation:" in docs
    assert "does not create workers" in docs


@pytest.mark.unit
class TestAgentProfile:
    def test_valid_profile_exposes_identity_prompt_tools_and_memory_policy(self):
        profile = _profile()

        assert profile.id == "reviewer"
        assert profile.role == "reviewer"
        assert profile.prompt_template == "Review this change carefully."
        assert profile.tools.allows("git.diff") is True
        assert profile.memory.scope == "project"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("id", ""),
            ("prompt_template", ""),
            ("tools", None),
            ("memory", None),
        ],
    )
    def test_invalid_profile_missing_required_policy_fails_with_specific_error(self, field, value):
        data = _profile().model_dump()
        data[field] = value

        with pytest.raises(ValidationError) as exc_info:
            AgentProfile(**data)

        assert field in str(exc_info.value)

    @pytest.mark.parametrize("profile_id", ["reviewer", "reviewer-agent", "reviewer_agent_1"])
    def test_stable_profile_ids_allow_slug_underscore_and_digits(self, profile_id):
        assert _profile(profile_id).id == profile_id

    @pytest.mark.parametrize("profile_id", ["Reviewer Agent", "reviewer.agent", "reviewer/agent"])
    def test_unstable_profile_ids_are_rejected(self, profile_id):
        with pytest.raises(ValidationError, match="id"):
            _profile(profile_id)

    def test_tool_policy_supports_allow_list_and_explicit_deny_all(self):
        allow_list = ToolPolicy(allowed=["filesystem.read"])
        deny_all = ToolPolicy(deny_all=True)

        assert allow_list.allows("filesystem.read") is True
        assert allow_list.allows("filesystem.write") is False
        assert deny_all.allows("filesystem.read") is False

    def test_tool_policy_requires_allow_list_or_explicit_deny_all(self):
        with pytest.raises(ValidationError, match="deny_all"):
            ToolPolicy()

    def test_delegation_metadata_defaults_to_enabled(self):
        """Default is `enabled=True` to preserve pre-gating behavior (the
        `delegate` tool was previously always exposed regardless of this
        field) for profiles that don't explicitly opt out."""
        profile = _profile()

        assert profile.delegation == DelegationMetadata(enabled=True)

    def test_delegation_metadata_can_be_explicitly_disabled(self):
        profile = _profile().model_copy(
            update={"delegation": DelegationMetadata(enabled=False, strategy="future-review-chain")}
        )

        assert profile.delegation.enabled is False
        assert profile.delegation.strategy == "future-review-chain"


@pytest.mark.unit
class TestAgentRegistry:
    def test_resolves_selected_profile_deterministically(self):
        reviewer = _profile("reviewer")
        builder = _profile("builder").model_copy(update={"name": "Builder", "role": "builder"})
        registry = AgentRegistry([reviewer, builder])

        assert registry.resolve("builder") == builder
        assert registry.resolve("reviewer") == reviewer

    def test_unknown_profile_fails_before_runtime_execution(self):
        registry = AgentRegistry([_profile("reviewer")])

        with pytest.raises(ProfileNotFoundError, match="missing"):
            registry.resolve("missing")

    def test_duplicate_profile_ids_are_rejected(self):
        duplicate = _profile("reviewer").model_copy(update={"name": "Second Reviewer"})

        with pytest.raises(DuplicateAgentProfileError, match="reviewer"):
            AgentRegistry([_profile("reviewer"), duplicate])

    def test_registry_does_not_execute_or_store_skill_implementations(self):
        registry = AgentRegistry([_profile("reviewer")])

        assert not hasattr(registry, "execute")
        assert not hasattr(registry, "register_skill")


@pytest.mark.unit
class TestAgentProfilesConfig:
    def test_absent_agent_profiles_preserves_empty_defaults(self):
        config = Config()

        assert config.agent_profiles.profiles == []
        assert config.agent_profiles.default is None

    def test_yaml_agent_profiles_parse_into_valid_profile_contracts(self, tmp_path: Path):
        config_path = tmp_path / "aki.yaml"
        config_path.write_text(
            """
agent_profiles:
  default: reviewer
  profiles:
    - id: reviewer
      name: Reviewer
      description: Reviews changes
      role: reviewer
      prompt_template: Review this change carefully.
      tools:
        allowed:
          - filesystem.read
          - git.diff
      memory:
        scope: session
""",
            encoding="utf-8",
        )

        config = Config.from_yaml(config_path)

        assert config.agent_profiles.default == "reviewer"
        assert config.agent_profiles.profiles[0].id == "reviewer"
        assert config.agent_profiles.profiles[0].tools.allows("git.diff") is True
        assert config.agent_profiles.profiles[0].memory.scope == "session"
