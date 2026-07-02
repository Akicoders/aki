# Explore: Web UI Cockpit

## What

Explored feasibility/scope of a local read-only Web UI for the Aki Cockpit, building on the existing terminal cockpit (`registry.py`, `navigation.py`, `audit/*`, `cli/main.py`). No code written — investigation only.

## Why

Web UI was explicitly deferred as a non-goal in `docs/superpowers/specs/2026-07-01-aki-cockpit-operational-design.md`. User now wants it implemented next. `--autofix` remains out of scope for this request.

## Findings

1. **Framework dependency**: `pyproject.toml` has no web framework (no FastAPI/Flask/Starlette/uvicorn). Only `mcp>=1.2` (stdio JSON-RPC via `FastMCP(...).run(transport="stdio")` in `src/agentos/mcp/server.py`) — not HTTP. Recommend **FastAPI + uvicorn** (new deps) for a small local API/SSR layer, matching the codebase's existing pydantic/SQLAlchemy style. A static SPA is a heavier lift with no precedent — not recommended for a first slice.

2. **CLI entrypoint**: `aki cockpit --web` (or `aki web`) is natural, symmetric with the existing `--interactive`/`-i` flag in `cockpit_callback` (`src/agentos/cli/main.py:396-418`). Spins up a local uvicorn server bound to localhost: project list, drill-down panels, audit reports — strictly read-only, no mutation endpoints.

3. **Reuse potential**:
   - HIGH: `cockpit/registry.py` (list_projects, upsert_project, touch_last_*) — pure SQLAlchemy CRUD, zero CLI coupling, reusable as-is.
   - HIGH: `cockpit/audit/base.py` (AuditContext, AuditFinding, run_registered_passes, merge_findings) and `audit/report.py` (render_markdown, persist_audit) — CLI-decoupled, reusable as-is.
   - LOW/NONE: `build_cockpit_snapshot` and `_render_*_panel`/`_render_*_detail` in `agentos.cli.cockpit` return Rich console markup, not HTML — not reusable by a web layer. Need a thin API/service layer between domain functions and HTTP: either (a) JSON API serializing snapshot/finding data, or (b) new HTML-rendering functions parallel to the Rich renderers, sharing only underlying data structures.
   - NONE: `cockpit/navigation.py`'s `CockpitUIState`/`run_cockpit_loop` is a stdin/stdout prompt loop — not reusable for web, though its view-state shape (current_view, selected_panel, filter_query) can inform URL/route design (e.g. `/project/{key}/panel/{panel_id}`).

4. **No existing HTTP server code** anywhere in the repo (confirmed via grep). MCP server (`src/agentos/mcp/server.py`) is stdio JSON-RPC — architecturally unrelated, not reusable/extendable for a browser-facing UI.

5. **Scope estimate: MEDIUM.** New dependency (FastAPI+uvicorn), new CLI command, new service/API layer, HTML templates or JSON API + minimal frontend. Suggested phase boundaries:
   - **Phase A (small)**: add FastAPI+uvicorn dep, scaffold `aki cockpit --web` starting a local server with one JSON endpoint (project list) + health check — proves the plumbing.
   - **Phase B (medium)**: project detail/drill-down endpoints reusing `build_cockpit_snapshot` + audit findings, server-rendered HTML (htmx or Jinja2) mirroring the 4-panel terminal layout.
   - **Phase C (small)**: audit report view (render existing markdown or convert to HTML), read-only — no autofix trigger endpoints.
   - Recommend NOT a single PR — Phase A should land and be reviewed before B/C given new-dependency risk and unproven server pattern.

## Where

`src/agentos/cockpit/registry.py`, `src/agentos/cockpit/navigation.py`, `src/agentos/cockpit/audit/{base,report}.py`, `src/agentos/cli/main.py`, `src/agentos/cli/cockpit.py` (renderers), `src/agentos/mcp/server.py` (confirmed non-reusable), `pyproject.toml` (no web framework dep yet).

## Learned

`src/agentos/core/config.py` intentionally not read/investigated (owned by a concurrent agent). If the web command needs env/config for host/port binding, scope that integration point carefully in design to avoid touching that file directly.
