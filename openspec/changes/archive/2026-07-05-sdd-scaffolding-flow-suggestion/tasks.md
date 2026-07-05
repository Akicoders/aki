# Tasks: SDD Scaffolding Flow Suggestion

Strict TDD mode active. For every implementation task: write the failing test
first (RED), confirm it fails for the right reason, then implement the
minimal change to pass (GREEN). Test command:

```
.venv/bin/python -m pytest -q
```

(`uv run pytest` intermittently resolves the wrong interpreter in this repo —
do not use it for verification.)

Delivery: single PR, additive change confined to `src/agentos/agent/core.py`
(reusing `detect_sdd_artifacts()` from `src/agentos/sdd/detector.py`
read-only). Design confirms no layer needs its own PR (see Review Workload
Forecast). `config.py` is OFF-LIMITS — do not read or modify it; the new
`NEW_PRODUCT_KEYWORDS` constant lands as a module constant next to
`SCAFFOLDING_KEYWORDS` (`core.py:35`), same convention as the archived
`agent-scaffolding-clarification` change (this change's "bigger sibling").

Confirmed against real code before writing this file:
- `SCAFFOLDING_KEYWORDS` at `core.py:35`, `ReasoningOutcome` at `core.py:50`.
- `chat()` at `core.py:198`; existing `_reasoning_loop` call at `core.py:250`.
- `_reasoning_loop` at `core.py:380`; `_run_delegation` at `core.py:530`,
  which calls `_reasoning_loop` directly at `core.py:572` (`depth=1`), never
  through `chat()`.
- `stream_chat` (`core.py:664`) calls `self.chat(...)` directly at
  `core.py:673` — it is a thin wrapper, so it naturally routes through the
  `chat()` short-circuit with zero additional integration code. Only a test
  is needed to lock this in, per design §11.

---

## Phase 1 — Pure Helpers (`NEW_PRODUCT_KEYWORDS`, `_is_new_product_request`, `_build_new_product_suggestion`)

Spec coverage: "New-Product Keyword Detection", "SDD-Status Enrichment via
`detect_sdd_artifacts()`". Fully independent of Phase 2 — pure functions,
zero I/O, zero `self`. Foundation for Phase 2's eligibility method and
Phase 3's call-site wiring.

### 1.1 `NEW_PRODUCT_KEYWORDS` constant
- [x] **GREEN** (no test needed — plain data): add the bilingual tuple to
      `src/agentos/agent/core.py`, immediately after `SCAFFOLDING_KEYWORDS`
      (`core.py:44` per design), with a `# deferred config` comment marker
      matching house convention. Content per design §4 — long multi-word
      phrases only (e.g. `"necesitamos ya poder tener"`, `"armar toda la
      app"`, `"todo el proyecto"`, `"build me a new app"`, `"from scratch"`,
      `"the entire project"`). MUST NOT reuse any bare token already present
      in `SCAFFOLDING_KEYWORDS` (e.g. no bare `"crear"`, `"armar"`, `"nuevo
      proyecto"`).
- Depends on: none. Blocks: 1.2, 1.3.

### 1.2 `_is_new_product_request(message: str) -> bool` — table-driven
- [x] **RED**: `test_is_new_product_request_canonical_failure_case` —
      `"necesitamos ya poder tener el astro hecho"` → `True`.
- [x] **RED**: `test_is_new_product_request_bilingual_variants` —
      parametrized over `"armar toda la app"`, `"build me a new app"`,
      `"todo el proyecto desde cero"`, `"set up the entire project"`, plus
      mixed-case variants (`"ARMAR TODA LA APP"`) → all `True`.
- [x] **RED**: `test_is_new_product_request_scaffolding_phrase_not_matched`
      (spec scenario "Narrow scaffolding phrase does not trigger the
      new-product path") — `"creá un componente nuevo"` → `False`.
- [x] **RED**: `test_is_new_product_request_unrelated_message_not_matched` —
      `"leé el archivo config.py"` → `False`.
- [x] **GREEN**: implement `_is_new_product_request(message: str) -> bool`
      as a module-level function in `src/agentos/agent/core.py`: lowercase
      substring match against `NEW_PRODUCT_KEYWORDS`, mirroring the
      structure of the existing `SCAFFOLDING_KEYWORDS` check
      (`core.py:361`).
- Depends on: 1.1. Parallelizable: yes, with Phase 2's scaffolding.

### 1.3 `_build_new_product_suggestion(has_sdd: bool) -> str` — both branches
- [x] **RED**: `test_build_new_product_suggestion_has_sdd_mentions_continue`
      — `has_sdd=True` → returned text mentions continuing/resuming the
      existing SDD workflow and does NOT mention `sdd-init`.
- [x] **RED**: `test_build_new_product_suggestion_no_sdd_mentions_bootstrap`
      — `has_sdd=False` → returned text mentions `sdd-init` as the way to
      start.
- [x] **RED**: `test_build_new_product_suggestion_no_worker_vocabulary`
      (spec "No Worker/Delegation Vocabulary") — for both `has_sdd` values,
      assert the returned text does NOT contain `"delegate"` or `"worker"`
      (case-insensitive substring check).
- [x] **RED**: `test_build_new_product_suggestion_is_advisory` — for both
      branches, assert the text indicates the suggestion is optional (e.g.
      contains phrasing equivalent to "if you'd rather I just do it,
      say so next turn") — locks in the "does NOT force SDD" success
      criterion at the message level.
- [x] **GREEN**: implement `_build_new_product_suggestion(has_sdd: bool) ->
      str` as a module-level function in `src/agentos/agent/core.py` per
      design §6 (Spanish strings, matching `_format_exhaustion_message`
      convention).
- Depends on: none (independent of 1.1/1.2). Parallelizable: yes.

**Phase 1 exit criteria:** `NEW_PRODUCT_KEYWORDS` exists as a named module
constant, non-overlapping with `SCAFFOLDING_KEYWORDS`; `_is_new_product_request`
and `_build_new_product_suggestion` are pure, fully table-tested, including
the anti-false-positive guarantee against scaffolding phrasing and the
no-worker-vocabulary guarantee; all new tests green.

---

## Phase 2 — Eligibility Method (`_should_suggest_sdd_flow`)

Spec coverage: "First-Turn Detection via Checkpoint Absence", "Suggestion
Suppressed When Memory Scope Is Disabled". Depends on Phase 1's
`_is_new_product_request` (calls it internally) and needs `self.memory`, so
it is a method on `AgentOS`, not a pure function.

### 2.1 `_should_suggest_sdd_flow` — guard-ordered, spy `read_checkpoint`
- [x] **RED**: `test_should_suggest_disabled_scope_suppresses_even_on_match`
      (spec "Memory scope disabled suppresses the suggestion...") — fake
      `profile.memory.scope == "disabled"`, exact `NEW_PRODUCT_KEYWORDS`
      match, spy `self.memory.read_checkpoint` → returns `False`, AND assert
      `read_checkpoint` was NEVER called (guard-ordering: cheapest/most-
      suppressive check first, per design §5c rationale).
- [x] **RED**: `test_should_suggest_non_keyword_input_short_circuits` —
      enabled scope, non-matching input → returns `False`, AND assert
      `read_checkpoint` was NEVER called (keyword check before DB read).
- [x] **RED**: `test_should_suggest_first_turn_matches_and_no_checkpoint` —
      enabled scope, matching input, spy `read_checkpoint` returns `None` →
      returns `True`.
- [x] **RED**: `test_should_suggest_later_turn_checkpoint_present` (spec "A
      checkpoint already exists — this is not the first turn") — enabled
      scope, matching input, spy `read_checkpoint` returns a non-`None`
      dict → returns `False`.
- [x] **RED**: `test_should_suggest_none_profile_treated_as_enabled` — the
      method is called with `profile=None` (a valid `chat()` call shape);
      matching input, no checkpoint → returns `True` (confirms the `if
      profile is not None and profile.memory.scope == "disabled"` guard
      does not crash or wrongly suppress on a missing profile).
- [x] **GREEN**: implement `_should_suggest_sdd_flow(self, user_input: str,
      profile: Optional[AgentProfile], project: str, session_id: str) ->
      bool` on `AgentOS` in `src/agentos/agent/core.py`, exactly per design
      §5c: disabled-scope check first, then `_is_new_product_request`, then
      `self.memory.read_checkpoint(project, session_id) is None` last.
- Depends on: 1.2. Parallelizable: no (needs Phase 1's helper to exist,
  even as a stub, to write against).

**Phase 2 exit criteria:** `_should_suggest_sdd_flow` covered by all 5
scenarios above including the two guard-ordering assertions (DB read only
reached when both earlier gates pass); all new tests green.

---

## Phase 3 — Call-Site Wiring in `chat()`

Spec coverage: "Zero-Tool-Call Short-Circuit on Trigger", "Independence from
Existing Scaffolding-Clarification Mechanisms". Depends on Phase 1 (message
builder) and Phase 2 (eligibility method). This is the REGRESSION-CRITICAL
phase: the checkpoint write for steps 6/6b MUST still run on the suggestion
turn, or the suggestion re-fires forever.

### 3.1 First-turn short-circuit fires, zero tool calls, checkpoint written
- [x] **RED**: `test_chat_first_turn_new_product_request_zero_tool_calls` —
      fake `QwenClient`/session with no existing checkpoint, `user_input`
      matching `NEW_PRODUCT_KEYWORDS`, enabled memory scope; spy
      `self._reasoning_loop` (must NOT be awaited) and `self.skills.execute`
      (must NEVER be called); assert the returned response text is the
      suggestion (`_build_new_product_suggestion` output) and reflects
      `detect_sdd_artifacts()` state for the target project.
- [x] **RED**: `test_chat_first_turn_suggestion_writes_checkpoint`
      (REGRESSION-CRITICAL — spec "does NOT fire on every matching turn" +
      success criterion #2) — same setup as above; spy `write_checkpoint`
      (or inspect persisted state) and assert a checkpoint IS written for
      `(project, session_id)` at the end of this turn, exactly as an
      ordinary tool-using turn would. This is what makes turn 2 read as
      "not first turn."
- [x] **RED**: `test_chat_second_turn_same_phrasing_proceeds_normally`
      (spec "The same phrasing on a later turn... proceeds through the loop
      normally", success criterion #2) — given the checkpoint written by
      the previous test's turn now exists for `(project, session_id)`, call
      `chat()` again with the identical `NEW_PRODUCT_KEYWORDS`-matching
      input; assert `self._reasoning_loop` IS awaited this time (no
      re-suggestion).
- [x] **RED**: `test_chat_disabled_memory_suppresses_short_circuit` — memory
      scope disabled, matching input, no checkpoint (as expected under
      disabled memory) → assert `self._reasoning_loop` IS awaited (loop
      runs normally, suggestion suppressed).
- [x] **GREEN**: in `chat()` (`src/agentos/agent/core.py`), replace the
      direct `outcome = await self._reasoning_loop(...)` call at
      `core.py:250` with the branch from design §5d:
      ```python
      if self._should_suggest_sdd_flow(user_input, profile, project, session_id):
          sdd_status = detect_sdd_artifacts()
          outcome = ReasoningOutcome(
              response=_build_new_product_suggestion(sdd_status.has_sdd),
              last_tool_summary="",
              exhausted=False,
          )
      else:
          outcome = await self._reasoning_loop(
              messages, tools, project, session_id,
              status_callback=status_callback, profile=profile,
          )
      ```
      Add `from agentos.sdd.detector import detect_sdd_artifacts` to the
      module's imports. Do NOT touch steps 6/6b (checkpoint write, response
      persistence) below this call — they must run unchanged on both
      branches so the checkpoint gets written on the suggestion turn.
- Depends on: 1.1, 1.2, 1.3, 2.1. Parallelizable: no (core wiring task).

### 3.2 Independence from `SCAFFOLDING_KEYWORDS` addendum and destructive gate
- [x] **RED**: `test_chat_scaffolding_addendum_and_destructive_gate_unaffected`
      (spec "Independence from Existing Scaffolding-Clarification
      Mechanisms") — a session whose first turn triggered the new-product
      short-circuit (no tool calls on turn 1, per 3.1); on the session's
      second turn, send input containing a `SCAFFOLDING_KEYWORDS` match
      (e.g. `"creá un componente nuevo"`) and/or script an under-specified
      destructive tool call; assert the scaffolding prompt addendum is
      still injected in `_build_messages` and/or the destructive-tool gate
      still fires exactly as it did before this change (reuse/adapt an
      existing gate test's assertions rather than re-deriving new ones).
- Depends on: 3.1. Parallelizable: no (extends the same wiring, but is a
  read-only regression check — does not modify `core.py` further).

**Phase 3 exit criteria:** the short-circuit fires exactly per the spec's 4
gating scenarios (disabled scope / non-first-turn / non-keyword / eligible);
`chat()`'s existing checkpoint-write and response-persistence steps
(6/6b) are unmodified and demonstrably still execute on the suggestion turn
(3.1's second test); the archived `agent-scaffolding-clarification`
mechanisms (`SCAFFOLDING_KEYWORDS` addendum, destructive gate) are
unaffected; all new tests green.

---

## Phase 4 — Worker Exclusion and `stream_chat` Regression Coverage

Spec coverage: implicit ("No Worker/Delegation Vocabulary", proposal's
worker-exclusion concern). Structural per design §3 — no production code
change in this phase, only tests that lock the guarantee in.

### 4.1 Delegation path never triggers the suggestion (end-to-end)
- [x] **RED → GREEN in one step** (this is a locking/regression test, not
      driving new production code — the exclusion is structural, per design
      ADR-2): `test_delegation_worker_never_triggers_new_product_suggestion`
      — drive `_run_delegation` (`core.py:530`) with a delegated `task`
      string that matches `NEW_PRODUCT_KEYWORDS` (e.g. `"armar toda la
      app"`); assert the worker's `_reasoning_loop` call at `core.py:572`
      executes normally (tool calls permitted, no suggestion text
      returned) and that `_should_suggest_sdd_flow` / `chat()`'s
      short-circuit branch is never invoked for the worker turn. This test
      should fail before Phase 3 lands (no short-circuit exists yet to
      bypass) and pass once Phase 3 is in place, confirming the guarantee
      holds without any explicit `depth` check.
- Depends on: 3.1. Parallelizable: yes, with 4.2.

### 4.2 `stream_chat` naturally inherits the short-circuit
- [x] **RED → GREEN in one step** (regression/locking test — `stream_chat`
      requires no production change per design §11, since it calls
      `self.chat(...)` directly at `core.py:673`):
      `test_stream_chat_first_turn_new_product_request_yields_suggestion` —
      call `stream_chat()` with a first-turn `NEW_PRODUCT_KEYWORDS`-matching
      input; assert the streamed/joined output equals the same suggestion
      text `chat()` would return, and that no tool call occurred underneath
      (spy through the same `self.skills.execute` hook used in 3.1).
- Depends on: 3.1. Parallelizable: yes, with 4.1.

**Phase 4 exit criteria:** both guarantees (worker exclusion is structural;
`stream_chat` inherits the short-circuit with zero new integration code) are
covered by passing end-to-end tests; no production code changes in this
phase beyond what Phase 3 already introduced.

---

## Final Sweep

### 5.1 Deferred-config constant check
- [x] Confirm `NEW_PRODUCT_KEYWORDS` exists as a named module constant (not
      inline literals) in `src/agentos/agent/core.py`, with a `# deferred
      config` comment marker, consistent with `SCAFFOLDING_KEYWORDS` and the
      `agent-scaffolding-clarification` convention. Confirm `config.py` was
      NOT read or modified during this change.
- Depends on: all prior phases. Parallelizable: no (final sweep).

### 5.2 Full suite green
- [x] Run `.venv/bin/python -m pytest -q` — full suite passes, no
      regressions in existing `core.py` tests (particularly `_build_messages`,
      `_reasoning_loop`, `_run_delegation`, and `stream_chat` coverage from
      prior changes).

---

## Review Workload Forecast

- **Chained PRs recommended:** No — single PR. The change touches one file
  (`src/agentos/agent/core.py`) plus a read-only import of an existing
  detector; Phases 1-2 are small independent pure-function additions and
  Phase 3 is a short, localized replacement of one call site. There is no
  cross-layer sequential dependency (unlike `session-persistence`) that
  would justify a split, and splitting would fragment review of the single
  REGRESSION-CRITICAL checkpoint-write behavior across PRs.
- **Estimated changed lines:** ~230-300 including tests, all in
  `src/agentos/agent/core.py` and its test file:
  - Production code — ~50-70 lines (`NEW_PRODUCT_KEYWORDS` constant,
    `_is_new_product_request`, `_build_new_product_suggestion` two
    branches, `_should_suggest_sdd_flow` method, the `chat()` call-site
    branch, one new import).
  - Tests — ~180-230 lines across ~18 test functions (table-driven Phase 1
    tests, guard-ordering Phase 2 tests, wiring/regression Phase 3-4 tests).
- **400-line budget risk:** Low — this change is meaningfully smaller than
  its sibling `agent-scaffolding-clarification` (~350-450 lines across 3
  files): no `Skill`/`SkillRegistry` metadata layer, no batch-ordering edge
  case, single call site.
- **Decision needed before apply:** No — proceed as a single PR without
  `size:exception`. Flag to the user only that Phase 3.1's second test
  (`test_chat_first_turn_suggestion_writes_checkpoint`) and Phase 3.2's
  independence test are the highest-value tests in the whole change and
  should not be dropped or watered down under time pressure — they are what
  the "no infinite re-suggestion" and "does not disturb existing gates"
  guarantees actually rest on.
