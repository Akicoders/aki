# Tasks: web-ui-cockpit

Delivery strategy: `stacked-to-main`. Each phase lands as its own PR merging
directly to `main`, in order: A → B → C. A must be reviewed and merged before
B starts; B before C. Do not open B/C PRs until the prior PR is merged.

Constraint: no task in this document touches `src/agentos/core/config.py`.

---

## Phase A — Scaffold, dependency, health, project-list JSON (PR #1)

Satisfies: web-server spec (CLI entrypoint, localhost bind, port-conflict
error, SIGINT shutdown, no non-localhost exposure) + web-endpoints spec
(health check, project list, no-mutation guarantee — partial, extended in B/C).

Sequential (each step depends on the previous):

1. [x] **[seq] Add `web` optional-extras group to `pyproject.toml`**
   - `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `jinja2>=3.1`
   - No test required (dependency declaration only); verify with
     `uv sync --extra web` or equivalent install succeeds.
   - Satisfies: design "Dependency placement" decision.

2. [x] **[seq] RED: `WebServerSettings` defaults test**
   - New test file `tests/cockpit/web/test_settings.py`
   - Failing test: `WebServerSettings().host == "127.0.0.1"` and
     `WebServerSettings().port == 8420`.
   - Satisfies: web-server spec "Server binds to localhost only by default".

3. [x] **[seq] GREEN: create `src/agentos/cockpit/web/settings.py`**
   - `@dataclass WebServerSettings(host: str = "127.0.0.1", port: int = 8420)`
   - Create `src/agentos/cockpit/web/__init__.py` (package marker).
   - Run test from step 2 → passes.

4. [x] **[seq] RED: `build_cockpit_snapshot(record_open=False)` no-upsert test**
   - Extend `tests/cli/test_cockpit.py` (or existing cockpit test file):
     failing test spying/monkeypatching `registry.upsert_project` and
     asserting it is NOT called when `record_open=False`, and IS called
     (unchanged behavior) when `record_open=True` (default).
   - Satisfies: design "Read-only guarantee" decision; supports
     web-endpoints "Audit report / drill-down ... no side effects".

5. [x] **[seq] GREEN: guard `build_cockpit_snapshot` in `cli/cockpit.py`**
   - Add additive param `record_open: bool = True` to
     `build_cockpit_snapshot(project: ProjectRef, ...)` (line ~203).
   - Wrap the `registry.upsert_project(...)` call (line ~210) with
     `if record_open:`.
   - Default value preserves existing terminal-cockpit behavior exactly —
     no other caller needs updating.
   - Run test from step 4 → passes. Run full existing cockpit test suite →
     no regressions.

6. [x] **[seq] RED: `create_app()` + `/health` TestClient test**
   - New test file `tests/cockpit/web/test_app.py`
   - Failing test: `TestClient(create_app()).get("/health")` returns 200
     with a body indicating healthy status. No real server bind.
   - Satisfies: web-endpoints spec "Health check endpoint".

7. [x] **[seq] GREEN: create `src/agentos/cockpit/web/app.py` and
   `src/agentos/cockpit/web/routes.py`**
   - `app.py`: `create_app() -> FastAPI` factory that includes the router
     from `routes.py`; `run_server(settings: WebServerSettings) -> None`
     thin `uvicorn.run(...)` wrapper (not exercised via real bind in tests).
   - `routes.py`: `/health` route only at this step.
   - Run test from step 6 → passes.

8. [x] **[seq] RED: `/api/projects` TestClient test (populated + empty)**
   - Extend `tests/cockpit/web/test_app.py`:
     - Failing test: registry with projects → `GET /api/projects` returns
       200 + JSON array matching `registry.list_projects()` output.
     - Failing test: empty registry → `GET /api/projects` returns 200 +
       empty JSON array.
   - Satisfies: web-endpoints spec "Project list endpoint" (both scenarios).

9. [x] **[seq] GREEN: implement `/api/projects` route**
   - Add route to `routes.py` calling `registry.list_projects()` directly,
     no transformation beyond JSON serialization.
   - Run tests from step 8 → pass.

10. [x] **[seq] RED: no-mutation-verb test**
    - Failing test: `TestClient(create_app())` — for every registered route,
      `POST`/`PUT`/`PATCH`/`DELETE` returns 405 (or 404, never 2xx).
    - Satisfies: web-endpoints spec "No mutation endpoints exist" (partial —
      re-verified again in Phase B/C once more routes exist).

11. [x] **[seq] GREEN: confirm route table is GET-only**
    - No implementation expected beyond what steps 7/9 already produced;
      this step exists to make the guarantee explicit and testable early,
      before more routes are added in B/C. Run test from step 10 → passes.

12. [x] **[seq] RED: 500-safety test**
    - Failing test: monkeypatch `registry.list_projects` (or a handler
      dependency) to raise; assert response is 500 and body does NOT
      contain a raw traceback or file path.
    - Satisfies: web-endpoints spec "Unhandled server errors return a safe
      response".

13. [x] **[seq] GREEN: add exception handler in `app.py`**
    - Register a FastAPI exception handler that catches unhandled
      exceptions and returns a generic 500 JSON body (`{"detail": "internal
      server error"}` or similar, no traceback).
    - Run test from step 12 → passes.

14. [x] **[seq] RED: `run_server` lifecycle test**
    - Failing test: monkeypatch `uvicorn.run`; call
      `run_server(WebServerSettings(host="127.0.0.1", port=9000))`; assert
      `uvicorn.run` was called with `host="127.0.0.1", port=9000` and the
      app produced by `create_app()`. No real process spawned.
    - Satisfies: web-server spec "Server shuts down cleanly on interrupt"
      (lifecycle wiring — actual SIGINT behavior is delegated to uvicorn,
      verified structurally here) + "Default bind address".

15. [x] **[seq] GREEN: finalize `run_server` in `app.py`**
    - Implementation already sketched in step 7; ensure it matches the
      test's expected call signature exactly.
    - Run test from step 14 → passes.

16. [x] **[seq] RED: CLI wiring test for `aki cockpit --web/--host/--port`**
    - Extend `tests/cli/test_main.py` (or equivalent): failing test using
      Typer's `CliRunner` — monkeypatch `run_server`; invoke
      `aki cockpit --web --host 127.0.0.1 --port 9001`; assert `run_server`
      called with a `WebServerSettings(host="127.0.0.1", port=9001)` and
      that the terminal cockpit render path was NOT invoked.
    - Also: failing test that `aki cockpit` (no `--web`) still invokes the
      existing terminal cockpit path unchanged.
    - Satisfies: web-server spec "CLI entrypoint starts a local web server"
      + "Terminal cockpit remains unaffected" + "Host/port override via
      additive config surface" (confirms no `core/config.py` touch).

17. [x] **[seq] GREEN: wire `--web`/`--host`/`--port` in `cockpit_callback`
    (`cli/main.py` ~line 396)**
    - Add `web: bool = typer.Option(False, "--web", ...)`,
      `host: str = typer.Option("127.0.0.1", "--host")`,
      `port: int = typer.Option(8420, "--port")`.
    - When `web` is true: dispatch to
      `run_server(WebServerSettings(host=host, port=port))` and return
      before reaching the terminal-cockpit render path.
    - Run tests from step 16 → pass. Run full CLI test suite → no
      regressions.

18. [x] **[seq] RED: port-conflict error test**
    - Failing test: monkeypatch `uvicorn.run` (or the underlying socket
      bind call it delegates to) to raise `OSError`/`SystemExit`-worthy
      "address already in use"; assert the CLI command exits non-zero with
      an actionable message naming the port and suggesting `--port`,
      instead of an unhandled traceback.
    - Satisfies: web-server spec "Server startup reports a clear error on
      port conflict".

19. [x] **[seq] GREEN: catch bind errors in `run_server`/`cockpit_callback`**
    - Wrap the `run_server` dispatch in `cockpit_callback` with a
      try/except around `OSError` (or the equivalent uvicorn startup
      failure), print an actionable `typer.echo`/`rich` message, and
      `raise typer.Exit(code=1)`.
    - Run test from step 18 → passes.

20. [x] **[seq] Full Phase A regression pass**
    - Run entire test suite (`uv run pytest` or project's configured
      runner). No real server bind anywhere in the suite — confirm via
      test run that no port was actually opened (TestClient only).
    - No new test; this is a verification gate before PR.

Parallelizable within Phase A (can be done concurrently once step 1 lands,
by a second contributor, since they touch disjoint files):
- Steps 2-3 (settings) and step 4-5 (record_open guard) are independent of
  each other and can run in parallel once step 1 is merged.

**Phase A size estimate**: ~5 new/modified files
(`pyproject.toml`, `cockpit/web/__init__.py`, `cockpit/web/settings.py`,
`cockpit/web/app.py`, `cockpit/web/routes.py`, `cli/cockpit.py` diff,
`cli/main.py` diff) + ~4 test files. Estimated changed lines: **~350-420**
including tests. **Risk: borderline the 400-line budget threshold.** If
implementation runs long, split further: land steps 1-11 (dependency +
health + project-list + no-mutation-verb) as PR #1a, and steps 12-20
(error safety + CLI wiring + port-conflict handling) as PR #1b. Decide at
apply-time based on actual diff size.

---

## Phase B — Drill-down endpoints + Jinja2 templates (PR #2)

Depends on: Phase A merged (uses `create_app()`, `routes.py`,
`WebServerSettings`, `build_cockpit_snapshot(record_open=False)`).

Satisfies: web-endpoints spec "Project drill-down endpoint" (both
scenarios) + reinforces "No mutation endpoints exist" with the new routes.

Sequential:

1. [x] **[seq] RED: `/project/{key}` 404-for-unknown test**
   - Failing test: `TestClient` GET `/project/does-not-exist` → 404 with
     body indicating "not found".
   - Satisfies: web-endpoints "Project not found" scenario.

2. [x] **[seq] RED: `/project/{key}` 200-with-panel-data test**
   - Failing test: register a project, GET `/project/{key}` → 200, response
     contains data equivalent to the 4 terminal-cockpit panels (derived
     from `build_cockpit_snapshot(project, record_open=False)`).
   - Satisfies: web-endpoints "View an existing project's detail" scenario.

3. [x] **[seq] GREEN: add `/project/{key}` route in `routes.py`**
   - Look up project via registry; 404 if missing.
   - Call `build_cockpit_snapshot(project, record_open=False)`.
   - Render via Jinja2 template (see step 5) instead of raw JSON — mirrors
     terminal 4-panel layout.
   - Run tests from steps 1-2 → pass.

4. [x] **[seq] RED: Jinja2 templates render smoke test**
   - Failing test: response `Content-Type` is `text/html`; response body
     contains expected panel section markers/labels (e.g. project name,
     4 panel headings) for a known fixture project.
   - Satisfies: web-endpoints "drill-down ... mirrors the 4-panel terminal
     cockpit layout".

5. [x] **[seq] GREEN: create `src/agentos/cockpit/web/templates/`**
   - `base.html` (shared layout), `project_list.html`, `project_detail.html`
     (4-panel mirror). Wire `Jinja2Templates` into `app.py`/`routes.py`.
   - Run test from step 4 → passes.

6. [x] **[seq] RED: `/` project-list HTML view test**
   - Failing test: GET `/` returns 200, `text/html`, and lists registered
     project keys (server-rendered, replaces/augments the Phase A JSON-only
     `/api/projects`, which remains for plumbing).
   - Satisfies: web-endpoints "Project list endpoint" rendered as HTML
     (spec allows JSON and/or HTML — this adds the HTML view).

7. [x] **[seq] GREEN: implement `/` route using `project_list.html`**
   - Run test from step 6 → passes.

8. [x] **[seq] RED: no-mutation-verb regression on new routes**
   - Extend the Phase A "all routes GET-only" test to include
     `/`, `/project/{key}` — assert POST/PUT/PATCH/DELETE are non-2xx.
   - Satisfies: web-endpoints "No mutation endpoints exist" (re-verified).

9. [x] **[seq] GREEN: confirm (no code change expected)**
   - Run test from step 8 → passes given GET-only route registration.

10. [x] **[seq] Full Phase B regression pass**
    - Run entire suite; confirm Phase A tests still pass unmodified.

**Phase B size estimate**: ~4 new template files + `routes.py`/`app.py`
diffs + ~3 test files. Estimated changed lines: **~250-320**. Within
budget, no split needed.

---

## Phase C — Audit report view (PR #3)

Depends on: Phase A + Phase B merged (reuses `create_app()`, templates
base layout, routing conventions).

Satisfies: web-endpoints spec "Audit report view endpoint" (both
scenarios) + reinforces "Autofix is unreachable from the Web UI" and
"No mutation endpoints exist".

Sequential:

1. [x] **[seq] RED: audit endpoint 404-for-unknown-project test**
   - Failing test: GET audit route for an unregistered project key → 404.
   - Satisfies: web-endpoints "Audit report requested for unknown project".

2. [x] **[seq] RED: audit endpoint renders findings, no side effects test**
   - Failing test: fixture project with prior audit findings available via
     the audit domain layer; GET audit route → 200, rendered content
     reflects existing findings; spy/monkeypatch confirms no new persisted
     audit run is triggered and no autofix function is invoked as part of
     the request.
   - Satisfies: web-endpoints "View audit report for a project with
     findings" scenario + "no write, persistence, or autofix action occurs".

3. [x] **[seq] GREEN: add audit route in `routes.py`**
   - Call existing `run_registered_passes` / `render_markdown` (read-only
     retrieval of existing findings — do NOT trigger a new persisted run;
     confirm with design/audit-engine domain code which call is read-only
     vs. a fresh run, and use the read-only path only).
   - Render markdown output inside a template (`<pre>` block per design's
     Open Question resolution — deferred decision resolved here as `<pre>`
     wrapped in `audit_report.html` extending `base.html`, to avoid a new
     markdown→HTML conversion dependency).
   - Run tests from steps 1-2 → pass.

4. [x] **[seq] RED: autofix-unreachable test**
   - Failing test: inspect the app's route table (`app.routes`) — assert no
     route path/handler references any autofix-triggering domain function;
     also assert rendered `audit_report.html` / `project_detail.html`
     contain no form, link, or button pointing at an autofix action.
   - Satisfies: web-endpoints "Autofix is unreachable from the Web UI".

5. [x] **[seq] GREEN: confirm (no code change expected beyond step 3)**
   - Run test from step 4 → passes given no autofix wiring was added.

6. [x] **[seq] RED: no-mutation-verb regression on audit route**
   - Extend the running "all routes GET-only" test to include the new
     audit route.
   - Satisfies: web-endpoints "No mutation endpoints exist" (final pass,
     all phases).

7. [x] **[seq] GREEN: confirm (no code change expected)**
   - Run test from step 6 → passes.

8. [x] **[seq] Full Phase C regression pass**
   - Run entire suite; confirm Phase A + B tests still pass unmodified.
   - Manual smoke check (not automated): `aki cockpit --web`, browse to a
     project's audit view locally, confirm no crash — remove before PR
     merge, not part of the automated suite.

**Phase C size estimate**: 1 new template + `routes.py` diff + ~3 test
files. Estimated changed lines: **~150-200**. Well within budget.

---

## Review Workload Forecast

- Chained PRs recommended: **Yes** (already the cached delivery strategy —
  `stacked-to-main`, A → B → C, each its own PR merging to main in order).
- 400-line budget risk: **Medium** — Phase A is borderline (~350-420 lines
  estimated including tests) due to combining dependency scaffolding, two
  domain guard changes, and CLI wiring in one PR. Phases B and C are
  comfortably under budget individually.
- Decision needed before apply: **Yes, conditionally** — if Phase A's actual
  diff exceeds ~400 changed lines once code is written, split it into PR #1a
  (steps 1-11: dependency, settings, record_open guard, health, project-list
  JSON, GET-only guarantee) and PR #1b (steps 12-20: 500-safety handler, CLI
  `--web`/`--host`/`--port` wiring, port-conflict handling). This decision
  should be made at `sdd-apply` time based on the real diff, not pre-split
  speculatively, since the guard chapters are small and splitting them now
  would fragment TDD RED/GREEN pairs across two PRs unnecessarily.
