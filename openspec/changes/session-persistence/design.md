# Design: Session Persistence & Context Rehydration

## Status

Design phase for change `session-persistence`. Inputs: `proposal.md`, `explore.md`.
Validated against actual schemas in `src/agentos/memory/models.py` and
`src/agentos/memory/repository.py`. `src/agentos/core/config.py` is OFF-LIMITS this
session (concurrent ownership) — NOT read, NOT modified; tunables land as module
constants and wiring is deferred.

## 1. Architecture Approach

Approach C from exploration: reuse `MemoryRepository`, no new store, no new
`EventType`. Two orthogonal capabilities, layered so each ships as its own PR:

1. **Durable session identity** — a reserved-key `MemoryFact` records the last-used
   `session_id` per project. CLI resolves it at startup so `chat`/`interactive`
   auto-resume.
2. **Structured checkpoint** — a reserved-key `MemoryFact` per session holds a
   deterministic JSON snapshot (goal, open items, last tool-result summary). Written
   per turn and on iteration-limit exhaustion; read back into a dedicated,
   budget-immune system message in `_build_messages`.

Layering (dependency direction, all downward):

```
cli/main.py        resolve session_id (fact read) ── writes last_session on start
   │ passes session_id
agent/core.py      chat() ── checkpoint write hook (post-loop + on exhaustion)
   │               _build_messages() ── checkpoint read → reserved system slot
   │ calls typed helpers
memory/repository.py   checkpoint + last_session read/write helpers on facts
   │ uses
memory/models.py       MemoryFact / MemoryFactModel (UNCHANGED — reuse only)
```

The checkpoint read path is **deliberately separate** from `assemble_context()`.
`assemble_context` retrieves facts via `search_facts` (keyword `ilike`) and then
runs `_fit_context_to_budget`, which silently drops facts/events that don't fit.
Routing the checkpoint through that path would make rehydration relevance-dependent
and truncatable — exactly the bug we're fixing. Instead the checkpoint is fetched by
exact `(scope, key)` and injected verbatim in its own reserved slot.

## 2. Key Decision: MemoryFact vs. MemoryEvent discriminator (RESOLVED)

**Decision: reserved-key `MemoryFact`. Rejected: `EventType` + `meta={"kind":
"checkpoint"}` discriminator.** Validated against the real schemas:

| Requirement | `MemoryFact` | `MemoryEvent` + meta kind |
|---|---|---|
| Mutable current-state (overwrite, not append) | `upsert_fact` exists; one row per `(scope,key)` | append-only log; every turn adds a row, must query-latest + prune |
| Exact-key lookup | `get_fact(key, scope)` — direct, indexed (`ix_memory_facts_scope_key`) | no exact-key read; must `search_events`/filter by meta and sort |
| No new enum / migration | none needed | needs a value; reusing `OUTCOME`/`DECISION` pollutes those semantics + Chroma index |
| Bounded storage | 1 row per session, stable id | unbounded rows unless we prune |
| Avoids embedding cost | facts are not embedded | `add_event` always embeds `content` — wasteful for a mutable blob |

Events are an **append-only episodic log with embeddings**; a checkpoint is
**mutable current-state read by exact key**. The fact table is the correct home. The
`session_id` pointer is likewise a single mutable value → fact.

**Schema fit confirmed:** `MemoryFactModel.value` is `Text` (unbounded) → JSON blob
fits. `key` and `scope` are `String(256)` → reserved keys well within limits.
`confidence` is unused for checkpoints; pin to `1.0`.

### Critical gotcha — `upsert_fact` keys on `id`, NOT `(key, scope)`

`upsert_fact(fact)` looks up `session.get(MemoryFactModel, fact.id)` by **primary
key id**. A fresh `MemoryFact(...)` gets a random `fact_{uuid}` id, so naive upsert
would INSERT a duplicate row every turn — never updating in place. The repository
helper MUST implement read-then-write:

```python
def _upsert_reserved_fact(self, key: str, scope: str, value: str) -> MemoryFact:
    existing = self.get_fact(key, scope)          # exact (scope,key) lookup
    fact = MemoryFact(
        id=existing.id if existing else None,      # reuse id → true in-place update
        key=key, scope=scope, value=value, confidence=1.0,
    )
    return self.upsert_fact(fact)
```

(If `existing` is None, let the `MemoryFact` default factory mint the id.) This keeps
exactly one checkpoint row per session and one `session:last` row per project.

## 3. Fact Key / Scope Naming Scheme (RESOLVED)

Single scope per project, distinct reserved keys — mirrors existing
`scope=project:{name}` convention already used by `assemble_context`/`get_facts_by_scope`.

| Purpose | scope | key |
|---|---|---|
| Last-used session pointer | `project:{project}` | `session:last` |
| Per-session checkpoint | `project:{project}` | `session:{session_id}:checkpoint` |

Reserved-key prefix is `session:`. Because these live in the normal
`project:{name}` scope, `get_facts_by_scope` (fallback path in `assemble_context`)
could surface them. Guard: when `assemble_context` falls back to
`get_facts_by_scope`, filter out keys starting with `session:` so reserved control
facts never leak into the generic memory section (they have a dedicated slot). This
is a small additive filter, not a behavior change to ranking.

### Checkpoint value structure

`value` is a JSON string (parsed/serialized by the repository helper, not the
caller). Fields deterministic, no LLM summarization this cycle:

```json
{
  "v": 1,
  "session_id": "sess_ab12cd34",
  "project": "aki",
  "goal": "string — the user's current objective (latest user turn or carried goal)",
  "open_items": ["string", "..."],
  "last_tool_result": "string — truncated summary of the last tool execution",
  "last_response": "string — truncated final assistant response",
  "iterations_exhausted": false,
  "updated_at": "ISO-8601 UTC"
}
```

- `v` is a schema version for forward-safe evolution; reader tolerates missing/unknown fields.
- All free-text fields are hard-capped (see constants) before serialization so the
  row and its rehydrated render stay bounded.
- `open_items` this cycle = deterministic derivation (e.g. carried over + the goal if
  the loop exhausted). No planner. A follow-up may enrich it.

## 4. Hook Points in `agent/core.py` (RESOLVED)

### 4a. Checkpoint WRITE — in `chat()`, after `_reasoning_loop` returns (step 6 area, ~line 97–108)

`chat()` already stores the assistant event at line 99. Add the checkpoint write
immediately after, in the same method, so it runs on EVERY turn regardless of whether
the loop finished naturally or exhausted:

```python
# 6b. Persist structured checkpoint (mutable current-state)
self.memory.write_checkpoint(
    project=project,
    session_id=session_id,
    goal=user_input,                     # latest objective
    last_response=response,
    last_tool_result=last_tool_summary,  # see below
    iterations_exhausted=response.startswith(EXHAUSTION_SENTINEL),
)
```

**Getting `last_tool_result`:** `_reasoning_loop` currently returns only the final
string. Minimal change: have `_reasoning_loop` also surface the last tool-result
summary (return a small tuple/dataclass, or stash it on an attribute). Preferred:
return a lightweight `ReasoningOutcome(response, last_tool_summary, exhausted)` so
`chat` doesn't re-parse the exhaustion string. The exhaustion branch (line 241) sets
`exhausted=True`; the natural-return branch (line 197) sets it False. This keeps the
"write on iteration-limit exhaustion" requirement satisfied by the SAME single write
call — no second write site.

Rationale for single write site in `chat()` (not inside the loop): one deterministic
write per turn, avoids mid-loop churn and duplicate rows, and both success and
exhaustion paths converge there.

### 4b. Checkpoint READ — in `_build_messages()` (~after line 126, before memory-context injection)

`_build_messages` currently has no `session_id` parameter. Thread `session_id`
through from `chat()` (line 88 call site) into `_build_messages`. Then, right after
the base system prompt and BEFORE the memory-context message, inject the reserved
checkpoint slot:

```python
checkpoint = self.memory.read_checkpoint(project, session_id)  # exact (scope,key)
if checkpoint:
    messages.append({
        "role": "system",
        "content": render_checkpoint(checkpoint, cap=CHECKPOINT_REHYDRATION_CHAR_CAP),
    })
```

`render_checkpoint` is a deterministic bounded formatter (reuse the
`capsule.py` bounded-render pattern conceptually — plain function, hard char cap).
Placing it BEFORE the memory-context message gives it positional primacy and, more
importantly, it NEVER passes through `context.format_for_prompt` /
`_fit_context_to_budget`, so it is immune to the existing budget-fit truncation. Its
size is bounded independently by `CHECKPOINT_REHYDRATION_CHAR_CAP`, so it cannot crowd
the token budget unboundedly.

**Budget immunity guarantee:** the checkpoint is a separate `messages` entry built
from a separate read; `assemble_context`'s `max_tokens` governs only `context`
(facts+events), never this slot. There is no reserved-slice logic today and we are
NOT adding one to `_fit_context_to_budget` — we sidestep it entirely.

### 4c. No change to `_reasoning_loop` control flow

Only its return shape changes (to carry `last_tool_summary` + `exhausted`). The
exhaustion message helper (`_format_exhaustion_message`) is unchanged; we detect
exhaustion via the structured flag, not string-sniffing.

## 5. Session Auto-Resume Mechanics in `cli/main.py` (RESOLVED)

### Resolution order (both `chat` and `interactive`)

```
1. --session <id>          → explicit, wins unconditionally
2. --new-session flag      → force a fresh random id, and DO persist it as new last
3. last_session fact       → repo.get_fact("session:last", "project:{project}").value
4. new random id           → f"sess_{uuid4().hex[:8]}" (only when no fact exists)
```

Implementation shape (shared helper to avoid duplication between the two commands):

```python
def _resolve_session_id(project: str, session: Optional[str], new_session: bool) -> str:
    if session:
        return session
    if not new_session:
        last = _memory().get_fact("session:last", f"project:{project}")
        if last:
            return last.value
    return f"sess_{uuid.uuid4().hex[:8]}"
```

`--new-session` semantics: a boolean `typer.Option(False, "--new-session")` on both
`chat` and `interactive`. When set, skip the last-session lookup and mint fresh. It
is mutually informative with `--session`: if BOTH are passed, `--session` wins (an
explicit id already IS a deliberate session choice); optionally warn. Document that
`--new-session` without `--session` = "start clean here".

### Persisting `session:last`

The pointer must be written so the NEXT invocation resumes. Two viable sites:
- **Preferred:** write it inside `AgentOS.chat()` alongside the checkpoint write
  (`write_checkpoint` already runs every turn — have it also upsert `session:last`,
  OR call a sibling `touch_last_session(project, session_id)`). This guarantees the
  pointer is durable even for one-shot `aki chat`, and keeps CLI thin.
- Alternative: CLI writes it right after resolution. Rejected — duplicates logic
  across `chat`/`interactive` and misses the MCP/programmatic callers.

Decision: `AgentOS.chat()` writes `session:last` every turn via the repository
helper. CLI only READS for resolution. This keeps a single write authority and makes
resume work identically for `chat`, `interactive`, and any future caller.

Log the resolved id (already partially done via `logger.info(f"User [{session_id}]...")`
and `_print_interactive_header`) so auto-resume is observable — mitigates the
"stale session surprise" risk from the proposal.

## 6. Hardcoded Default Constants (config.py deferred) (RESOLVED)

`config.py` is off-limits. Define named module-level constants (NOT literals inline)
so the follow-up migration is a mechanical lift-and-wire. Location: co-locate with
the code that consumes them, grouped and commented as "deferred config".

In `memory/repository.py` (or a small `memory/session.py` if preferred for cohesion):

```python
# --- Deferred config (see follow-up: wire into AgentConfig/MemoryConfig) ---
CHECKPOINT_FIELD_CHAR_CAP = 1000        # per free-text field cap before serialize
CHECKPOINT_REHYDRATION_CHAR_CAP = 2000  # hard cap on rendered rehydration slot
RESERVED_FACT_KEY_PREFIX = "session:"   # reserved-key namespace guard
LAST_SESSION_KEY = "session:last"
```

In `agent/core.py`:

```python
# --- Deferred config (see follow-up: wire into AgentConfig) ---
CHECKPOINT_CADENCE_TURNS = 1  # write checkpoint every N turns (1 = every turn)
```

Cadence is `1` this cycle (write every turn) — simplest, deterministic, and the write
is cheap (single fact upsert, no embedding). The constant exists so the follow-up can
raise it without touching call sites. `CHECKPOINT_REHYDRATION_CHAR_CAP` is the
"rehydration budget slice" the proposal calls for — a plain char cap, independent of
`memory.max_context_tokens`.

Rationale for constants over literals: the proposal's risk row "Deferred config.py
wiring drifts from defaults" is mitigated by centralizing every knob as a single named
symbol with a `# deferred config` marker, so the migration is grep-able.

## 7. Repository Helpers (new, on `MemoryRepository`)

All additive, no signature changes to existing methods:

```python
def read_checkpoint(self, project: str, session_id: str) -> Optional[dict]: ...
def write_checkpoint(self, project: str, session_id: str, *, goal: str,
                     last_response: str, last_tool_result: str,
                     iterations_exhausted: bool) -> None: ...
def touch_last_session(self, project: str, session_id: str) -> None: ...
def get_last_session(self, project: str) -> Optional[str]: ...
def _upsert_reserved_fact(self, key: str, scope: str, value: str) -> MemoryFact: ...
```

- `write_checkpoint` builds the JSON (caps each field to `CHECKPOINT_FIELD_CHAR_CAP`),
  calls `_upsert_reserved_fact`, and also calls `touch_last_session`.
- `read_checkpoint` does `get_fact(f"session:{session_id}:checkpoint",
  f"project:{project}")`, `json.loads` with tolerance for missing/legacy `v`.
- `get_last_session` reads `session:last`; returns `.value` or None.

## 8. Test Strategy (strict TDD, pytest) (RESOLVED)

Write tests FIRST for each unit. Two tiers:

### Tier A — pure unit (repository + formatter), no CLI, no LLM

Fast, isolated, in-memory. Use an in-memory/temp SQLite `MemoryRepository` with a
fake `Embedder` (the repo already supports injecting `embedder=` — pass a stub whose
`embed` returns a fixed vector so no model download). Facts aren't embedded anyway.

- `test_upsert_reserved_fact_updates_in_place` — write twice with same key/scope →
  exactly ONE row, value updated (guards the `id`-vs-`(key,scope)` gotcha).
- `test_write_then_read_checkpoint_roundtrip` — fields preserved, JSON valid.
- `test_write_checkpoint_caps_long_fields` — oversize goal truncated to cap.
- `test_write_checkpoint_touches_last_session` — `session:last` set to session_id.
- `test_read_checkpoint_missing_returns_none`.
- `test_get_last_session_absent_returns_none`.
- `test_read_checkpoint_tolerates_missing_version` — legacy/blob without `v`.
- `test_assemble_context_excludes_reserved_session_facts` — `session:*` keys never
  appear in generic facts section (fallback path filter).
- `render_checkpoint` formatter: `test_render_checkpoint_respects_char_cap`.

### Tier B — CLI resolution (CliRunner + monkeypatch), mock the agent

Follow the existing `tests/unit/test_cli_project_resolution.py` pattern exactly:
`typer.testing.CliRunner`, `patch("agentos.cli.main._get_agent", return_value=AsyncMock())`,
inspect `agent.chat.call_args`.

- `test_chat_explicit_session_wins` — `--session s1` → chat called with `s1`.
- `test_chat_resumes_last_session_fact` — monkeypatch repo `get_fact("session:last")`
  → chat called with stored id (patch the memory accessor used by `_resolve_session_id`).
- `test_chat_new_session_ignores_last_fact` — `--new-session` with a stored last →
  chat called with a FRESH `sess_` id, not the stored one.
- `test_chat_no_fact_mints_random` — no stored fact → `sess_`-prefixed id.
- `test_chat_session_and_new_session_prefers_explicit` — both flags → explicit wins.
- Mirror the resume/new-session cases for `interactive` (invoke may need input feed /
  early exit; assert on `agent.chat`/header, or factor `_resolve_session_id` as a pure
  function and unit-test it directly — preferred, keeps CLI tests thin).

### Tier C — agent hook wiring (lighter integration)

- `test_chat_writes_checkpoint_each_turn` — `AgentOS.chat` with a fake qwen + fake
  memory (or spy) asserts `write_checkpoint` called once per turn.
- `test_build_messages_injects_checkpoint_slot` — when `read_checkpoint` returns data,
  `_build_messages` output contains a system message with the rendered checkpoint,
  positioned before the memory-context message, and NOT routed through
  `format_for_prompt`.
- `test_build_messages_no_checkpoint_omits_slot` — None → no extra system message.

**Isolation call:** `_resolve_session_id` and `render_checkpoint` should be extracted
as pure functions specifically so the bulk of logic is Tier-A/pure-unit testable
without CliRunner or async plumbing. Reserve CliRunner for the flag-wiring assertions
only.

## 9. Architecture Decisions (ADR-style)

### ADR-1: Checkpoint stored as reserved-key MemoryFact, not a discriminated event
- **Decision:** reserved-key `MemoryFact` (`session:{id}:checkpoint`, scope `project:{name}`).
- **Rationale:** upsert/mutable-current-state semantics, exact-key indexed read, no
  new `EventType` (no SQLAlchemy Enum migration), no embedding cost, bounded storage.
- **Rejected:** `EventType.OUTCOME/DECISION` + `meta={"kind":"checkpoint"}` — append-only,
  pollutes episodic semantics + Chroma vector index, unbounded rows, needs latest-query.
- **Validated against:** `MemoryFactModel` (`value: Text`, `ix_memory_facts_scope_key`),
  `upsert_fact`/`get_fact` in `repository.py`.

### ADR-2: Checkpoint read bypasses assemble_context / budget-fit
- **Decision:** `_build_messages` reads the checkpoint by exact key and injects a
  dedicated system message, separate from `context`.
- **Rationale:** `_fit_context_to_budget` silently truncates and `search_facts` is
  relevance-gated — both would make rehydration unreliable. A separate slot with its
  own char cap is deterministic and budget-immune.
- **Rejected:** adding a reserved-slice to `_fit_context_to_budget` — more invasive,
  couples checkpoint to the ranking path we're trying to escape.

### ADR-3: Single checkpoint + last-session write authority in AgentOS.chat()
- **Decision:** `chat()` writes both the checkpoint and `session:last` every turn; CLI
  only reads for resolution.
- **Rationale:** one write site covers success and exhaustion, works for `chat`,
  `interactive`, and programmatic/MCP callers, keeps CLI thin, avoids duplicate-row
  bugs.
- **Rejected:** CLI-side pointer writes — duplicated across two commands, misses
  non-CLI callers.

### ADR-4: Tunables as named module constants, config.py wiring deferred
- **Decision:** constants in `repository.py`/`session.py` and `core.py`, marked
  `# deferred config`.
- **Rationale:** `config.py` off-limits (concurrent ownership); named symbols make the
  follow-up migration mechanical and grep-able, mitigating drift risk.

## 10. Assumptions & Risks for downstream phases

- **Assumption:** `_reasoning_loop` can be refactored to return a small outcome object
  without breaking `stream_chat` (which calls `chat`, not the loop directly) — verify
  in tasks/apply.
- **Assumption:** the memory accessor used by `_resolve_session_id` is reachable/mockable
  from CLI without constructing a full `AgentOS` (may need a thin `_memory()` accessor
  like the existing `_get_agent()`).
- **Risk:** reserved facts sharing `project:{name}` scope could leak into generic
  context — mitigated by the `session:` prefix filter in the `get_facts_by_scope`
  fallback; MUST be covered by `test_assemble_context_excludes_reserved_session_facts`.
- **Risk:** `--session` + `--new-session` ambiguity — resolved by "explicit id wins",
  documented, optionally warned.
- **Deferred:** LLM-derived `open_items`, config.py wiring, cadence > 1 — out of scope
  this cycle.
</content>
</invoke>
