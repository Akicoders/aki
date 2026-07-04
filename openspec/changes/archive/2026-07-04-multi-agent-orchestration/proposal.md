# Proposal: Multi-Agent Orchestration (Phase 1)

## Intent

Give Aki its first real orchestration capability: let one agent run (a
"supervisor") delegate a bounded sub-task to another agent profile (a
"worker") and integrate the worker's structured result back into its own
reasoning. Today `AgentOS.chat()` resolves at most one `AgentProfile` and
runs exactly one `_reasoning_loop()` per turn (`src/agentos/agent/core.py:203`,
`core.py:242-249`) — specialized agents differ in prompt/model/tool-set but a
turn is still one flat loop. This change adds nested/composed agent runs so a
single turn can invoke a worker and continue.

This is the foundational first slice of the user's ask for "multi-agent
usable for diverse activities" — not the full feature. It proves the
delegation call/return contract with the smallest safe diff so later phases
(parallel workers, worker-initiated delegation) build on validated ground.

## Scope

### In Scope (Phase 1 only)
- Supervisor delegates to **exactly one** worker profile, **synchronously**,
  **in-process**, per delegation call. The worker is any `AgentProfile`
  resolved from the existing `AgentRegistry` — no new profile contract.
- Delegation mechanism: approach (a) from exploration — a synthetic
  delegation tool call from inside `_reasoning_loop()` triggers a nested
  `_reasoning_loop()` with the worker profile; the worker's
  `ReasoningOutcome` is adapted into a tool-result message the supervisor's
  own loop consumes uniformly.
- **Depth guard of 1**: the delegation tool is exposed only at depth 0
  (supervisor). A worker's nested loop does not receive the delegation tool,
  so no worker-initiated further delegation is possible.
- **Worker memory isolation**: the worker gets a derived `session_id` (e.g.
  `f"{parent_session_id}:worker:{n}"`) so its internal chatter does not
  pollute the supervisor's checkpoint/session history, while shared
  project-level facts remain visible to both via existing `(project, session)`
  scoping. No new physical isolation layer.
- **Tool policy**: the worker's own `ToolPolicy` is authoritative
  (foundation-consistent — profiles are self-declared policy). It composes
  automatically with the existing destructive-tool gate (`_is_under_specified`,
  `core.py:75-87`), which is loop-local and applies unchanged inside the
  worker's nested loop.
- Preserve current default behavior: a turn with no delegation runs exactly
  as it does today.

### Out of Scope
- **Phase 2** — multiple/parallel workers (`asyncio.gather`), result
  aggregation contracts, and `run_id`/`parent_run_id` telemetry tagging to
  keep interleaved status streams distinguishable. Separate future change.
- **Phase 3** — worker-initiated recursive delegation (depth > 1) and any
  tool-policy intersection/inheritance it would require. Separate future change.
- **Telemetry redesign** — `agent-runtime-telemetry` stays the
  single-agent-scoped contract it is. No `run_id`, no worker/delegation
  language added to `StatusCallback` in this change (the single active worker
  reuses the supervisor's callback).
- **AgentProfile / AgentRegistry contract changes** — the
  specialized-agents foundation is reused as-is; this change builds on it and
  does not modify `profiles.py` or `registry.py` contracts. The inert
  `DelegationMetadata` field is not activated here.
- **Session-persistence redesign** — worker isolation is a derived
  `session_id` convention over existing `MemoryRepository` scoping, not a new
  persistence layer.

## Capabilities

### New Capabilities
- `multi-agent-orchestration`: Synchronous single-worker delegation — the
  delegation call/return contract, depth guard, worker session derivation,
  and worker tool-policy composition.

### Modified Capabilities
- None. Existing specialized-agents and telemetry contracts are unchanged.

## Approach

A delegation surfaces as a synthetic tool schema (parallel to
`SkillRegistry.get_all_tools()`, `core.py:237-239`) so the existing
tool-call parsing keeps working without a second dispatch path. When the
supervisor's loop emits a delegation call, `AgentOS` resolves the named
worker profile, runs a nested `_reasoning_loop()` with a derived
`session_id`, and adapts the worker's `ReasoningOutcome` (`response`, plus
enough of `last_tool_summary`/`exhausted` to signal success vs. budget
exhaustion) into a tool-result message. The delegation tool is present only
at depth 0, making the "no worker-initiated delegation" boundary trivially
enforceable.

Approach (b) (an orchestrator layer sequencing `chat()` calls) and (c) (an
async task-queue) are deferred: (a) has the smallest diff, reuses every
existing safety gate unmodified, and validates the contract shape before
investing in concurrency.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modified | Nested `_reasoning_loop()` delegation path, depth guard, worker `ReasoningOutcome`-to-tool-result adapter. |
| `src/agentos/agents/registry.py` | Read-only | Reuse `resolve()` to select worker profiles; no contract change. |
| `src/agentos/memory/repository.py` | Read-only | Reuse `(project, session)` scoping via derived worker `session_id`. |
| `src/agentos/cli/main.py` | Possibly modified | Surface/allow worker-capable profiles if a selection seam is needed. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Runaway nested recursion | Med | Hard depth guard of 1; delegation tool absent below depth 0. |
| Worker chatter pollutes supervisor session | High | Derived `session_id` per worker call; supervisor checkpoint isolated. |
| Privilege escalation via delegation | Med | Worker `ToolPolicy` authoritative; destructive-tool gate composes in nested loop. Intersection deferred to Phase 3. |
| Telemetry contract violation | Med | No status/`run_id` change; single active worker reuses supervisor callback. |
| Supervisor blocked by worker budget | Low | Accepted for Phase 1 (synchronous by design); true concurrency is Phase 2. |

## Rollback Plan

Remove the delegation tool schema and the nested-loop delegation branch;
`AgentOS.chat()` falls back to its single-loop path. No checkpoint, memory,
or profile-contract migration is required.

## Dependencies

- Existing `AgentOS._reasoning_loop()`, `AgentRegistry.resolve()`,
  `ToolPolicy`, `MemoryRepository` scoping, and the destructive-tool gate
  from `agent-scaffolding-clarification`.
- Specialized-agents and agent-runtime-telemetry remain adjacent, unchanged
  foundations — neither is a prerequisite to modify.

## Review Questions

- **How does the supervisor decide WHEN to delegate?** Is this a
  prompt/heuristic-driven decision the model makes on its own (like the
  scaffolding-intent keyword branch), or does the user pick the worker
  profile explicitly via a CLI flag for this first phase? This choice drives
  the delegation-tool surface and CLI shape and should be settled before spec.
- Should the worker's `session_id` derivation use a monotonic counter, the
  tool-call id, or a hash — and does it need to survive a checkpoint replay?
- Is a new `MemoryScope` literal (e.g. `"worker-private"`) needed for Phase 1,
  or is session-level isolation via derived `session_id` sufficient?

## Success Criteria

- [ ] A supervisor turn can delegate one sub-task to a worker profile and
      integrate its result inline.
- [ ] The worker runs with its own `ToolPolicy` and the destructive-tool gate
      applies in the nested loop.
- [ ] The worker uses a derived `session_id`; supervisor checkpoint/session
      history is not polluted by worker events.
- [ ] Workers cannot delegate further (depth guard of 1 enforced).
- [ ] Turns without delegation behave exactly as before; telemetry contract
      is unchanged.
