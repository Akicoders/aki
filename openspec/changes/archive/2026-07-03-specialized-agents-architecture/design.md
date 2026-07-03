# Design: Specialized Agents Architecture

## Technical Approach

Add declarative agent profiles as policy inputs to the existing single `AgentOS` loop. `AgentRegistry` resolves one `AgentProfile`; `AgentOS.chat()` applies its prompt/model/tool/memory policies while still using `SkillRegistry` for tool schemas and execution. With no profile selected, all current `AgentConfig`, `SkillRegistry`, checkpoint, CLI, and destructive-tool behavior remains unchanged.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Registry seam | Create `src/agentos/agents/profiles.py` and `registry.py`; inject `AgentRegistry` into `AgentOS` beside `SkillRegistry`. | Extend `SkillRegistry`; encode profiles as skills. | Agents define identity/policy; skills execute tools. Keeping seams separate prevents registry responsibility drift. |
| Storage | Start config-first: `Config.agent_profiles` loaded from YAML/env defaults plus built-ins. No SQLAlchemy/Chroma schema in Stage 1. | Persist profile rows in SQLite immediately. | Profiles are durable configuration, not memory observations. Avoids migration risk and keeps rollback to config deletion. |
| Runtime compatibility | Add optional `profile_id` args to CLI and `AgentOS.chat()/stream_chat()`, default `None`. | Change default agent into a profile. | Preserves current single-agent runtime exactly when no profile is selected. |
| Tool policy | Filter advertised tools and validate requested calls before `SkillRegistry.execute()`. | Trust model to only call advertised tools. | Tool filtering is UX; pre-execution validation is the safety boundary. Destructive gates still run after allow-policy checks. |
| Memory policy | Apply a small `MemoryPolicy` adapter around `assemble_context`, `create_event`, and checkpoint writes; metadata records active profile id only when selected. | Store separate vector collections per profile. | Stage 1 needs scoping, not physical isolation. Avoids Chroma migration while enabling future stricter isolation. |
| Delegation | Add inert metadata fields only, never execution hooks. | Supervisor/worker runtime now. | The spec forbids spawning/parallelism; metadata keeps future compatibility without behavior. |

## Data Flow

```text
CLI --profile? ──→ AgentOS.chat(profile_id?)
                       │
                       ├─→ AgentRegistry.resolve() ──→ AgentProfile | None
                       ├─→ MemoryPolicy.apply_read() ──→ MemoryRepository
                       ├─→ build messages(profile prompt + defaults)
                       ├─→ SkillRegistry.get_all_tools() ──→ ToolPolicy.filter()
                       └─→ existing reasoning loop ──→ ToolPolicy.validate() ──→ destructive gate ──→ SkillRegistry.execute()
```

No MCP server, subprocess, worker, or parallel agent is created by this flow.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/agentos/agents/__init__.py` | Create | Export profile models and registry. |
| `src/agentos/agents/profiles.py` | Create | Pydantic contracts: profile identity, runtime, tool, memory, delegation metadata. |
| `src/agentos/agents/registry.py` | Create | Built-in/config profile loading, validation, deterministic resolution. |
| `src/agentos/core/config.py` | Modify | Add `AgentProfilesConfig` and config parsing. |
| `src/agentos/agent/core.py` | Modify | Accept optional profile, merge runtime defaults, enforce tool/memory policy. |
| `src/agentos/cli/main.py` | Modify | Add optional `--profile` for `chat` and `interactive`; show selected profile in header. |
| `tests/unit/test_agent_profiles.py` | Create | Contract, registry, validation, tool policy tests. |
| `tests/integration/test_agent_profile_runtime.py` | Create | Default compatibility and selected-profile runtime tests. |

## Interfaces / Contracts

```python
class AgentProfile(BaseModel):
    id: str
    name: str
    description: str
    role: Literal["planner", "builder", "reviewer", "custom"]
    prompt_template: str
    model: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    tools: ToolPolicy
    memory: MemoryPolicy
    delegation: DelegationMetadata = DelegationMetadata(enabled=False)
```

Validation: non-empty stable `id`; prompt required; `tools` must be allow-list or explicit deny-all; memory scope must be one of `project`, `session`, `global`, `disabled`. Unknown selected profile raises before storing user input or calling Qwen.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Pydantic validation, duplicate ids, unknown profile, default inheritance, tool deny. | `pytest` with fake profiles and fake registry. |
| Integration | `AgentOS.chat()` default unchanged; selected prompt/model/tools applied; disallowed tool blocked pre-execution. | Fake Qwen client + fake memory/skills. |
| E2E | CLI chat with `--profile` still uses one `AgentOS` turn. | Typer runner or existing CLI subprocess pattern. |

## Migration / Rollout

No database/vector migration required. Roll out in three steps: profile models/registry, runtime wiring behind optional `profile_id`, then CLI option. Existing config without `agent_profiles` behaves identically. Future delegation can consume `AgentProfile.delegation` metadata only after separate supervisor/worker specs define isolation, telemetry, and lifecycle.

## Open Questions

- [ ] Which built-in profiles ship first, if any, versus custom-only configuration?
