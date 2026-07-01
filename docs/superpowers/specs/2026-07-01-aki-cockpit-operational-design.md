# Aki Operational Cockpit Design

Status: Approved
Date: 2026-07-01
Slice: CLI/TUI operational cockpit

This slice turns Aki's primary surface from a set of useful commands into a project cockpit. The default entry should open an active project when one is clearly detected, show operational state in one screen, and support deeper read-first workflows without forcing the user to remember command names first. The web surface stays frozen in this slice except for possible future informational reuse.

## 1. Problem Statement

Aki currently has memory, MCP, doctor, and SDD-related commands, but the operator still has to assemble project state manually.

Current limitations:

- Aki feels like a memory shell with utilities, not the home screen for technical work.
- The user must already know whether to run `doctor`, `recall`, `facts`, `mcp-config`, or inspect `docs/sdd/*` directly.
- Health, memory, and workflow state are fragmented across commands and files.
- There is no read-first operational overview that answers: what needs attention, what is healthy, and what should happen next.

The next slice should make Aki the first surface a developer opens for a project, especially in the terminal.

## 2. Goals / Non-Goals

### Goals

- Make `aki` open into an operational cockpit by default.
- Open the current project automatically when project context is clear.
- Provide a single overview screen with actionable operational signals.
- Support drill-down navigation without leaving the keyboard-first CLI/TUI flow.
- Add a browse flow for switching between known projects.
- Add a read-only `aki audit <project>` workflow that produces durable artifacts.
- Reuse existing Aki concepts where possible: project detection, SDD detection, memory, and health checks.

### Non-Goals

- Do not implement web product changes in this slice.
- Do not replace existing explicit commands such as `doctor`, `recall`, `facts`, `mcp-config`, or `sdd-init`.
- Do not introduce write automation from the cockpit overview.
- Do not ship `--autofix` in the first audit slice.
- Do not turn Aki into a general file manager or IDE replacement.
- Do not redesign the entire memory or MCP architecture.

## 3. Product Posture: Aki as Cockpit, Not Just Memory Shell

The product posture for this slice is explicit:

- Aki is the operational cockpit for a technical project.
- Memory remains foundational, but it becomes one subsystem inside the cockpit.
- The CLI/TUI is the primary product surface.
- The web is secondary and frozen for now.

This changes the default mental model:

| Before | After |
|---|---|
| Aki is a memory-backed CLI | Aki is the terminal home screen for project operations |
| Memory retrieval is the primary workflow | Operational awareness plus memory is the primary workflow |
| The user remembers commands first | The product shows state first and commands second |

The cockpit must feel like an instrument panel for technical work: dense, trustworthy, source-backed, and optimized for fast operator decisions.

## 4. Entry Behavior

`aki` with no subcommand becomes the cockpit entrypoint.

Resolution behavior:

1. If the current working directory is inside a git repository, open the cockpit for the git root project.
2. If there is no git root but the current working directory is a recognizable project root, open the cockpit for that directory.
3. If current project context is not clear, fall back to `aki projects browse`.

For this slice, "recognizable project root" means the directory has enough evidence to treat it as a project, such as one or more of:

- `.git/`
- `pyproject.toml`, `package.json`, or equivalent root marker
- `docs/sdd/`, `.sdd/`, or `openspec/`
- prior Aki project registration with a known root path

Important behavior rules:

- Do not treat any arbitrary directory name as a valid project.
- If the path is ambiguous, choose browse instead of guessing.
- Existing explicit commands remain scriptable and unchanged.

## 5. Main Overview Layout

The cockpit overview is a single-screen summary with four top-level sections:

1. Action Required
2. Project Health
3. Memory
4. SDD Status

Recommended layout:

- Wide terminals: two-column grid with four panels.
- Narrow terminals: stacked panels in the order above.
- Persistent top header: project name, root path, branch, dirty state, last refresh time.
- Persistent footer: available shortcuts and current view.

### Action Required

Purpose: show the few items that need operator attention now.

Content:

- Blocking test failures
- Missing SDD artifacts
- Dirty git state that blocks safe work
- Broken env/config state
- Missing MCP readiness for the selected host target, defaulting to OpenCode
- Missing audit artifact or stale audit metadata

Each row should include:

- severity
- short title
- evidence summary
- target drill-down or command

### Project Health

Purpose: show the current status of operational checks at a glance.

Content:

- tests
- SDD completeness
- git status
- env/config
- MCP readiness

Each check should show:

- status: healthy, warning, failing, or unknown
- last updated time
- short detail

### Memory

Purpose: keep durable context visible without making the screen chat-first.

Content:

- recent durable facts
- latest important decision
- recent procedure or workflow memory
- last memory activity timestamp
- last audit memory reference if available

This panel is not a transcript. It is a compact operational memory summary.

### SDD Status

Purpose: keep delivery structure visible.

Content:

- presence of `proposal`, `spec`, `design`, and `tasks`
- completeness summary
- latest modified artifact
- next missing artifact or next recommended step

The panel should make it obvious whether a project is operating with SDD discipline or drifting without it.

## 6. Drill-Down Navigation Model

The overview is the hub. Every panel must support a focused drill-down view.

Navigation model:

- `Tab` or arrow keys move between top-level panels.
- `j` / `k` move within a panel list.
- `Enter` opens the selected item or detail view.
- `b` returns to the previous view.
- `g` returns to overview.
- `r` refreshes the current snapshot.
- `/` opens search or filter when relevant.
- `q` exits.

Drill-down rules:

- Every detail view keeps the current project header visible.
- Detail views are read-first and evidence-first.
- A detail view can suggest a command, but it should not hide the underlying evidence.
- Navigation depth should stay shallow: overview -> panel detail -> item detail.

Initial drill-downs:

- Action Required detail: prioritized issues with direct next commands.
- Project Health detail: per-check evidence and last run metadata.
- Memory detail: searchable recent facts, decisions, procedures, and linked sources.
- SDD detail: artifact presence, previews, and missing-step guidance.

## 7. `aki projects browse`

`aki projects browse` is the fallback entry when the current project cannot be resolved and the explicit switcher for multi-project users.

Primary responsibilities:

- list known projects
- support search and filtering
- show enough metadata to choose the right project quickly
- open the selected project cockpit

Recommended list columns:

- project key
- root path
- branch
- git dirty summary
- SDD completeness
- last memory activity
- last audit date

Project sources may include:

- recently opened cockpit projects
- projects with stored Aki memory
- projects with prior audit artifacts
- projects with detected SDD roots
- manual additions in a later slice if needed

Behavior rules:

- If no projects are known, show onboarding guidance instead of an empty table.
- Browse should be fast and local-first.
- Browse is a selector, not a separate product area.

## 8. `aki audit <project>`

`aki audit <project>` is the first deep operational workflow in this slice.

### Purpose

Generate a read-only project audit that helps the operator understand technical risk, missing structure, and next actions.

### Scope for the first slice

- Read-only only
- No code modifications
- No automatic fixes
- No silent side effects except artifact persistence

### Audit model

The audit should run named specialized passes instead of one monolithic generic prompt.

Recommended audit passes:

- test and runtime posture
- SDD completeness and artifact quality
- git and repository hygiene
- env/config posture
- MCP readiness and host integration posture
- memory posture and memory gaps

Each pass should emit structured findings with:

- priority
- category
- title
- evidence
- recommendation
- autofixable later: yes or no

### Specialized agent/skills concept

The audit system should be extensible through specialized audit agents or skills.

Design rules:

- Each audit pass owns one technical area.
- Each pass emits the same structured finding schema.
- The report merger is deterministic and does not depend on free-form prose shape.
- New audit passes can be added later without redesigning the report format.

This keeps audits composable and prevents the first audit feature from collapsing into a single opaque LLM output.

### Report output

The report should be written as markdown to the audited project root:

`docs/audits/YYYY-MM-DD-<project>-audit.md`

Recommended report sections:

- executive summary
- snapshot metadata
- priority tables
- detailed findings by area
- recommended next actions
- appendix: evidence and command references

Priority tables should be explicit. Recommended grouping:

- P0: blockers
- P1: high priority
- P2: medium priority
- P3: low priority

Recommended columns:

- area
- finding
- evidence
- recommendation
- autofix later

### Persistence

Audit persistence is dual-sink by design:

- local markdown artifact in `docs/audits/...`
- Engram persistence for retrieval and later reuse

Recommended Engram storage model:

- immutable report record keyed by timestamp, for example `audit/<project>/<timestamp>`
- latest report pointer keyed by project, for example `audit/<project>/latest`

The Engram record should store:

- project key
- root path
- report path
- generated timestamp
- summary counts by priority
- structured findings summary

### `--autofix` as later step

`--autofix` is intentionally out of scope for the first audit slice.

When introduced later, it should:

- require a prior audit for the same project
- load the previous audit from Engram and local artifact memory
- target only explicitly supported findings
- require clear user confirmation before any write action

The first audit slice must establish trustworthy report structure before any automated fixing is allowed.

## 9. Health Checks Shown in Overview

The overview health section must include these checks.

### Tests

Show:

- last known test result
- freshness of that result
- whether the result is full suite, targeted suite, or unknown

Important design choice:

- Do not run the full test suite automatically on every cockpit open.
- Show cached last-known status by default.
- Allow explicit refresh or audit to recompute when needed.

### SDD Completeness

Show:

- whether SDD structure exists
- which core artifacts are present
- which are missing
- a simple completeness summary

This can reuse the current artifact detection model already present in Aki.

### Git Status

Show:

- current branch
- dirty or clean state
- modified count
- untracked count
- merge or conflict warning if present

This is operator-critical because it determines whether the project is safe to modify.

### Env/Config

Show:

- Python and `uv` availability
- `.env` presence when expected
- required API key presence
- config parse health
- lockfile presence where relevant

This should extend the spirit of the current `doctor` checks rather than duplicate incompatible logic.

### MCP Readiness

Show:

- whether `aki mcp` can start cleanly in a smoke path
- whether `aki mcp-config` can generate a valid host snippet
- whether the selected host target, defaulting to OpenCode, appears configured
- whether required local dependencies are available

MCP readiness should be visible because Aki's product value depends on host integration actually working.

## 10. Data Model / State Needed for the Cockpit

The cockpit needs a small but explicit state model.

### Persistent project registry

`ProjectRef`

- `key`: stable project identifier
- `root_path`: canonical filesystem root
- `source`: detected, remembered, audited, or manual
- `last_opened_at`
- `last_audit_at`
- `last_memory_activity_at`

Purpose:

- drives `aki projects browse`
- avoids path guessing from arbitrary directories
- ties project identity to a real root path

### Runtime snapshot

`CockpitSnapshot`

- `project`: `ProjectRef`
- `generated_at`
- `action_items[]`
- `health_checks[]`
- `memory_summary`
- `sdd_summary`
- `last_audit`

Purpose:

- one assembled view for overview rendering
- common input for TUI and future informational web reuse

### Health model

`HealthCheckResult`

- `id`: tests, sdd, git, env, mcp
- `status`: healthy, warning, failing, unknown
- `summary`
- `detail`
- `updated_at`
- `is_stale`
- `source`

Purpose:

- keeps every panel deterministic
- makes degraded states visible instead of implicit

### Audit model

`AuditFinding`

- `priority`
- `category`
- `title`
- `evidence`
- `recommendation`
- `autofixable_later`

`AuditReportRef`

- `project_key`
- `report_path`
- `engram_topic`
- `generated_at`
- `priority_counts`

Purpose:

- stable report format
- deterministic markdown generation
- future `--autofix` compatibility

### Session UI state

`CockpitUIState`

- `current_view`
- `selected_panel`
- `selected_index`
- `filter_query`
- `refresh_in_progress`

Purpose:

- keeps navigation predictable
- allows snapshot refresh without rebuilding the whole interaction model

## 11. UX Principles for a Unique Technical Cockpit

The cockpit should not look or behave like a chatbot wrapper.

Principles:

- Signal first, prompt second.
- Dense but legible. Show more operational value per screen than a generic assistant shell.
- Keyboard first. Every important action must be reachable without a mouse.
- Evidence first. Every warning or recommendation should point to why it exists.
- Read before write. The cockpit is primarily an observability and decision surface.
- Stable layout. Operators should build muscle memory quickly.
- Honest status. Unknown is better than fake green.
- Technical visual language. Favor structured panels, terse labels, timestamps, paths, and priority markers over decorative chrome.

The desired feel is closer to a lightweight operations console than to a conversational assistant.

## 12. Error Handling

Error handling should protect operator trust.

Rules:

- If current project detection is unclear, fall back to browse instead of guessing.
- If one health check fails to execute, mark only that check as `unknown` or `failing`; do not crash the cockpit.
- If the snapshot is partially stale, show stale timestamps explicitly.
- If audit generation partially succeeds, preserve whatever artifact was produced and report the exact failed stage.
- If local markdown persistence succeeds but Engram persistence fails, report partial persistence and exit `aki audit` with a non-zero status.
- If Engram succeeds but local file write fails, also return non-zero because the dual-sink contract was not met.
- Read-only commands must never mutate project files except for their own explicit artifact outputs.

Recommended failure classes:

- project resolution failure
- health probe failure
- external dependency failure
- audit pass failure
- persistence failure

Each class should surface a precise operator-facing message and the impacted area.

## 13. Testing Strategy

Testing must cover both command behavior and rendered artifacts.

### Unit tests

- project detection gating: open current project vs browse fallback
- snapshot assembly
- SDD completeness calculation
- health check mapping and stale-state behavior
- audit finding ranking and priority grouping

### CLI/TUI integration tests

- `aki` default entry from git root
- `aki` default entry from non-project directory
- `aki projects browse`
- `aki audit <project>` artifact generation
- keyboard navigation behavior for overview and drill-down transitions

### Golden/snapshot tests

- overview rendering for wide terminal
- overview rendering for narrow terminal
- markdown audit report output
- priority table formatting

### Fixture repos

Create fixture projects for:

- clean repo with complete SDD
- dirty repo with missing SDD artifacts
- repo with broken env/config
- repo with missing MCP readiness
- repo with stale or missing tests metadata

### Contract tests for specialized audit passes

- every pass emits the structured finding schema
- merger order is deterministic
- empty-pass and error-pass behavior is defined

## 14. Phased Implementation Recommendation

Recommended delivery order:

### Phase 1: Cockpit foundation

- define `ProjectRef`, `CockpitSnapshot`, and health result models
- add root `aki` entry behavior
- implement safe current-project resolution and browse fallback

### Phase 2: Overview screen

- build overview layout
- wire Action Required, Project Health, Memory, and SDD Status panels
- reuse existing SDD detection and doctor-style checks where possible

### Phase 3: Drill-downs and browse

- implement panel drill-down views
- implement `aki projects browse`
- add lightweight project registry persistence

### Phase 4: Read-only audit

- implement `aki audit <project>`
- add specialized audit pass interface
- generate markdown report
- persist report to `docs/audits/...` and Engram

### Phase 5: Later follow-up

- add `--autofix` based on prior audit memory
- optionally expose informational web surfaces backed by the same snapshot and audit models

This order keeps the first user-visible win small and coherent: open Aki, see the project, understand the state, then go deeper only when necessary.

## 15. Risks / Tradeoffs

- Defaulting `aki` to the cockpit changes user expectations from help-first to product-first. This is good for posture but must preserve explicit command discoverability.
- Startup checks can become slow if they eagerly run tests or full MCP smoke paths. Cached last-known status plus explicit refresh keeps the cockpit responsive.
- Project identity based only on directory names is unreliable. The registry must keep canonical root paths.
- A dense TUI can become noisy on narrow terminals. The stacked layout and shallow drill-down model reduce that risk.
- Dual persistence for audits improves durability but increases failure modes. The command must surface partial persistence clearly.
- Specialized audit passes improve trust and extensibility but require schema discipline and maintenance.
- Keeping the web frozen avoids distraction now, but later web reuse should consume the same snapshot model instead of creating a second source of truth.

## 16. Self-Review Pass

This document was reviewed for implementation ambiguity and scope drift.

Review outcomes:

- Entry behavior is concrete: open detected current project, otherwise browse.
- Project detection does not rely on arbitrary directory names alone.
- The overview sections are fixed and explicitly scoped.
- `aki audit <project>` is read-only in this slice.
- `--autofix` is explicitly deferred to a later phase.
- Web work is explicitly out of scope.
- Artifact paths, persistence expectations, and priority groupings are concrete.

No placeholders remain.
