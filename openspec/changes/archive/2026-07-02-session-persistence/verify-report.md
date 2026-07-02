# Verify Report: session-persistence

**Change**: session-persistence
**Mode**: hybrid (Engram + OpenSpec files)
**Verified against**: openspec/changes/session-persistence/specs/session-persistence.md, tasks.md, apply-progress (Engram #177)
**Date**: 2026-07-02
**Verdict**: PASS WITH WARNINGS

## Task Completeness

All checkboxes across Phase 1 (PR #1, `072d1c9`), Phase 2 (PR #2, `dc4be25`), Phase 3 (PR #3, `5db28e8`) are `[x]` in `tasks.md`, including the two standalone "Critical Gotcha" checklist items. Confirmed by direct file read, not just trusting apply-progress.

## Test Execution

```
.venv/bin/python -m pytest -q
====================== 216 passed, 305 warnings in 44.08s ======================
```
Matches apply-progress's claimed count (216 passed, up from 210 pre-Phase-3). No failures, no skips.

## Spec Compliance Matrix

| Requirement | Scenario coverage | Test evidence | Status |
|---|---|---|---|
| Durable Last-Session Pointer | first invocation, update on new session | `test_get_last_session_absent_returns_none`, `test_touch_last_session_upserts_pointer` | PASS |
| Auto-Resume on `aki chat` | resume, explicit override | `test_chat_resumes_last_session_fact`, `test_chat_explicit_session_wins` | PASS |
| Auto-Resume on `aki interactive` | restart resumes | mirrored `_resolve_session_id` tests | PASS |
| Explicit New-Session Escape Hatch | `--new-session` bypass, mutual exclusion | `test_chat_new_session_ignores_last_fact`, `test_chat_session_and_new_session_prefers_explicit` | PASS |
| Structured Checkpoint Write | write after turn, on exhaustion, upsert not accumulate | `test_chat_writes_checkpoint_each_turn` (+ exhaustion variant), `test_write_checkpoint_no_duplicate_rows_across_multiple_writes` | PASS |
| Guaranteed Checkpoint Rehydration | injected regardless of relevance, survives truncation, no-op when absent, capped | `test_build_messages_injects_checkpoint_slot`, `test_build_messages_checkpoint_survives_budget_truncation`, `test_build_messages_no_checkpoint_omits_slot`, `test_render_checkpoint_respects_char_cap` | PASS (see WARNING on truncation test strength) |

## Targeted Verification (per verification request)

1. **All tasks.md checkboxes `[x]` across 3 phases** — confirmed by direct read of `tasks.md`; no unchecked items found, including the standalone Critical Gotcha section.

2. **Spec requirement -> code + test spot-check** — done above; each requirement traced to concrete implementation (`_upsert_reserved_fact`, `touch_last_session`/`get_last_session`, `_resolve_session_id`, `write_checkpoint`/`read_checkpoint`, `ReasoningOutcome`, `render_checkpoint`, `_build_messages` checkpoint slot, `assemble_context` reserved-prefix filter) and a passing test, not just checkbox trust.

3. **`upsert_fact`-keys-on-`id` gotcha** — CONFIRMED closed. `_upsert_reserved_fact` (repository.py:304) is the sole path that reads the existing fact via `get_fact(key, scope)`, reuses `existing.id` when present, then calls `upsert_fact`. Grepped all `upsert_fact(` call sites in `repository.py`: only two — inside `_upsert_reserved_fact` and inside unrelated event-consolidation code (line 514, generic non-reserved facts, pre-existing, untouched by this change). No call site constructs a raw `MemoryFact` for `session:last` or `session:{id}:checkpoint` outside the helper.
   - Regression test `test_write_checkpoint_no_duplicate_rows_across_multiple_writes` writes the same checkpoint 3x with varying fields and asserts exactly ONE `session:{id}:checkpoint` row and exactly ONE `session:last` row exist (via direct fact-count query, not just "no exception"). Read the test body directly — assertion is real, not a placeholder. PASSES.

4. **Reserved checkpoint slot survives budget truncation** — implementation CONFIRMED structurally correct: in `_build_messages` (core.py:139-178), the checkpoint system message is appended to `messages` BEFORE `context.format_for_prompt(max_tokens=...)` is called and is never passed through that call or through `_fit_context_to_budget`. Code comment at core.py:157-161 documents this explicitly.
   - **WARNING**: `test_build_messages_checkpoint_survives_budget_truncation` does not actually verify that truncation occurred on the competing content. It builds 50 facts (25KB) and asserts the checkpoint string is present — but never asserts that `memory_text`/the facts content in the final messages was itself reduced/truncated. The test's own inline comment admits this: "the key assertion is that the checkpoint slot is present regardless of context.format_for_prompt output size/content" — i.e., it degrades to the same assertion as `test_build_messages_injects_checkpoint_slot` with a larger fixture, not a true truncation-differential test. It does not fail today because the code path genuinely never routes the checkpoint through budget-fit (confirmed by direct code read above), so the spec requirement IS met by the implementation — but the test as named overclaims what it proves. Recommend strengthening (assert `len(memory_text_in_messages) < len(raw_facts_text)` or mock `_fit_context_to_budget`/`format_for_prompt` to prove it was invoked/truncating and the checkpoint content bypassed it) in a follow-up, not blocking for this verify.

5. **`session:*`-prefixed facts excluded from `assemble_context` fallback** — CONFIRMED. `RESERVED_FACT_KEY_PREFIX = "session:"` (repository.py:36) filters `get_facts_by_scope` fallback results at repository.py:422-423 (`if not fact.key.startswith(RESERVED_FACT_KEY_PREFIX)`). Test `test_assemble_context_excludes_reserved_session_facts` seeds `session:last`, `session:{id}:checkpoint`, and a normal fact in the same scope, forces the fallback path via a query with no keyword match, and asserts only the normal fact key surfaces. PASSES.

6. **`src/agentos/core/config.py` not modified in this change** — CONFIRMED. `git diff 072d1c9..5db28e8 --stat -- src/agentos/core/config.py` (the exact commit range spanning PR #1 through PR #3) returns empty — zero changes to that file within the session-persistence PRs. (A prior, unrelated commit `7f8044b` on main, predating this change's PRs, did touch config.py for `.env` git-root discovery — not part of this change and outside the verified commit range.) New tunables (`CHECKPOINT_FIELD_CHAR_CAP`, `CHECKPOINT_REHYDRATION_CHAR_CAP`, `RESERVED_FACT_KEY_PREFIX`, `LAST_SESSION_KEY`, `CHECKPOINT_CADENCE_TURNS`) were correctly added as named module constants in `repository.py`/`core.py` instead, per design.md ADR-4.

7. **Full suite run** — 216 passed, 0 failed, 44.08s. Matches apply-progress's claimed count.

## Issues

### CRITICAL
None.

### WARNING
- `test_build_messages_checkpoint_survives_budget_truncation` (tests/unit/test_build_messages_checkpoint.py:87) does not assert that truncation actually happened to the competing facts content — it only proves checkpoint presence, same as the simpler injection test. The spec requirement is still satisfied by the implementation (verified via direct code read: checkpoint bypasses `format_for_prompt`/`_fit_context_to_budget` entirely), so this does not block archive, but the test should be strengthened in a follow-up so it fails if a future refactor accidentally routes the checkpoint through the budget-fit path.

### SUGGESTION
- None of the new `datetime.utcnow()` usages in `write_checkpoint`/`touch_last_session` are new to this change (pre-existing pattern in repository.py), but they now fire deprecation warnings in test output at higher volume due to more checkpoint writes in tests. Not blocking; consider a repo-wide `datetime.now(UTC)` migration separately.

## Config Constraint Check
`src/agentos/core/config.py`: 0 lines changed within `072d1c9..5db28e8`. Constraint honored.

## Final Verdict
**PASS WITH WARNINGS** — 0 CRITICAL, 1 WARNING, 1 SUGGESTION. Safe to proceed to `sdd-archive`.
