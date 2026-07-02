# Archive Report: session-persistence

**Change**: session-persistence
**Archive Date**: 2026-07-02
**Status**: CLOSED — PASS WITH WARNINGS (0 CRITICAL, 1 WARNING, 1 SUGGESTION)
**Artifact Store Mode**: hybrid

## Executive Summary

Session persistence change fully implemented, verified, and closed. All 3-phase stacked PRs (auto-resume, checkpoint write, checkpoint rehydration) merged to main. Specs synced, change folder archived. Verification passed with warnings on test coverage (implementation correct, test assertions overclaim what they prove). No blocking issues.

## Change Metadata

| Field | Value |
|-------|-------|
| **Name** | session-persistence |
| **Type** | Feature: durable auto-resumable sessions + structured checkpoint |
| **Phases** | 3 (auto-resume PR #1, checkpoint write PR #2, checkpoint read PR #3) |
| **Scope** | Durable `session_id` + structured checkpoint (goal/open_items/last_tool_result) via reserved-key MemoryFacts |
| **Non-Goals** | No new config.py fields, no new EventType, no LLM summarization, no new file store |
| **PRs Merged** | #5, #6, #7 (commits 072d1c9..5db28e8) |
| **Delivery Strategy** | stacked-to-main chained PRs (Phase 1 → Phase 2 → Phase 3) |
| **Test Coverage** | 216 passed, 0 failed, 44.08s |

## Artifacts

### Engram Observations (for cross-session recovery)
- Proposal: #173 (`sdd/session-persistence/proposal`)
- Spec: #174 (`sdd/session-persistence/spec`)
- Design: #175 (`sdd/session-persistence/design`)
- Tasks: #176 (`sdd/session-persistence/tasks`)
- Verify Report: #178 (`sdd/session-persistence/verify-report`)
- Archive Report: saved to this topic key after archival

### OpenSpec Files
All change artifacts archived under `openspec/changes/archive/2026-07-02-session-persistence/`:
- `proposal.md` ✅
- `explore.md` ✅
- `design.md` ✅
- `specs/session-persistence.md` ✅
- `tasks.md` ✅
- `verify-report.md` ✅
- `archive-report.md` ✅

### Main Specs
New domain spec created and synced:
- **Created**: `openspec/specs/session-persistence/spec.md` (delta spec copied as full spec — new domain, no prior spec to merge)

## Verification Summary

**Verdict**: PASS WITH WARNINGS

### Task Completeness
All implementation tasks across 3 phases marked complete ([x]). Verified by direct read of `tasks.md`. No unchecked items.

### Test Execution
```
.venv/bin/python -m pytest -q
====================== 216 passed, 305 warnings in 44.08s ======================
```

### Spec Compliance
| Requirement | Status | Notes |
|---|---|---|
| Durable Last-Session Pointer | PASS | `test_get_last_session_absent_returns_none`, `test_touch_last_session_upserts_pointer` |
| Auto-Resume on `aki chat` | PASS | `test_chat_resumes_last_session_fact`, `test_chat_explicit_session_wins` |
| Auto-Resume on `aki interactive` | PASS | Mirrored `_resolve_session_id` tests |
| Explicit New-Session Escape Hatch | PASS | `test_chat_new_session_ignores_last_fact`, `test_chat_session_and_new_session_prefers_explicit` |
| Structured Checkpoint Write | PASS | `test_chat_writes_checkpoint_each_turn`, `test_write_checkpoint_no_duplicate_rows_across_multiple_writes` |
| Guaranteed Checkpoint Rehydration | PASS | `test_build_messages_injects_checkpoint_slot`, `test_build_messages_checkpoint_survives_budget_truncation`, `test_render_checkpoint_respects_char_cap` |

### Critical Gotcha Validation
**Status**: CLOSED ✅

`MemoryRepository.upsert_fact` keys on `fact.id`, not `(key, scope)`. Helper `_upsert_reserved_fact` (sole code path for reserved-key writes) correctly reads existing fact via `get_fact(key, scope)`, reuses id when present, then calls `upsert_fact`. All call sites verified:
- `touch_last_session` → routes through `_upsert_reserved_fact`
- `write_checkpoint` → routes through `_upsert_reserved_fact`
- Regression tests: `test_upsert_reserved_fact_updates_in_place`, `test_touch_last_session_upserts_pointer`, `test_write_checkpoint_no_duplicate_rows_across_multiple_writes` all pass.

### Config Constraint Honored
**Status**: ✅ VERIFIED

`src/agentos/core/config.py` unchanged within commit range `072d1c9..5db28e8` (all 3 phases). Off-limits constraint honored. Tunables implemented as named module constants:
- `CHECKPOINT_FIELD_CHAR_CAP` (memory/repository.py)
- `CHECKPOINT_REHYDRATION_CHAR_CAP` (agent/core.py)
- `RESERVED_FACT_KEY_PREFIX` (memory/repository.py)
- `LAST_SESSION_KEY` (memory/repository.py)
- `CHECKPOINT_CADENCE_TURNS` (agent/core.py)

### Issues Found

#### CRITICAL
None.

#### WARNING
`test_build_messages_checkpoint_survives_budget_truncation` (tests/unit/test_build_messages_checkpoint.py:87)
- **Issue**: Test does not assert truncation actually occurred on competing facts content; only proves checkpoint presence (same assertion as simpler injection test).
- **Code Status**: CORRECT — Implementation verified via direct read: checkpoint bypasses `format_for_prompt`/`_fit_context_to_budget` entirely (separate messages entry, exact-key read, never passed through budget-fit).
- **Test Status**: OVERCLAIMS — Test assertion is weaker than its name implies. Recommend strengthening (assert `len(memory_text) < len(raw_facts)` or mock budget functions to prove truncation occurred while checkpoint bypassed it) in follow-up.
- **Blocking**: NO — Implementation is sound. Archive proceeds; test strengthening deferred.

#### SUGGESTION
Deprecation warnings from `datetime.utcnow()` in `write_checkpoint`/`touch_last_session` appear at higher volume in tests. Pre-existing pattern in repository.py, not new to this change. Consider repo-wide `datetime.now(UTC)` migration separately. Not blocking.

## Rollback Plan

Each phase was designed to be independently revertible:
- **Phase 1 only**: `aki chat`/`interactive` revert to random-per-call `session_id` behavior. Auto-resume lost, but forward-looking intact.
- **Phases 1–2**: Checkpoint writes stop. Existing facts remain inert (not read, not harmful).
- **All phases**: Full revert restores original continuity-via-relevance-retrieval behavior. No schema migration to undo; reserved facts are inert if unread.

Fact-based approach chosen specifically to avoid: new EventType enum (no migration), new file store (no second source of truth), new config fields (config.py stayed untouched).

## Dependencies & Follow-up Work

### Closed by this archive
- Durable session identity ✅
- Structured checkpoint write ✅
- Guaranteed checkpoint rehydration ✅
- Auto-resume session escape hatch ✅

### Deferred to future change
- Config.py wiring for tunables (PR branches, new AgentConfig/MemoryConfig fields)
- LLM-based `open_items` enrichment (currently deterministic carry-over)
- Checkpoint cadence > 1 (currently hardcoded to every turn, cheap single upsert)

## Deployment Notes

- No schema changes to deploy
- No migration scripts needed
- Reserved-key facts (`session:*` prefix) are idempotent if unread
- All new code is additive; existing call sites unchanged
- Backward compatible: old sessions without checkpoints work fine (no-op on read)
- Config.py wiring deferred; named constants serve as grep-able future wiring points

## Success Criteria Met

- [x] `aki chat` twice in a row (no `--session`) continues the same session
- [x] `aki interactive` restart resumes the prior session unless `--new-session`
- [x] Structured checkpoint always appears in rehydrated context, independent of query relevance
- [x] No new `EventType`, no `config.py` change, no new file store
- [x] All tasks marked complete; all tests green
- [x] Specs synced to main
- [x] Change archived with audit trail

## Signing Off

Archive completed. All phase outputs persisted. SDD cycle for `session-persistence` closed.

The change is ready for deployment and ready for the next SDD cycle.
