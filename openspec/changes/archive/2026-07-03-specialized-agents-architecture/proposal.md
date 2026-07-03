# Proposal: Specialized Agents Architecture

## Intent

Introduce a safe foundation for user-facing specialized agents in Aki. Today Aki has one agent loop plus skills; users cannot define distinct planner/reviewer/builder identities with separate prompts, model preferences, tool scopes, or memory policy.

## Scope

### In Scope
- Define `AgentProfile` identity, runtime config, tool policy, and memory policy.
- Add an `AgentRegistry` separate from `SkillRegistry`; skills remain tool execution backends.
- Support explicit profile selection or deterministic single-profile routing over the existing `AgentOS` loop.
- Preserve current default single-agent behavior when no profile is selected.

### Out of Scope
- Recursive delegation, autonomous worker spawning, parallel agents, or external process orchestration.
- Runtime telemetry internals, dashboards, persistent telemetry schemas, or status UX.
- Breaking existing `aki chat`, `aki interactive`, `/skills`, checkpoints, or destructive-tool safeguards.

## Capabilities

### New Capabilities
- `specialized-agents`: Declarative agent profiles, registry behavior, and profile-scoped runtime policy.

### Modified Capabilities
- None.

## Approach

Stage 1 creates profile and registry primitives first: `AgentProfile` captures `id`, `name`, `description`, `role`, prompt template, optional model/temperature/max-iterations override, allowed skill/function set, and memory scope. `AgentRegistry` resolves built-in/configured profiles and hands one selected profile to the current `AgentOS` loop. Stage 2 may add bounded delegation later, after profile isolation, memory ownership, and telemetry contracts are proven.

This remains separate from `agent-runtime-telemetry` because telemetry explains what one current turn is doing; specialized agents define who is acting and with which policy. Mixing them would blur product behavior with observability and risk duplicating the active single-agent telemetry contract.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/core/config.py` | New/Modified | Profile config, validation, defaults. |
| `src/agentos/agent/core.py` | Modified | Accept selected profile without changing default loop behavior. |
| `src/agentos/skills/base.py` | Read-only/Modified | Reuse `SkillRegistry`; do not turn it into an agent registry. |
| `src/agentos/memory/models.py` | Modified | Persist profile metadata only if design requires storage. |
| `src/agentos/cli/main.py` | Modified | Optional profile selection/help without breaking current commands. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Registry boundary gets muddy | Med | Keep agent identity in `AgentRegistry`, tool execution in `SkillRegistry`. |
| Memory leaks across profiles | High | Specify project/session/global scope rules before delegation. |
| Premature multi-agent complexity | Med | Ship profile selection first; defer worker handoff. |
| Conflicts with telemetry change | Med | Only expose minimal future metadata; leave status/iteration UX to telemetry. |

## Rollback Plan

Remove profile config/registry wiring and fall back to the existing global `AgentConfig` + `SkillRegistry` path. No checkpoint, MCP server, or vector-store migration should be required for Stage 1.

## Dependencies

- Existing `AgentOS` loop, `SkillRegistry`, `AgentConfig`, session persistence, project metadata, and destructive-tool gate.
- `agent-runtime-telemetry` remains an adjacent single-agent visibility change, not a prerequisite for profile primitives.

## Review Questions

- Which built-in profiles are required first: planner, reviewer, builder, or only a custom-profile mechanism?
- Should profile metadata be persisted immediately, or start as config-only until delegation exists?

## Success Criteria

- [x] Aki can resolve a selected profile with scoped prompt/model/tool/memory policy.
- [x] Default chat behavior remains unchanged without a selected profile.
- [x] `SkillRegistry` stays a tool registry, not an agent identity registry.
- [x] Delegation is explicitly deferred and documented for a later change.
