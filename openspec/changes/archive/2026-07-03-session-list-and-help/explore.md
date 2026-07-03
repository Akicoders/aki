# Explore: session listing + better interactive help

## 1. Session data model (what's actually queryable)

Sessions are NOT a first-class table. There is no `sessions` table — session
identity lives entirely as a convention encoded into `MemoryFactModel` rows
(`src/agentos/memory/models.py:55-71`):

- `key` (String(256), indexed) — e.g. `session:last` or
  `session:{session_id}:checkpoint`
- `scope` (String(256), indexed) — `project:{project}`
- `value` (Text) — for checkpoint rows, a JSON blob; for `session:last`, the
  raw session_id string
- `updated_at` / `created_at` (DateTime) — per-row timestamps

Reserved-key helpers in `src/agentos/memory/repository.py`:
- `LAST_SESSION_KEY = "session:last"` (line 37) — one pointer row per project,
  overwritten on every `touch_last_session` call (line 320-322). Only the
  *most recent* session_id is retrievable this way — no history.
- `CHECKPOINT_KEY_TEMPLATE = "session:{session_id}:checkpoint"` (line 38) —
  one row per session, upserted by `write_checkpoint` (line 329-358). The
  payload includes `session_id`, `project`, `goal`, `open_items`,
  `last_tool_result`, `last_response`, `iterations_exhausted`, `updated_at`.

Existing read paths only fetch by exact `(key, scope)` (`get_fact`, line 266)
or by `scope` with a limit (`get_facts_by_scope`, line 274) — no by-prefix or
by-project-and-key-prefix query exists yet. `search_facts` (line 280) does an
`ilike` substring match on `key`/`value` within an optional `scope`, ordered
by `confidence` (all reserved facts hardcode `confidence=1.0`, so ties break
arbitrarily) — not ordered by `updated_at`, and not session-aware.

**Feasibility of "list sessions for this project" without new tables:**
Feasible. Every checkpoint row's `key` already embeds the session_id and its
`scope` already embeds the project (`f"project:{project}"`, e.g. repository.py
line 356-357). A query filtering
`MemoryFactModel.scope == f"project:{project}"` AND
`MemoryFactModel.key.like("session:%:checkpoint")`, ordered by `updated_at
desc`, returns exactly the set of sessions with a checkpoint for that
project, each with its last-updated timestamp and (after `json.loads(value)`)
its `goal` / `iterations_exhausted` fields — a reasonable "session picker"
list. This requires **one new repository method** (e.g.
`list_sessions(project, limit)`), not a schema migration. No existing method
does this today — confirmed by reading all of `MemoryRepository` (lines
118-379, only method list: `upsert_fact`, `get_fact`, `get_facts_by_scope`,
`search_facts`, `_upsert_reserved_fact`, `touch_last_session`,
`get_last_session`, `write_checkpoint`, `read_checkpoint`,
`increment_fact_access`).

Caveats:
- A session only appears in this list once it has completed at least one
  turn that called `write_checkpoint` (per the archived session-persistence
  design, checkpoint is written "on every turn" — see
  `openspec/changes/archive/2026-07-02-session-persistence/`). A session that
  errored before its first checkpoint write is invisible.
- `key.like(...)` with SQLite is a substring scan over an indexed column
  (`ix_memory_facts_scope_key` on `(scope, key)`, models.py:70) — fine at
  hackathon scale, would want a real `session_id` column + index if this grows.
  Consider this a known scaling debt if the change proceeds, not a blocker.
- No explicit `session_id -> title/label` exists; the only human-friendly
  field is `goal` inside the checkpoint JSON, which may be truncated to 1000
  chars (`CHECKPOINT_FIELD_CHAR_CAP`, repository.py:34) and can be empty.

## 2. Help experience: current state vs CLI --help

- `aki --help` (Typer-generated, from `app = typer.Typer(..., help="Aki - AI
  agent with portable project memory")`, `src/agentos/cli/main.py:63-66`)
  auto-lists all top-level commands (`chat`, `interactive`, `mcp`,
  `mcp-config`, `mcp-setup`, `cockpit`, `audit`, `sdd-init`, `remember`, etc.,
  found via `@app.command()` grep across the file) with their one-line
  docstrings as descriptions. This is Typer's default behavior — reasonably
  useful for discovering *commands*, but static and non-contextual (same
  output regardless of whether a project/session already exists).

- Inside interactive mode, `/help` calls `_show_help()`
  (`src/agentos/cli/main.py:903-913`), which prints a **hardcoded static
  Panel** listing 6 items (`/memory`, `/facts`, `/skills`, `/sdd`, `/clear`,
  `exit/quit`) with one-line descriptions each. It is NOT contextual: no
  awareness of current `project`/`session_id` (both are in scope as
  parameters to `_async_interactive` at line 751, and `_handle_command`
  already receives them at line 916, but `_show_help()` takes zero
  arguments and ignores them). It does not mention that a session was
  resumed, whether a checkpoint exists, or what to do next. It's a manpage
  fragment, not a walkthrough — matches the user's complaint exactly.

- Command dispatch is a flat `if/elif` chain in `_handle_command` (line
  916-928); adding a `/sessions` command here is a small, additive change
  (append one `elif`), no structural rework needed.

## 3. Candidate approaches

### A. List sessions command

1. **New `MemoryRepository.list_sessions(project, limit=20)`** — query
   `MemoryFactModel` where `scope == f"project:{project}"` and
   `key.like("session:%:checkpoint")`, order by `updated_at desc`, parse each
   `value` as JSON, return `(session_id, goal, updated_at, iterations_exhausted)`
   tuples. Cheapest option — no schema change, reuses the checkpoint's own
   session_id embedded in the key. Trade-off: substring `LIKE` scan, and
   `session_id` has to be parsed back out of the key string (or read from the
   JSON payload's own `session_id` field, which is already present — safer,
   avoids key-parsing regressions if the key template ever changes).
2. **New CLI command `aki sessions [--project]`** and interactive `/sessions`
   — render a Rich table (goal preview, updated_at, session_id, whether last
   turn exhausted budget). Mirrors existing patterns (`_show_facts`,
   `_show_skills` in main.py) — same shape, no new UI paradigm introduced.
3. (Rejected/deferred) Add a dedicated `sessions` table — more correct
   long-term (proper index on session_id + project, could track
   started_at/turn_count) but is schema-migration work disproportionate to
   the ask; only justified if checkpoint-key scanning proves too slow or the
   product wants richer session metadata (title, message count) that doesn't
   fit the checkpoint JSON.

### B. Better `/help`

1. **Contextual help panel** — thread `project`/`session_id` into
   `_show_help(project, session_id)`, and have it report live state: whether
   a session was resumed (checkpoint exists via `read_checkpoint`), what the
   last goal was, and a "what you can do right now" section (e.g. if a
   checkpoint exists, suggest `/sessions` or continuing; if facts exist,
   mention `/facts`). Low-risk, additive; reuses already-available
   `agent`/`project`/`session_id` params already passed to `_handle_command`.
2. **Step-by-step first-run walkthrough** — detect first-ever session for a
   project (no `session:last` fact) and print a short onboarding sequence
   instead of the static command list. Higher effort, more product-decision
   surface (what counts as "first run", how to avoid nagging repeat users).
3. **Keep `--help` as-is** — Typer's default is fine for command discovery;
   the actual complaint is about the in-session `/help`, so `aki --help`
   itself is out of scope unless the user says otherwise.

Recommendation for proposal phase: pair A.1+A.2 (repository method + CLI/
interactive surface) with B.1 (contextual help using already-existing
project/session params) — both are additive, don't touch the archived
session-persistence data model, and reuse established code patterns
(`_show_*` functions, Rich Table/Panel).

## 4. Risks / overlaps with existing archived work

- No schema changes needed → no conflict with the archived
  `session-persistence` spec (`openspec/specs/session-persistence/spec.md`),
  which defined the checkpoint-write contract this change reads from but
  does not modify.
- Must not break the reserved-key namespace guard (`RESERVED_FACT_KEY_PREFIX
  = "session:"`, repository.py:36) — the new list query only reads, never
  writes, so no risk of colliding with that guard.
- `_show_help()`'s signature change (adding params) is a small breaking
  change to an internal function — no external callers found besides the one
  call site at main.py:759.
