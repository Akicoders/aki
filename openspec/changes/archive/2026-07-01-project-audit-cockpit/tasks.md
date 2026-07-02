# Tasks: project-audit-cockpit

Ordered checklist derived from spec (`sdd/project-audit-cockpit/spec`) and design
(`sdd/project-audit-cockpit/design`). Each task lists its spec requirement and
parallelization eligibility. `[S]` = sequential (has unresolved dependency),
`[P]` = safe to parallelize once its listed dependency is done.

## 0. Cross-cutting constraint (read before starting)

**RISK — do not action as a task:** Another agent/session is concurrently modifying
`.env` loading / environment config bootstrap in this repo, outside this SDD change.
The audit engine's "env/config" pass (task 6.4) MUST be **read-only**: it may call
`agentos.core.config.get_config()` (already an existing import in `cockpit.py`) to
inspect current config state, but MUST NOT modify `get_config`, its loading
mechanism, `.env` parsing, or any config bootstrap file. No task in this checklist
touches `src/agentos/core/config.py`'s write/load path. If implementation later
discovers env/config pass logic requires changing that mechanism, STOP and flag it
back to the user as a merge-conflict risk rather than editing the file.

## 1. Registry schema (foundation — everything depends on this)

- [x] 1.1 `[S]` Add `ProjectRefModel` (SQLAlchemy) + `ProjectRefRecord` (Pydantic,
      `from_model`/`to_model`) to `src/agentos/memory/models.py`, mirroring the
      `MemoryFactModel` split. Fields: key, root_path, source, last_opened_at,
      last_audit_at, last_memory_activity_at.
      — Spec: "Persistent ProjectRef Registry"
- [x] 1.2 `[S]` Import `ProjectRefModel` in `src/agentos/memory/database.py` so
      `Base.metadata.create_all` picks it up (no Alembic; additive schema only).
      — Spec: "Persistent ProjectRef Registry"; Design: "Schema migration" decision
- [x] 1.3 `[P]` (after 1.1/1.2) Unit tests: table created via `init_db` on a tmp
      sqlite DB; round-trip `from_model`/`to_model`.
      — Design §13 Unit layer

## 2. Registry CRUD/query layer

- [x] 2.1 `[S]` (after 1.2) Create `src/agentos/cockpit/registry.py`:
      `upsert_project`, `list_projects`, `touch_last_opened`, `touch_last_audit`,
      keyed on canonical `root_path` (resolve symlinks/relative paths before key
      lookup to avoid duplicate rows).
      — Spec: "Persistent ProjectRef Registry" scenarios (insert/update on open,
      no duplicate rows for equivalent paths, last_audit_at update)
- [x] 2.2 `[P]` (after 2.1) Unit tests: upsert idempotency, canonical-path
      dedup, last_opened_at/last_audit_at mutation.
      — Design §13 Unit layer

## 3. Wire registry into existing cockpit snapshot build

- [x] 3.1 `[S]` (after 2.1) Modify `src/agentos/cli/cockpit.py`: call
      `registry.upsert_project` inside `build_cockpit_snapshot`; keep the
      existing `ProjectRef` dataclass exported unchanged (registry model is a
      separate persistence-layer concern, not a rename).
      — Spec: "Opening a project inserts or updates its ProjectRef"

## 4. `aki projects browse` command

- [x] 4.1 `[S]` (after 2.1) Add `aki projects browse` in
      `src/agentos/cli/main.py`: real registry table (columns: key, root path,
      branch, git dirty summary, SDD completeness, last memory activity, last
      audit date).
      — Spec: "`aki projects browse` Listing"
- [x] 4.2 `[S]` (after 4.1) Onboarding empty state: no ProjectRef rows renders
      guidance instead of an empty table.
      — Spec: "Onboarding empty state"
- [x] 4.3 `[S]` (after 4.1) Search/filter by key/root-path substring; explicit
      "no matches" message when filter yields nothing.
      — Spec: "Search and Filter"
- [x] 4.4 `[S]` (after 4.1) Select-to-open: selecting a project opens its
      cockpit overview.
      — Spec: "Select-to-Open"
- [x] 4.5 `[P]` (after 4.1-4.4) Golden/snapshot tests for browse table
      rendering (populated, empty-state, filtered, no-matches).
      — Design §13 Golden layer (covered via CliRunner output assertions in
      tests/unit/test_cockpit.py rather than separate golden fixtures)

## 5. Prompt-loop drill-down navigation

- [x] 5.1 `[S]` (after 3.1) Create `src/agentos/cockpit/navigation.py`:
      `CockpitUIState` dataclass (current_view, selected_panel,
      selected_index, filter_query, refresh_in_progress) and
      `run_cockpit_loop(console, project)`.
      — Design: "Interfaces / Contracts"
- [x] 5.2 `[S]` (after 5.1) Implement keymap: Tab/arrows between panels, j/k
      within list, Enter drills (overview -> panel detail -> item detail,
      capped at item detail), b back one level, g jump to overview, r
      refresh (re-run `build_cockpit_snapshot`), `/` filter, q exit code 0.
      — Spec: "Keymap" scenarios
- [x] 5.3 `[S]` (after 5.2) Header persistence: project header (name, root,
      branch, dirty, last refresh) stays visible at every drill-down depth.
      — Spec: "Header Persistence During Navigation"
- [x] 5.4 `[S]` (after 5.1) Wire `aki cockpit --interactive` in
      `src/agentos/cli/main.py` to `run_cockpit_loop`; confirm direct
      one-shot subcommands (e.g. `aki cockpit health`) remain unchanged
      (no loop invocation).
      — Spec: "Direct Typer subcommand invocation ... keeps static one-shot
      Phase 1/2 output unchanged"
- [x] 5.5 `[P]` (after 5.2-5.4) Integration tests for the loop: scripted key
      sequences (Enter/Enter/b/g/r/q) against `CliRunner` input, asserting
      view transitions and exit code.
      — Design §13 Integration layer

## 6. Audit pass framework + the 6 passes

- [x] 6.1 `[S]` (after 1.1) Create `src/agentos/cockpit/audit/base.py`:
      `AuditPass` protocol, `AuditContext`, `AuditFinding` dataclass (priority,
      category, title, evidence, recommendation, autofixable_later),
      `AuditReportRef`, `merge_findings` (deterministic merge/ranking),
      `PASS_REGISTRY`. Wrap `pass.run()` calls so a raising pass becomes one
      P2 "pass failed" finding instead of crashing the audit.
      — Spec: "Uniform AuditFinding Schema", "Deterministic Merge and Priority
      Ranking", "Error Handling — Failure Classes" (audit pass failure)
- [x] 6.2 `[P]` (after 6.1) Tests pass in
      `src/agentos/cockpit/audit/passes.py`: bridges `CodeIntelSkill`
      (`run_tests`/`run_lint`/`get_coverage`) via `asyncio.run` at this sync
      call site only.
      — Spec: "Test/runtime pass reuses CodeIntelSkill... instead of new
      subprocess calls"
- [x] 6.3 `[P]` (after 6.1) SDD completeness pass: reuse
      `detect_sdd_artifacts`/`load_sdd_artifact` from `agentos.sdd.detector`.
      — Spec: "Read-Only Audit Passes"
- [x] 6.4 `[P]` (after 6.1) Env/config pass — READ-ONLY: call existing
      `agentos.core.config.get_config()` to inspect current config; emit
      findings only, no writes to config files or env-loading code. Do NOT
      modify `src/agentos/core/config.py` (see section 0 constraint).
      — Spec: "Read-Only Audit Passes" ("no side effects beyond audit's own
      artifacts")
- [x] 6.5 `[P]` (after 6.1) Git hygiene pass: reuse existing git-dirty/branch
      probing already used by cockpit snapshot (`GitPython` `Repo`).
      — Spec: "Read-Only Audit Passes"
- [x] 6.6 `[P]` (after 6.1) MCP readiness pass: reuse
      `_get_host_config_path`/`_get_mcp_snippet` from `agentos.cli.mcp_hosts`.
      — Spec: "Read-Only Audit Passes"
- [x] 6.7 `[P]` (after 6.1) Memory posture pass: reuse existing
      `MemoryFactModel`/`MemoryEventModel` queries already used by cockpit
      snapshot for last-activity signals.
      — Spec: "Read-Only Audit Passes"
- [x] 6.8 `[S]` (after 6.2-6.7) Contract tests parametrized over
      `PASS_REGISTRY`: every pass emits the six-field schema; empty pass
      returns `[]` without failing; one pass raising is isolated, others
      still run.
      — Spec: "Uniform AuditFinding Schema" scenarios; Design §13 Contract
      layer

## 7. Audit report generation + dual-sink persistence

- [x] 7.1 `[S]` (after 6.8) Create `src/agentos/cockpit/audit/report.py`:
      `render_markdown` producing `docs/audits/YYYY-MM-DD-<project>-audit.md`
      with the six required sections in order (executive summary, snapshot
      metadata, P0-P3 tables, findings by area, next actions, evidence
      appendix).
      — Spec: "Markdown Report Generation"
- [x] 7.2 `[S]` (after 7.1) Dual-sink persistence: write local markdown file
      AND Engram (`audit/<project>/<timestamp>` immutable +
      `audit/<project>/latest` pointer). Either sink failing -> non-zero
      exit, operator-facing message naming the failed stage, partial
      artifact preserved.
      — Spec: "Dual-Sink Persistence" (all three scenarios)
- [x] 7.3 `[S]` (after 7.2) Failure classification: project resolution
      failure (exit non-zero, no passes attempted), health probe failure
      (marked unknown/failing, audit still proceeds), audit pass failure
      (already isolated per 6.1/6.8), persistence failure (7.2).
      — Spec: "Error Handling — Failure Classes"
- [x] 7.4 `[S]` (after 7.1-7.3) Wire `aki audit <project>` command in
      `src/agentos/cli/main.py`: resolve project ref -> registry upsert ->
      build `AuditContext` -> run `PASS_REGISTRY` -> `merge_findings` ->
      `render_markdown` -> dual-sink persist -> exit code per outcome; on
      success, call `registry.touch_last_audit`.
      — Spec: "Persistent ProjectRef Registry" (audit updates
      last_audit_at); Data Flow in design.md
- [x] 7.5 `[P]` (after 7.4) Integration tests: `CliRunner` invocation of
      `aki audit <project>` — artifact write assertion, non-zero exit on
      monkeypatched Engram sink failure, non-zero exit on monkeypatched
      local-write failure, exit 0 with both artifacts retrievable on success.
      — Spec: "Dual-Sink Persistence" scenarios; Design §13 Integration layer
- [x] 7.6 `[P]` (after 7.1) Golden/snapshot tests for the rendered markdown
      report (fixed fixture findings -> exact section order/content).
      — Design §13 Golden layer

## 8. Fixture repos + full test sweep

- [x] 8.1 `[P]` (after 3-7, independent of exact task order) Build fixture
      repos for audit contract/integration tests: one clean/healthy repo,
      one with SDD gaps, one with git-dirty state, one with a failing pass
      to exercise isolation.
      — Design §13 Integration/Contract layers
- [x] 8.2 `[S]` (after all above) Full test sweep: `pytest` unit + contract +
      integration + golden suites green; run `aki cockpit --interactive` and
      `aki audit <project>` manually against the fixture repos as a smoke
      check.

## Review Workload Forecast

- Estimated changed/added lines: **~950-1150** across 8 new files
  (`registry.py` ~120, `navigation.py` ~180, `audit/base.py` ~140,
  `audit/passes.py` ~300, `audit/report.py` ~150) + modifications
  (`models.py` +~60, `database.py` +~5, `cli/main.py` +~150,
  `cli/cockpit.py` +~20) + new test files (~400-500 lines, often excluded
  from "production diff" budgets but still reviewer load).
- **400-line budget risk: High.** Production code alone (excluding tests)
  is estimated at ~975 lines, well past the 400-line single-PR guidance,
  and the work spans three logically separable capabilities (registry +
  browse, drill-down nav, audit engine + report).
- **Chained PRs recommended: Yes.** Natural slice boundaries:
  1. Registry schema + CRUD + `aki projects browse` (sections 1-4)
  2. Drill-down navigation (section 5)
  3. Audit pass framework + 6 passes + report + dual-sink + `aki audit`
     command (sections 6-7)
  4. Fixture repos + full sweep (section 8) can ride with PR 3 or land as
     a small follow-up.
- **Decision needed before apply: Yes.** Per `delivery_strategy:
  ask-on-risk`, the orchestrator must stop before `sdd-apply` and ask
  whether to split into chained PRs (and which `chain_strategy` —
  `stacked-to-main` vs `feature-branch-chain`) or proceed under a
  `size:exception`.
