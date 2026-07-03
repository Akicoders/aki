# Design: Session Listing & Contextual Interactive Help

## Status

Design phase for change `session-list-and-help`. Inputs: `proposal.md`, `specs/session-list-and-help.md`.
Validated against actual code in `src/agentos/memory/repository.py` (reserved-key
checkpoint helpers, lines 302–371) and `src/agentos/cli/main.py` (`_show_help` @903,
`_handle_command` @916, `_show_facts` @936, call site @759). All three changes are
additive and read-only — they consume the checkpoint contract shipped by the archived
`session-persistence` change without respec'ing it.

## 1. Architecture Approach

Three additive surfaces, no schema change, no migration, no change to the
checkpoint-write contract:

```
cli/main.py  _async_interactive(agent, project, session_id)   [call site @759, @762]
   ├─ /help        → _show_help(project, session_id)   ── reads read_checkpoint
   └─ /sessions    → _show_sessions(agent, project)     ── reads list_sessions
memory/repository.py  list_sessions(project, limit=20)  ── LIKE-scan on MemoryFactModel
memory/models.py      MemoryFactModel                   (UNCHANGED — reuse only)
```

`list_sessions` reuses the exact reserved-key naming already in `repository.py`
(`RESERVED_FACT_KEY_PREFIX = "session:"`, `CHECKPOINT_KEY_TEMPLATE =
"session:{session_id}:checkpoint"`), so the `LIKE` pattern is derived from the same
constants rather than a re-hardcoded string — no key-template coupling.

## 2. Key Decision: Corrupt-JSON handling (RESOLVED)

The core open question from the spec phase. Three sub-decisions:

### 2a. Where the try/except lives — **inside `list_sessions` only. No shared helper. `read_checkpoint` is NOT touched.**

`read_checkpoint(project, session_id)` (repository.py:360) does an **exact
`(scope, key)`** lookup for ONE session the caller explicitly named, then
`json.loads` unguarded. Its contract is "give me THIS session's checkpoint." If that
one row is corrupt, raising is the correct, honest behavior — the caller asked for a
specific thing that is broken; silently returning `None` would masquerade a corrupt
checkpoint as a brand-new session and is a worse failure mode (it would, e.g., make
`_build_messages` skip rehydration silently). So `read_checkpoint` keeps raising.

`list_sessions` is a **bulk best-effort scan** over N rows for a "show me what I've
got" surface. One poison row must not blank the whole list. These are genuinely
different contracts, so a shared parse helper would be a false abstraction — it would
have to take a "raise vs skip" flag, which is just two call sites wearing a trench
coat. The `try/except json.JSONDecodeError` lives inline in the `list_sessions` loop.

**This is NOT a behavior change to `read_checkpoint`** — it stays exactly as shipped
by `session-persistence`, satisfying the proposal's "no change to the checkpoint-read
contract" out-of-scope line. Purely additive and local to the new method.

### 2b. What "skip" means operationally

- The malformed row is **dropped from the result list** (not surfaced as a "corrupt"
  placeholder row this cycle — the proposal's scope is a listing surface, not a repair
  UI; a fake row would need its own column semantics and invites the user to act on
  garbage).
- It is **logged at `WARNING`** via the module logger
  (`logger.warning("Skipping corrupt checkpoint fact key=%s: %s", model.key, exc)`),
  matching the "logged, not raised" wording in the spec scenario. `repository.py`
  already has `import logging` and a module `logger` (used elsewhere in the file).
- **No warning surfaces to the interactive user** — the `/sessions` table just shows
  the valid rows. Rationale: a per-row parse failure is an operator/log concern, not
  an end-user actionable event mid-chat. (If a future cycle wants a "N rows
  skipped" footer, `list_sessions` can return a count — deferred, not this cycle.)

### 2c. Exception scope

Catch **`(json.JSONDecodeError, TypeError, KeyError)`** narrowly, NOT bare `except`.
`json.loads` on truncated text → `JSONDecodeError`; a non-string / null `value` →
`TypeError`; the extraction reads keys defensively with `.get(...)` so `KeyError`
should not occur, but is included as belt-and-suspenders. A bare `except` would
swallow programming errors and is banned by house style.

## 3. `MemoryRepository.list_sessions` — signature & return type (RESOLVED)

```python
@dataclass
class SessionSummary:
    session_id: str
    goal: str
    updated_at: datetime
    iterations_exhausted: bool

def list_sessions(self, project: str, limit: int = 20) -> list[SessionSummary]:
    ...
```

- **Return type: a small `@dataclass SessionSummary`, NOT a raw dict and NOT an ORM
  model.** The spec allows "dicts or a small dataclass"; the dataclass is chosen for
  the same reason the codebase already prefers typed `MemoryFact` over dicts — the
  `/sessions` renderer gets attribute access and type clarity, and the field set is
  fixed. Define it at module level in `repository.py`, next to the reserved-key
  constants (top of file, near line 34–38). Uses `from dataclasses import dataclass`
  (add to imports).
- **The method returns plain structures, never leaks `MemoryFactModel`** — consistent
  with `get_facts_by_scope`/`search_facts` which map through `MemoryFact.from_model`.

### Query shape (house style: `select` + `db.session()`, mirrors `search_facts`)

```python
def list_sessions(self, project: str, limit: int = 20) -> list[SessionSummary]:
    scope = f"project:{project}"
    like_pattern = RESERVED_FACT_KEY_PREFIX + "%:checkpoint"   # "session:%:checkpoint"
    with self.db.session() as session:
        stmt = (
            select(MemoryFactModel)
            .where(
                and_(
                    MemoryFactModel.scope == scope,
                    MemoryFactModel.key.like(like_pattern),
                )
            )
            .order_by(MemoryFactModel.updated_at.desc())
            .limit(limit)
        )
        models = session.execute(stmt).scalars().all()

    summaries: list[SessionSummary] = []
    for model in models:
        try:
            data = json.loads(model.value)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Skipping corrupt checkpoint fact key=%s: %s", model.key, exc)
            continue
        summaries.append(
            SessionSummary(
                session_id=data.get("session_id") or _session_id_from_key(model.key),
                goal=(data.get("goal") or ""),
                updated_at=_parse_updated_at(data.get("updated_at"), model.updated_at),
                iterations_exhausted=bool(data.get("iterations_exhausted", False)),
            )
        )
    return summaries
```

- **`updated_at` fallback** (spec-required): prefer the payload's ISO string
  (`data["updated_at"]`, written as `...isoformat() + "Z"` by `write_checkpoint`),
  fall back to the ORM column `model.updated_at` when the payload lacks/!parses it.
  `_parse_updated_at(iso_or_none, fallback_dt)` is a tiny module helper:
  `datetime.fromisoformat(s.rstrip("Z"))` guarded by try/except → fallback. Note the
  **`LIKE`-vs-payload ordering nuance**: SQL orders by the ORM `updated_at` column
  (indexed, cheap); the payload `updated_at` is only used for display. They are
  written together each turn so they agree in practice — ordering by the column is
  correct and avoids parsing every row just to sort.
- **`session_id` fallback**: derive from the key
  (`"session:{id}:checkpoint"` → strip prefix/suffix) only if the payload somehow
  lacks it — defensive, matches the exploration's "read from payload, not the key"
  primary path.
- **Empty project** → `models` empty → returns `[]`. No special-casing (spec scenario
  satisfied for free).
- **No-checkpoint sessions** are absent because the `LIKE` only matches checkpoint
  keys — `session:last` (the pointer) does NOT match `%:checkpoint`, so it is
  correctly excluded (spec scenario satisfied).

## 4. `/sessions` command — renderer & dispatch wiring (RESOLVED)

### Renderer `_show_sessions(agent, project)` — mirrors `_show_facts` (main.py:936)

```python
async def _show_sessions(agent: "AgentOS", project: str):
    sessions = agent.memory.list_sessions(project)     # see accessor note below
    if not sessions:
        console.print("[dim]No sessions yet for this project[/dim]")
        return
    table = Table(title=f"Sessions: {project}")
    table.add_column("Session", style="cyan")
    table.add_column("Goal", style="white")
    table.add_column("Updated", style="green")
    for s in sessions:
        label = s.goal.strip()[:60] if s.goal.strip() else f"(no goal) {s.session_id}"
        table.add_row(s.session_id, label, s.updated_at.strftime("%Y-%m-%d %H:%M"))
    console.print(table)
```

- **Empty state**: `[dim]...[/dim]` line, identical style to `_show_facts`'s
  `[dim]No facts[/dim]` (spec-required parity).
- **Goal fallback**: blank goal → `"(no goal) {session_id}"` label (spec-required
  "session_id + timestamp" fallback; timestamp already shown in its own column).
- **Truncation**: `[:60]` mirrors the existing `f.value[:80]` truncation pattern in
  `_show_facts`.
- **`async def`**: kept for signature symmetry with the other `_show_*` handlers that
  `_handle_command` awaits, even though the repo call is sync — matches house style
  (`_show_facts` is `async` around a call too).

### Accessor note (downstream flag)

`_show_facts` reaches memory via `agent.get_facts(project)` (an `AgentOS` async
wrapper), NOT the repository directly. `list_sessions` is a **new repository method**
with no `AgentOS` wrapper yet. Two options for tasks/apply:
- **(A) Preferred:** call `agent.memory.list_sessions(project)` directly if `AgentOS`
  exposes `.memory` (verify the attribute name in apply — the existing checkpoint
  hooks call `self.memory.write_checkpoint`, so `AgentOS.memory` is the
  `MemoryRepository`; the CLI holds an `AgentOS`, so `agent.memory` should reach it).
- **(B)** Add a thin `AgentOS.list_sessions(project)` pass-through for symmetry with
  `get_facts`. Low cost, more consistent. **Recommend (B)** if `get_facts`-style
  wrapping is the established convention; otherwise (A). Flagged for apply to confirm
  `AgentOS.memory` visibility.

### Dispatch wiring — additive `elif` in `_handle_command` (main.py:916)

Insert one branch, no existing branch altered:

```python
    elif cmd == "/sessions":
        await _show_sessions(agent, project)
```

Place it adjacent to `/facts` / `/skills`. `_handle_command` already has `project` in
scope. (Spec scenario "wired into command dispatch" satisfied.)

## 5. `_show_help(project, session_id)` — signature change & panel content (RESOLVED)

### Signature & call site

`_show_help()` → `_show_help(project, session_id)`. **Confirmed single call site** via
`rg "_show_help" src/`: only `main.py:759` (inside
`_async_interactive(agent, project, session_id)`, both params already in scope) and
the def at `903`. No other caller — the signature change is safe and local. Update
line 759 to `_show_help(project, session_id)`.

### "Resumed vs new" signal — **checkpoint presence, not resume provenance**

The interactive loop does NOT currently carry a "was this session resumed?" boolean —
`session_id` arrives already resolved (`_resolve_session_id` discards the
provenance). Threading a `resumed` flag would ripple through the resolution chain and
the `_async_interactive` signature — out of proportion for a help panel and beyond
this change's additive scope.

**Decision:** `_show_help` calls `agent.memory.read_checkpoint(project, session_id)`
and keys the contextual line off its result:
- checkpoint **present** → "Resuming session `{session_id}` — last goal: `{goal}`"
- checkpoint **`None`** → "New session `{session_id}` — no history yet"

This matches BOTH spec scenarios exactly (they are written in terms of checkpoint
existence: "a checkpoint exists with goal=…" vs "no checkpoint fact exists yet →
receives None"). It is a faithful proxy: a resumed session that has taken ≥1 turn has
a checkpoint; a freshly minted one does not until its first turn completes. The one
edge — a resumed session whose very first turn hasn't written yet — renders as "new,"
which is acceptable and non-misleading. **Flagged as an accepted approximation** for
tasks/verify so it isn't mistaken for a bug.

`read_checkpoint` raising on a corrupt row (see §2a) is acceptable here: help wraps
the read in a small `try/except` that falls back to the "new session" line rather
than crashing the help panel — but does NOT swallow silently for `list_sessions`'
sake; it's a local render-safety guard.

### Panel content

```python
def _show_help(project: str, session_id: str):
    try:
        checkpoint = _get_agent().memory.read_checkpoint(project, session_id)
    except Exception:
        checkpoint = None
    if checkpoint and checkpoint.get("goal"):
        state = (
            f"[green]Resuming[/green] session [cyan]{session_id}[/cyan]\n"
            f"Last goal: {checkpoint['goal'][:80]}"
        )
    else:
        state = f"[yellow]New[/yellow] session [cyan]{session_id}[/cyan] — no history yet"
    console.print(Panel(
        f"{state}\n\n"
        "[bold]Commands:[/bold]\n"
        "  /help           - Show this help\n"
        "  /memory         - Show recent memory\n"
        "  /facts          - Show facts for current project\n"
        "  /skills         - List skills\n"
        "  /sessions       - List past sessions for this project\n"
        "  /sdd            - Show SDD artifact status\n"
        "  /clear          - Clear screen\n"
        "  exit/quit       - Exit\n",
        title="Help", border_style="blue",
    ))
```

- **`/sessions` added to the command list** (spec-required — the list must gain the
  new command alongside the existing ones).
- The static command list is **preserved verbatim** (all 6 prior items) — spec
  requires the existing list stay.
- Agent accessor for `read_checkpoint`: `_show_help` currently takes no `agent`. Two
  options: (A) thread `agent` in too (`_show_help(agent, project, session_id)`) — the
  call site @759 has `agent` in scope; or (B) reuse the `_get_agent()` accessor if one
  exists in `main.py`. **Recommend (A)** — explicit, matches how `_handle_command`
  passes `agent, project, session_id`; avoids a hidden global lookup. Apply should
  make it `_show_help(agent, project, session_id)` and update line 759 accordingly.

## 6. Architecture Decisions (ADR-style)

### ADR-1: Corrupt-JSON tolerance is local to `list_sessions`; `read_checkpoint` unchanged
- **Decision:** inline narrow `try/except (JSONDecodeError, TypeError)` in the
  `list_sessions` loop, WARNING-log + skip row. `read_checkpoint` keeps raising.
- **Rationale:** bulk best-effort scan vs exact single-key read are different
  contracts; a shared helper with a raise/skip flag is a false abstraction. Keeping
  `read_checkpoint` unchanged honors the proposal's out-of-scope boundary.
- **Rejected:** shared parse helper (over-abstracted); making `read_checkpoint`
  swallow (would mask corruption as a new session in rehydration).

### ADR-2: `list_sessions` returns a typed `SessionSummary` dataclass
- **Decision:** `@dataclass SessionSummary(session_id, goal, updated_at,
  iterations_exhausted)`; never leak `MemoryFactModel`.
- **Rationale:** matches the codebase's typed-model convention (`MemoryFact`), gives
  the renderer attribute access, fixed field set.
- **Rejected:** raw dicts (untyped, spec allows but weaker), ORM leakage (couples CLI
  to persistence).

### ADR-3: Help "resumed vs new" derives from checkpoint presence, not resume provenance
- **Decision:** `read_checkpoint(...) is not None` drives the contextual line.
- **Rationale:** spec scenarios are written in checkpoint-existence terms; avoids
  rippling a `resumed` flag through `_resolve_session_id` → `_async_interactive`.
- **Rejected:** threading a provenance boolean (out of additive scope, larger blast
  radius).

### ADR-4: `LIKE`-scan ordered by the ORM `updated_at` column
- **Decision:** `MemoryFactModel.key.like("session:%:checkpoint")`, `order_by(updated_at.desc())`, `limit`.
- **Rationale:** cheap indexed sort; payload `updated_at` only for display. Fine at
  current scale (proposal's accepted scaling debt; `sessions` table deferred).

## 7. Assumptions & Risks for downstream phases

- **Assumption:** `AgentOS.memory` is the `MemoryRepository` and is reachable from the
  CLI's `agent` handle (the checkpoint hooks already use `self.memory.write_checkpoint`).
  Apply MUST confirm `agent.memory.list_sessions` / `agent.memory.read_checkpoint`
  resolve, or add thin `AgentOS` pass-throughs (see §4 option B, §5 option A).
- **Assumption:** `repository.py` has a module `logger` (`import logging` present at
  line 5) — apply confirms `logger = logging.getLogger(__name__)` exists or adds it.
- **Accepted approximation (not a bug):** help shows "new session" for a resumed
  session that hasn't completed its first turn (no checkpoint yet). Documented in §5.
- **Risk:** `_show_help` gaining an `agent` param is a second signature change in the
  same file — trivial, single call site, mechanical.
- **Deferred:** "N rows skipped" footer, `sessions` table/index, top-level
  `aki sessions` command, LLM titles — all out of scope this cycle per proposal.
```
