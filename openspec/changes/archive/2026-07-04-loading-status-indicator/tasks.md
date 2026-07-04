# Tasks: Loading Status Indicator (Phase 1 — Status Text Polish)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 120-180 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a |

Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Low

This is a formatting-string-only change confined to one function set in
`src/agentos/agent/core.py` (five small pure helpers replacing two, plus
call-site swaps and one deletion) and four test files updating string
assertions/expected sequences. No new logic, no new files beyond the
existing test suite, no `main.py` change. Comfortably under the 400-line
budget; a single PR is appropriate.

## Phase 1: Collapse Iteration Formatters, Remove Redundant Final-Notify

- [x] 1.1 RED: In `tests/unit/test_agent_status.py`, update/add unit tests
      asserting `_format_thinking_status(iteration, max_iterations)` returns
      exactly `🧠 Thinking — iteration {i}/{n}` for a mid-loop case
      (`2/5`) and for the final-iteration case (`5/5`), using the SAME
      helper for both — no `_format_final_iteration_status` reference
      remains anywhere in the test file. Run to confirm RED (helper does not
      exist yet / old assertions fail against new expectations).
- [x] 1.2 GREEN: In `src/agentos/agent/core.py`, replace
      `_format_iteration_status` and `_format_final_iteration_status` with a
      single `_format_thinking_status(iteration: int, max_iterations: int) -> str`
      returning `f"🧠 Thinking — iteration {iteration}/{max_iterations}"`.
      Update the notify call inside `_reasoning_loop()`'s per-iteration loop
      to use it.
- [x] 1.3 RED: In `tests/unit/test_reasoning_outcome.py`, update the expected
      status-event sequence (~lines 143-146): DELETE the entry asserting
      `"Final iteration 2/2; no automatic retry remains"` (or equivalent
      wording) — the assertion must prove that string/event no longer
      appears in the sequence, not just re-spell it. Update remaining
      thinking-status entries to the new `🧠 Thinking — iteration {i}/{n}`
      template. Run to confirm RED.
- [x] 1.4 GREEN: In `src/agentos/agent/core.py`, DELETE the
      `if current_iteration == max_iterations:` second-notify block
      (core.py:411-415) entirely — do not re-spell it with the new
      template, remove the block and its call to
      `_format_final_iteration_status` (already removed in 1.2). Run 1.1,
      1.3 tests to confirm GREEN and that the duplicate-notify behavior is
      gone (only one status notification per iteration, regardless of
      whether it is the final one).

## Phase 2: Tool, Context, Saving, Terminal Formatters

- [x] 2.1 RED: In `tests/unit/test_agent_status.py`, update/add a unit test
      asserting `_format_tool_status(ordinal, total, safe_tool_name)`
      returns exactly `🔧 Running {safe_tool_name} ({ordinal}/{total})`
      (e.g. `🔧 Running memory.search (2/3)`), signature unchanged. Run to
      confirm RED.
- [x] 2.2 GREEN: In `src/agentos/agent/core.py`, update `_format_tool_status`
      body only (signature unchanged) to
      `f"🔧 Running {safe_tool_name} ({ordinal}/{total})"`.
- [x] 2.3 RED: Add unit tests for two new pure helpers:
      `_format_context_status() -> "📚 Collecting project context"` and
      `_format_saving_status() -> "💾 Saving conversation"`. Run to confirm
      RED (helpers do not exist).
- [x] 2.4 GREEN: In `src/agentos/agent/core.py`, add
      `_format_context_status()` and `_format_saving_status()` per 2.3;
      swap the hardcoded literal status strings at the context-collection
      call site (core.py:219) and the saving-conversation call site
      (core.py:253) to call these helpers instead of using inline text.
- [x] 2.5 RED: Add a unit test for
      `_format_terminal_status(exhausted: bool) -> str` asserting
      `exhausted=False` → `✅ Turn complete` and `exhausted=True` →
      `⏳ Turn exhausted`. Run to confirm RED.
- [x] 2.6 GREEN: In `src/agentos/agent/core.py`, add
      `_format_terminal_status(exhausted: bool) -> str` per 2.5; replace the
      inline conditional literal at the terminal-status call site
      (core.py:280) with a call to it.

## Phase 3: Downstream Test Updates and Regression Proof

- [x] 3.1 GREEN: Update `tests/unit/test_cli_chat.py` status-string
      assertions (~lines 63-64, 77, 116-117, 177-178) to the six new
      templates. No production code change expected here — `main.py:77`
      `_format_status` stays a pure Rich wrapper (`[bold cyan]{message}...`)
      and is NOT modified, per design.
- [x] 3.2 RED: In `tests/integration/test_delegation_runtime.py`, update the
      expected supervisor status sequence (~lines 346-350) to the new
      templates, and DELETE the assertion for the removed
      `"Final iteration 2/2; no automatic retry remains"` line (do not
      re-spell it — the line no longer exists). Add/adjust an assertion
      that the worker's nested `_reasoning_loop(depth=1)` emits the
      identical `🔧 Running {name} ({k}/{m})` shape as a depth-0 supervisor
      turn, with no "worker"/"supervisor"/"delegate"/"delegation" substring
      anywhere in the emitted string (spec Requirement 3 / design
      Composition section). Run to confirm RED.
- [x] 3.3 GREEN: Fix any regressions surfacing from 3.2 — confirm the
      depth=1 worker path requires no code change beyond what Phases 1-2
      already did (helpers are depth-agnostic by construction; no depth
      branch is introduced). Run 3.2 to confirm GREEN.
- [x] 3.4 Full verification pass: run `pytest -xvs` across
      `tests/unit/test_agent_status.py`, `tests/unit/test_cli_chat.py`,
      `tests/unit/test_reasoning_outcome.py`,
      `tests/integration/test_delegation_runtime.py`, plus the full unit
      suite; run `ruff check .` and `mypy src/agentos`. Confirm:
      - `StatusCallback` signature (`Callable[[str], None]`) is unchanged
        everywhere (grep for its definition and call sites).
      - No worker/supervisor/delegation vocabulary appears in any status
        string emitted by either a depth-0 or depth=1 loop.
      - `main.py:77` `_format_status` is byte-for-byte unchanged from
        before this change (diff confirms zero lines touched in that
        function).
</content>
