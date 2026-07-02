# Explore: Project Metadata Store (closing QA issue #4 remainder)

## What

Investigated whether a new `.aki/` file-based project-metadata store is needed to close the remaining gap in QA issue #4 (`.env` loading depends on cwd), vs. reusing existing DB-backed infra. No code written.

## Why

Commit `7f8044b` already anchored `load_runtime_env` on git-root, fixing the "launched from a subdirectory of the repo" case. It cannot fix the "cwd has zero relation to the repo at all" case — there's no ancestor path to walk. User wants a persisted "last known project" pointer to bootstrap resolution in that case.

## Findings

### 1. `db_path` is cwd-relative with no anchoring at all

`src/agentos/core/config.py`: `MemoryConfig.db_path: Path = Path("data/agentos.db")` — relative, cwd-dependent, and unlike `.env` search has **zero** fallback/walk logic. `src/agentos/memory/database.py`'s `get_engine()` builds `sqlite:///{db_path}` directly against whatever the process cwd is at engine-creation time. `get_database()` pulls `db_path` from `get_config().memory.db_path` (or a `MEMORY_DB_PATH` env var — which would itself live in the `.env` we're trying to locate, making that override circular/unusable for bootstrapping).

### 2. Existing project-resolution helpers solve a different problem

`src/agentos/mcp/project.py`'s `detect_project()` and `src/agentos/cli/cockpit.py`'s `resolve_project_ref()`/`_find_git_root()` both answer "what project is cwd currently inside" via a git-root walk from a **known-related** cwd. That's a different problem from "what project was I last in, when cwd has no relation at all." Not directly reusable as-is, but `resolve_project_ref`'s result is what feeds `registry.upsert_project()`.

### 3. The cockpit registry can't bootstrap either

`src/agentos/cockpit/registry.py`'s `ProjectRefModel` (root_path, key, source, last_opened_at) is already a DB-backed "recently used projects" registry via `upsert_project`/`list_projects`/`touch_last_opened`. But it's DB-backed, so it inherits the same cwd-relative `db_path` bootstrap problem: it can only be queried once the *correct* DB is already open — which is exactly what we don't know from an unrelated cwd.

### 4. No existing global storage precedent

Grep for `~/.aki`, `~/.config/aki`, XDG usage across `src/`: nothing. `Path.home()` is used only for unrelated things (`mcp_hosts.py` configs, `update.py`'s uv binary lookup, `FilesystemConfig.allowed_roots` defaults). Fully greenfield for a global Aki directory.

### 5. Cross-check against the earlier-rejected session-persistence file store

Archived `openspec/changes/archive/2026-07-02-session-persistence/{explore,proposal}.md` rejected Approach B — a file-based `.aki/sessions/<id>.json` store for session checkpoints — because it would be a second source of truth alongside SQLite, and the DB was *already reachable* at the point session state was needed (project was already known).

**This is a different situation, not the same objection**: here the DB path itself is cwd-relative and unresolved *before* project identity is even known. That's a genuine chicken-and-egg bootstrap problem the DB cannot solve for itself — you'd need to already know which DB file to open in order to read a "last known project" row from it.

## Two real fixes identified

**Option 1 — Anchor `MemoryConfig.db_path` to a fixed global location** (e.g. `~/.aki/agentos.db`) instead of cwd-relative `data/agentos.db`. This would let the existing cockpit `ProjectRefModel` registry double as the "last known project" source with zero new file format.
- Pros: no new storage format, reuses all existing registry/audit infra as-is.
- Cons: structural change to `config.py`'s default (not just an anchoring *resolution* like the already-landed `.env` fix), real migration implications for any existing local `data/agentos.db` files, and touches the file flagged off-limits this session beyond the already-authorized narrow edit. **Needs explicit user confirmation before proposing.**

**Option 2 — Minimal `.aki/last-project` breadcrumb file** (single small JSON: `{"root_path": "...", "updated_at": "..."}`), written whenever a project is positively resolved (chat/interactive/cockpit start via `resolve_project_ref`/`detect_project`), read only by `load_runtime_env`/`_iter_env_search_roots` as a last-resort candidate root before falling back to plain cwd/no-op.
- Pros: does not touch `db_path` resolution or `config.py` structurally beyond an additive read; does not compete with the cockpit registry as a "recently used projects" list (that job stays DB-backed once the DB is reachable); scoped singularly to bootstrapping `.env` discovery, avoiding the "second source of truth" objection from session-persistence's Approach B because it's not modeling general project metadata — just one breadcrumb pointer.
- Cons: yes, technically a new file format, but deliberately the smallest possible one (single pointer, not a checkpoint/session format).

## Recommendation

**Option 2** for this change: a minimal, single-purpose `.aki/last-project` breadcrumb file, explicitly scoped to one `root_path` pointer — not a general `.aki/` metadata store, and not a richer checkpoint/session format (that idea was already explored and rejected this session for a related but distinct problem).

Flag Option 1 (fixed global `db_path`) as the superior long-term fix, but out of scope for this cycle: it structurally modifies the off-limits `config.py` beyond the already-authorized narrow git-root-anchor edit, and has DB-location migration implications for existing users. Would need explicit sign-off as its own follow-up change.

## Scope estimate: SMALL

Single new small module (breadcrumb read/write helpers) + wiring into `load_runtime_env`'s search-root fallback + wiring writes into the points where a project is already positively resolved (`resolve_project_ref` callers). No new EventType, no `config.py` structural change, no DB schema change.

## Where

New: a small breadcrumb read/write module (e.g. `src/agentos/core/project_breadcrumb.py` or similar — design phase to decide exact location/naming).
Modified: `src/agentos/core/config.py`'s `_iter_env_search_roots` (additive last-resort candidate), `src/agentos/cli/cockpit.py`/`src/agentos/cli/main.py` (write breadcrumb wherever a project is positively resolved).

## Learned

The two "rejected file store" and "needed file store" cases in the same session look superficially identical (both are "should we add `.aki/` file storage?") but differ on a load-bearing technical fact: whether the DB is reachable at the point the state is needed. Session checkpoints: DB already reachable (project known) → reuse DB. Project bootstrap: DB path itself unresolved before project is known → DB cannot solve its own bootstrap, so a file is justified. Must verify this distinction explicitly rather than pattern-matching on "file vs DB" alone.
