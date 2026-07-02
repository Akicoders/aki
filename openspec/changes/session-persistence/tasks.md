# Tasks: Session Persistence & Context Rehydration

Strict TDD mode active. For every implementation task: write the failing test
first (RED), confirm it fails for the right reason, then implement the
minimal change to pass (GREEN). Test command:

```
.venv/bin/python -m pytest -q
```

(`uv run pytest` intermittently resolves the wrong interpreter in this repo —
do not use it for verification.)

Delivery: 3 stacked PRs on `stacked-to-main`, one per phase below. Each PR
merges to main before the next starts. Phase boundaries are hard checkpoints
— do not begin Phase 2 tasks in the same PR as Phase 1.

---

## Phase 1 — Auto-Resume Session ID (PR #1)

Spec coverage: "Durable Last-Session Pointer", "Auto-Resume Session on `aki
chat`", "Auto-Resume Session on `aki interactive`", "Explicit New-Session
Escape Hatch".

### 1.1 Repository: reserved-fact upsert helper (foundation for all phases)
- [x] **RED**: `test_upsert_reserved_fact_updates_in_place` — write the same
      `(key, scope)` twice via the new helper → repository query returns
      exactly ONE row, `value` reflects the second write. This is the
      dedicated test for the `upsert_fact` keys-on-`id` gotcha (see "Critical
      Gotcha" section below).
- [x] **GREEN**: implement `MemoryRepository._upsert_reserved_fact(key, scope,
      value)` — reads existing fact via `get_fact(key, scope)` first, reuses
      `existing.id` when present, calls `upsert_fact`.
- Depends on: none. Blocks: 1.2, 1.3, 2.1, 2.2 (all reserved-fact writes route
  through this helper).
- Parallelizable: no (foundation, must land first within Phase 1).

### 1.2 Repository: last-session read/write helpers
- [x] **RED**: `test_get_last_session_absent_returns_none`.
- [x] **RED**: `test_touch_last_session_upserts_pointer` — call twice with
      different session ids for the same project → `get_last_session` returns
      the latest, and only one `session:last` row exists (reuse pattern from
      1.1's gotcha test, applied to this concrete helper).
- [x] **GREEN**: implement `MemoryRepository.touch_last_session(project,
      session_id)` and `get_last_session(project)`, both via
      `_upsert_reserved_fact` / `get_fact` with `LAST_SESSION_KEY =
      "session:last"` and scope `project:{project}`.
- Depends on: 1.1. Parallelizable: no.

### 1.3 CLI: pure `_resolve_session_id` helper
- [x] **RED**: unit tests (no CliRunner) for `_resolve_session_id(project,
      session, new_session)`:
      - explicit `session` wins regardless of `new_session` or stored fact
      - `new_session=True` + stored last → mints fresh `sess_`-prefixed id,
        ignores stored value
      - no `session`, `new_session=False`, stored last present → returns
        stored value
      - no `session`, `new_session=False`, no stored fact → mints fresh
        `sess_`-prefixed id
- [x] **GREEN**: implement `_resolve_session_id` as a pure function in
      `cli/main.py` (or a small helper module), taking a memory accessor
      (repository/`get_last_session`) as a parameter so it is testable without
      constructing a full `AgentOS`.
- Depends on: 1.2 (needs `get_last_session` to call in the "stored fact"
  branch — can be stubbed/mocked in tests so this may run in parallel with
  1.2's GREEN, but must integrate before 1.4).
- Parallelizable: yes, with 1.2, once the shape of `get_last_session` is
  agreed (signature is already fixed by design doc section 5).

### 1.4 CLI: wire `--new-session` flag + auto-resume into `chat` and `interactive`
- [x] **RED**: `test_chat_explicit_session_wins`, `test_chat_resumes_last_session_fact`,
      `test_chat_new_session_ignores_last_fact`, `test_chat_no_fact_mints_random`,
      `test_chat_session_and_new_session_prefers_explicit` (CliRunner +
      `patch("agentos.cli.main._get_agent", return_value=AsyncMock())`,
      inspect `agent.chat.call_args`, mirroring
      `tests/unit/test_cli_project_resolution.py`).
- [x] **RED**: mirror the resume/new-session/no-fact cases for `interactive`
      (prefer asserting via the extracted `_resolve_session_id` call site if
      full CliRunner interactive flow is awkward to drive).
- [x] **GREEN**: add `--new-session` (`typer.Option(False, "--new-session")`)
      to both `chat` and `interactive`; call `_resolve_session_id` at each
      command's entry to compute `session_id` before invoking the agent.
- Depends on: 1.3. Parallelizable: no.

### 1.5 Verify `session:last` write authority end-to-end (deferred integration note)
- [x] Confirm (via existing Tier C groundwork, not new tests yet — full
      coverage lands in Phase 2 since the write site is `AgentOS.chat()`)
      that CLI does NOT itself write `session:last` — only reads. Add a code
      comment at the CLI resolution site noting the write happens in
      `AgentOS.chat()` (Phase 2), so Phase 1 ships read-only resolution with
      the flag/escape-hatch behavior fully correct even before the write path
      exists.
- Depends on: 1.4. Parallelizable: no (documentation/consistency check, quick).

**Phase 1 exit criteria:** `aki chat`/`aki interactive` resolve session_id per
the 4-step order in design.md section 5; `--new-session` and `--session`
flags behave per spec; all new tests green; no regressions in
`test_cli_project_resolution.py`.

---

## Phase 2 — Checkpoint Write (PR #2)

Spec coverage: "Structured Checkpoint Write". Depends on Phase 1 merged
(reuses `_upsert_reserved_fact`, and Phase 1's CLI resolution feeds
`session_id` into `chat()`).

### 2.1 Repository: `write_checkpoint` / `read_checkpoint` core
- [ ] **RED**: `test_write_then_read_checkpoint_roundtrip` — write with all
      fields, read back, assert `goal`, `open_items`, `last_tool_result`,
      `last_response`, `iterations_exhausted` match.
- [ ] **RED**: `test_write_checkpoint_caps_long_fields` — oversize `goal`
      (> `CHECKPOINT_FIELD_CHAR_CAP`) truncated deterministically before
      serialize.
- [ ] **RED**: `test_read_checkpoint_missing_returns_none`.
- [ ] **RED**: `test_read_checkpoint_tolerates_missing_version` — hand-craft a
      JSON blob without `"v"` key, assert `read_checkpoint` does not raise and
      returns a usable dict.
- [ ] **GREEN**: implement `MemoryRepository.write_checkpoint(project,
      session_id, *, goal, last_response, last_tool_result,
      iterations_exhausted)` — caps each free-text field to
      `CHECKPOINT_FIELD_CHAR_CAP`, serializes the JSON shape from design.md
      section 3, calls `_upsert_reserved_fact` with key
      `session:{session_id}:checkpoint`, scope `project:{project}`.
      Implement `read_checkpoint(project, session_id)` — `get_fact` +
      `json.loads` tolerant of missing/legacy `v`.
- Depends on: 1.1 (reuses `_upsert_reserved_fact`). Parallelizable: no.

### 2.2 Repository: checkpoint write also touches `session:last` — no duplicate rows
- [ ] **RED**: `test_write_checkpoint_touches_last_session` — after
      `write_checkpoint`, `get_last_session` returns the same `session_id`.
- [ ] **RED**: `test_write_checkpoint_no_duplicate_rows_across_multiple_writes`
      — call `write_checkpoint` 3+ times for the SAME `session_id` (varying
      `goal`/fields each time) → assert exactly ONE `session:{id}:checkpoint`
      row exists in the backing store (query facts by scope/key prefix
      directly) AND exactly ONE `session:last` row exists. This is the
      dedicated regression test named in the task brief, guarding the
      `upsert_fact`-keys-on-`id` gotcha at the checkpoint-write level (not
      just the generic helper level in 1.1).
- [ ] **GREEN**: have `write_checkpoint` call `touch_last_session` internally
      after the reserved-fact upsert succeeds.
- Depends on: 2.1, 1.2. Parallelizable: no.

### 2.3 `_reasoning_loop` return shape: carry last-tool-summary + exhausted flag
- [ ] **RED**: unit test on `_reasoning_loop` (or its extracted outcome type)
      asserting a natural completion returns `exhausted=False` and a
      non-empty `last_tool_summary` when a tool was called during the loop.
- [ ] **RED**: unit test asserting the `max_iterations`-exhaustion branch
      returns `exhausted=True` with the best-known `last_tool_summary` at cutoff.
- [ ] **GREEN**: introduce `ReasoningOutcome` (dataclass or small namedtuple:
      `response`, `last_tool_summary`, `exhausted`) as `_reasoning_loop`'s
      return type; update the natural-return branch (~line 197) and the
      exhaustion branch (~line 241) to populate it. Verify `stream_chat` (which
      calls `chat`, not `_reasoning_loop` directly per design assumption in
      section 10) is unaffected — add a regression check/assertion if
      `stream_chat` has existing tests, or note explicitly in the PR that this
      was verified manually if no such test exists.
- Depends on: none within Phase 2, but must land before 2.4. Parallelizable:
  yes, with 2.1/2.2 (different code area — repository vs. agent/core.py).

### 2.4 `AgentOS.chat()`: single checkpoint write site (every turn + on exhaustion)
- [ ] **RED**: `test_chat_writes_checkpoint_each_turn` — fake qwen + fake/spy
      memory, run `chat()` once, assert `write_checkpoint` called exactly once
      with the turn's `goal`/`last_response`/`last_tool_result`/
      `iterations_exhausted=False`.
- [ ] **RED**: extend/parametrize the same test (or add a sibling) for the
      exhaustion path — force `_reasoning_loop` (or its stub) to return
      `exhausted=True`, assert `write_checkpoint` is still called exactly once
      with `iterations_exhausted=True`. This is the "single write site covers
      both paths" requirement from design.md section 4a — must NOT be two
      separate write call sites.
- [ ] **GREEN**: in `chat()`, immediately after the assistant event is stored
      (design.md ~line 99 area), add the single `self.memory.write_checkpoint(...)`
      call using the `ReasoningOutcome` from 2.3.
- Depends on: 2.1, 2.2, 2.3. Parallelizable: no.

**Phase 2 exit criteria:** every `AgentOS.chat()` turn (success or
iteration-exhaustion) upserts exactly one checkpoint row and one
`session:last` row; no duplicate rows across repeated turns on the same
session (regression-tested); all new tests green.

---

## Phase 3 — Checkpoint Rehydration Read (PR #3)

Spec coverage: "Guaranteed Checkpoint Rehydration". Depends on Phase 2 merged
(needs `read_checkpoint` and populated checkpoint data to rehydrate).

### 3.1 `render_checkpoint` deterministic bounded formatter
- [ ] **RED**: `test_render_checkpoint_respects_char_cap` — feed a checkpoint
      dict whose serialized rendering would exceed
      `CHECKPOINT_REHYDRATION_CHAR_CAP`, assert output length <= cap and
      truncation is deterministic (same input → same truncated output).
- [ ] **RED**: `test_render_checkpoint_handles_empty_open_items` — no
      open_items → renders without error, no stray formatting artifacts.
- [ ] **GREEN**: implement `render_checkpoint(checkpoint: dict, cap: int) -> str`
      as a plain function (module-level, no class state), producing a
      human/model-readable summary of `goal`, `open_items`,
      `last_tool_result`, hard-capped to `cap` chars.
- Depends on: none (pure function, can start anytime, but logically Phase 3).
  Parallelizable: yes, can start in parallel with 3.2's RED tests.

### 3.2 `_build_messages`: thread `session_id`, inject reserved checkpoint slot
- [ ] **RED**: `test_build_messages_injects_checkpoint_slot` — mock
      `read_checkpoint` to return a populated dict, call `_build_messages`
      with a `session_id`, assert the returned messages contain a system
      message with the rendered checkpoint content, positioned before the
      memory-context message, and that this content is NOT passed through
      `format_for_prompt` / `_fit_context_to_budget` (assert by checking the
      call sequence/mocked budget-fit function was not invoked on this
      content, or by asserting presence even when budget-fit is mocked to
      drop everything).
- [ ] **RED**: `test_build_messages_no_checkpoint_omits_slot` — mock
      `read_checkpoint` to return `None`, assert no extra system message is
      added and no error is raised.
- [ ] **RED**: `test_build_messages_checkpoint_survives_budget_truncation` —
      construct a scenario where `assemble_context`'s facts/events are large
      enough that budget-fit truncation would drop them, assert the
      checkpoint slot content is still present in full (up to its own cap)
      in the final message list. This directly covers the "Checkpoint
      survives budget-fit truncation" spec scenario.
- [ ] **GREEN**: add `session_id` parameter to `_build_messages` (threaded
      from `chat()`'s existing call site, design.md ~line 88); after the base
      system prompt and BEFORE the memory-context message, call
      `self.memory.read_checkpoint(project, session_id)` and, if present,
      append a system message built via `render_checkpoint(checkpoint,
      cap=CHECKPOINT_REHYDRATION_CHAR_CAP)`.
- Depends on: 3.1, Phase 2 (2.4, for `read_checkpoint` to return real data in
  integration). Parallelizable: no (core wiring task).

### 3.3 Reserved-key facts must not leak into `assemble_context` fallback path
- [ ] **RED**: `test_assemble_context_excludes_reserved_session_facts` — seed
      the repository with both a `session:last` fact and a
      `session:{id}:checkpoint` fact plus at least one normal fact, in the
      SAME `project:{name}` scope; call `assemble_context`'s
      `get_facts_by_scope` fallback path (the branch exercised when
      `search_facts` falls back to scope listing); assert the reserved-prefix
      facts (`RESERVED_FACT_KEY_PREFIX = "session:"`) are filtered out and
      only the normal fact(s) surface.
- [ ] **GREEN**: add an additive filter in the `get_facts_by_scope` fallback
      call site inside `assemble_context` (per design.md section 3 and
      "Risk" callout in section 10) — exclude any fact whose `key` starts
      with `RESERVED_FACT_KEY_PREFIX`. No change to ranking/relevance logic
      for non-reserved facts.
- Depends on: none technically (only needs `RESERVED_FACT_KEY_PREFIX`
  constant from Phase 1/2), but sequenced in Phase 3 since it guards the
  rehydration risk this phase introduces end-to-end. Parallelizable: yes,
  with 3.1/3.2 — different code path (`assemble_context` vs.
  `_build_messages`).

### 3.4 Deferred-config constants consolidation check
- [ ] Confirm `CHECKPOINT_FIELD_CHAR_CAP`, `CHECKPOINT_REHYDRATION_CHAR_CAP`,
      `RESERVED_FACT_KEY_PREFIX`, `LAST_SESSION_KEY` (memory side) and
      `CHECKPOINT_CADENCE_TURNS` (agent/core.py side) all exist as named
      module constants with a `# deferred config` comment marker (per
      design.md section 6), not inline literals, across all three phases'
      changes. Grep for stray literals (e.g. hardcoded `1000`, `2000`,
      `"session:"`) introduced during Phases 1–3 and replace with the named
      constants if any slipped through.
- Depends on: 3.1, 3.2, 3.3 (all code that could introduce literals). Parallelizable: no (final sweep).

**Phase 3 exit criteria:** checkpoint appears in every subsequent turn's
messages regardless of textual relevance to the new user message; survives
budget-fit truncation; absent-checkpoint case is a no-op; reserved facts never
leak into the generic memory-context fallback; all new tests green; full
suite (`.venv/bin/python -m pytest -q`) green.

---

## Critical Gotcha — explicit standalone task (cross-referenced above)

This is called out again here as a standing checklist item because it is the
single highest-risk mechanical bug in this change:

> `MemoryRepository.upsert_fact` keys on `fact.id` (primary key), NOT
> `(key, scope)`. A naive "construct a fresh `MemoryFact(...)` and call
> `upsert_fact`" on every write will INSERT a new row every time instead of
> updating in place, silently accumulating duplicate `session:last` and
> `session:{id}:checkpoint` rows.

- [ ] Task 1.1's `_upsert_reserved_fact` helper is the ONLY code path allowed
      to write `session:last` or `session:{id}:checkpoint` facts — no other
      call site should construct a raw `MemoryFact` for these reserved keys
      and call `upsert_fact` directly. Verify this via code review at PR #2
      and PR #3 time (both `write_checkpoint` and `touch_last_session` must
      route through `_upsert_reserved_fact`).
- [ ] Regression test `test_write_checkpoint_no_duplicate_rows_across_multiple_writes`
      (task 2.2) is the concrete proof this gotcha is closed for the
      checkpoint path; `test_touch_last_session_upserts_pointer` (task 1.2)
      is the proof for the last-session pointer path.

---

## Review Workload Forecast

- **Chained PRs recommended:** Yes — matches the proposal's 3-phase plan
  exactly (auto-resume → checkpoint write → checkpoint read/rehydration).
  Chain strategy: `stacked-to-main` (each PR merges to main in order before
  the next starts).
- **400-line budget risk:** Low-Medium per PR.
  - PR #1 (auto-resume): touches `cli/main.py` (+flag, +resolution helper)
    and `memory/repository.py` (+2 small helpers) plus tests — estimated
    150–250 changed lines including tests. Low risk.
  - PR #2 (checkpoint write): touches `memory/repository.py`
    (`write_checkpoint`/`read_checkpoint`/caps), `agent/core.py`
    (`ReasoningOutcome` refactor + single write call site) plus tests —
    estimated 250–350 changed lines including tests. Medium risk, mainly from
    the `_reasoning_loop` return-shape refactor touching two branches.
  - PR #3 (checkpoint read): touches `agent/core.py` (`_build_messages`
    signature + injection), a new `render_checkpoint` formatter, and the
    `assemble_context` fallback filter, plus tests — estimated 200–300
    changed lines including tests. Low-Medium risk.
  - None individually likely to exceed the 400-line budget given the design
    is additive (no broad rewrites), but PR #2's `_reasoning_loop` return-type
    change touches existing control flow and deserves careful review.
- **Decision needed before apply:** No — chain strategy and phase boundaries
  are already fixed by the proposal and this tasks breakdown. `sdd-apply`
  should proceed directly with PR #1, gated by the strict-TDD RED-GREEN
  pattern per task above.
