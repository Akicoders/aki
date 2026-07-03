# Archive Report: Specialized Agents Architecture

## Change Summary

**specialized-agents-architecture** adds a safe foundation for declarative specialized agents: `AgentProfile` (identity, prompt, model overrides, tool policy, memory policy, inert delegation metadata) and a separate `AgentRegistry` that resolves one selected profile per turn into the existing single `AgentOS` loop. Default single-agent behavior is preserved when no profile is selected. CLI gained `--profile` for `chat`/`interactive` and an `aki agents` listing command.

## Verification

**Verdict: PASS WITH WARNINGS** (10/12 spec scenarios fully compliant, 2 partial; 38/38 targeted tests pass; full suite 356/357 pass)

- All 15 tasks complete.
- CLI hang root-caused and fixed (shared root cause with agent-runtime-telemetry): missing mock in a `CliRunner`-based interactive test.

### Non-Blocking Warnings (carried forward)
- Mypy backlog: 200 pre-existing project-wide errors, none introduced by this change (same backlog noted in agent-runtime-telemetry — tracked once, not duplicated).
- Coverage-depth suggestions: no explicit passing test for an *allowed* tool call reaching `SkillRegistry.execute()`, and no explicit cross-profile memory-leakage fixture (only session/project filtering is proven).
- `Chain strategy` remains `pending` in the tasks artifact even though all three slices (profiles/registry, runtime policy, CLI/docs) were applied — noted, not a blocker.
- One pre-existing unrelated test failure in `tests/unit/test_cli_update.py` (`aki update` command), introduced in commit 623f4c1.

## Files Modified

| File | Change |
|------|--------|
| `src/agentos/agents/profiles.py`, `registry.py`, `__init__.py` | New: profile contracts and registry (created) |
| `src/agentos/core/config.py` | `AgentProfilesConfig` parsing |
| `src/agentos/agent/core.py` | Optional `profile_id`, prompt/model/tool/memory policy application |
| `src/agentos/cli/main.py` | `--profile` option, `aki agents` command |
| Test files | `test_agent_profiles.py`, `test_agent_profile_runtime.py`, `test_cli_chat.py` |

## Rollback Plan

Remove profile config/registry wiring; fall back to existing global `AgentConfig` + `SkillRegistry` path. No checkpoint, MCP, or vector-store migration required.

## Archival Action

- Copied proposal, design, tasks, verify-report, specs/ to `openspec/changes/archive/2026-07-03-specialized-agents-architecture/`; `exploration.md` copied as `explore.md`.
- Delta spec did not have a prior main spec — copied directly to `openspec/specs/specialized-agents/spec.md`.
- Original change folder `openspec/changes/specialized-agents-architecture/` removed.

### Fast-Follow Recommendations

1. Add an integration test proving an allowed profile tool call reaches `SkillRegistry.execute()`.
2. Add an explicit cross-profile memory exclusion test.
3. Resolve `Chain strategy: pending` in future task planning for this line of work.

**Status: Archived 2026-07-03**
