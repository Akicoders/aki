# Multi-Agent Orchestration Specification (Phase 1)

## Purpose

Define the synchronous, in-process, single-worker delegation contract that
lets a supervisor `_reasoning_loop()` invoke exactly one worker
`AgentProfile` and consume its result as an ordinary tool result — with a
hard depth guard, a derived worker `session_id` for memory isolation, and
worker-authoritative tool policy composed with the existing destructive-tool
gate. This is additive to the existing single-loop `AgentOS` foundation
(`specialized-agents`) and does not modify `AgentProfile`, `AgentRegistry`,
or the telemetry contract.

## Requirements

### Requirement: Delegation Trigger Is Model-Driven

Delegation MUST be triggered exclusively by the supervisor's own model
emitting a delegation tool call during `_reasoning_loop()` — the same
pattern used by the existing scaffolding-intent / destructive-tool gate
mechanism (`_is_under_specified`, `core.py:75-87`). There MUST NOT be a
user-facing CLI flag, argument, or interactive prompt that lets the user
pick the worker profile directly for a turn. The user's only input is the
natural-language request; whether and which worker to delegate to is a
decision the supervisor's model makes by emitting the `delegate` tool call
with its own chosen arguments.

#### Scenario: Model chooses to delegate without user flag (`integration`)

- GIVEN a supervisor turn with no delegation-related CLI flag or argument
  present anywhere in the invocation
- WHEN the supervisor's model judges that delegating to a worker profile is
  useful for the user's request
- THEN the model MUST emit a `delegate` tool call as an ordinary tool call
  in its response
- AND `AgentOS` MUST resolve and run the named worker profile as a result of
  that tool call alone

#### Scenario: No delegation is attempted when the model doesn't ask for it (`unit`)

- GIVEN a supervisor turn where the model's response contains no `delegate`
  tool call
- WHEN `_reasoning_loop()` processes the turn
- THEN no worker profile SHALL be resolved or run
- AND turn behavior MUST be identical to the pre-existing single-loop path

### Requirement: Delegation Tool Schema and Depth Threading

The system MUST expose a synthetic `delegate` tool schema to the supervisor,
parallel in construction to `SkillRegistry.get_all_tools()`
(`core.py:237-239`), with parameters for the worker profile identifier
(a `profile_id: str` matching an `AgentRegistry`-resolvable id) and a task
description (`task: str`, free-form natural language handed to the worker as
its initial user message). `_reasoning_loop()` MUST accept a `depth: int`
parameter (default `0`) threaded through every recursive/nested invocation,
and the delegation tool schema MUST be included in, or excluded from, the
tools list passed to the model based on that depth.

#### Scenario: Delegate tool schema is present at depth 0 (`unit`)

- GIVEN the supervisor's `_reasoning_loop()` is invoked with `depth=0`
- WHEN the tools list for that turn is assembled
- THEN the `delegate` tool schema MUST be included alongside the profile's
  allowed skill tools

#### Scenario: Delegate tool call resolves worker and returns a result (`integration`)

- GIVEN a supervisor turn at depth 0 where the model emits a `delegate` tool
  call with a valid `profile_id` and a `task` string
- WHEN `AgentOS` processes that tool call
- THEN it MUST resolve the named worker profile via the existing
  `AgentRegistry.resolve()` (no contract change)
- AND it MUST run a nested `_reasoning_loop()` for that worker at `depth=1`
- AND the supervisor's own loop MUST resume with the worker's result
  available as a tool-result message, continuing to a final response in the
  same turn

### Requirement: Hard Depth Guard of 1

The delegation tool schema MUST be entirely absent from the tools list
whenever `_reasoning_loop()` is invoked with `depth >= 1`. This is the sole
enforcement mechanism for the "no worker-initiated further delegation"
boundary in Phase 1 — there MUST NOT be any other check (recursion counter,
explicit profile flag, etc.) required to prevent depth-2 delegation.

#### Scenario: Delegation tool is absent at depth 1 (`unit`)

- GIVEN `_reasoning_loop()` is invoked with `depth=1` (i.e. running as a
  worker spawned by a supervisor's delegation call)
- WHEN the tools list for that loop instance is assembled
- THEN the `delegate` tool schema MUST NOT appear in the list
- AND the worker's model has no way to emit a delegation call even if it
  attempts to reference the tool by name

#### Scenario: Worker cannot itself delegate (`integration`)

- GIVEN a worker running at `depth=1` whose model output references a
  `delegate`-shaped function call anyway (e.g. hallucinated)
- WHEN the worker's `_reasoning_loop()` processes the model output
- THEN the call MUST be rejected the same way any unknown/unlisted tool name
  is rejected today — no nested loop at `depth=2` SHALL ever be created

### Requirement: Derived Worker Session Isolation

Each delegation call MUST derive a worker `session_id` from the supervisor's
own `session_id` plus a per-call unique component, using the scheme:

```
worker_session_id = f"{parent_session_id}:delegate:{tool_call_id}"
```

where `tool_call_id` is the id the model/provider assigned to the specific
`delegate` tool-call invocation (the same id used to correlate the tool
result back to the call, already present on every tool call in the existing
message-handling path). This derivation MUST be deterministic and
reproducible for a given `(parent_session_id, tool_call_id)` pair, and MUST
NOT require a new `MemoryScope` literal or any new persistence layer — it is
a naming convention over the existing `(project, session_id)` scoping in
`MemoryRepository`.

#### Scenario: Two sequential delegation calls in one turn get distinct session ids (`unit`)

- GIVEN a supervisor turn in which the model emits two separate `delegate`
  tool calls (sequentially, each with its own tool-call id) within the same
  parent `session_id`
- WHEN `AgentOS` derives the worker `session_id` for each call
- THEN the two derived `session_id` values MUST differ
- AND each worker's checkpoint/session-scoped memory MUST be stored under
  its own derived key with no collision

#### Scenario: Derivation is reproducible for the same call (`unit`)

- GIVEN a fixed `parent_session_id` and `tool_call_id`
- WHEN the derivation function is invoked more than once with the same
  inputs (e.g. during a checkpoint replay or retry)
- THEN it MUST return the identical derived `session_id` both times

### Requirement: Memory Sharing Boundary

The worker MUST read project-level facts through the existing
`(project, session_id)` scoping and `MemoryScope` filtering
(`_filter_context_for_profile`, `core.py:137-152`) unchanged — `project`- and
`global`-scoped facts remain visible to the worker exactly as they would to
any profile. The worker's own checkpoint and session-scoped writes MUST be
persisted under its derived `session_id`, and MUST NOT be merged into, or
overwrite, the supervisor's checkpoint or session-scoped event history.

#### Scenario: Worker writes do not leak into supervisor's checkpoint (`integration`)

- GIVEN a supervisor delegates to a worker, and the worker's nested loop
  writes a checkpoint and session-scoped facts under its derived
  `session_id`
- WHEN the supervisor's turn completes and its own checkpoint is written
- THEN the supervisor's checkpoint MUST reflect only supervisor-loop events
- AND a subsequent read of the supervisor's `session_id` checkpoint MUST NOT
  contain any worker-only session-scoped event or fact

#### Scenario: Worker still sees shared project facts (`integration`)

- GIVEN project-level facts exist under the shared `project` scope
- WHEN a worker's nested loop assembles its context via
  `_filter_context_for_profile` for its own (`project`, derived
  `session_id`) pair
- THEN project- and global-scoped facts MUST still be visible to the worker
  under the worker's own profile memory policy, unaffected by the derived
  `session_id`

### Requirement: Worker Tool Policy Is Authoritative and Composes With the Destructive Gate

The worker's nested `_reasoning_loop()` MUST use the worker's own
`AgentProfile.tools` (`ToolPolicy`) exactly as `_filter_tools_for_profile`
(`core.py:123-134`) applies it for any single-loop turn today — the worker
tool set MUST NOT be widened, inherited, or unioned with the supervisor's
own allowed tools. The existing destructive-tool gate
(`_is_under_specified`, `core.py:75-87`, invoked at `core.py:456-464`) MUST
continue to apply unchanged inside the worker's nested loop, exactly as it
would for a standalone turn running that same profile.

#### Scenario: Worker's ToolPolicy restricts a tool the supervisor could otherwise use (`unit`)

- GIVEN a supervisor profile whose `ToolPolicy` allows a tool `X`
- AND a worker profile whose `ToolPolicy` does not allow tool `X`
- WHEN the supervisor delegates to that worker
- THEN the worker's assembled tools list MUST NOT include tool `X`
- AND the worker's model cannot invoke `X` even though the supervisor could

#### Scenario: Destructive-tool gate still fires inside the worker's nested loop (`integration`)

- GIVEN a worker's nested `_reasoning_loop()` at `depth=1`
- AND the worker's model emits an under-specified call to a tool the
  `SkillRegistry` marks destructive
- WHEN the worker's loop processes that tool call
- THEN `_is_under_specified` MUST short-circuit the call
- AND the worker's `ReasoningOutcome` MUST carry a clarifying-question
  response with `exhausted=False`, exactly as it would for a supervisor-only
  turn

### Requirement: Worker Result Adapted Into a Uniform Tool-Result Message

The worker's `ReasoningOutcome` (`response: str`, `last_tool_summary: str`,
`exhausted: bool`) MUST be adapted into a single tool-result message keyed
to the originating `delegate` tool-call id, structured so the supervisor's
own `_reasoning_loop()` consumes it through the identical code path used for
every other tool result (no separate dispatch branch). The adapted content
MUST convey the worker's `response` text on success, and MUST clearly signal
budget exhaustion (`exhausted=True`) so the supervisor's model can decide
how to proceed (e.g. retry, narrow the task, or answer without the worker's
result) rather than silently treating an exhausted worker as a successful
one.

#### Scenario: Worker response becomes an ordinary tool result (`integration`)

- GIVEN a worker's nested loop completes with `exhausted=False` and a
  non-empty `response`
- WHEN `AgentOS` adapts the `ReasoningOutcome` for the supervisor
- THEN it MUST append a tool-result message with `tool_call_id` matching the
  original `delegate` call and content containing the worker's `response`
- AND the supervisor's loop MUST continue processing that message exactly
  as it would any other tool result

#### Scenario: Worker exhaustion is surfaced, not hidden (`unit`)

- GIVEN a worker's nested loop completes with `exhausted=True`
- WHEN `AgentOS` adapts the `ReasoningOutcome` for the supervisor
- THEN the resulting tool-result message content MUST indicate the worker
  did not reach a final answer within its iteration budget
- AND the supervisor's loop MUST NOT treat this as equivalent to a
  successful worker response

### Requirement: Telemetry Contract Untouched in Phase 1

This change MUST NOT introduce `run_id`, `parent_run_id`, or any
worker/delegation-specific vocabulary into `StatusCallback` or its emitted
events. The worker's nested `_reasoning_loop()` MUST reuse the same
`status_callback` instance passed to the supervisor's loop, so existing
per-loop-instance events continue to fire exactly as they do for any single
loop today, with no way for a caller to distinguish supervisor-originated
events from worker-originated events in Phase 1.

#### Scenario: Worker loop reuses supervisor's status callback unchanged (`unit`)

- GIVEN a supervisor delegates to a worker
- WHEN the worker's nested `_reasoning_loop()` emits status events during
  its own tool calls
- THEN those events MUST be delivered through the same `status_callback`
  instance the supervisor's loop was given
- AND no `run_id` or `parent_run_id` field SHALL appear on any emitted event

#### Scenario: Non-delegating turn's telemetry is unaffected (`integration`)

- GIVEN a turn where the model never emits a `delegate` tool call
- WHEN the turn completes
- THEN the sequence and shape of emitted status events MUST be identical to
  the current pre-delegation behavior
