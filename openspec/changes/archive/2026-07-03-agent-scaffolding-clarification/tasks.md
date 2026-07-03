# Tasks: Agent Scaffolding Clarification

Strict TDD mode active. For every implementation task: write the failing test
first (RED), confirm it fails for the right reason, then implement the
minimal change to pass (GREEN). Test command:

```
.venv/bin/python -m pytest -q
```

(`uv run pytest` intermittently resolves the wrong interpreter in this repo —
do not use it for verification.)

Delivery: single PR, additive change across `base.py`, `filesystem.py`,
`core.py`. Design confirms no individual layer needs its own PR (see Review
Workload Forecast). `config.py` is OFF-LIMITS — do not read or modify it;
new constants land as module constants next to their consumer.

---

## Phase 1 — Destructive Metadata (`Skill` / `SkillRegistry`)

Spec coverage: "Destructive Tool Metadata". Foundation for Phase 3's gate
(nothing in Phase 2/3 can query destructiveness until this lands).

### 1.1 `Skill` base: `destructive_functions` + `is_destructive`
- [x] **RED**: `test_skill_default_destructive_functions_empty` — a bare
      `Skill` subclass with no override → `is_destructive("anything")` is
      `False`.
- [x] **GREEN**: add `destructive_functions: frozenset[str] = frozenset()`
      class attribute and `is_destructive(self, fn_name: str) -> bool` method
      to `Skill` in `src/agentos/skills/base.py`.
- Depends on: none. Blocks: 1.2, 1.3, 1.4, 3.x.
- Parallelizable: no (foundation).

### 1.2 `FilesystemSkill`: tag write/append/delete destructive
- [x] **RED**: `test_filesystem_write_append_delete_are_destructive` —
      `FilesystemSkill().is_destructive("write"/"append"/"delete")` → `True`.
- [x] **RED**: `test_filesystem_reads_are_not_destructive` —
      `is_destructive("read"/"list"/"glob"/"search"/"exists")` → `False`.
- [x] **GREEN**: set `destructive_functions = frozenset({"write", "append",
      "delete"})` on `FilesystemSkill` in `src/agentos/skills/filesystem.py`.
- Depends on: 1.1. Parallelizable: no.

### 1.3 `SkillRegistry.is_destructive` accessor
- [x] **RED**: `test_registry_is_destructive_true_for_filesystem_write`,
      `test_registry_is_destructive_false_for_unknown_skill_or_fn` (unknown
      skill name, and known skill with unknown fn name → both `False`, no
      exception).
- [x] **GREEN**: implement `SkillRegistry.is_destructive(self, skill_name:
      str, fn_name: str) -> bool` in `src/agentos/skills/base.py` — `skill =
      self.get(skill_name); return bool(skill and
      skill.is_destructive(fn_name))`.
- Depends on: 1.1, 1.2. Parallelizable: no.

### 1.4 Surface `destructive` in `get_openai_tool` / `get_all_tools`
- [x] **RED**: `test_get_all_tools_filesystem_write_reports_destructive_true`,
      `test_get_all_tools_filesystem_read_reports_destructive_false`,
      `test_get_all_tools_other_skill_defaults_destructive_false` (a
      second built-in skill's tools all report `destructive: false`,
      confirming the default is preserved for previously-untagged tools).
- [x] **GREEN**: in `get_openai_tool` (`src/agentos/skills/base.py`), add
      `"destructive": self.is_destructive(fn_name)` to the emitted
      `function` object. No change to `get_all_tools()` iteration logic —
      the flag rides along automatically.
- [x] **Smoke check**: confirm the Qwen client tolerates the extra
      `destructive` key on the function object (manual check or existing
      client test fixture) — per design §3b fallback note. If the
      OpenAI-compat layer rejects it, note the fallback (move under
      `parameters` / drop from wire) as a follow-up, do NOT block this PR on
      it since the gate (Phase 3) does not depend on the wire schema.
- Depends on: 1.1, 1.2, 1.3. Parallelizable: no.

**Phase 1 exit criteria:** `Skill.is_destructive`, `SkillRegistry.is_destructive`
both correct per design; `filesystem_write/append/delete` report
`destructive: true` in `get_all_tools()`; all other tools (filesystem reads,
other skills) report `destructive: false`; all new tests green.

---

## Phase 2 — Pure Gate Helpers (`_is_under_specified`, `_build_clarifying_question`)

Spec coverage: "Destructive-Call Gate in the Reasoning Loop" (heuristic
portion). Fully independent of Phase 1 — pure functions over `fn_args`, zero
LLM, zero I/O. Can run in parallel with Phase 1 if desired, but sequenced
after for narrative clarity.

### 2.1 `GENERIC_CONTENT_PLACEHOLDERS` constant
- [x] **GREEN** (no test needed — plain data): add the frozenset to
      `src/agentos/agent/core.py` near the gate, with a `# deferred config`
      comment marker (per design §9 / house convention):
      `{"todo", "tbd", "fixme", "...", "…", "placeholder", "content",
      "contenido", "content here", "contenido aqui", "your content here",
      "tu contenido aqui"}`.
- Depends on: none. Blocks: 2.2.

### 2.2 `_is_under_specified(fn_name, fn_args)` — table-driven
- [x] **RED**: `test_is_under_specified_empty_or_none_path_gated` —
      parametrized over `path in ("", None, "   ")`, for `fn_name` in
      `("write", "append", "delete")` → `True`.
- [x] **RED**: `test_is_under_specified_valid_path_and_content_not_gated` —
      valid `path` + valid `content` (e.g. `"print('hello')"`) for
      `write`/`append` → `False`.
- [x] **RED**: `test_is_under_specified_empty_or_whitespace_content_gated` —
      valid `path`, `content in ("", "   ", None)` for `write`/`append` →
      `True`.
- [x] **RED**: `test_is_under_specified_placeholder_content_gated` —
      parametrized over each token in `GENERIC_CONTENT_PLACEHOLDERS` plus
      case/whitespace variants (`"TODO"`, `" ... "`, `"Content Here"`) →
      `True`.
- [x] **RED**: `test_is_under_specified_real_short_content_not_gated`
      (anti-false-positive, load-bearing per design ADR-1) — valid `path` +
      `content` in `("port=8080", "export default App")` → `False`.
- [x] **RED**: `test_is_under_specified_delete_ignores_content` — `delete`
      with valid `path` and no `content` key in `fn_args` at all → `False`.
- [x] **GREEN**: implement `_is_under_specified(fn_name: str, fn_args:
      dict[str, Any]) -> bool` in `src/agentos/agent/core.py` exactly per
      design §4b: path check first (missing/None/empty/whitespace → gated),
      then for `write`/`append` only, content check (missing/empty/
      whitespace → gated; else exact-match-after-strip-lower against
      `GENERIC_CONTENT_PLACEHOLDERS` → gated).
- Depends on: 2.1. Parallelizable: yes, with Phase 1.

### 2.3 `_build_clarifying_question(skill_name, fn_name, fn_args)`
- [x] **RED**: `test_build_clarifying_question_missing_path_asks_for_path` —
      `fn_args` with missing/empty `path` → returned string mentions the
      path/destination (branch selection, not exact wording).
- [x] **RED**: `test_build_clarifying_question_missing_content_asks_for_content`
      — valid `path`, empty/placeholder `content` → returned string mentions
      content and includes the given `path`.
- [x] **GREEN**: implement `_build_clarifying_question` in
      `src/agentos/agent/core.py` per design §4b (Spanish strings, matching
      existing `_format_exhaustion_message` convention).
- Depends on: 2.2 (shares the args shape, not a hard runtime dependency).
  Parallelizable: yes.

**Phase 2 exit criteria:** `_is_under_specified` and `_build_clarifying_question`
fully covered by table-driven pure-unit tests, including the anti-false-positive
guarantee (`port=8080` style real content NOT gated); zero LLM/IO in these
tests; all green.

---

## Phase 3 — Gate Wiring in `_reasoning_loop`

Spec coverage: "Destructive-Call Gate in the Reasoning Loop" (interception +
wiring). Depends on Phase 1 (`SkillRegistry.is_destructive`) and Phase 2
(the two pure helpers).

### 3.1 Interception point + short-circuit return
- [x] **RED**: `test_reasoning_loop_gates_destructive_underspecified_call` —
      fake `QwenClient` scripted to emit a `filesystem_write` tool call with
      empty `path`; assert `self.skills.execute` is NOT called (spy/mock the
      executor), the returned `ReasoningOutcome.response` is the clarifying
      question, and `exhausted is False`.
- [x] **RED**: `test_reasoning_loop_executes_well_specified_destructive_call`
      — scripted `filesystem_write` call with valid `path` + valid `content`
      → `self.skills.execute` IS called with the expected args, as today.
- [x] **RED**: `test_reasoning_loop_never_gates_nondestructive_calls` —
      scripted `filesystem_read` call with missing/empty args → gate does
      NOT fire, `execute` is called (or fails downstream on its own
      validation, unrelated to this gate).
- [x] **RED**: `test_reasoning_loop_gate_fires_without_scaffolding_keyword`
      (independence scenario, ADR-4) — user input has NO scaffolding
      keyword (so no prompt addendum is injected) AND the model still emits
      an under-specified `filesystem_delete` call → gate still fires,
      `execute` not called.
- [x] **GREEN**: inside `_reasoning_loop`'s `for tool_call in
      response.tool_calls:` loop in `src/agentos/agent/core.py`, after the
      `skill_name, fn_name = fn_name.split("_", 1)` split and BEFORE
      `self.skills.execute(...)` (~line 253-261), add:
      ```python
      if self.skills.is_destructive(skill_name, fn_name) and \
              _is_under_specified(fn_name, fn_args):
          logger.info(f"Destructive gate fired: {skill_name}.{fn_name} under-specified")
          return ReasoningOutcome(
              response=_build_clarifying_question(skill_name, fn_name, fn_args),
              last_tool_summary=", ".join(last_tools_used[-3:]),
              exhausted=False,
          )
      ```
      Reuse the existing `ReasoningOutcome` type (already introduced by the
      session-persistence change) — no new return shape.
- Depends on: 1.3, 2.2, 2.3. Parallelizable: no (core wiring task, must land
  after both dependencies).

### 3.2 Batch tool-call ordering sanity check
- [x] **RED**: `test_reasoning_loop_batch_nondestructive_before_gated_destructive`
      — scripted response with TWO tool calls: a non-destructive
      `filesystem_read` first, then an under-specified `filesystem_write`
      second → assert the read's `execute` call happened (result appended)
      AND the write's `execute` was never called AND the turn short-circuits
      with the clarifying question. Documents/locks in the accepted design
      tradeoff (design §4a, proposal risk row "batch tool calls").
- Depends on: 3.1. Parallelizable: no (extends the same wiring).

**Phase 3 exit criteria:** the gate fires exactly per the spec's 4 scenarios
(complete args proceed / empty path gated / generic content gated /
non-destructive never gated) plus the independence scenario; `chat()`'s
existing checkpoint-write and return-`outcome.response` path is unaffected
(verify manually — no `chat()` signature change); all new tests green.

---

## Phase 4 — Scaffolding-Intent Prompt Addendum

Spec coverage: "Scaffolding-Intent Prompt Addendum". Fully independent of
Phases 1-3 (ADR-4) — can be implemented/tested in any order relative to them,
sequenced last here only because it is the lowest-risk, most mechanical
piece (mirrors the existing SDD-keyword branch exactly).

### 4.1 `SCAFFOLDING_KEYWORDS` constant + `_build_messages` branch
- [x] **RED**: `test_build_messages_scaffolding_keyword_injects_addendum` —
      `_build_messages` called with `user_input="creá un componente nuevo"`
      → exactly one extra system message appended containing the
      scaffolding-clarification instruction, in addition to existing
      system/context messages.
- [x] **RED**: `test_build_messages_non_scaffolding_input_no_addendum` —
      `user_input="leé el archivo config.py"` → no scaffolding system
      message appended.
- [x] **RED**: `test_build_messages_english_scaffolding_keyword_injects_addendum`
      — e.g. `"create a new component"` or `"set up the project structure"`
      → addendum injected (covers the bilingual keyword set, not just
      Spanish).
- [x] **GREEN**: add `SCAFFOLDING_KEYWORDS` tuple (bilingual, per design §5)
      and the `if any(kw in user_input.lower() for kw in
      SCAFFOLDING_KEYWORDS):` branch to `_build_messages` in
      `src/agentos/agent/core.py`, placed right after the existing
      SDD-keyword branch (`core.py:193-200`) and before the user message is
      appended — structurally identical to that branch.
- Depends on: none (independent of Phases 1-3). Parallelizable: yes, with
  any other phase.

**Phase 4 exit criteria:** scaffolding keyword branch mirrors the SDD-keyword
branch's structure exactly; bilingual keyword matching confirmed by tests;
zero shared state with the Phase 3 gate (confirmed by Phase 3's independence
test, 3.1's fourth case).

---

## Final Sweep

### 5.1 Deferred-config constants check
- [x] Confirm `GENERIC_CONTENT_PLACEHOLDERS` and `SCAFFOLDING_KEYWORDS` both
      exist as named module constants (not inline literals) in
      `src/agentos/agent/core.py`, each with a `# deferred config` comment
      marker, consistent with the session-persistence change's convention.
      Grep for stray literal placeholder strings or keyword lists introduced
      during Phases 1-4 and replace with the named constants if any slipped
      through.
- Depends on: all prior phases. Parallelizable: no (final sweep).

### 5.2 Full suite green
- [x] Run `.venv/bin/python -m pytest -q` — full suite passes, no
      regressions in existing `filesystem`/`base`/`core` tests
      (particularly `_build_messages` and `_reasoning_loop` existing
      coverage from the session-persistence change).

---

## Review Workload Forecast

- **Chained PRs recommended:** No — single PR. Unlike session-persistence,
  this change has no hard sequential data-migration dependency between
  layers; Phases 1-2 (metadata + pure helpers) and Phase 4 (prompt branch)
  are independent and small, and Phase 3 (wiring) is a short, localized
  addition to an existing loop. Splitting would create more review overhead
  (cross-PR context on `_is_under_specified`) than it saves.
- **Estimated changed lines:** ~350-450 including tests, across:
  - `src/agentos/skills/base.py` — ~20-30 lines (`destructive_functions`,
    `is_destructive` x2, `get_openai_tool` change).
  - `src/agentos/skills/filesystem.py` — ~3 lines (one class attribute).
  - `src/agentos/agent/core.py` — ~70-90 lines (two constants, two pure
    helpers, one gate branch, one prompt branch).
  - Tests — the bulk of the volume: ~20 new test functions across 4 phases,
    largely table-driven/parametrized, estimated 220-300 lines.
- **400-line budget risk:** Medium — this is close to or slightly over the
  400-line budget once tests are included, primarily driven by the number of
  table-driven test cases in Phase 2 (placeholder/anti-false-positive table)
  and Phase 3 (four gate scenarios + batch-ordering test). The production
  code itself is small (~100 lines); tests dominate the count.
- **Decision needed before apply:** Yes, per the guard — flag to the user:
  proceed as `size:exception` (single PR, test-heavy but low architectural
  risk, all changes additive) OR split into 2 PRs (PR A: Phases 1-2, metadata
  + pure helpers, ~200 lines; PR B: Phases 3-4, wiring + prompt branch, ~200
  lines) if the team prefers stricter review slices. No chain-strategy
  preference implied either way — this is a size call, not a dependency call.
