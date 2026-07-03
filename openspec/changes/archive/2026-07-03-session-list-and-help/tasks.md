# Tasks: Session Listing & Contextual Interactive Help

Strict TDD mode active. For every implementation task: write the failing test
first (RED), confirm it fails for the right reason, then implement the
minimal change to pass (GREEN). Test command:

```
.venv/bin/python -m pytest -q
```

(`uv run pytest` intermittently resolves the wrong interpreter in this repo —
do not use it for verification.)

Delivery: **single PR, not stacked/chained.** All three surfaces are small,
additive, and land together (proposal-assessed low review-workload risk).
Do not split into multiple PRs.

---

## Phase 1 — Repository: `list_sessions` (foundation)

Spec coverage: "Session Listing Query".

### 1.1 `SessionSummary` dataclass + happy-path listing
- [x] **RED**: `test_list_sessions_orders_newest_first` — seed three
      `session:{id}:checkpoint` facts (via `write_checkpoint` or direct fact
      inserts) in the same `project:{name}` scope with different
      `updated_at` values, call `list_sessions(project)`, assert all three
      come back as `SessionSummary` instances ordered by `updated_at` desc.
- [x] **GREEN**: add `@dataclass SessionSummary(session_id, goal, updated_at,
      iterations_exhausted)` near the reserved-key constants (top of
      `repository.py`, ~line 34-38); implement
      `list_sessions(self, project: str, limit: int = 20) -> list[SessionSummary]`
      per design.md section 3 — `select(MemoryFactModel)` filtered by
      `scope == f"project:{project}"` and
      `key.like(RESERVED_FACT_KEY_PREFIX + "%:checkpoint")`, `order_by
      updated_at desc`, `limit`. Add `from dataclasses import dataclass` to
      imports if not already present.
- Depends on: none (reuses existing `MemoryFactModel`, `RESERVED_FACT_KEY_PREFIX`).
  Parallelizable: no (foundation for 1.2-1.4).

### 1.2 `session:last` pointer excluded from results
- [x] **RED**: `test_list_sessions_excludes_last_pointer` — seed a
      `session:last` fact (no `:checkpoint` suffix) plus one real
      `session:{id}:checkpoint` fact in the same scope; assert
      `list_sessions(project)` returns exactly one row (the checkpoint), the
      pointer is absent.
- [x] **GREEN**: covered for free by the `LIKE "session:%:checkpoint"`
      pattern in 1.1 — this task is a dedicated regression test proving the
      spec scenario "A session with no checkpoint is absent from the list";
      no additional production code expected. If the test fails, fix the
      `LIKE` pattern (not `session:last` special-casing).
- Depends on: 1.1. Parallelizable: no.

### 1.3 Corrupt-JSON row skip (local to `list_sessions` only)
- [x] **RED**: `test_list_sessions_skips_corrupt_row_logs_warning` — seed one
      `session:{id}:checkpoint` fact with a hand-crafted non-JSON (or
      `None`) `value` alongside 1-2 valid checkpoint facts; assert
      `list_sessions(project)` returns only the valid rows, no exception
      propagates, and a `WARNING` is logged (use `caplog` at `WARNING` level,
      assert the corrupt fact's `key` appears in the message).
- [x] **RED**: `test_read_checkpoint_still_raises_on_corrupt_row` — regression
      guard proving `read_checkpoint` is UNTOUCHED by this change: seed a
      corrupt `session:{id}:checkpoint` fact, call
      `read_checkpoint(project, session_id)` directly for that exact
      session_id, assert it still raises (does NOT silently return `None`).
- [x] **GREEN**: inline `try/except (json.JSONDecodeError, TypeError)` in the
      `list_sessions` loop only, per design.md ADR-1 —
      `logger.warning("Skipping corrupt checkpoint fact key=%s: %s",
      model.key, exc)` then `continue`. Do NOT touch `read_checkpoint` or
      extract a shared parse helper.
- Depends on: 1.1. Parallelizable: yes, with 1.2 (different scenarios, same
  method).

### 1.4 `updated_at` / `session_id` fallback + empty project
- [x] **RED**: `test_list_sessions_updated_at_falls_back_to_column` — seed a
      checkpoint fact whose JSON payload has no (or unparseable)
      `updated_at`; assert the returned `SessionSummary.updated_at` equals
      the fact row's own `updated_at` column value.
- [x] **RED**: `test_list_sessions_empty_project_returns_empty_list` — no
      checkpoint facts for the project at all; assert `list_sessions`
      returns `[]`, not an error.
- [x] **GREEN**: implement the `_parse_updated_at(iso_or_none, fallback_dt)`
      module helper (try `datetime.fromisoformat`, fall back on failure) and
      the `session_id` key-derived fallback, per design.md section 3.
- Depends on: 1.1, 1.3. Parallelizable: no.

**Phase 1 exit criteria:** `MemoryRepository.list_sessions(project, limit=20)`
returns typed `SessionSummary` list, newest-first, tolerant of corrupt rows
and missing fields; `read_checkpoint` behavior is provably unchanged; all new
tests green.

---

## Phase 2 — Interactive `/sessions` command

Spec coverage: "Interactive `/sessions` Command".

### 2.1 `AgentOS.memory` accessor confirmation
- [x] Confirm (via existing code, no new test needed —
      `self.memory.write_checkpoint` already proves `AgentOS.memory` is the
      `MemoryRepository`) that `agent.memory.list_sessions(project)` resolves
      from the CLI's `agent` handle. If it does not resolve as expected, add
      a thin `AgentOS.list_sessions(project)` pass-through mirroring
      `get_facts` (design.md section 4, option B) and note the deviation in
      the PR description.
- Depends on: Phase 1. Parallelizable: no (blocks 2.2).

### 2.2 `_show_sessions` renderer with empty state
- [x] **RED**: `test_show_sessions_empty_state_prints_dim_message` — mock
      `agent.memory.list_sessions` to return `[]`, call `_show_sessions(agent,
      project)`, assert the dim "no sessions" message is printed (capture via
      the same console-capture pattern used for `_show_facts` tests) and no
      table is rendered.
- [x] **RED**: `test_show_sessions_renders_table_newest_first` — mock
      `list_sessions` to return 2+ `SessionSummary` rows; assert a `Table`
      with columns Session/Goal/Updated is printed, one row per session, in
      the order returned (list_sessions already guarantees newest-first, so
      renderer must not re-sort).
- [x] **RED**: `test_show_sessions_blank_goal_falls_back_to_session_id` — a
      `SessionSummary` with `goal=""`; assert the rendered row's goal column
      shows `"(no goal) {session_id}"`.
- [x] **GREEN**: implement `async def _show_sessions(agent, project)` in
      `main.py` per design.md section 4 — mirrors `_show_facts`: empty-state
      dim print, else `Table(title=f"Sessions: {project}")` with
      Session/Goal/Updated columns, `goal.strip()[:60]` truncation with
      no-goal fallback, `updated_at.strftime("%Y-%m-%d %H:%M")`.
- Depends on: 2.1. Parallelizable: no.

### 2.3 Wire `/sessions` into `_handle_command`
- [x] **RED**: `test_handle_command_sessions_dispatches_to_show_sessions` —
      patch `_show_sessions`, call `_handle_command("/sessions", agent,
      project, session_id)` (or however the existing `/facts` dispatch test
      is shaped — mirror it exactly), assert `_show_sessions` was awaited
      with `(agent, project)`.
- [x] **RED**: existing `/facts`, `/skills`, `/sdd`, `/clear` dispatch tests
      still pass unmodified (regression check — no existing branch altered).
- [x] **GREEN**: add `elif cmd == "/sessions": await _show_sessions(agent,
      project)` in `_handle_command`, adjacent to the `/facts`/`/skills`
      branches, per design.md section 4.
- Depends on: 2.2. Parallelizable: no.

**Phase 2 exit criteria:** `/sessions` in interactive mode lists sessions
newest-first with goal/session_id/updated_at columns; empty state matches
`_show_facts` styling; dispatch is a pure additive `elif`; all new tests
green; existing command-dispatch tests unaffected.

---

## Phase 3 — Contextual `_show_help`

Spec coverage: "Contextual Interactive Help".

### 3.1 `_show_help` signature change + resumed/new state line
- [x] **RED**: `test_show_help_resumed_session_shows_last_goal` — mock
      `agent.memory.read_checkpoint(project, session_id)` to return a dict
      with `goal="refactor auth"`; call `_show_help(agent, project,
      session_id)`; assert the printed panel contains "Resuming" (or
      equivalent per design copy), the `session_id`, and "refactor auth".
- [x] **RED**: `test_show_help_new_session_no_checkpoint` — mock
      `read_checkpoint` to return `None`; assert the panel states "New
      session" / "no history yet" and does NOT raise or print a stale goal.
- [x] **RED**: `test_show_help_read_checkpoint_raising_falls_back_to_new` —
      mock `read_checkpoint` to raise (simulating a corrupt single-session
      read per design.md ADR-1/section 5); assert `_show_help` catches it
      locally and renders the "new session" state instead of propagating the
      exception.
- [x] **GREEN**: change `_show_help()` signature to `_show_help(agent,
      project, session_id)` per design.md section 5; call
      `agent.memory.read_checkpoint(project, session_id)` wrapped in a local
      `try/except Exception` that falls back to `checkpoint = None`; branch
      on `checkpoint and checkpoint.get("goal")` for the resumed-vs-new state
      line.
- Depends on: none (independent of Phase 1/2 repository work — only needs
  `read_checkpoint`, which already exists from `session-persistence`).
  Parallelizable: yes, with Phase 1/2.

### 3.2 Command list gains `/sessions`; existing list preserved
- [x] **RED**: `test_show_help_lists_all_commands_including_sessions` — call
      `_show_help(agent, project, session_id)` with any checkpoint state;
      assert the panel content includes all prior command entries (`/help`,
      `/memory`, `/facts`, `/skills`, `/sdd`, `/clear`, `exit`/`quit`) AND the
      new `/sessions` entry.
- [x] **GREEN**: add the `/sessions` line to the static command list in the
      `Panel` body per design.md section 5; do not remove or reorder existing
      entries.
- Depends on: 3.1. Parallelizable: no.

### 3.3 Update the single call site (`main.py:759`)
- [x] **RED**: `test_interactive_help_command_passes_agent_project_session` —
      drive the interactive loop's `/help` dispatch (or the narrowest test
      that exercises the call site — mirror however `main.py:759`'s
      surrounding flow is currently tested), patch `_show_help`, assert it is
      called with `(agent, project, session_id)`.
- [x] **GREEN**: update the call site at `main.py:759` from `_show_help()` to
      `_show_help(agent, project, session_id)` — confirmed single caller via
      design.md's `rg "_show_help" src/` check; no other call site exists.
- Depends on: 3.1, 3.2. Parallelizable: no.

**Phase 3 exit criteria:** `/help` reports resumed/new state + last goal
alongside the full (now `/sessions`-inclusive) command list; corrupt
single-session reads degrade to "new session" rather than crashing help; the
one call site is updated and no other caller breaks; all new tests green.

---

## Cross-Phase Verification

### 4.1 Full suite regression pass
- [x] Run `.venv/bin/python -m pytest -q` after all three phases land in the
      same PR; confirm no regressions in existing `test_cli_project_resolution.py`,
      `/facts`/`/skills` dispatch tests, or the archived `session-persistence`
      checkpoint tests (`read_checkpoint`/`write_checkpoint` untouched).
- Depends on: 1.4, 2.3, 3.3. Parallelizable: no (final gate before PR).

### 4.2 No-schema-change / no-migration confirmation
- [x] Grep the diff for any `alembic`/migration file additions or
      `MemoryFactModel` schema edits; confirm none exist — this change is
      read-only against the existing schema per proposal scope.
- Depends on: 4.1. Parallelizable: no.

---

## Review Workload Forecast

- **Chained PRs recommended:** No. All three surfaces (`list_sessions`,
  `/sessions` command, contextual `_show_help`) are small, additive, and
  independent enough in review terms to land as one PR — matches the
  proposal's explicit "SMALL — single PR, not stacked" delivery call and the
  design's confirmation of a single `_show_help` call site.
- **400-line budget risk:** Low.
  - `memory/repository.py`: +1 dataclass, +1 method (~40-50 lines) plus
    tests (~80-100 lines) — estimated 120-150 changed lines.
  - `cli/main.py`: +1 renderer function (~15 lines), +1 dispatch `elif` (2
    lines), `_show_help` signature/body change (~15 lines changed) plus tests
    (~100-120 lines) — estimated 150-180 changed lines.
  - **Total estimated: ~270-330 changed lines including tests** — comfortably
    under the 400-line budget.
- **Decision needed before apply:** No. Delivery strategy and phase order are
  already fixed by the proposal and this tasks breakdown; `sdd-apply` should
  proceed directly with Phase 1, gated by the strict-TDD RED-GREEN pattern
  per task above, and land all three phases in one PR.
