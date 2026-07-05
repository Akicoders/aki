# Archive Report: sdd-scaffolding-flow-suggestion

**Change**: sdd-scaffolding-flow-suggestion
**Archived**: 2026-07-05
**Status**: Complete

## SDD Cycle Summary

This change adds a first-turn, zero-tool-call short-circuit in `chat()` that
detects whole-new-product/app requests (`NEW_PRODUCT_KEYWORDS`, distinct from
the narrower `SCAFFOLDING_KEYWORDS`) and suggests starting or resuming the SDD
flow instead of guessing at file writes. It fires only when memory scope is
not disabled, no session checkpoint exists yet (first turn), and the message
matches the new-product phrasing; it branches its suggestion text on whether
SDD artifacts already exist via `detect_sdd_artifacts()`.

## Verification Status

- **Spec Compliance**: All 7 requirements met (see verify-report.md checklist items 1-7)
- **Task Completion**: All 27 tasks in tasks.md marked [x], cross-referenced against real test files
- **Test Coverage**: Full suite passes (420/420 as of this archive run); a 4-test flake noted in the
  original verify-report was reproducible only in isolated partial runs and is a pre-existing,
  order-dependent issue tracked separately (not a regression from this change)
- **Merged Artifacts**: Main spec created at `openspec/specs/sdd-scaffolding-flow-suggestion/spec.md`

## Artifacts Archived

### Change Folder Contents
- explore.md
- proposal.md
- design.md
- specs/sdd-scaffolding-flow-suggestion/spec.md
- tasks.md (27/27 tasks complete)

### Specs Synced to Main

| Domain | Action | Details |
|--------|--------|---------|
| sdd-scaffolding-flow-suggestion | Created | New domain spec (was delta-only, now in main specs) |

## Verification Findings

### CRITICAL Finding (Corrected, Not a Code Defect)
The verify-report found the design doc's claim "no bare token from
`SCAFFOLDING_KEYWORDS` is reused" was factually false — 7 concrete substring
overlaps exist between `NEW_PRODUCT_KEYWORDS` and `SCAFFOLDING_KEYWORDS`
(e.g. `"armar toda la app"` contains `"armar"`). This has no runtime impact:
`_should_suggest_sdd_flow` short-circuits `chat()` before
`SCAFFOLDING_KEYWORDS` matching ever runs, so there is no ambiguous
double-match at runtime — only incidental overlap in the source token lists.
The design doc has been corrected in place (see the "Correction (found
during verify)" note) to state the actual invariant: non-overlapping
*intent* (whole-product framing vs. single-file framing), not zero shared
substrings.

### WARNING Findings
- The original verify run observed 4 flaky, order-dependent test failures in
  unrelated files (`test_cli_chat.py`, `test_cli_project_resolution.py`)
  that passed in 3 of 4 full-suite runs and in isolation; this is a known
  pre-existing flakiness issue, not caused by this change.
- The claimed "414 passed, 0 failures" in the apply-progress report
  understated observed flakiness; this archive run confirms 420/420 passing
  with the codebase as currently committed.

### No Blocking Issues
All spec requirements are met, all tasks are complete and independently
verified, and the one CRITICAL finding was a documentation inaccuracy
(now corrected) rather than a functional defect.

## SDD Cycle Complete

The change has been fully planned (exploration → proposal → spec → design),
implemented (strict TDD, single batch), verified (PASS WITH WARNINGS, all
resolved), and is now archived.

**Archive Folder**: `openspec/changes/archive/2026-07-05-sdd-scaffolding-flow-suggestion/`
