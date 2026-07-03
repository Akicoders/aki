# Proposal: Session Listing & Contextual Interactive Help

## Intent

Two everyday-visibility gaps in Aki's CLI/interactive-mode UX. First, there is no way to see past sessions: session identity lives only as `session:last` (a single most-recent pointer) and per-session checkpoint facts, so a user cannot answer "what was I working on before?" without guessing a `session_id`. Second, the user's direct complaint: `aki help` "isn't helping much anymore — you have to go step by step." Inside interactive mode `/help` (`_show_help`, `main.py:903-913`) is a static hardcoded 6-item Panel that ignores the `project`/`session_id` already in scope — it never says whether a session was resumed, what the last goal was, or what to do next. Fix both with additive, pattern-matching changes: a session-listing surface and a contextual help panel.

## Scope

### In Scope
- New read-only `MemoryRepository.list_sessions(project, limit)` — query `MemoryFactModel` where `scope == "project:{project}"` and `key LIKE "session:%:checkpoint"`, order by `updated_at desc`, parse each checkpoint JSON, return `(session_id, goal, updated_at, iterations_exhausted)`. No schema change, no migration.
- New interactive `/sessions` command (append one `elif` in `_handle_command`) rendering a Rich table (goal preview, updated_at, session_id, exhausted flag), mirroring existing `_show_facts` / `_show_skills`.
- Contextual `_show_help(project, session_id)` — thread the already-in-scope params in; report live state (session resumed? last goal via `read_checkpoint`? what to do right now) alongside the command list.

### Out of Scope
- New `sessions` table / schema migration (Approach A.3) — deferred; `LIKE`-scan is fine at current scale, tracked as known scaling debt.
- New top-level `aki sessions` CLI command — the complaint is about in-session UX; a top-level command can be a follow-up if wanted.
- Changes to `aki --help` (Typer-generated) — command discovery there is already adequate; the complaint targets interactive `/help`.
- Any change to the checkpoint-write contract or the archived `session-persistence` data model — this change only reads it.
- LLM-generated session titles/summaries — use the existing `goal` field as-is.

## Capabilities

### New Capabilities
- `session-listing`: read-only listing of a project's sessions derived from existing checkpoint facts, plus a contextual interactive help panel that reports live session/checkpoint state.

### Modified Capabilities
- None (reads the archived `session-persistence` checkpoint contract without respec'ing it).

## Approach

Exploration recommendation: pair A.1 + A.2 (repository method + interactive `/sessions`) with B.1 (contextual help). All three are additive and reuse established patterns. The list query reads `session_id` from each checkpoint JSON payload (already present) rather than parsing it out of the key string — avoids key-template coupling. `_show_help`'s signature gains `project`/`session_id`; the only caller is the single call site at `main.py:759`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/memory/repository.py` | Modified | New read-only `list_sessions(project, limit)` helper on facts |
| `src/agentos/cli/main.py` `_handle_command` | Modified | New `/sessions` command branch (additive `elif`) |
| `src/agentos/cli/main.py` `_show_help` | Modified | Add `project`/`session_id` params; contextual live-state section |
| `src/agentos/memory/models.py` | Read-only | Reuse `MemoryFactModel`; no new table/index |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `LIKE "session:%:checkpoint"` scan slow at scale | Low | Fine at hackathon scale; logged as scaling debt, table deferred |
| Sessions with no checkpoint yet are invisible | Med | Expected per checkpoint-write contract; note in `/sessions` empty/edge copy |
| Empty/truncated `goal` yields poor row label | Low | Fall back to session_id + timestamp when goal is blank |
| `_show_help` signature change breaks a caller | Low | Only one call site (`main.py:759`); internal function |

## Rollback Plan

Fully additive and read-only. Revert the `list_sessions` method, the `/sessions` branch, and the `_show_help` param change to restore exact prior behavior — no migration, no data change, no schema to undo.

## Dependencies

- None external. Reads existing checkpoint facts written by the archived `session-persistence` change.

## Delivery

**SMALL — single PR, not stacked.** One repository method plus two additive edits in `main.py`; no >400-line risk. No delivery-mechanics decision needed at proposal time.

## Success Criteria

- [ ] `/sessions` in interactive mode lists the project's sessions (goal preview, updated_at, session_id) newest-first.
- [ ] Sessions without a checkpoint are handled gracefully (no crash; sensible empty/edge copy).
- [ ] `/help` reports current session state (resumed? last goal? next action) in addition to the command list.
- [ ] No schema change, no change to the checkpoint-write contract, `aki --help` untouched.
