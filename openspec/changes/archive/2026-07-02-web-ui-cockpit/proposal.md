# Proposal: Web UI Cockpit

## Intent

### Problem

The Aki Cockpit today is terminal-only: project registry, keyboard drill-down
navigation, and the read-only audit engine all live behind Rich-rendered
console panels (`aki cockpit`, `aki cockpit -i`). This works for terminal-native
operators but excludes browser-based inspection, shareable views over local
network sessions, and any workflow where a user wants to glance at project
health without a TTY. A Web UI was explicitly deferred as a non-goal in the
original design (`docs/superpowers/specs/2026-07-01-aki-cockpit-operational-design.md`);
it is now greenlit as a follow-up slice.

### Why now

The domain layer is already Web-ready. `cockpit/registry.py` and
`cockpit/audit/{base,report}.py` are CLI-decoupled and reusable as-is, so the
incremental cost of a read-only Web surface is bounded to a new HTTP/rendering
layer rather than a domain rewrite. Building it now — while the cockpit data
model is fresh — avoids re-learning the snapshot/finding shapes later.

### Success looks like

- `aki cockpit --web` starts a local HTTP server bound to localhost that serves
  a read-only view of the project registry, per-project drill-down, and audit
  reports — mirroring the information the terminal cockpit already exposes.
- Zero mutation paths: the Web UI can display but never modify registry rows,
  never trigger audits-with-writes, and never expose autofix.
- The terminal cockpit remains fully functional and unchanged in behavior.

## Scope

### In scope

- New optional dependencies: **FastAPI + uvicorn** (small local API/SSR layer,
  consistent with the existing pydantic/SQLAlchemy style).
- New CLI entrypoint `aki cockpit --web`, symmetric with the existing
  `--interactive`/`-i` flag in `cockpit_callback`.
- A thin service/API layer bridging the reusable domain functions
  (`registry.list_projects`, audit `run_registered_passes` / `render_markdown`)
  to HTTP responses — JSON endpoints and/or server-rendered HTML.
- Read-only views: project list, per-project drill-down (mirroring the 4-panel
  terminal layout), and audit report rendering.
- A narrow, additive host/port configuration surface (defaulting to
  `127.0.0.1` and a fixed default port) that does NOT edit existing logic in
  `src/agentos/core/config.py`.
- Tests for each phase (Strict TDD mode is active).

### Out of scope (non-goals)

- **`--autofix` / any mutation endpoint.** The Web UI is strictly read-only.
  No registry writes, no audit persistence triggered from the browser, no
  autofix. This stays out of scope, explicitly.
- Binding to `0.0.0.0` or any non-localhost interface. Local-only by default;
  remote/multi-host access is not part of this slice.
- Editing `src/agentos/core/config.py` (owned by a concurrent agent). Any
  config need is satisfied additively.
- Authentication, multi-user sessions, TLS, or hosting concerns.
- A heavyweight static SPA / client-side framework — no precedent in the repo,
  not a first-slice investment.
- Reworking or replacing the terminal cockpit.
- Reusing `navigation.py`'s prompt loop (its view-state shape only informs
  route design; the loop itself is not portable to HTTP).

## Approach

Server-rendered read-only Web UI on FastAPI + uvicorn, delivered in three
reviewable phases. Phase A must land and be reviewed before B/C, because it
introduces a new dependency and an unproven-in-this-repo server pattern.

### Phase A — Scaffold (small)

- Add FastAPI + uvicorn to `pyproject.toml`.
- Add `aki cockpit --web` that spins up a localhost-bound uvicorn server.
- One JSON endpoint (project list via `registry.list_projects`) + a health
  check. Proves the plumbing end-to-end.
- Additive host/port config surface with safe localhost defaults.

### Phase B — Drill-down + HTML (medium)

- Project detail / drill-down endpoints reusing the cockpit snapshot data and
  audit findings.
- Server-rendered HTML (Jinja2 or htmx-style) mirroring the 4-panel terminal
  layout. Route shape can borrow from `CockpitUIState`
  (e.g. `/project/{key}/panel/{panel_id}`).

### Phase C — Audit report view (small)

- Read-only audit report view: render existing audit markdown (or convert to
  HTML). No autofix, no persistence triggers from the browser.

### Rationale

- **FastAPI + uvicorn over a SPA or Flask**: matches existing pydantic style,
  minimal boilerplate for a small local surface, first-class async and JSON,
  and server-side rendering keeps the frontend footprint near zero.
- **Reuse domain, add rendering**: `registry.py` and `audit/{base,report}.py`
  are reused unchanged; only a new HTTP/render layer is added. The Rich-panel
  renderers in `cli/cockpit.py` are NOT reusable (they emit console markup),
  so a parallel HTML/JSON rendering path is created rather than retrofitted.
- **Phased, multi-PR**: isolates new-dependency risk in a small reviewable
  Phase A before building drill-down and audit views on top.
- **Localhost-only by default**: read-only does not mean safe-to-expose;
  binding to localhost avoids accidentally serving project metadata to the
  local network. Any change to this default requires an explicit security
  rationale in design.

## Open questions / risks

- **Config integration boundary**: exact additive host/port surface must be
  designed without touching `core/config.py`; the design phase should specify
  this narrowly (e.g. CLI flags + a small dedicated settings object).
- **Rendering choice (JSON API vs. Jinja2 vs. htmx)**: deferred to spec/design;
  Phase B needs a concrete decision. Server-rendered HTML is the default lean.
- **Snapshot reuse shape**: `build_cockpit_snapshot` returns Rich markup, not
  data — design must confirm whether to extract a data-only snapshot function
  or serialize upstream domain structures directly.
- **New dependency footprint**: FastAPI + uvicorn pull transitive deps; confirm
  acceptable for the project's install profile.
