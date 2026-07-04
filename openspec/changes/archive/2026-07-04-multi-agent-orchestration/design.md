# Design: Multi-Agent Orchestration (Phase 1)

## Technical Approach

Add a synchronous, single-worker delegation path to the existing single
`AgentOS._reasoning_loop()` (`src/agentos/agent/core.py:372`). Delegation is a
synthetic `delegate` tool the supervisor's model may emit; `AgentOS`
intercepts that tool call *before* the normal `SkillRegistry` dispatch,
resolves the named worker `AgentProfile` via `AgentRegistry.resolve()`, runs a
nested `_reasoning_loop()` at `depth=1` under a derived worker `session_id`,
and adapts the worker's `ReasoningOutcome` into an ordinary tool-result
message the supervisor's loop consumes through its existing code path. The
delegate tool schema is present in the tools list only at `depth=0`, which is
the *sole* structural enforcement of the depth-1 guard. With no `delegate`
call emitted, every existing behavior — telemetry, checkpoints, destructive
gate, profile policy — is byte-for-byte unchanged.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Depth threading | Add `depth: int = 0` to `_reasoning_loop()`; `chat()` calls it with no `depth` arg (defaults to 0). Nested worker call passes `depth=1`. | Separate `_worker_loop()` method; a recursion-counter object. | Additive keyword-only-in-effect param keeps `chat()` (core.py:242-249) a minimal change (no new arg) and reuses one loop body for supervisor and worker. |
| Delegate tool exposure | Build the `delegate` schema in a helper and append it to the `tools` list **inside** `_reasoning_loop` only when `depth == 0`, right after the profile-filtered tools are received. | Add it in `chat()` before the loop. | The guard must hold for the *nested* call too; deciding exposure inside the loop keyed on `depth` makes depth-1 absence structural, not caller-dependent. |
| Delegate interception | Match `fn_name == "delegate"` at the top of the per-tool-call body (before the `"_"` skill split at core.py:439), branch into the delegation handler, `continue`. | A registered pseudo-skill in `SkillRegistry`. | Keeps delegation out of `SkillRegistry` (a skill executes tools; delegation resolves an agent). Avoids the `skill_name.fn_name` split mangling the flat `delegate` name. |
| `tool_call_id` capture | Read `tool_call["id"]` (already extracted at core.py:436) at the start of the delegation branch, *before* invoking the nested loop, and use it to derive the worker `session_id`. | Generate a fresh uuid per delegation. | The id already exists on the tool-call object and is required to key the tool-result message back; reusing it makes derivation deterministic and reproducible (spec: replay-safe). |
| Worker `session_id` | `f"{parent_session_id}:delegate:{tool_call_id}"` (confirmed spec contract). | Monotonic counter; hash. | Deterministic per `(parent_session_id, tool_call_id)`; distinct per call; no new `MemoryScope` or persistence layer — pure convention over existing `(project, session_id)` scoping. |
| Worker context / memory | Reuse the same `self.memory` (`MemoryRepository`) instance; the worker builds its own context via `assemble_context` + `_filter_context_for_profile` for `(project, worker_session_id)`. Worker writes its checkpoint/events under `worker_session_id`. | A fresh isolated `MemoryRepository`. | Shared repo gives the worker project/global facts (spec: shared boundary) while the derived `session_id` isolates its session-scoped writes from the supervisor's checkpoint — no physical isolation needed. |
| Worker tool policy | The nested loop resolves the worker `AgentProfile` and applies `_filter_tools_for_profile` on `self.skills.get_all_tools()` for the *worker's* policy — never unioned with the supervisor's tools. Destructive gate (`_is_under_specified`) runs unchanged inside the nested loop. | Inherit/union supervisor tools. | Spec: worker `ToolPolicy` authoritative; the loop already applies profile policy per-instance, so running the worker profile through the same body composes the gate for free. |
| Result adaptation | Convert the worker `ReasoningOutcome` into a single `{"role": "tool", "tool_call_id": <delegate id>, "content": <adapted>}` message, appended to the supervisor's `messages` before the loop continues. On `exhausted=True`, prefix a clear "worker did not finish within its budget" marker so the supervisor's model does not read it as success. | A bespoke assistant message; a second dispatch branch. | Reuses the identical tool-result consumption path (core.py:476-481); no new branch in the supervisor's continuation logic. |
| Telemetry | The nested loop receives the **same** `status_callback` instance. Worker iteration/tool status events flow through it exactly like nested tool-call status, with no `run_id`/`parent_run_id` and no new primitives. | New delegation-scoped callback or event fields. | Spec: telemetry contract untouched in Phase 1; single active worker reuses the supervisor callback. |

## Data Flow

```text
supervisor _reasoning_loop(depth=0)
  tools = _filter_tools_for_profile(...) + [delegate_schema]   # delegate only at depth 0
  model emits tool_call "delegate"{profile_id, task}
        │
        ├─ intercept (fn_name == "delegate", before skill split)
        ├─ tool_call_id = tool_call["id"]
        ├─ worker_sid = f"{session_id}:delegate:{tool_call_id}"
        ├─ worker_profile = agent_registry.resolve(args.profile_id)
        ├─ worker_msgs = _build_messages(task, worker_ctx, project, worker_sid, worker_profile)
        ├─ worker_tools = _filter_tools_for_profile(get_all_tools(), worker_profile)  # NO delegate
        ├─ outcome = _reasoning_loop(worker_msgs, worker_tools, project,
        │                            worker_sid, status_callback, worker_profile, depth=1)
        ├─ append {"role":"tool","tool_call_id":tool_call_id,"content":adapt(outcome)}
        └─ continue supervisor loop → final response
```

At `depth=1` the tools list omits `delegate`, so the worker's model cannot
emit a delegation call; a hallucinated `delegate` name falls through to the
normal unknown-tool path (no depth-2 loop is ever constructed).

## File Changes

| File | Action | Description |
|---|---|---|
| `src/agentos/agent/core.py` | Modify | Add `depth: int = 0` to `_reasoning_loop`; append `delegate` schema when `depth == 0`; add delegation interception branch (resolve worker, derive session, nested loop, adapt outcome); add `_build_delegate_tool_schema`, `_derive_worker_session_id`, `_adapt_worker_outcome` helpers. |
| `src/agentos/agents/registry.py` | Read-only | `resolve(profile_id)` reused to select worker; no contract change. |
| `src/agentos/memory/repository.py` | Read-only | `(project, worker_session_id)` scoping reused; no schema change. |
| `src/agentos/cli/main.py` | Not modified | Delegation is model-driven; no CLI flag (spec: no user-facing worker selection). |
| `tests/unit/test_multi_agent_orchestration.py` | Create | Depth-guard tool presence/absence, session derivation determinism/uniqueness, outcome adaptation (success vs. exhausted), worker tool-policy filtering. |
| `tests/integration/test_delegation_runtime.py` | Create | End-to-end delegate call → worker run → supervisor continuation; worker checkpoint isolation; destructive gate fires in nested loop; non-delegating turn unchanged. |

## Interfaces / Contracts

```python
async def _reasoning_loop(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    project: str,
    session_id: str,
    status_callback: Optional[StatusCallback] = None,
    profile: Optional[AgentProfile] = None,
    depth: int = 0,               # NEW — 0 supervisor, 1 worker; >=1 hides delegate tool
) -> ReasoningOutcome: ...

def _build_delegate_tool_schema() -> dict[str, Any]:
    """OpenAI-style function schema named `delegate`, params:
    profile_id: str (AgentRegistry-resolvable), task: str (worker initial message)."""

@staticmethod
def _derive_worker_session_id(parent_session_id: str, tool_call_id: str) -> str:
    return f"{parent_session_id}:delegate:{tool_call_id}"

@staticmethod
def _adapt_worker_outcome(outcome: ReasoningOutcome) -> str:
    """Success -> outcome.response. exhausted=True -> a clearly-marked
    'worker did not finish within its iteration budget' wrapper so the
    supervisor's model does not treat it as a completed answer."""
```

`chat()` continues to call `_reasoning_loop(...)` with no `depth` argument
(defaults to `0`), so the supervisor call site (core.py:242-249) needs no
change beyond what already exists.

### Delegation branch (inside the per-tool-call loop, before the skill split)

```python
if fn_name == "delegate":
    worker_sid = self._derive_worker_session_id(session_id, tool_call_id)
    worker_profile = self.agent_registry.resolve(fn_args["profile_id"])
    task = fn_args["task"]
    worker_ctx = _filter_context_for_profile(
        self.memory.assemble_context(query=task, project=project,
                                     session_id=worker_sid,
                                     max_tokens=get_config().memory.max_context_tokens),
        worker_profile, worker_sid,
    )
    worker_msgs = self._build_messages(task, worker_ctx, project,
                                       session_id=worker_sid, profile=worker_profile)
    worker_tools = _filter_tools_for_profile(self.skills.get_all_tools(), worker_profile)
    outcome = await self._reasoning_loop(
        worker_msgs, worker_tools, project, worker_sid,
        status_callback=status_callback, profile=worker_profile, depth=1,
    )
    messages.append({"role": "tool", "tool_call_id": tool_call_id,
                     "content": self._adapt_worker_outcome(outcome)})
    continue   # next tool_call / next iteration; supervisor loop resumes uniformly
```

## Depth-Guard Enforcement (structural)

The `delegate` schema is appended to `tools` **only** when `depth == 0`. The
nested worker loop is invoked with `depth=1`, so its assembled tools list
never contains `delegate`. There is no recursion counter, no profile flag, and
no prompt instruction backing this — the guard is that the tool literally does
not exist in the worker's schema. A worker model that hallucinates a
`delegate` call hits the same unknown/unlisted-tool rejection any bogus tool
name hits today; no `depth=2` loop can be constructed.

## Telemetry Behavior (explicit)

The worker's nested `_reasoning_loop()` is passed the **same**
`status_callback` instance the supervisor received. The worker therefore emits
its own per-iteration and per-tool status events through that callback,
interleaved with the supervisor's — indistinguishable from nested tool-call
status. No `run_id`, `parent_run_id`, or delegation vocabulary is added to
`StatusCallback` or any event. A non-delegating turn emits the identical
event sequence as today. This is the deliberate Phase-1 choice: no telemetry
redesign; distinguishable interleaved streams are Phase 2.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `depth=0` tools include `delegate`; `depth=1` excludes it; `_derive_worker_session_id` deterministic + distinct per id; `_adapt_worker_outcome` success vs. exhausted wording; worker tool-policy filtering. | `pytest` with fake profiles/registry; no LLM. |
| Integration | Fake Qwen scripted to emit a `delegate` call → worker runs → supervisor produces final response; worker checkpoint under derived `session_id` not merged into supervisor's; destructive gate fires inside worker loop; hallucinated `delegate` at depth 1 rejected. | Fake Qwen client + real `MemoryRepository` (temp db) + fake skills. |
| E2E/regression | Non-delegating turn: identical response + telemetry sequence as pre-change. | Existing CLI/loop harness with delegation absent. |

## Migration / Rollout

No database, vector, or profile-contract migration. Rollback = remove the
`delegate` schema append and the interception branch; `_reasoning_loop` falls
back to its single-loop path (the `depth` param becomes inert). Existing
config, checkpoints, and telemetry are unaffected.

## Open Questions

- [ ] Should `_adapt_worker_outcome` include `last_tool_summary` in the
      success payload, or only `response`? (Spec requires signaling exhaustion;
      including the tool summary is optional richer context for the supervisor.)
- [ ] If `resolve(profile_id)` raises on an unknown worker id, adapt the error
      into the tool-result message (so the supervisor can recover) vs. letting
      it propagate — Phase 1 leans toward an error tool-result for resilience.
</parameter>
</invoke>
