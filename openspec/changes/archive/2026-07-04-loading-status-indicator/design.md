# Design: Loading Status Indicator (Phase 1 — Status Text Polish)

## Technical Approach

This is a presentation-only refinement of strings already produced by the
status-formatting helpers in `src/agentos/agent/core.py` and passed through
the unchanged `StatusCallback = Callable[[str], None]` boundary. No new data
crosses the callback, no new Rich component is introduced, and no call site
gains an argument. Each of the six phase formatters gains a leading glyph and a
phase-specific verb per the confirmed spec templates; the wiring in `chat()`,
`_reasoning_loop()`, and both CLI commands stays byte-for-byte identical in
shape. Because the worker's nested `_reasoning_loop(depth=1)` reuses the exact
same pure formatters and the exact same callback instance, worker status is
indistinguishable in shape from a depth-0 supervisor turn — the
`multi-agent-orchestration` telemetry constraint is preserved for free.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Emoji-only, NO ASCII fallback (Open Q #1) | Ship emoji glyphs only (🧠/🔧/📚/💾/✅/⏳). No ASCII/`[tool]`-style fallback path this phase. Declared an explicit **non-goal** below. | Dual emoji+ASCII with a config/env toggle; ASCII-only. | Proposal explicitly deferred the fork as "trivially swappable at the formatting layer if requested"; the spec deliberately added **no** fallback requirement. Adding a toggle now is speculative surface for zero confirmed demand. The verb prefix ("Thinking", "Running", …) already differentiates phases if a terminal renders emoji poorly, so emoji-only degrades gracefully without a code path. |
| Collapse the two iteration formatters into ONE helper (Open Q #2) | Replace `_format_iteration_status` **and** `_format_final_iteration_status` with a single shared `_format_thinking_status(iteration, max_iterations) -> "🧠 Thinking — iteration {i}/{n}"`. Remove `_format_final_iteration_status` and the `if current_iteration == max_iterations:` second-notify block (core.py:411-415) entirely. | Keep two functions with identical bodies; keep the second notify emitting the (now duplicate) same string. | The confirmed spec gives ONE template for both mid-loop and final iteration. Two functions with identical output is drift-prone duplication (house style: collapse when trivial). The final-iteration notify previously carried distinct "no automatic retry remains" wording; that success/exhaustion SIGNAL now lives solely and sufficiently in the terminal template (`✅ Turn complete` vs `⏳ Turn exhausted`), so the mid-loop second emit is pure redundancy and is dropped. |
| Terminal formatter | Add `_format_terminal_status(exhausted: bool) -> str` returning `⏳ Turn exhausted` / `✅ Turn complete`. Replace the inline conditional literal at core.py:280 with a call to it. | Keep the inline `"Turn exhausted" if ... else "Turn complete"` conditional, glyphs added inline. | A named pure helper gives the spec's terminal unit scenario a direct target and keeps all six templates co-located and testable next to the others. |
| Context / saving formatters | Add `_format_context_status() -> "📚 Collecting project context"` and `_format_saving_status() -> "💾 Saving conversation"`; call them at core.py:219 and core.py:253 in place of the bare literals. | Inline the emoji literals at both call sites. | Consistency with the existing `_format_*` helper family and a single source of truth for each fixed template (unit-testable, no duplicated literal). |
| Tool formatter | Keep `_format_tool_status(ordinal, total, safe_tool_name)` signature unchanged; only the body changes to `f"🔧 Running {safe_tool_name} ({ordinal}/{total})"`. | New signature ordering. | Spec requires the same already-resolved tool name + ordinal/total; no caller change needed. |
| `main.py` `_format_status` | **No change.** It stays `f"[bold cyan]{message}...[/bold cyan]"` — a pure Rich wrapper. Emoji glyphs pass through the f-string transparently. | Move glyph selection into `_format_status`; add per-phase color. | Division of responsibility already holds: `core.py` emits phase-specific message CONTENT; `main.py` only wraps that content for Rich display. Per-phase color is an explicit proposal Decision to defer to Phase 2. The pre-existing trailing `...` renders as `✅ Turn complete...` exactly as `Turn complete...` renders today — cosmetically unchanged behavior. |
| `"Starting turn"` / `"Loading memory engine"` | **Unchanged.** Left as plain literals; not among the six spec templates. | Give `"Starting turn"` a 🧠 glyph. | The spec defines exactly six phase templates; the thinking template requires `{i}/{n}` counts that do not yet exist at core.py:204 (before the loop). `"Loading memory engine"` is a CLI-only pre-agent spinner. Both are out of the spec's six-phase set — touching them is scope creep. |

## Non-Goals (explicit — resolving Open Q #1)

- **No ASCII/plain-marker fallback path.** Emoji glyphs are the only rendering
  this phase. There is no toggle, env var, config flag, or branch selecting an
  ASCII variant. This is a deliberate, stated non-goal, not an oversight.
  Re-adding it later is a one-line-per-template change at the formatting layer,
  exactly as the proposal noted.
- No per-phase color (kept `bold cyan` for all — proposal Decision).
- No `StatusCallback` signature/shape change; no telemetry-contract change.
- No worker/supervisor/delegation vocabulary in any status string.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/agentos/agent/core.py` | Modify | Replace `_format_iteration_status`/`_format_final_iteration_status` with one `_format_thinking_status`; update `_format_tool_status` body; add `_format_context_status`, `_format_saving_status`, `_format_terminal_status`. Remove the `if current_iteration == max_iterations:` second-notify block (core.py:411-415). Swap the context/saving/terminal call-site literals (core.py:219, 253, 280) for the new helpers. |
| `src/agentos/cli/main.py` | Not modified | `_format_status` is a pure Rich wrapper; glyphs pass through. No wiring change. |
| `tests/unit/test_agent_status.py` | Modify | Update expected strings (lines ~104-108, 135-138) to the six new templates; drop the now-removed "Final iteration …" emission from the expected sequence. |
| `tests/unit/test_cli_chat.py` | Modify | Update status-string assertions (lines ~63-64, 77, 116-117, 177-178). |
| `tests/unit/test_reasoning_outcome.py` | Modify | Update expected sequence (lines ~143-146): new thinking/tool strings; remove the "Final iteration …" entry. |
| `tests/integration/test_delegation_runtime.py` | Modify | Update expected supervisor sequence (lines ~346-350) to new templates. Add/adjust a worker-path assertion that the depth=1 loop emits the identical `🔧 Running {name} ({k}/{m})` shape (spec Requirement 3). |

## Interfaces / Contracts

```python
def _format_thinking_status(iteration: int, max_iterations: int) -> str:
    return f"🧠 Thinking — iteration {iteration}/{max_iterations}"

def _format_tool_status(ordinal: int, total: int, safe_tool_name: str) -> str:
    return f"🔧 Running {safe_tool_name} ({ordinal}/{total})"

def _format_context_status() -> str:
    return "📚 Collecting project context"

def _format_saving_status() -> str:
    return "💾 Saving conversation"

def _format_terminal_status(exhausted: bool) -> str:
    return "⏳ Turn exhausted" if exhausted else "✅ Turn complete"
```

`StatusCallback = Callable[[str], None]` and `_notify_status` are unchanged.
Every helper stays pure (no `self`, no history), so it is directly
unit-testable and depth-agnostic.

### Reasoning-loop notify sites (after change)

```python
for iteration in range(max_iterations):
    current_iteration = iteration + 1
    _notify_status(status_callback,
                   _format_thinking_status(current_iteration, max_iterations))
    # NOTE: the former `if current_iteration == max_iterations: _notify_status(
    #   _format_final_iteration_status(...))` block is REMOVED — it now emits
    #   the same string, and the exhaustion signal is carried by the terminal
    #   template in chat().
    ...
    _notify_status(status_callback,
                   _format_tool_status(tool_ordinal, total_tools_in_response, safe_tool_name))
```

## Composition / Depth-1 Worker (spec Requirement 3)

The worker runs through `_run_delegation` → `_reasoning_loop(..., depth=1)`
with the SAME `status_callback` instance (core.py:569-577). It reuses the
identical `_format_thinking_status` and `_format_tool_status` helpers with **no
depth branch** — the helpers take only counts and a tool name and never see
`depth`, so a worker's status string is byte-identical in shape to a depth-0
supervisor's. There is therefore no place for "worker"/"supervisor"/"delegate"
vocabulary to enter, satisfying the "no delegation vocabulary" requirement
structurally.

Terminal status (`✅`/`⏳`) is emitted only in `chat()` (core.py:280), which the
worker path never enters — the worker returns a `ReasoningOutcome` that
`_adapt_worker_outcome` consumes. `_format_terminal_status` is nonetheless
pure and depth-independent, so the spec's worker-terminal unit scenario holds
by construction: formatting a worker outcome's exhaustion yields the same
`⏳ Turn exhausted` a supervisor would produce. No terminal notify is added to
the worker path (that would be a new emission, out of scope).

## `status_callback` Signature (spec Requirement 4)

Unchanged across the entire chain: `chat()`, `_reasoning_loop()`,
`_run_delegation()`, `stream_chat()`, and both CLI `update_status` closures all
continue to call the callback with exactly one `str`. No `run_id`, phase enum,
or structured payload is introduced.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Each of the six formatters returns its exact template (`🧠 Thinking — iteration 2/5`, `🔧 Running memory.search (2/3)`, `📚 …`, `💾 …`, `✅ Turn complete`, `⏳ Turn exhausted`). Final-iteration still reports the true `5/5` from the unchanged counter. | Direct calls to the pure helpers; no LLM. |
| Unit/Integration | Supervisor turn emits the new sequence; the removed "Final iteration" line is gone. | Existing `test_agent_status.py` / `test_reasoning_outcome.py` fake-Qwen harness with updated expected strings. |
| Integration | Worker depth=1 loop emits `🔧 Running fs.write (1/2)` with no worker/supervisor/delegate substring; shape identical to depth-0. | `test_delegation_runtime.py` scripted delegate call, assert worker-emitted status strings. |

## Migration / Rollout

No data, checkpoint, vector, or contract migration. Rollback = revert the
formatter bodies to their prior strings, restore the two-function iteration
split and its second-notify block, and restore the original test assertions.
Purely a string change behind an unchanged callback.

## Open Questions

None. Both flagged open questions are resolved above: (1) emoji-only, no ASCII
fallback — declared a non-goal; (2) the two iteration formatters collapse into
a single `_format_thinking_status` helper, with the redundant final-iteration
notify removed.

## Risk Callout for Tasks/Apply

The proposal's Affected Areas table listed only `test_agent_status.py` and
`test_cli_chat.py` as test updates, but **four** test files assert the old
plain-text strings and MUST be updated in the same slice:

- `tests/unit/test_agent_status.py` (~104-108, 135-138)
- `tests/unit/test_cli_chat.py` (~63-64, 77, 116-117, 177-178)
- `tests/unit/test_reasoning_outcome.py` (~143-146) — **not in the proposal list**
- `tests/integration/test_delegation_runtime.py` (~346-350) — **not in the proposal list**

`test_reasoning_outcome.py` and `test_delegation_runtime.py` also assert the
`"Final iteration 2/2; no automatic retry remains"` line, which the design
removes — those expected sequences must drop that entry, not just re-spell it.
</content>
</invoke>
