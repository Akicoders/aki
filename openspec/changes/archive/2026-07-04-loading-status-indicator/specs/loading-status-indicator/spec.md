# Loading Status Indicator Specification (Phase 1 — Status Text Polish)

## Purpose

Define the exact phase-differentiated text templates the status-formatting
layer (`_format_iteration_status`, `_format_final_iteration_status`,
`_format_tool_status`, the "Collecting project context" / "Saving
conversation" / "Turn complete" / "Turn exhausted" call sites in
`src/agentos/agent/core.py`, and `_format_status` in
`src/agentos/cli/main.py:77-78`) MUST produce, and the composition
constraints that keep this presentation-only change from leaking into the
telemetry contract (`agent-runtime-telemetry`) or the multi-agent delegation
boundary (`multi-agent-orchestration`). This is additive polish over the
existing `console.status(...)` spinner and the existing
`StatusCallback = Callable[[str], None]` contract — no new capability, no
new data crossing the callback boundary.

## Requirements

### Requirement: Phase-Specific Status Text Templates

The status-formatting layer MUST render each of the six phase types using
the following exact templates, where `{i}`/`{n}` are the current/max
iteration counts already tracked by `_reasoning_loop()` and
`{skill.function}`/`{k}`/`{m}` are the already-resolved tool name and
ordinal/total already passed into `_format_tool_status`:

| Phase | Template |
|-------|----------|
| Thinking / model turn | `🧠 Thinking — iteration {i}/{n}` |
| Tool execution | `🔧 Running {skill.function} ({k}/{m})` |
| Context collection | `📚 Collecting project context` |
| Saving conversation | `💾 Saving conversation` |
| Terminal — turn complete | `✅ Turn complete` |
| Terminal — turn exhausted | `⏳ Turn exhausted` |

No other glyph, verb, or wording variant SHALL be used for these six phases.

#### Scenario: Thinking phase renders iteration glyph and counts (`unit`)

- GIVEN `_reasoning_loop()` is at iteration `2` of a `5`-iteration budget
- WHEN the iteration status is formatted
- THEN the produced string MUST equal `🧠 Thinking — iteration 2/5`

#### Scenario: Tool execution phase renders tool glyph, name, and ordinal (`unit`)

- GIVEN a tool call is the 2nd of 3 tool calls in the current turn, resolving
  to skill/function name `memory.search`
- WHEN `_format_tool_status` formats the status
- THEN the produced string MUST equal `🔧 Running memory.search (2/3)`

#### Scenario: Context collection phase renders its fixed template (`unit`)

- GIVEN `AgentOS` begins collecting project context for a turn
- WHEN the status callback fires for that phase
- THEN the produced string MUST equal `📚 Collecting project context`

#### Scenario: Saving-conversation phase renders its fixed template (`unit`)

- GIVEN `AgentOS` begins persisting the checkpoint/session event history
  after a turn
- WHEN the status callback fires for that phase
- THEN the produced string MUST equal `💾 Saving conversation`

#### Scenario: Terminal phase renders complete vs. exhausted correctly (`unit`)

- GIVEN a turn's `ReasoningOutcome.exhausted` is `False`
- WHEN the terminal status is formatted
- THEN the produced string MUST equal `✅ Turn complete`
- GIVEN a turn's `ReasoningOutcome.exhausted` is `True`
- WHEN the terminal status is formatted
- THEN the produced string MUST equal `⏳ Turn exhausted`

### Requirement: Iteration Count Format Matches Existing Telemetry Counters

The `{i}/{n}` iteration format MUST use the same `iteration` and
`max_iterations` values already tracked and passed to
`_format_iteration_status` / `_format_final_iteration_status` by
`_reasoning_loop()` today (per the shipped `agent-runtime-telemetry` spec).
This change MUST NOT introduce a new counter, a new source of truth for
iteration count, or any adjustment to the exhaustion boundary condition
(e.g., off-by-one at the final iteration).

#### Scenario: Final-iteration status still reports the true iteration/max pair (`unit`)

- GIVEN `_reasoning_loop()` reaches its final allowed iteration (e.g.
  iteration `5` of a `5`-iteration budget) with no automatic retry remaining
- WHEN the iteration status is formatted for that final iteration
- THEN the string MUST still read `🧠 Thinking — iteration 5/5`
- AND the reported `5/5` MUST come from the exact same `iteration` /
  `max_iterations` values the pre-existing exhaustion logic already used to
  decide no retry remains — no separately incremented or recomputed counter

### Requirement: No Worker/Delegation Vocabulary Leaks Into Status Text

Status text emitted during a delegated worker's nested `_reasoning_loop()`
(per `multi-agent-orchestration`, "Telemetry Contract Untouched in Phase 1")
MUST use the identical generic templates defined in this spec — the same
glyphs and verbs a supervisor-only turn would emit. No template SHALL vary
by depth, by whether the loop is a supervisor or a worker, or reference
"worker", "supervisor", "delegate", "delegation", or any other orchestration
role name.

#### Scenario: Worker's nested loop emits the same generic templates as the supervisor (`integration`)

- GIVEN a supervisor delegates to a worker profile, and the worker's nested
  `_reasoning_loop()` runs at `depth=1` reusing the supervisor's
  `status_callback` instance
- WHEN the worker's nested loop emits a tool-execution status during its own
  tool call (e.g. its 1st of 2 tool calls, resolving to `fs.write`)
- THEN the emitted string MUST equal `🔧 Running fs.write (1/2)`
- AND the string MUST NOT contain "worker", "supervisor", "delegate", or
  "delegation" in any form
- AND this MUST be indistinguishable in shape from a status string emitted
  by a non-delegating, depth-0 supervisor turn

#### Scenario: Worker's terminal status uses the same complete/exhausted templates (`unit`)

- GIVEN a worker's nested loop completes with `exhausted=True`
- WHEN the terminal status is formatted for that worker's loop
- THEN the string MUST equal `⏳ Turn exhausted` — the same string a
  depth-0 supervisor turn would emit for the same outcome, not a
  worker-specific variant

### Requirement: `StatusCallback` Signature and Contract Are Unchanged

This change MUST NOT alter the `StatusCallback = Callable[[str], None]`
type alias, its call sites, or the `console.status(...)` wiring in either
the `chat` command or `_async_interactive`. Only the string content passed
to an unchanged callback signature is affected.

#### Scenario: Callback still accepts a single plain string argument (`unit`)

- GIVEN any of the six phase formatters defined in this spec
- WHEN a formatter's output is passed to `_notify_status(status_callback,
  message)`
- THEN `status_callback` MUST be invoked with exactly one positional
  argument of type `str`
- AND no additional argument (e.g. `run_id`, phase enum, structured payload)
  SHALL be added to that call
- AND the call MUST succeed against the pre-existing
  `StatusCallback = Callable[[str], None]` type alias with no signature
  change required
</content>
