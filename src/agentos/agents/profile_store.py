"""File-based persistence for agent profiles, used by the Cockpit TUI.

`AgentRegistry` (see `registry.py`) is normally built from static config via
`AgentRegistry.from_config(...)` and stays untouched here — production
`AgentOS` wiring is not affected by this module.

This module adds an independent JSON store (`data/agent_profiles.json`,
matching the convention set by `cockpit/tui/task_model.py` for the Kanban
board) so the Cockpit "Agents" tab can create/edit/delete `AgentProfile`
entries without a database. Persisted profiles are merged with config-defined
ones by id, with persisted entries taking precedence — this lets a user
override or extend the profiles declared in `config.yaml` from the TUI.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentos.agents.profiles import AgentProfile


def get_profiles_file_path() -> Path:
    """Return the path to the persisted agent-profiles JSON store."""
    path = Path("data/agent_profiles.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_store() -> dict:
    path = get_profiles_file_path()
    if not path.exists():
        return {"profiles": [], "deleted": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "profiles": data.get("profiles", []),
            "deleted": data.get("deleted", []),
        }
    except Exception:
        return {"profiles": [], "deleted": []}


def load_persisted_profiles() -> list[AgentProfile]:
    """Load profiles previously saved from the Cockpit Agents tab."""
    store = _load_store()
    profiles: list[AgentProfile] = []
    for item in store["profiles"]:
        try:
            profiles.append(AgentProfile.model_validate(item))
        except Exception:
            continue
    return profiles


def load_deleted_ids() -> set[str]:
    """Return ids the user explicitly removed via the Cockpit Agents tab.

    These are tombstoned so a config-defined profile with the same id does
    not silently reappear after being deleted in the TUI.
    """
    return set(_load_store()["deleted"])


def save_persisted_profiles(profiles: list[AgentProfile], deleted: set[str] | None = None) -> None:
    """Persist the given profiles (and deletion tombstones), overwriting the store."""
    path = get_profiles_file_path()
    try:
        data = {
            "profiles": [profile.model_dump() for profile in profiles],
            "deleted": sorted(deleted or load_deleted_ids()),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_merged_profiles(config_profiles: list[AgentProfile] | None = None) -> list[AgentProfile]:
    """Merge config-declared profiles with persisted ones.

    Persisted profiles win on id collision, so edits made in the Cockpit TUI
    take effect without mutating `config.yaml`. Ids explicitly deleted via
    the TUI are excluded even if still declared in config.
    """
    deleted = load_deleted_ids()
    merged: dict[str, AgentProfile] = {
        p.id: p for p in (config_profiles or []) if p.id not in deleted
    }
    for profile in load_persisted_profiles():
        merged[profile.id] = profile
    return sorted(merged.values(), key=lambda p: p.id)


def delete_profile(profile_id: str, config_profiles: list[AgentProfile] | None = None) -> None:
    """Remove a profile from the persisted store and tombstone its id.

    Tombstoning ensures a config-declared profile of the same id does not
    reappear on the next merge.
    """
    persisted = [p for p in load_persisted_profiles() if p.id != profile_id]
    deleted = load_deleted_ids()
    deleted.add(profile_id)
    save_persisted_profiles(persisted, deleted)


def upsert_profile(profile: AgentProfile) -> None:
    """Create or update one profile in the persisted store."""
    persisted = [p for p in load_persisted_profiles() if p.id != profile.id]
    persisted.append(profile)
    deleted = load_deleted_ids()
    deleted.discard(profile.id)
    save_persisted_profiles(persisted, deleted)
