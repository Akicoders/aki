"""Registry for specialized agent profiles."""

from collections.abc import Iterable

from pydantic import BaseModel, Field, model_validator

from agentos.agents.profiles import AgentProfile


class DuplicateAgentProfileError(ValueError):
    """Raised when two agent profiles share the same id."""


class ProfileNotFoundError(KeyError):
    """Raised when a requested agent profile does not exist."""


class AgentProfilesConfig(BaseModel):
    """Configuration seam for declarative specialized agent profiles."""

    profiles: list[AgentProfile] = Field(default_factory=list)
    default: str | None = None

    @model_validator(mode="after")
    def _validate_default_exists(self) -> "AgentProfilesConfig":
        if self.default and self.default not in {profile.id for profile in self.profiles}:
            raise ValueError(f"default agent profile not found: {self.default}")
        return self


class AgentRegistry:
    """Discover and resolve agent profiles without executing tools."""

    def __init__(self, profiles: Iterable[AgentProfile] | None = None):
        self._profiles: dict[str, AgentProfile] = {}
        for profile in profiles or []:
            self.register(profile)

    @classmethod
    def from_config(cls, config: AgentProfilesConfig) -> "AgentRegistry":
        """Create a registry from validated profile configuration."""
        return cls(config.profiles)

    def register(self, profile: AgentProfile) -> None:
        """Register a profile, rejecting duplicate ids deterministically."""
        if profile.id in self._profiles:
            raise DuplicateAgentProfileError(f"duplicate agent profile id: {profile.id}")
        self._profiles[profile.id] = profile

    def resolve(self, profile_id: str) -> AgentProfile:
        """Resolve one selected profile or fail before runtime execution."""
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise ProfileNotFoundError(f"agent profile not found: {profile_id}") from exc

    def list_profiles(self) -> list[AgentProfile]:
        """Return registered profiles in deterministic id order."""
        return [self._profiles[key] for key in sorted(self._profiles)]
