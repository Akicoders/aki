# Proposal: Session Persistence & Context Rehydration

## Intent

Aki loses cross-turn continuity. `session_id` is never persisted: `aki chat` mints a fresh random id per call and `aki interactive` keeps it in a local variable that dies with the process. Continuity depends solely on `assemble_context()` relevance retrieval (2h/10-event window, no reserved slot for "what we're doing / what's still open"), so context silently drops and the agent re-explores solved ground, burning iterations. Fix both: durable, auto-resumable sessions plus a structured checkpoint that always rehydrates.

## Scope

### In Scope
- Auto-resume `session_id`: resolve last-used session from a durable fact when `--session` is omitted (both `chat` and `interactive`), with an explicit `--new-session` escape hatch.
- Durable checkpoint state (goal, open items, last tool-result summary) written per turn / on iteration-limit exhaustion, stored via existing `MemoryRepository` (facts), no new store.
- Guaranteed checkpoint rehydration: `_build_messages` injects the current session's checkpoint as a dedicated system message, bypassing relevance ranking and budget truncation.
- Hardcoded sane defaults for tunables (checkpoint cadence, rehydration budget slice) in the new/existing memory + agent modules.

### Out of Scope
- New `.aki/` file-based session store (Approach B) — rejected, second source of truth.
- LLM-based summarization/compaction of checkpoints — keep structured/deterministic this cycle.
- Any change to the MCP server surface.
- New `config.py` fields — `config.py` is off-limits this session; tunable wiring deferred to a follow-up change.
- New `EventType` enum value — avoided (SQLAlchemy Enum migration risk).

## Capabilities

### New Capabilities
- `session-persistence`: durable, auto-resumable session identity and structured checkpoint write/read/rehydration.

### Modified Capabilities
- None (no existing spec files; `assemble_context` behavior extended, not respec'd at capability level yet).

## Approach

Approach C from exploration. Reuse `MemoryRepository`: persist `last_session_id` and per-session checkpoint state as **reserved-key `MemoryFact`s** (scope `project:{name}`, e.g. key `session:last` and `session:{id}:checkpoint`). Facts chosen over events because they have upsert semantics (checkpoint is mutable current-state, not an append log) and need no `EventType` change — satisfying the no-new-enum constraint. Design phase may revisit the fact-vs-event discriminator. CLI resolves session id at startup via fact lookup; `AgentOS._build_messages` reads the checkpoint fact and injects it verbatim in a reserved system slot.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/cli/main.py` | Modified | Session-id resolution in `chat`/`interactive`; `--new-session` flag |
| `src/agentos/agent/core.py` | Modified | `_build_messages` reserved checkpoint slot; checkpoint write hook in `chat`/`_reasoning_loop` |
| `src/agentos/memory/repository.py` | Modified | Checkpoint + last-session read/write helpers on facts |
| `src/agentos/memory/models.py` | Read-only | Reuse `MemoryFactModel`; no new tables/enum |
| `src/agentos/core/config.py` | Untouched | Off-limits; defaults hardcoded, wiring deferred |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Checkpoint crowds token budget | Med | Reserved bounded slice with hardcoded cap; facts prioritized deterministically |
| Fact schema not designed for "current state" | Med | Upsert on reserved keys; design phase validates fit vs event alternative |
| Auto-resume surprises user with stale session | Low | `--new-session` escape hatch; log resolved session id |
| Deferred `config.py` wiring drifts from defaults | Low | Centralize defaults as named module constants for easy follow-up migration |

## Rollback Plan

Revert per stacked PR. Auto-resume and checkpoint are additive: reverting restores random-per-call `session_id` behavior. Reserved-key facts are inert if unread — no migration to undo, no schema change to roll back.

## Dependencies

- None external. Relies only on existing SQLite/Chroma `MemoryRepository` infra.

## Delivery

Stacked-to-main chained PRs (same pattern as prior `web-ui-cockpit` change): (1) auto-resume session_id — small, high-value; (2) checkpoint write; (3) checkpoint rehydration read. `config.py` tunables = separate follow-up.

## Success Criteria

- [ ] `aki chat` twice in a row (no `--session`) continues the same session.
- [ ] `aki interactive` restart resumes the prior session unless `--new-session`.
- [ ] Structured checkpoint always appears in rehydrated context, independent of query relevance.
- [ ] No new `EventType`, no `config.py` change, no new file store.
