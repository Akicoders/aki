# Design: Project Audit Cockpit (Phase 3 + Phase 4)

## Technical Approach

Extend the existing cockpit seam (`build_cockpit_snapshot` → render functions) with two capabilities: a lightweight interactive drill-down loop reusing today's Rich renders, and a read-only `aki audit <project>` engine built on pluggable audit passes. Persist a `ProjectRef` registry in the SAME memory SQLite DB. Reuse `CodeIntelSkill` (async) for test posture, bridging into Typer via `asyncio.run` at the command boundary. Web and `--autofix` are untouched.

## Architecture Decisions

| Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|
| Registry persistence | New `ProjectRefModel` SQLAlchemy table in `memory/models.py`, created by existing `init_db`/`create_all`; Pydantic `ProjectRefRecord` for I/O | Engram; separate DB file; JSON file | Fixed by user: reuse memory SQLite. Mirrors `MemoryFactModel` split (SQLAlchemy model + Pydantic + `from_model`/`to_model`). |
| Schema migration | Rely on `Base.metadata.create_all` (additive, auto-creates missing table) | Alembic revision | CONFIRMED: no `alembic.ini`/`alembic/` env exists; runtime never invokes Alembic. Adding one now would INVENT a pattern, not follow one. See Migration section. |
| Keyboard nav | Synchronous prompt loop over existing Rich renders using `rich.prompt.Prompt.ask` (already a dep, already used in `main.py:437`) | textual/prompt-toolkit TUI; `readchar` raw keypress | Fixed by user: lightweight loop, no new dep. Enter-submitted shortcut string is enough; keeps golden/snapshot tests intact. |
| Audit pass interface | `AuditPass` protocol with sync `run(ctx) -> list[AuditFinding]`; passes registered in an ordered list; deterministic merge by (pass order, priority, category, title) | Async passes; entry-point discovery; LLM free-form | Deterministic, testable, matches contract-test requirement (design §13). Async work isolated to the tests pass via `asyncio.run`. |
| Async bridge | `asyncio.run(code_intel.run_tests(...))` inside the sync tests pass | Make Typer command async; thread pool | Single call boundary; no event loop leaks; Typer stays sync. |

## Module / File Layout

New package `src/agentos/cockpit/` (cockpit.py is already ~790 lines — do not grow it further):

| File | Action | Description |
|---|---|---|
| `src/agentos/memory/models.py` | Modify | Add `ProjectRefModel` + Pydantic `ProjectRefRecord` (`from_model`/`to_model`). |
| `src/agentos/memory/database.py` | Modify | Import `ProjectRefModel` so `create_all` sees it. |
| `src/agentos/cockpit/registry.py` | Create | Registry CRUD: `upsert_project`, `list_projects`, `touch_last_opened/last_audit`, keyed on canonical `root_path`. |
| `src/agentos/cockpit/navigation.py` | Create | `CockpitUIState` dataclass + `run_cockpit_loop(console, project)` prompt loop. |
| `src/agentos/cockpit/audit/base.py` | Create | `AuditPass` protocol, `AuditContext`, `AuditFinding`, `AuditReportRef`, `merge_findings`, `PASS_REGISTRY`. |
| `src/agentos/cockpit/audit/passes.py` | Create | Six passes: tests, sdd, git, env, mcp, memory (reuse existing snapshot builders + `CodeIntelSkill`). |
| `src/agentos/cockpit/audit/report.py` | Create | Markdown generation + dual-sink persistence. |
| `src/agentos/cli/main.py` | Modify | `aki cockpit --interactive` → loop; `aki projects browse` → real registry table; `aki audit <project>`. |
| `src/agentos/cli/cockpit.py` | Modify | Export `ProjectRef` (keep dataclass), call `registry.upsert_project` inside `build_cockpit_snapshot`. |

## Data Flow

```
aki audit <proj> ──► resolve_project_ref ──► registry.upsert
       │
       ▼
  AuditContext ──► PASS_REGISTRY[tests,sdd,git,env,mcp,memory]
       │              each pass.run() ─► [AuditFinding]
       ▼
  merge_findings (deterministic) ─► report.render_markdown
       │
       ├─► write docs/audits/YYYY-MM-DD-<proj>-audit.md   (sink 1)
       └─► Engram audit/<proj>/<ts> + audit/<proj>/latest  (sink 2)
   if EITHER sink fails ► report failed stage ► exit non-zero
```

Interactive loop: `render_cockpit_overview` → `Prompt.ask` shortcut → mutate `CockpitUIState` → re-render. `r` calls `build_cockpit_snapshot` again; all other keys reuse the cached snapshot.

## Interfaces / Contracts

```python
@dataclass
class AuditFinding:
    priority: Literal["P0","P1","P2","P3"]
    category: str            # tests|sdd|git|env|mcp|memory
    title: str
    evidence: str
    recommendation: str
    autofixable_later: bool = False

class AuditPass(Protocol):
    id: str
    def run(self, ctx: "AuditContext") -> list[AuditFinding]: ...

@dataclass
class CockpitUIState:
    current_view: str = "overview"   # overview|action|health|memory|sdd
    selected_panel: int = 0
    selected_index: int = 0
    filter_query: str = ""
    refresh_in_progress: bool = False
```

Empty pass returns `[]`; a raising pass is caught, converted to one `P2` `category="<id>"` "pass failed" finding — the audit never crashes (design §12).

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | registry upsert idempotency; `merge_findings` ordering; finding ranking | pytest, tmp sqlite |
| Contract | every pass emits schema; empty/error-pass behavior | parametrized over `PASS_REGISTRY` |
| Integration | `aki audit` artifact write + non-zero exit on sink failure | Typer `CliRunner`, monkeypatched Engram sink |
| Golden | markdown report; browse table | snapshot files |

## Migration / Rollout

No Alembic migration. The new `ProjectRefModel` is picked up by the existing `Base.metadata.create_all` in `init_db`, which is additive (creates only missing tables) and safe for existing DBs. This matches the ACTUAL working schema mechanism; Alembic is a declared dependency with Makefile targets but has no scaffolded env, so there is no migration pattern to follow.

## Scope Confirmation

Web surface: NOT touched. `--autofix`: NOT implemented (findings carry `autofixable_later` flag only for a future slice).

## Open Questions

- [ ] Alembic gap: adopt `create_all` (this design) vs. scaffold the Alembic env in a separate change? Recommend `create_all` now.
- [ ] Tests pass may run the suite (slow) — gate behind explicit `aki audit` only, never cockpit open (design §9).
