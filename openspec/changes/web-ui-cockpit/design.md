# Design: Web UI Cockpit

## Technical Approach

Add a thin, read-only FastAPI + uvicorn layer that reuses the EXISTING domain
data. Critically, `build_cockpit_snapshot()` (`cli/cockpit.py:203`) already
returns a pure-data `CockpitSnapshot` dataclass — only the `_render_*_panel`
helpers emit Rich markup. So the web layer consumes the SAME snapshot the CLI
uses; NO refactor of the snapshot into a new model is required. The web layer
adds a parallel HTML/JSON presentation path over that shared data. Delivered in
three reviewable phases (A scaffold, B drill-down HTML, C audit view), Phase A
lands first to isolate new-dependency risk.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|----------|--------|----------|-----------|
| Data source | Reuse `build_cockpit_snapshot()` + `registry.list_projects()` + audit `run_registered_passes`/`render_markdown` directly | New parallel data-fetch code; refactor snapshot into pydantic model | Snapshot is ALREADY data-only dataclass; zero domain change, no touch to `core/config.py` |
| Web framework | FastAPI + uvicorn (proposal-locked) | Flask, SPA | Matches pydantic style, async, minimal boilerplate |
| Rendering (Phase B) | Server-rendered Jinja2 templates | JSON+htmx, SPA | Zero existing frontend tooling in repo; no build step, no JS framework; SSR keeps footprint near zero. JSON endpoints kept only for Phase A plumbing/health |
| Host/port config | CLI flags `--host`/`--port` on `aki cockpit --web`, defaults `127.0.0.1`/`8420`, held in a small local `WebServerSettings` dataclass in the web package | New config file; editing `core/config.py` | Additive, narrow, honors localhost-only + no-config-touch constraints |
| Read-only guarantee | Web calls `build_cockpit_snapshot(project, record_open=False)` via a new additive optional param; no POST/PUT/DELETE routes registered | Reuse builder as-is (writes `last_opened_at`) | Strictly read-only: the browser view must not mutate even registry open-metadata |
| Dependency placement | New `web` optional-extras group in `pyproject.toml` | Main deps | Keeps base install lean; web is opt-in (`pip install .[web]`) |

## Data Flow

    Browser ──HTTP──▶ FastAPI routes (web/routes.py)
                          │
                          ▼
        registry.list_projects()      → project list (JSON + /)
        build_cockpit_snapshot(        → 4-panel drill-down (Jinja2)
            project, record_open=False)
        audit.run_registered_passes /  → audit report view (Phase C)
            render_markdown()
                          │
                          ▼
                 Jinja2 templates / JSONResponse (read-only)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/agentos/cockpit/web/__init__.py` | Create | Package marker |
| `src/agentos/cockpit/web/settings.py` | Create | `WebServerSettings` dataclass (host, port defaults) |
| `src/agentos/cockpit/web/app.py` | Create | `create_app()` FastAPI factory + `run_server(settings)` uvicorn launcher |
| `src/agentos/cockpit/web/routes.py` | Create | Read-only routes: `/health`, `/api/projects`, `/`, `/project/{key}`, audit view |
| `src/agentos/cockpit/web/templates/` | Create | Jinja2 templates (Phase B/C): base, project list, drill-down 4-panel, audit |
| `src/agentos/cli/cockpit.py` | Modify | Add optional `record_open: bool = True` param to `build_cockpit_snapshot`; guard the `registry.upsert_project` call |
| `src/agentos/cli/main.py` | Modify | Add `--web`, `--host`, `--port` options to `cockpit_callback`; dispatch to `run_server` before the overview render |
| `pyproject.toml` | Modify | Add `web` extra: `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `jinja2>=3.1` |

## Interfaces / Contracts

```python
# web/settings.py
@dataclass
class WebServerSettings:
    host: str = "127.0.0.1"
    port: int = 8420

# web/app.py
def create_app() -> FastAPI: ...          # testable via TestClient, no server
def run_server(settings: WebServerSettings) -> None: ...  # uvicorn.run wrapper

# cli/main.py — cockpit_callback (additive, symmetric with -i)
web: bool = typer.Option(False, "--web", help="Serve read-only cockpit over HTTP")
host: str = typer.Option("127.0.0.1", "--host")
port: int = typer.Option(8420, "--port")
```

`uvicorn[standard]` chosen over plain uvicorn for websockets/httptools perf and
reload tooling; acceptable transitive footprint for an opt-in extra.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `WebServerSettings` defaults; `build_cockpit_snapshot(record_open=False)` performs no upsert | pytest + monkeypatch/spy on `registry.upsert_project` |
| Integration | Routes return snapshot data; `/health` ok; `/api/projects` mirrors `list_projects`; no mutation verbs registered (assert 405 on POST) | `fastapi.testclient.TestClient(create_app())` — NO real server, NO port bind |
| Config | Default bind is `127.0.0.1`, never `0.0.0.0` | Assert `WebServerSettings().host == "127.0.0.1"`; test CLI wiring passes flags through |
| Lifecycle | `run_server` builds app + calls uvicorn with settings | Mock `uvicorn.run`; assert host/port passed. No real process spawned in tests |

Strict TDD: write failing tests per phase first. TestClient avoids process
leaks entirely — the server is never actually bound during the suite.

## Migration / Rollout

No data migration. Phased multi-PR: A (scaffold+dep+health+JSON project list)
→ B (Jinja2 drill-down) → C (audit view). A must merge before B/C.

## Open Questions

- [ ] Confirm port `8420` has no conflict convention in the repo (assumed free).
- [ ] Phase C: serve audit markdown as `<pre>` vs. convert to HTML — defer to tasks.
