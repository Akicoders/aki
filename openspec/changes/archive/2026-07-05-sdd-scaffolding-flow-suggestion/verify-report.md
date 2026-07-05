# Verify Report: sdd-scaffolding-flow-suggestion

## Verdict
1 CRITICAL, 2 WARNING, 1 SUGGESTION. No CRITICAL blocks spec compliance functionally, but one is a factual inaccuracy in claimed guarantees that should be corrected before archive.

## Test Suite
Ran `.venv/bin/python -m pytest -q` (full suite, repeatedly) from repo root:
- Run 1: 4 failed (`test_cli_chat.py::test_chat_command_shows_startup_status`, `test_chat_command_passes_selected_profile_and_prints_header`, `test_chat_command_rejects_unknown_profile_before_agent_execution`, `test_cli_project_resolution.py::test_chat_resolves_project_via_git_root`), 410 passed.
- Run 2 (`-x`, full suite): 414 passed, 0 failed.
- Run 3 (plain, full suite): 414 passed, 0 failed.
- Run 4 (plain, full suite): 414 passed, 0 failed.
- Isolated re-run of the 4 "failing" tests alone, and together: all pass.

Conclusion: the 4 failures are **flaky/order-dependent**, not deterministic regressions from this change — 3 of 4 runs matched the claimed 414/0. This matches the cross-reference note about a known pre-existing `test_cli_chat.py` flakiness/hang issue tracked under the separate `configurable-iteration-budget` change. WARNING (not CRITICAL) since it is reproducibly non-deterministic and not isolated to this change's new test files, but the claimed report ("414 passed, 0 failures, no regressions") understates real observed flakiness and should have disclosed it.

## Checklist Findings

1. **Guard order (disabled → keyword → checkpoint).** CONFIRMED. `_should_suggest_sdd_flow` (`src/agentos/agent/core.py:245-262`) checks `profile.memory.scope == "disabled"` first, then `_is_new_product_request`, then `read_checkpoint` last. `tests/unit/test_agent_should_suggest_sdd_flow.py::test_should_suggest_disabled_scope_suppresses_even_on_match` and `test_should_suggest_non_keyword_input_short_circuits` both assert `memory.read_checkpoint.assert_not_called()` — real call-count assertions, not tautological. PASS.

2. **Checkpoint-write regression test, both halves.** CONFIRMED, split across two tests in `tests/unit/test_agent_new_product_chat_wiring.py`:
   - `test_chat_first_turn_suggestion_writes_checkpoint` proves the checkpoint IS written on the suggestion turn (`memory.write_checkpoint_calls` length 1, keyed correctly).
   - `test_chat_second_turn_same_phrasing_proceeds_normally` proves a second turn with identical phrasing does NOT re-trigger (`qwen.calls == []` after turn 1, then `len(qwen.calls) == 1` after turn 2, i.e. loop actually ran).
   Both halves are real and independently verifiable. PASS.

3. **Worker exclusion, end-to-end.** CONFIRMED. `test_delegation_worker_never_triggers_new_product_suggestion` (`tests/unit/test_agent_new_product_suggestion_exclusions.py`) drives `_run_delegation` directly with a `task` matching `NEW_PRODUCT_KEYWORDS`, asserts the fake LLM was actually called (`len(qwen.calls) == 1`) and the worker's real response is returned unmodified — not a structural/code-path assertion. PASS.

4. **`stream_chat` coverage.** CONFIRMED BY READING CODE: `stream_chat` (`core.py:738-753`) calls `self.chat(...)` directly — a thin wrapper, no independent reasoning-loop duplication. It inherits the short-circuit for free. `test_stream_chat_first_turn_new_product_request_yields_suggestion` locks this in end-to-end (zero qwen calls, zero skill executions, suggestion text streamed). No gap requiring its own gate. PASS.

5. **Independence of `SCAFFOLDING_KEYWORDS` addendum and destructive gate.** CONFIRMED both structurally (neither `_build_messages`'s addendum block at `core.py:435-447` nor the destructive gate at `core.py:550-558` were touched by this change) and behaviorally via `test_chat_scaffolding_addendum_and_destructive_gate_unaffected`, which runs a real second turn after the suggestion fired on turn 1 and asserts both the addendum is injected and the destructive-gate clarifying question (`"?"` in response) still fires. PASS.

6. **`config.py` untouched by this change.** CONFIRMED. This change is uncommitted (no commits exist for it yet). The working-tree diff to `src/agentos/core/config.py` (1 line) is attributable to the separate, also-uncommitted `configurable-iteration-budget` change per the apply-progress note and matches the `max_iterations` field describer in that change's own artifacts — not touched by any code path in `_is_new_product_request` / `_build_new_product_suggestion` / `_should_suggest_sdd_flow` / the `chat()` wiring, all confined to `core.py`. PASS (with the caveat that verification relies on the cross-reference note rather than a dedicated commit boundary, since neither change has been committed yet).

7. **Keyword non-overlap — CRITICAL FINDING.** The design document (§4, "Design rationale — coarser than, and deliberately non-overlapping with, SCAFFOLDING_KEYWORDS") explicitly claims: *"No bare token from `SCAFFOLDING_KEYWORDS` is reused."* This claim is **false**. Programmatic substring cross-check of the actual constants in `core.py` found 7 concrete overlaps:
   - `"build a new project"` and `"start a new project"` (NEW_PRODUCT) both contain the literal SCAFFOLDING token `"new project"`.
   - `"create a whole new product"` contains SCAFFOLDING tokens `"create"` and `"crea"`.
   - `"set up the entire project"` contains SCAFFOLDING token `"set up"`.
   - `"armar toda la app"` contains SCAFFOLDING tokens `"armar"` and `"arma"`.

   Functional impact: the spec's own requirement is only that the two checks are *independent* (matching one need not imply matching the other) — it does not forbid double-matching, and since `_should_suggest_sdd_flow` short-circuits `chat()` before `_reasoning_loop` runs, a double-match on turn 1 does not cause any observable bug (the addendum branch inside `_build_messages` is simply never reached that turn, same as any short-circuited turn). So there is no runtime defect. However, the design's explicit non-overlap guarantee is a factual claim used to justify keeping the two keyword sets "deliberately non-overlapping," and it does not hold for the actual shipped constants. This should be corrected in the design record (or the constants tightened) before archive, since a future reader/reviewer will trust a false invariant.

## Additional Findings

- **WARNING — Phase 3.1 GREEN task in tasks.md** is fully matched by code (`core.py:316-322` matches design §5d verbatim, including `last_tool_summary=""` and `exhausted=False`).
- **SUGGESTION** — consider adding an explicit regression test asserting the exact overlap behavior (either "no overlap" with a corrected constant list, or an explicit test documenting that overlap is intentionally tolerated) so the invariant is enforced by CI rather than by design-doc prose alone.

## Spec Compliance Summary

| Spec Requirement | Status |
|---|---|
| New-Product Keyword Detection (distinct constant, scenario coverage) | Met, with the non-overlap sub-claim being inaccurate (§7 above) |
| First-Turn Detection via Checkpoint Absence | Met |
| Suggestion Suppressed When Memory Scope Disabled | Met |
| Zero-Tool-Call Short-Circuit on Trigger | Met |
| SDD-Status Enrichment via `detect_sdd_artifacts()` | Met |
| Independence from Scaffolding-Clarification Mechanisms | Met |
| No Worker/Delegation Vocabulary | Met (tests assert absence of "delegate"/"worker" in suggestion text; worker path never reaches short-circuit) |

## Tasks vs Code State
All 27 tasks in `tasks.md` are checked `[x]`. Cross-referencing test files confirms all claimed test names exist and pass individually and in the full suite (414/414 in 3 of 4 runs; see Test Suite section for the flaky exception). No incomplete or mismatched task markers found.
