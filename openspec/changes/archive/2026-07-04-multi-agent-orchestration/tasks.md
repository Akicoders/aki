# Tasks: Multi-Agent Orchestration (Phase 1)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 350-480 |
| 400-line budget risk | Medium-High |
| Chained PRs recommended | Yes (recommended, not forced) |
| Suggested split | PR 1 depth/schema/session-derivation/adapter helpers + unit tests → PR 2 delegation interception branch wired into `_reasoning_loop` + integration/regression tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium-High

All changes land in a single file (`src/agentos/agent/core.py`) plus two new
test files. The single-file concentration keeps review focus high per PR even
if chained, so `ask-on-risk` is appropriate rather than a hard `size:exception`
mandate — but the two-file split below should be honored if total diff nears
400 lines, since `core.py`'s `_reasoning_loop` is a regression-critical path
(non-delegating turns must stay byte-identical).

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Depth threading, `delegate` schema helper, session-id derivation, outcome adapter — all as isolated, independently unit-testable helpers | PR 1 | No interception wiring yet; `_reasoning_loop` signature changes but behavior for depth=0 callers unaffected until Unit 2 wires the branch. |
| 2 | Delegation interception branch inside `_reasoning_loop`, worker context/tools assembly, nested loop invocation, message append | PR 2 | Depends on PR 1. Regression-critical: non-delegating turn must remain byte-identical. |
| 3 | Integration/regression proof, resolved open-decision behaviors, final review pass | PR 2 (same PR as Unit 2) or PR 3 if diff runs long | `pytest`, `ruff`, `mypy`. |

## Resolved Open Decisions (finalized for this pass)

- **`last_tool_summary` in success payload**: SKIP for now — `ReasoningOutcome.last_tool_summary` is not new plumbing to *read*, but folding it into the adapted success string is extra shaping logic the spec does not require (spec only requires `response` text on success + a clear exhaustion marker). Keep `_adapt_worker_outcome` success path to `outcome.response` only. Revisit in Phase 2 if supervisors need richer context.
- **Unknown `profile_id` on delegate call**: adapt to an error tool-result message (`{"role": "tool", "tool_call_id": ..., "content": "delegate error: unknown profile '<id>'"}`), appended the same way a successful outcome would be, and `continue` the supervisor loop — do NOT let `AgentRegistry.resolve()`'s exception propagate out of `_reasoning_loop`. This matches design's leaning and keeps the supervisor in control of recovery (retry, different profile, or proceed without the worker).

## Phase 1: Depth Threading, Delegate Schema, Session Derivation, Outcome Adapter

- [x] 1.1 RED: Add `tests/unit/test_multi_agent_orchestration.py` with cases: `_reasoning_loop` tools list includes `delegate` schema when `depth=0`; tools list excludes `delegate` when `depth=1`; `chat()` call site with no `depth` arg defaults to depth 0 behavior (tools list still contains `delegate`).
- [x] 1.2 GREEN: Add `depth: int = 0` parameter to `_reasoning_loop` (`src/agentos/agent/core.py:372`); add `_build_delegate_tool_schema()` helper (OpenAI-style function schema, `profile_id: str`, `task: str`); append its output to the assembled `tools` list only when `depth == 0`, immediately after `_filter_tools_for_profile` output is built inside the loop. Leave the `chat()` call site (`core.py:242-249`) unchanged — no `depth` argument passed, defaulting to `0`.
- [x] 1.3 RED: Add unit tests for `_derive_worker_session_id(parent_session_id, tool_call_id)`: deterministic/reproducible for the same `(parent_session_id, tool_call_id)` pair; distinct output for two different `tool_call_id`s under the same parent; exact format `f"{parent_session_id}:delegate:{tool_call_id}"`.
- [x] 1.4 GREEN: Add `_derive_worker_session_id` static helper on `AgentOS` (or module-level, matching design's `@staticmethod` signature) implementing the exact derivation scheme above.
- [x] 1.5 RED: Add unit tests for `_adapt_worker_outcome(outcome)`: success (`exhausted=False`, non-empty `response`) returns content containing exactly `outcome.response` with no `last_tool_summary` folded in; exhaustion (`exhausted=True`) returns content containing a clear "worker did not finish within its iteration budget" marker, distinguishable from a normal response by the supervisor's model.
- [x] 1.6 GREEN: Add `_adapt_worker_outcome` static helper implementing the success/exhaustion branching per 1.5 and the Resolved Open Decisions above.

## Phase 2: Delegation Interception and Nested Loop Wiring

- [x] 2.1 RED: Add integration tests in `tests/integration/test_delegation_runtime.py` for the end-to-end path: fake Qwen client scripted to emit a `delegate` tool call with a valid `profile_id`/`task` → assert a nested worker `_reasoning_loop` runs at `depth=1` → assert the supervisor's loop resumes and produces a final response in the same turn, with the tool-result message's `tool_call_id` matching the original delegate call.
- [x] 2.2 GREEN: Inside `_reasoning_loop`'s per-tool-call body, intercept `fn_name == "delegate"` before the `"_"` skill-name split (`core.py:439`), branching before `skill_name, fn_name = fn_name.split("_", 1)` reads garbage from a flat `"delegate"` name. Read `tool_call_id = tool_call["id"]` (already extracted at `core.py:436`) before invoking the nested loop.
- [x] 2.3 GREEN: In the delegation branch, derive `worker_sid` via `_derive_worker_session_id(session_id, tool_call_id)`, resolve `worker_profile = self.agent_registry.resolve(fn_args["profile_id"])`, assemble worker context via `self.memory.assemble_context(...)` + `_filter_context_for_profile` for `(project, worker_sid)`, build `worker_msgs` via `_build_messages(task, worker_ctx, project, session_id=worker_sid, profile=worker_profile)`, and compute `worker_tools = _filter_tools_for_profile(self.skills.get_all_tools(), worker_profile)` (never unioned with supervisor tools, and never includes `delegate` since the nested call uses `depth=1`).
- [x] 2.4 GREEN: Invoke `outcome = await self._reasoning_loop(worker_msgs, worker_tools, project, worker_sid, status_callback=status_callback, profile=worker_profile, depth=1)` — same `status_callback` instance, no new telemetry primitives. Append `{"role": "tool", "tool_call_id": tool_call_id, "content": self._adapt_worker_outcome(outcome)}` to `messages`, then `continue` so the supervisor loop resumes through its existing tool-result consumption path.
- [x] 2.5 RED: Add a unit test asserting that an unknown `profile_id` passed to `delegate` results in an error tool-result message appended (not a raised/propagated exception) and the supervisor loop continues.
- [x] 2.6 GREEN: Wrap `self.agent_registry.resolve(fn_args["profile_id"])` in a try/except that catches the registry's unknown-profile error, appends an error tool-result message (`tool_call_id` matching, content describing the unknown profile), and `continue`s instead of propagating.
- [x] 2.7 RED: Add an integration test asserting a worker at `depth=1` whose model output references a hallucinated `delegate`-shaped call is rejected via the existing unknown/unlisted-tool path (`_tool_is_allowed` / equivalent), and that no `depth=2` nested loop is ever constructed.
- [x] 2.8 RED: Add an integration test proving worker checkpoint/session-scoped writes under `worker_sid` are never merged into or read back from the supervisor's `session_id` checkpoint, while project/global-scoped facts remain visible to the worker via `_filter_context_for_profile`.
- [x] 2.9 RED: Add an integration test proving the destructive-tool gate (`_is_under_specified`) still fires inside the worker's nested loop exactly as it would for a standalone turn on that profile (clarifying-question response, `exhausted=False`).
- [x] 2.10 RED: Add a regression test proving a non-delegating turn (model never emits `delegate`) produces an identical response and identical status-event sequence to pre-change behavior — no `run_id`/`parent_run_id` on any emitted event.
- [x] 2.11 GREEN: Fix any regressions surfaced by 2.7-2.10; confirm no behavior changes leak into the depth=0 default path outside the delegation branch itself.
- [x] 2.12 Run `pytest -xvs`, targeted unit/integration marker runs, `ruff check .`, and `mypy src/agentos`; fix regressions in-slice.
