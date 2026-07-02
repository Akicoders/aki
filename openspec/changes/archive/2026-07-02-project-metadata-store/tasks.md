# Tasks: Project Metadata Store (last-project breadcrumb)

Strict TDD mode active. Test command: `.venv/bin/python -m pytest -q`.
Each numbered task pair is a RED step (write failing test) followed by a GREEN
step (minimum code to pass). Do not write production code before its test.

Delivery: **single PR, not chained/stacked** (see Review Workload Forecast below).

---

## 1. Module — `src/agentos/core/project_breadcrumb.py`

Spec: Fail-Soft Breadcrumb Handling; Breadcrumb Write on Positive Project Resolution.
Design: §3 (module), §7 ADR-5.

- [x] 1.1 RED — `tests/core/test_project_breadcrumb.py`: write test 1 (write-then-read
      round-trips to the same resolved `root_path`), using `tmp_path` +
      `monkeypatch.setenv("HOME", ...)`. Run pytest, confirm it fails (`ImportError`
      or `AttributeError` — module doesn't exist yet).
- [x] 1.2 GREEN — create `src/agentos/core/project_breadcrumb.py` with
      `write_breadcrumb(root_path: Path) -> None` and
      `read_breadcrumb() -> Optional[Path]` per design §3 exact implementation.
      Run pytest, confirm test 1 passes.
- [x] 1.3 RED — add test 2: `read_breadcrumb()` returns `None` when no file exists.
      Confirm it already passes or fails appropriately, then proceed (should pass
      given §3 impl — if so, mark as regression-guard, not a new RED).
- [x] 1.4 RED — add test 3: `read_breadcrumb()` returns `None` on corrupt/invalid
      JSON content in the breadcrumb file.
- [x] 1.5 RED — add test 4: `read_breadcrumb()` returns `None` when the stored
      `root_path` no longer exists on disk (stale/deleted project).
- [x] 1.6 RED — add test 5: `write_breadcrumb()` creates `~/.aki/` when the
      directory is absent.
- [x] 1.7 RED — add test 6: `write_breadcrumb()` is best-effort — patch
      `Path.mkdir`/`Path.write_text` (or point `HOME` at a file, not a dir) to raise,
      assert no exception propagates and the call is a silent no-op.
- [x] 1.8 RED — add test 7: `updated_at` field is present in the written JSON and
      parses as ISO 8601 (`datetime.fromisoformat`).
- [x] 1.9 GREEN — run full `test_project_breadcrumb.py` suite, fix any gaps in the
      module implementation (should already satisfy tests 3-8 per §3 design; this
      step is verification, not new logic) until all pass.

## 2. Config integration — `_iter_env_search_roots` (config.py)

Spec: Breadcrumb as Last-Resort `.env` Search Candidate.
Design: §5 (exact additive edit — one import + one 3-line branch, no other change).

- [x] 2.1 RED — `tests/core/test_config.py` (or existing config test file): add test 8
      — `_iter_env_search_roots` yields the breadcrumb root **last**, and only when
      `read_breadcrumb()` resolves to a non-`None` path; use `monkeypatch` on `HOME`
      and `cwd`/`start` to isolate. Confirm it fails (breadcrumb not yet consulted).
- [x] 2.2 GREEN — edit `src/agentos/core/config.py`: add
      `from agentos.core.project_breadcrumb import read_breadcrumb` at module top,
      and the exact 3-line branch from design §5 immediately before `return roots`
      in `_iter_env_search_roots`. No other change to this file — do not touch
      `MemoryConfig.db_path` or any other default. Run pytest, confirm test 8 passes.
- [x] 2.3 Regression check — run the full existing `test_config.py` suite to confirm
      the additive branch changes no prior candidate ordering when no breadcrumb
      exists (dedup via `add_root`'s `seen` set holds).

## 3. Write call site — Cockpit `build_cockpit_snapshot`

Spec: Breadcrumb Write on Positive Project Resolution (CLI scenario).
Design: §4a, ADR-4.

- [x] 3.1 RED — add test 10 to the relevant cockpit test file: `build_cockpit_snapshot(...,
      record_open=True)` calls `write_breadcrumb(project.root_path)`; assert via a
      spy/monkeypatch on `project_breadcrumb.write_breadcrumb`. Also assert
      `record_open=False` does NOT call it. Confirm both assertions fail (or the
      "does not call" half trivially passes and the "does call" half fails).
- [x] 3.2 GREEN — edit `src/agentos/cli/cockpit.py`: inside the existing
      `if record_open:` block in `build_cockpit_snapshot`, add
      `write_breadcrumb(project.root_path)` immediately after the existing
      `registry.upsert_project(...)` call, per design §4a. Add the corresponding
      import. Run pytest, confirm test 10 passes.

## 4. Write call site — MCP `detect_project`

Spec: Breadcrumb Write on Positive Project Resolution (MCP scenario).
Design: §4b, ADR-3.

- [x] 4.1 RED — add test 9 to the MCP project test file: `detect_project()` calls
      `write_breadcrumb(git_root)` only inside the `if git_root and git_root.name:`
      branch; assert NO call on the cwd-name fallback path and NO call on the
      `"default"` fallback path (use monkeypatch/spy on
      `project_breadcrumb.write_breadcrumb`). Confirm it fails.
- [x] 4.2 GREEN — edit `src/agentos/mcp/project.py`: inside the
      `if git_root and git_root.name:` branch of `detect_project`, add
      `write_breadcrumb(git_root)` before `return git_root.name`, per design §4b.
      Add the corresponding import. Run pytest, confirm test 9 passes, and confirm
      the fallback-path negative assertions still hold.

## 5. Integration tests — end-to-end bootstrap

Spec: both "Breadcrumb as Last-Resort" scenarios (unrelated-cwd bootstrap,
earlier-candidate-wins precedence).
Design: §6 (data flow), §8 tests 11-12.

- [x] 5.1 RED — add test 11 to an integration test module: create a repo dir with a
      real `.env`; write a breadcrumb (via `write_breadcrumb`) pointing at it;
      `chdir` to an unrelated tmp dir with no `.git` ancestor and no `.env`; call
      `load_runtime_env()`; assert the repo's `.env` was loaded via the breadcrumb
      candidate. Confirm it fails before task 2's GREEN would be needed (should
      already pass once task 2 lands — write this test to lock behavior, run it
      against current tree to confirm intended RED/GREEN state).
- [x] 5.2 GREEN — no new production code expected (covered by task 2); run pytest,
      confirm test 11 passes given the task 2 config integration. If it fails,
      the fix belongs in task 2's code, not a new abstraction.
- [x] 5.3 RED — add test 12 (precedence guard): cwd/git context DOES contain a
      valid `.env`; a breadcrumb also exists pointing to a different, unrelated
      root; assert the current-context `.env` wins and the breadcrumb is not
      consulted for the result (breadcrumb never overrides current context).
- [x] 5.4 GREEN — run pytest, confirm test 12 passes (should already hold given
      §5's append-last ordering; this step verifies, doesn't add new logic).

## 6. Full-suite verification

- [x] 6.1 Run `.venv/bin/python -m pytest -q` for the full repo test suite (not just
      the new files) to confirm no regression in existing cockpit/MCP/config tests.
- [x] 6.2 Confirm rollback plan (design §9) is accurate: deleting
      `project_breadcrumb.py`, the two single-line write calls, and the 4-line
      config branch + import restores prior behavior with no other cleanup needed.

---

## Traceability (task -> spec requirement)

| Task | Spec Requirement |
|------|-------------------|
| 1.1-1.9 | Fail-Soft Breadcrumb Handling |
| 2.1-2.3 | Breadcrumb as Last-Resort `.env` Search Candidate |
| 3.1-3.2 | Breadcrumb Write on Positive Project Resolution (CLI) |
| 4.1-4.2 | Breadcrumb Write on Positive Project Resolution (MCP) |
| 5.1-5.4 | Breadcrumb as Last-Resort `.env` Search Candidate (integration) |
| 6.1-6.2 | Non-Goals (regression + rollback guard) |

## Parallelization

- Task 1 (module) is a hard prerequisite for tasks 2, 3, 4, 5 — sequential first.
- Tasks 3 and 4 (the two write call sites) are independent of each other and of
  task 2 once task 1 lands — can run in parallel by two engineers/agents if
  desired, but both must land before task 5's integration tests are meaningful.
- Task 2 (config read integration) can run in parallel with tasks 3/4 — it only
  depends on task 1, not on the write call sites.
- Task 5 (integration) depends on tasks 1, 2, 3, 4 all being GREEN.
- Task 6 is strictly last.

Given SMALL total surface (1 new module + 2 one-line call-site edits + 1
four-line config branch), sequential single-agent execution is recommended in
practice over parallelizing 3/4 — coordination overhead would exceed the time
saved.

---

## Review Workload Forecast

- **Estimated changed lines**: ~15-20 production lines (new module ~40 lines
  including docstring/imports, cockpit +2 lines, mcp/project.py +2 lines,
  config.py +4 lines + 1 import) plus test files (~150-200 lines across 5
  test files/additions). Production diff is well under the 400-line threshold.
- **Files touched (production)**: 1 new file
  (`src/agentos/core/project_breadcrumb.py`), 3 edited files
  (`src/agentos/cli/cockpit.py`, `src/agentos/mcp/project.py`,
  `src/agentos/core/config.py`), each edit additive-only and independently
  revertible per design §9 rollback plan.
- **Chained PRs recommended**: No.
- **400-line budget risk**: Low.
- **Decision needed before apply**: No.
- **Confirmation of proposal's delivery note**: Holds. Design's final shape
  (new module + 2 write-site edits + 1 additive config.py branch) is smaller
  and more contained than a typical PR needing a split — no cross-cutting
  refactor, no schema change, no touched public API signatures. Single PR,
  not stacked, is still correct.
