# Proposal: project-audit-cockpit (Phase 3 + Phase 4)

Status: Proposed
Date: 2026-07-01
Artifact store: hybrid (openspec + engram)
Authoritative spec: `docs/superpowers/specs/2026-07-01-aki-cockpit-operational-design.md`

This is NOT a from-scratch design. It implements the next two phases of an
already-approved 5-phase design. Sections 6, 7, 8, 10, 13, and 14 of that doc
are the primary source of truth. This proposal frames intent, bounds scope, and
surfaces the architectural questions that `sdd-design` must resolve.

## 1. Intent

### Problem / why now
Aki's cockpit today is a set of static Typer commands that render a one-shot Rich
snapshot per invocation. Phases 1 and 2 (foundation + overview) are done and
landed in `src/agentos/cli/cockpit.py`. The cockpit shows state but the operator
cannot yet move through it fluidly, cannot switch between known projects, and has
no durable, structured audit of technical risk. The design doc's promise — "open
Aki, see the project, understand state, then go deeper" — stops at "see the
project". This change delivers the "go deeper" half.

### Success looks like
- An operator can move through overview and drill-down views with keyboard
  navigation instead of remembering four separate subcommand names.
- `aki projects browse` lists real known projects with actionable metadata and
  opens the selected project's cockpit, instead of showing a placeholder panel.
- `aki audit <project>` produces a deterministic, read-only markdown report at
  `docs/audits/YYYY-MM-DD-<project>-audit.md` AND an Engram record, built from
  named specialized passes that reuse existing check logic.
- No web surface, no autofix, no rewrite of the working Phase 1/2 overview.

## 2. Scope

### In scope — Phase 3: Drill-downs, browse, keyboard navigation
- Keyboard-navigable drill-down model per design section 6
  (`Tab`/arrows between panels, `j`/`k` within a list, `Enter` to open,
  `b` back, `g` overview, `r` refresh, `/` filter, `q` quit).
- Real `aki projects browse` per section 7: list known projects with columns
  (key, root path, branch, git dirty summary, SDD completeness, last memory
  activity, last audit date); search/filter; select-to-open; onboarding guidance
  when no projects are known.
- Lightweight persistent project registry (`ProjectRef` persistence) per section
  10 and phase 3 of section 14, keyed on canonical root path — the identity
  source browse reads from.

### In scope — Phase 4: Read-only audit engine
- `aki audit <project>` read-only command per section 8. No code modification, no
  autofix, no side effects except artifact persistence.
- Specialized audit-pass interface: each pass owns one technical area
  (tests/runtime, SDD completeness, git hygiene, env/config, MCP readiness,
  memory posture), emits the same `AuditFinding` schema, deterministic merge.
- Reuse `src/agentos/skills/code_intel.py` (`CodeIntelSkill.run_tests`,
  `run_lint`, `get_coverage`) as the execution base for the test/runtime pass
  instead of reimplementing subprocess calls.
- Markdown report generation with executive summary, snapshot metadata, P0–P3
  priority tables, findings by area, next actions, evidence appendix.
- Dual-sink persistence: local markdown + Engram (`audit/<project>/<timestamp>`
  immutable record and `audit/<project>/latest` pointer per section 8), with the
  section 12 partial-persistence error contract (non-zero exit if either sink
  fails).

### Out of scope (explicit — do not include)
- Web surface / web dashboard — frozen per design non-goals.
- `--autofix` — deferred to Phase 5 per design non-goals.
- Rewriting Phase 1/2 overview logic in `cockpit.py` — keep as-is unless a
  genuine interface change is required to support Phase 3/4.
- Replacing explicit commands (`doctor`, `recall`, `facts`, `mcp-config`,
  `sdd-init`); they stay scriptable and unchanged.

## 3. Current state: built vs. added

### Already built (Phase 1 + 2)
- Data models in `cockpit.py`: `ProjectRef`, `CockpitSnapshot`,
  `HealthCheckResult`, `ActionItem`, `MemorySummary`, `SDDSummary`, `GitSummary`.
- `resolve_project_ref` (git-root / marker / browse-fallback gating).
- `build_cockpit_snapshot` assembling git, SDD, memory, and the five health
  checks (tests placeholder, sdd, git, env, mcp).
- Overview rendering + four static drill-down renders (`render_cockpit_detail`
  for action/health/memory/sdd), wired as Typer subcommands
  `aki cockpit {action,health,memory,sdd}` in `main.py`.
- `render_projects_browse` — a placeholder panel only (no project list).
- Test coverage in `tests/unit/test_cockpit.py` for resolution, snapshot,
  a drill-down detail render, and the browse placeholder.

### This change adds
- Interaction layer: keyboard navigation over the existing snapshot/render
  functions (drill-down transitions, refresh, filter, quit).
- Persistent project registry backing a real browse list.
- Real `render_projects_browse` (list + filter + select-to-open).
- New audit subsystem: `AuditFinding` / `AuditReportRef` models, pass interface,
  concrete passes, deterministic merger, markdown writer, dual-sink persistence.
- `aki audit <project>` command wiring in `main.py`.

## 4. Approach and rationale

Extend the existing Typer + Rich architecture rather than rewrite it. The current
cockpit already cleanly separates snapshot assembly (`build_cockpit_snapshot`)
from rendering (`render_*`), which is the right seam: navigation and audit can be
layered on top of the same snapshot model without disturbing Phase 1/2 logic.

For Phase 4, reuse over reinvention: `CodeIntelSkill` already wraps
tests/lint/coverage as async subprocess calls with structured results — the
audit pass interface should consume it rather than shell out again. The design's
"same finding schema, deterministic merge" rule keeps audit output stable and
future-`--autofix`-compatible without building autofix now.

## 5. Key architectural questions for sdd-design

These are genuine forks the design phase must resolve; the proposal deliberately
does not decide them:

1. **Keyboard navigation mechanism (biggest fork).** The current cockpit is
   command-driven static Rich output, not a live TUI. The design keymap
   (section 6) implies a persistent screen. Options: (a) full live TUI via a new
   dependency (`textual`/`prompt-toolkit`) — richest UX but adds a dependency and
   forces reworking the Rich-panel snapshot-based testing strategy; (b) a
   lightweight interactive prompt loop over existing render functions — smaller,
   keeps golden/snapshot tests intact, but less "full-screen instrument panel".
   Explore recommends (b) unless design finds strong reason for (a). Design must
   choose and justify, and reconcile with section 13's golden/snapshot tests.

2. **Project registry persistence.** Where does `ProjectRef` live? Candidates:
   reuse the existing memory SQLite DB (`agentos.memory.database.Database`,
   already used for the memory panel), a dedicated small store, or Engram. Must
   key on canonical root path (design section 15 risk: directory names are
   unreliable) and populate from recently-opened, memory-bearing, audited, and
   SDD-root projects.

3. **Audit pass plugin interface.** Concrete shape of the pass contract: sync vs
   async (`CodeIntelSkill` is async), how a pass declares its area, how the
   deterministic merger orders findings, and how empty-pass / error-pass cases
   behave (design section 13 contract tests require these to be defined).

4. **Test-posture reuse in audit vs. overview.** The overview `tests` health check
   is a deliberate placeholder that does NOT run the suite (section 9: don't run
   tests on every open). The audit test pass DOES run via `CodeIntelSkill`.
   Design should define how (or whether) an audit result refreshes the overview's
   cached test posture without violating the "don't auto-run on open" rule.

5. **Dual-sink failure semantics wiring.** Section 12 requires non-zero exit if
   either the markdown write or the Engram write fails, preserving whatever
   partial artifact was produced. Design must specify the ordering and the
   exact operator-facing failure classes.

## 6. Acceptance criteria

- Keyboard navigation moves between panels and into/out of drill-downs and can
  refresh and quit, per section 6 keymap; the Phase 1/2 overview output is
  unchanged when navigation is not used.
- `aki projects browse` lists known projects with the section 7 columns, supports
  filter/search, opens the selected project's cockpit, and shows onboarding
  guidance (not an empty table) when no projects are known.
- The project registry persists across invocations keyed on canonical root path.
- `aki audit <project>` runs the named passes, emits a uniform `AuditFinding`
  schema, and merges deterministically.
- The audit writes `docs/audits/YYYY-MM-DD-<project>-audit.md` with executive
  summary, snapshot metadata, P0–P3 priority tables, findings by area, next
  actions, and evidence appendix.
- The audit persists to Engram (`audit/<project>/<timestamp>` +
  `audit/<project>/latest`); if either sink fails, the command exits non-zero and
  reports the failed stage while preserving any partial artifact.
- The audit performs no writes outside its own artifact outputs (read-only
  guarantee).
- No web surface and no `--autofix` are introduced.
- New unit / CLI / golden tests cover navigation transitions, browse listing and
  gating, audit finding ranking, markdown output, and the pass-schema contract,
  per section 13.

## 7. Risks / open questions

- The keyboard-navigation decision (Q1) is the highest-leverage and highest-risk
  choice: a `textual` TUI reshapes the testing strategy and adds a dependency; a
  prompt loop may under-deliver the "instrument panel" feel. Must be settled in
  design before tasks.
- Registry persistence choice (Q2) risks a second source of truth for project
  identity if not aligned with existing memory storage.
- Dual-sink persistence increases audit failure modes (design section 15); the
  error contract must be explicit and tested.
- Reusing `CodeIntelSkill` (async) inside a Typer command needs an event-loop
  bridge decision.

## Next
`sdd-spec` and `sdd-design` can run in parallel. Design must resolve section 5's
five questions; spec formalizes the section 6 acceptance criteria into testable
requirements.
