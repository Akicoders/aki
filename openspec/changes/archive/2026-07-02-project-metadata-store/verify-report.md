# Verify Report: Project Metadata Store (last-project breadcrumb)

Date: 2026-07-02
Verified against: PR #8 (commit b8f3b2d), base commit 3193a9d

## Summary

No CRITICAL issues. No WARNING issues. 1 SUGGESTION (documentation nit, pre-existing deviation already justified in design).

## 1. Tasks completeness

All 22 checkboxes in `tasks.md` (1.1 through 6.2) are marked `[x]`. Confirmed by direct read of the file.

## 2. Spec scenario coverage (spot check)

- Breadcrumb Write on Positive Project Resolution — covered by `test_detect_project_writes_breadcrumb_on_git_root_branch`, `test_build_cockpit_snapshot_writes_breadcrumb_when_record_open`. PASS.
- Breadcrumb as Last-Resort `.env` Search Candidate — covered by `test_breadcrumb_root_yielded_last_when_present`, `test_load_runtime_env_bootstraps_via_breadcrumb_from_unrelated_cwd`, `test_load_runtime_env_prefers_current_context_over_breadcrumb`. PASS.
- Fail-Soft Breadcrumb Handling — covered by `test_read_returns_none_on_corrupt_json`, `test_read_returns_none_when_stored_root_path_missing`, `test_read_returns_none_when_no_file_exists`, `test_write_is_best_effort_and_never_raises`. PASS.

SUGGESTION: the spec's Requirement text names `resolve_project_ref` as the CLI write site, but design.md §4a (ADR-4) deliberately moved the write to `build_cockpit_snapshot`'s `record_open` gate to keep the resolver pure. This is a documented, reasoned deviation (not a silent drift) and the implementation correctly follows design over the earlier spec wording. Recommend updating the spec Requirement text to name `build_cockpit_snapshot` for future-reader accuracy before archiving, but it is not blocking.

## 3. config.py diff — additive-only check

`git diff 3193a9d..b8f3b2d -- src/agentos/core/config.py` shows exactly:
- 1 new import: `from agentos.core.project_breadcrumb import read_breadcrumb`
- 1 new 3-line branch appended immediately before `return roots` in `_iter_env_search_roots`

No changes to `MemoryConfig.db_path` or any other default. Matches design §5 verbatim. PASS.

## 4. Write call sites vs design

- `build_cockpit_snapshot` (cockpit.py): `write_breadcrumb(project.root_path)` added inside the existing `if record_open:` block, immediately after `registry.upsert_project(...)`. NOT in `resolve_project_ref` (which remains a pure resolver). `test_build_cockpit_snapshot_writes_breadcrumb_when_record_open` and `test_build_cockpit_snapshot_skips_breadcrumb_when_record_open_false` prove the gate. PASS.
- `detect_project` (mcp/project.py): `write_breadcrumb(git_root)` added only inside `if git_root and git_root.name:`. `test_detect_project_writes_breadcrumb_on_git_root_branch` proves the write; `test_detect_project_does_not_write_breadcrumb_on_cwd_name_fallback` and `test_detect_project_does_not_write_breadcrumb_on_default_fallback` prove no-write on both fallback paths. PASS.

## 5. Fail-soft guarantee

`tests/unit/test_project_breadcrumb.py` proves:
- missing file -> `None`, no raise (`test_read_returns_none_when_no_file_exists`)
- corrupt JSON -> `None`, no raise (`test_read_returns_none_on_corrupt_json`)
- stale root_path (deleted/moved) -> `None`, no raise (`test_read_returns_none_when_stored_root_path_missing`)
- write failure (patched `Path.mkdir` to raise) -> silent no-op, no raise (`test_write_is_best_effort_and_never_raises`)

All fail-soft scenarios from the spec are backed by passing tests. PASS.

## 6. Full suite

`.venv/bin/python -m pytest -q` → **232 passed**, 0 failed, 0 skipped (305 warnings, all pre-existing `datetime.utcnow()` deprecation noise unrelated to this change). Matches the expected count from apply-progress (216 baseline -> 232).

## Verdict

Implementation matches spec and design. Safe to archive.
