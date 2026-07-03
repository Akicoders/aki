# Proposal: Agent Runtime Telemetry

## Intent

Make single-agent turns visibly understandable while they run. Today `aki chat` has coarse one-shot status and `aki interactive` waits silently; users only learn about iteration exhaustion after failure. This change gives live progress for reasoning/tool use and clearer max-iteration exhaustion guidance without changing agent architecture.

## Scope

### In Scope
- Enrich existing `StatusCallback` messages with iteration, tool count/name, and final-iteration warning.
- Wire `aki interactive` through the same Rich status path used by one-shot `aki chat`.
- Improve exhaustion copy to explain what happened, what was last attempted, and safe next steps.

### Out of Scope
- Specialized/multi-agent routing, worker names, delegation, or orchestration.
- New telemetry persistence schemas, database migrations, dashboards, or broad observability infrastructure.
- New config knobs for `max_iterations` unless later design proves a minimal read-only use is insufficient.

## Capabilities

### New Capabilities
- `agent-runtime-telemetry`: Live single-agent runtime status and exhaustion UX for CLI turns.

### Modified Capabilities
- None.

## Approach

Use the existing string status callback as the compatibility seam. Emit centralized, bounded status updates from `AgentOS.chat()` / `_reasoning_loop()` at phase, iteration, and tool boundaries; render them in both one-shot and interactive CLI paths. Keep status content factual: tool names/counts only, never raw tool arguments.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modified | Runtime status emission, iteration/tool progress, exhaustion text. |
| `src/agentos/cli/main.py` | Modified | Interactive Rich status callback wiring. |
| `src/agentos/core/config.py` | Read-only | Existing `AgentConfig.max_iterations` remains the source of budget truth. |
| `tests/unit/test_cli_chat.py` | Modified | CLI status assertions. |
| `tests/unit/test_agent_status.py`, `test_agent_exhaustion.py`, `test_reasoning_outcome.py` | Modified | Runtime status/exhaustion coverage. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| String statuses become future UI debt | Med | Centralize formatting; avoid exposing a new structured API now. |
| Rich status flicker/noise | Med | Emit only phase/iteration/tool-boundary updates. |
| Leaking sensitive tool args | Low | Display tool name and count only. |
| Interactive Ctrl-C/EOF regression | Med | Preserve command loop control flow and add unit coverage. |

## Rollback Plan

Revert the additive status emissions, interactive status wrapper, and exhaustion-copy changes. Existing one-shot chat and reasoning behavior should fall back to current coarse statuses with no persistence or schema rollback.

## Dependencies

- Existing `StatusCallback`, Rich console status, `AgentConfig.max_iterations`, and reasoning-loop counters.
- No MCP server, memory persistence, or database dependency changes.

## Success Criteria

- [x] One-shot and interactive turns show live reasoning iteration progress.
- [x] Tool execution status shows tool name/count without arguments.
- [x] Final-iteration warning appears before exhaustion.
- [x] Exhaustion response is actionable and does not imply multi-agent behavior.
- [x] Existing tests plus focused status/exhaustion tests pass.
