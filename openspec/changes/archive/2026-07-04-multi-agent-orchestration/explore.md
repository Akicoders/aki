# Exploration: Multi-Agent Orchestration

## Purpose

Investigate what real multi-agent orchestration (one agent run delegating a
sub-task to another agent run and integrating its result) would require on
top of the existing `AgentProfile` / `AgentRegistry` / telemetry foundation.
This is exploration only — no proposal, spec, or design decisions are made
here.

## Existing foundation (already built, do not redo)

**Specialized agents** (`openspec/specs/specialized-agents/spec.md`,
archived design `openspec/changes/archive/2026-07-03-specialized-agents-architecture/design.md`):

- `AgentProfile` (`src/agentos/agents/profiles.py:46-79`) is a declarative
  Pydantic contract: `id`, `name`, `description`, `role`, `prompt_template`,
  optional `model`/`temperature`/`max_iterations`, `tools: ToolPolicy`,
  `memory: MemoryPolicy`, and an **inert** `delegation: DelegationMetadata`
  field (`enabled: bool = False`, `strategy: str | None`) that the spec
  explicitly forbids from executing anything
  (`openspec/specs/specialized-agents/spec.md:90-104`).
- `AgentRegistry` (`src/agentos/agents/registry.py:31-59`) resolves exactly
  one profile by id (`resolve()`), no concept of "N profiles for one turn."
- `AgentOS.chat()` (`src/agentos/agent/core.py:190-282`) accepts a single
  optional `profile_id`, resolves at most one `AgentProfile`
  (`core.py:203`), and runs **one** `_reasoning_loop()` call
  (`core.py:242-249`) for the whole turn.
- Tool policy: `_tool_is_allowed` / `_filter_tools_for_profile`
  (`core.py:117-134`) gate advertised tools and pre-execution calls against
  `profile.tools.allows(...)`; the destructive-tool gate
  (`_is_under_specified`, `core.py:75-87`, wired at `core.py:456-464`) still
  runs after the tool-policy check, composing cleanly for a single profile.
- Memory policy: `_filter_context_for_profile` (`core.py:137-152`) narrows
  `MemoryContext` to session-only or empty based on `profile.memory.scope`;
  storage itself (`MemoryRepository`, `src/agentos/memory/repository.py:146+`)
  is not partitioned per profile — it is filtered at read time, and writes
  (`create_event`, `write_checkpoint`) tag `active_profile_id` in event
  metadata (`core.py:104-109`, `core.py:266-278`) but do not physically
  isolate storage.
- Telemetry (`openspec/specs/agent-runtime-telemetry/spec.md`,
  `openspec/changes/archive/2026-07-03-agent-runtime-telemetry/design.md`):
  `StatusCallback = Callable[[str], None]` (`core.py:46`) is the only public
  seam. `AgentOS.chat()` emits turn-level status; `_reasoning_loop()` emits
  iteration/tool/exhaustion status (`core.py:395-528`). The spec explicitly
  forbids worker names, delegation status, or multi-agent language in this
  telemetry (`openspec/specs/agent-runtime-telemetry/spec.md:72-80`) — it is
  scoped single-agent by contract, not by accident.

Engram topic keys `sdd/specialized-agents-architecture/design` (#221) and
`sdd/agent-runtime-telemetry/design` (#216) were checked; content matches the
archived files above verbatim, no additional undocumented decisions found.

## The boundary, stated explicitly

- **Specialized agents (exists today):** a single `AgentOS.chat()` turn picks
  **one** `AgentProfile` up front and runs it through the **same, single**
  `_reasoning_loop()`. Different prompt/model/tool-set/memory-scope, but
  still exactly one reasoning loop, one call to Qwen at a time, one
  `ReasoningOutcome`. There is no notion of one agent run invoking another
  agent run as a sub-unit and getting a structured result back.
- **Multi-agent orchestration (net-new, this change):** one agent run (a
  "supervisor") decides mid-turn to spawn or invoke **another** agent run
  (a "worker", itself just an `AgentProfile` instance) as a sub-task, waits
  for (or schedules) its result, and integrates that result back into the
  supervisor's own reasoning — i.e., nested/composed `_reasoning_loop()`
  invocations, not a single flat one.

Anything that still resolves to exactly one profile and one reasoning loop
per user turn is "specialized agents," not "orchestration."

## 1. Supervisor/worker model — what's missing structurally

`_reasoning_loop()` (`core.py:372-508`) is a plain `async` method taking
`messages`, `tools`, `project`, `session_id`, and one `profile`. Nothing
about its signature or `ReasoningOutcome` (`core.py:50-55`: `response`,
`last_tool_summary`, `exhausted`) prevents calling it again recursively —
but nothing invokes it that way today. `AgentOS.chat()` is the only caller
and it call-once's it (`core.py:242`).

Missing structurally:
- **No sub-task invocation point.** There is no tool/function the model can
  call from inside `_reasoning_loop()` that results in another
  `_reasoning_loop()` (or `AgentOS.chat()`) execution. Tool calls today only
  reach `SkillRegistry.execute()` (`core.py:473`), which runs deterministic
  skills, not another LLM turn.
- **No depth/recursion guard.** `max_iterations` bounds one loop's own
  iterations; nothing bounds nested loop depth if `_reasoning_loop` called
  itself.
- **No worker selection contract.** A supervisor would need a way to name
  which `AgentProfile` (from `AgentRegistry`) should handle a delegated
  sub-task — `AgentRegistry.resolve()` already supports resolving an
  arbitrary profile by id, so this part is reusable as-is.

## 2. Delegation/handoff contract shape

Given the existing shapes, a delegation call/return contract would need:

- **Call side:** a structured "delegate to profile X with task description
  Y" request. This could surface as a new synthetic tool schema (parallel to
  `SkillRegistry.get_all_tools()`, `core.py:237-239`) so the existing
  tool-calling loop mechanics (parse `skill_name_fn_name`, `core.py:439-442`)
  keep working without inventing a second dispatch path — a `orchestration`
  "skill" whose function is `delegate`, or a first-class field alongside
  tool_calls, are the two shapes worth comparing at design time.
- **Return side:** `ReasoningOutcome` (`core.py:50-55`) is close to what a
  worker should hand back (`response`, plus enough of `last_tool_summary`/
  `exhausted` for the supervisor to know if the worker succeeded or ran out
  of budget) but it is not currently serializable as a tool result — the
  supervisor's reasoning loop only knows how to append `SkillResult`-shaped
  tool messages (`core.py:476-481`). A worker's `ReasoningOutcome` would need
  an adapter into that same tool-result message shape so the supervisor's
  own loop can keep consuming it uniformly.

## 3. Shared vs. private memory per agent

- Today, scoping is entirely by `(project, session_id)` plus an optional
  `active_profile_id` tag in event metadata — see `create_event` calls
  throughout `core.py` (e.g. `core.py:208-215`, `core.py:255-262`,
  `core.py:483-501`) and `write_checkpoint`/`read_checkpoint`
  (`src/agentos/memory/repository.py:357-391`) which key by
  `(project, session_id)` only, one checkpoint per session, not per profile.
- `_filter_context_for_profile` (`core.py:137-152`) is a **read-time**
  filter, not physical isolation: `project` scope returns everything,
  `session` scope narrows to same-session events, `disabled` returns
  nothing. There is no `worker`-only scope today.
- For a supervisor/worker split, the natural reuse is: same `project`
  (shared facts/checkpoint — a worker should see project-level facts the
  supervisor already has) but a **new** `session_id` per worker invocation
  (e.g. derived as `f"{parent_session_id}:worker:{n}"`) so a worker's
  internal tool-call chatter does not pollute the supervisor's own
  checkpoint/session history, while `assemble_context`
  (`src/agentos/memory/repository.py:482+`) can still surface project facts
  to both. This reuses existing scoping primitives — it does not require
  a new physical isolation layer, only a session-id convention plus
  possibly a new `MemoryScope` literal (e.g. `"worker-private"`) if session-
  level isolation from the parent's own session events turns out
  insufficient.

## 4. Tool permission inheritance/restrictions

- `ToolPolicy.allows()` (`profiles.py:26-30`) is a pure allow-list/deny-all
  check with no notion of a parent policy. Composing a worker's tools with
  a supervisor's tools would need an explicit decision:
  (a) worker profile's own `ToolPolicy` is authoritative (simplest, matches
  "profiles are independent policy" as already designed), or
  (b) intersect with the supervisor's policy (stricter, prevents privilege
  escalation via delegation, but requires new merge logic not in
  `ToolPolicy` today).
  Given the existing model treats each profile as fully self-declared
  policy (no inheritance anywhere in `profiles.py` or `registry.py`), **(a)
  is the smaller, foundation-consistent default**; (b) is a hardening
  option worth flagging as a design open question, not decided here.
- The destructive-tool gate (`_is_under_specified`, `core.py:75-87`,
  `openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/`)
  is applied inside `_reasoning_loop()` per tool call
  (`core.py:456-464`), independent of `profile`. If a worker runs its own
  nested `_reasoning_loop()`, this gate composes automatically for free —
  no change needed, since the gate is a loop-local check, not a
  profile-scoped one.
- Telemetry composition: `_notify_status` (`core.py:58-60`) is a flat
  callback with no run identity. A nested worker loop reusing the same
  `status_callback` would interleave worker iteration/tool messages with
  the supervisor's under the same status stream with no way to tell them
  apart — this is the one place existing telemetry does NOT compose
  cleanly without a small addition (see section 6).

## 5. Execution model

- Today: exactly one `_reasoning_loop()` call per `chat()`, so sequential-
  single is the only existing execution model. `max_iterations`
  (`AgentConfig`, consumed at `core.py:382-386`) bounds one loop's own
  retries; there is no retry-a-failed-sub-task concept and no cancellation
  primitive anywhere in `core.py` (loops run to completion or exhaustion,
  no `asyncio.CancelledError` handling visible).
- Net-new for orchestration: sequencing multiple worker invocations
  (trivial extension — just call the delegation path N times), true
  parallel worker execution (`asyncio.gather` over N nested loop calls —
  requires each worker to have an independent session_id per point 3, and
  independent message/tool state, which the current per-call `messages`
  list already supports since it's a local variable, not shared state),
  and any retry/cancellation semantics beyond what `max_iterations` already
  bounds.

## 6. Compatibility with existing telemetry

- Current telemetry is explicitly single-run: `StatusCallback` carries only
  a message string, no run/agent identity, and the spec forbids
  orchestration language in status text
  (`openspec/specs/agent-runtime-telemetry/spec.md:72-80`). That spec's
  "Single-Agent Scope Boundary" requirement is a hard boundary this change
  must not violate by mutating the existing telemetry contract.
- To make telemetry multi-agent-aware **without redesigning it**, the
  smallest compatible addition is a `run_id` (and optional `parent_run_id`)
  threaded alongside the existing `StatusCallback` calls — e.g. wrapping
  `_notify_status` calls with a prefix/tag identifying which run (supervisor
  vs. worker N) emitted them, while keeping the message content itself
  exactly as factual/safe as it is today (tool name, ordinal, phase — no
  new sensitive fields). This is additive metadata, not a change to what
  telemetry already reports, so it should be a **separate, later** SDD
  change once the delegation call shape itself is decided, not bundled into
  this exploration/first apply.

## 7. Staged migration (recommended)

- **Phase 1 (this change's likely first apply scope):** Supervisor can
  invoke exactly **one** worker profile **synchronously**, in-process, and
  get a single structured result back, integrated into the supervisor's own
  reasoning loop as a tool-result message. No parallelism, no worker-
  initiated further delegation (worker profiles used as workers do not get
  a delegation tool of their own — enforced by simply not exposing the
  delegation tool inside a nested loop, or via a depth guard of exactly 1).
  New session_id per worker call (section 3), worker's own `ToolPolicy` is
  authoritative (section 4), telemetry unchanged (no run_id yet — worker's
  status callback can simply reuse the supervisor's callback since there is
  only ever one worker active at a time).
- **Phase 2:** Multiple workers, potentially parallel (`asyncio.gather`),
  requiring the `run_id`/telemetry tagging from section 6 to keep status
  streams distinguishable, and an aggregation contract for how the
  supervisor combines N worker results.
- **Phase 3:** Worker-initiated further delegation (recursive depth > 1),
  requiring an explicit depth guard and re-examining whether tool-policy
  intersection (option (b) in section 4) becomes necessary once delegation
  chains are more than one hop deep.

## Candidate architectural approaches for the delegation mechanism

**(a) Synchronous in-process delegation, recursive `_reasoning_loop()` with
a depth guard.**
Reuses `_reasoning_loop()` almost as-is; a delegation "tool call" triggers a
nested `await self._reasoning_loop(...)` with a different `profile` and a
derived `session_id`, whose `ReasoningOutcome.response` is adapted into a
tool-result message for the supervisor's own loop. Tradeoffs: smallest
diff, reuses every existing safety gate (destructive-tool gate, tool
policy) for free since it's the same code path; but couples worker
execution to the supervisor's call stack — a worker exhausting its own
`max_iterations` blocks the supervisor's iteration too (no true
concurrency), and a bug in recursion depth handling risks runaway nested
calls.

**(b) A new orchestrator layer above `AgentOS` sequencing multiple
`AgentOS.chat()`-like calls.**
A separate class (e.g. `Orchestrator`) owns calling `AgentOS.chat()` for
the supervisor, inspecting its output for a delegation request, then
calling `AgentOS.chat()` again for the worker profile, and feeding the
worker's response back into a second supervisor `AgentOS.chat()` call.
Tradeoffs: cleaner separation (no changes to `_reasoning_loop()` internals,
lower risk to existing single-agent behavior), but loses the tight
single-loop feedback where a worker result reenters the supervisor's *same*
in-flight tool-call sequence — this shape works better if delegation is
modeled as "ask a sub-agent, then continue as a fresh turn" rather than "a
tool call that returns a result inline," which is a real behavioral
difference from (a) that must be settled before design.

**(c) An async task-queue model for parallel workers.**
Worker invocations become queued/async tasks (`asyncio.create_task` or an
actual queue) that the supervisor can fire off and later await/collect,
enabling true parallelism from the start. Tradeoffs: needed eventually for
Phase 2, but premature for Phase 1 — it requires solving cancellation,
partial-failure aggregation, and telemetry multiplexing (section 6) all at
once, which is exactly the "big-bang" risk the non-goals for this change
warn against.

**Recommendation:** start with **(a)** for Phase 1 — it has the smallest
diff, reuses every existing safety/telemetry gate unmodified, and the depth
guard (delegation tool only available at depth 0) keeps the non-goal of
"no worker-initiated further delegation" trivially enforceable. Revisit
(b) or a hybrid only if Phase 1 usage shows the tight-recursion coupling
of (a) causes real problems (e.g. blocking behavior under load); (c) is
the natural Phase 2 evolution once (a) validates the delegation contract
shape.

## Explicit non-goals (carried forward, do not scope-creep later phases)

- Do not redo telemetry design (`agent-runtime-telemetry` stays as the
  single-agent-scoped contract it is; only additive `run_id` tagging is
  proposed, as a later change).
- Do not redo specialized-agent foundations — `AgentProfile`/`AgentRegistry`
  are reused as-is; this change composes on top of them, it does not modify
  their contracts.
- Do not redesign session persistence from scratch — worker isolation is
  achieved via a derived `session_id` convention reusing existing
  `MemoryRepository` scoping, not a new persistence layer.
- Do not implement a full autonomous runtime in exploration or first apply
  — Phase 1 scope above (one worker, synchronous, no further delegation) is
  the ceiling for the first apply; Phases 2-3 are noted but out of scope
  until separate SDD cycles.
