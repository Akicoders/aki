# Explore: Session Persistence & Context Rehydration

## What

Investigated "sessions do not rehydrate context reliably" — no code written, investigation only.

## Why

Remaining unfixed item from the QA punch list. Symptoms: loss of continuity across turns, hitting "maximum iterations" too easily, weak persistence of important context.

## Findings

### 1. How messages are built per turn (`src/agentos/agent/core.py`)

`AgentOS.chat()` does **not** pass a growing raw transcript across turns — this contradicts the original QA framing. Each call to `chat()` rebuilds `messages` from scratch in `_build_messages()`: system prompt, one system message injecting `MemoryRepository.assemble_context()` output, one system message listing enabled skills, optional SDD-context message, and the current user message only.

Cross-turn continuity depends **entirely** on `assemble_context(query, project, session_id, max_tokens)`, which returns: up to 15 keyword-matched facts, up to 10 vector/keyword-matched events (project-scoped, not session-scoped), plus (if `session_id` given) up to 10 additional events from *this session in the last 2 hours*, merged and deduped, then budget-fit to `max_tokens` (facts prioritized before events, both silently truncatable).

Only *within* a single turn does the message list grow (assistant/tool messages across `_reasoning_loop` iterations) — discarded once `chat()` returns.

**Root cause of "loss of continuity"**: session-scoped recall only reaches back 2 hours, caps at 10 events, and has no explicit "what we were doing / what's still open" state — just raw event content subject to relevance matching, which can miss anything not textually similar to the current query.

**Root cause of hitting max_iterations too easily**: each turn re-injects memory context + skills + prior tool-output events verbatim, with no summarization/compaction of what's already been tried. The model can re-explore the same ground because there's no structured "already-attempted" or "current plan" state.

### 2. Where `session_id` comes from / persistence

- `aki chat` (no `--session`): `AgentOS.chat()` generates `f"sess_{uuid4().hex[:8]}"` inline per call, never persisted or returned to the caller — every invocation without `--session` gets a fresh random id.
- `aki interactive`: generates one id at process start, held only in a local variable, never written to disk. Restarting always starts a new session unless the user manually pastes a prior id via `--session`.
- No `.aki/` directory, session file, or "last session" pointer exists anywhere in the codebase (confirmed via Glob/Grep).
- **Conclusion**: `session_id` today is a purely in-memory, per-process, best-effort correlation key — never a durable, resumable handle.

### 3. What `MemoryRepository` already provides for free

- `MemoryEventModel` already has an indexed `session_id` column and an `EventType` enum (USER_PREFERENCE, DECISION, TASK, CONVERSATION, ERROR, OUTCOME, CODE_CHANGE, DEPLOY). Conversation turns are already persisted as `CONVERSATION` events with `meta={"role": ...}`.
- `MemoryFactModel` — scoped key/value store (`project:{name}` / `global` / `user:{x}`) with confidence and upsert semantics — natural home for durable "session state" if modeled as a reserved-key fact.
- `MemoryRepository.consolidate_project()` exists as a **stub** (`# TODO: Use LLM to extract facts from events`), threshold-triggered by raw event count (10000, effectively never fires), not session-scoped, and has **no caller anywhere in the codebase outside tests** — dead code today. Closest existing thing to a "checkpoint" concept.
- `assemble_context()` is itself the existing rehydration mechanism — retrieval-based (vector + keyword + time window), not checkpoint-based.
- `capsule.py`'s `build_memory_capsule` is a separate MCP-only bounded-text renderer (4000 char cap, tags facts/decisions/procedures/recent with sources) — not wired into `AgentOS.chat()` at all. Reusable *formatting* pattern, not a persistence mechanism.

### 4. Existing checkpoint/compact/rehydrate concepts

Grep for `checkpoint|compact|rehydrat|Session(Repository|Store|State)` across `src/` found exactly one hit: `capsule.py`'s docstring "Compact memory capsule formatting" — a naming coincidence, unrelated to checkpointing. This is greenfield.

### 5. `config.py` scope note

`src/agentos/core/config.py` almost certainly already holds `AgentConfig.max_iterations`, `memory.max_context_tokens`, and the prompt templates referenced throughout `core.py`. Any new config knobs (checkpoint interval, rehydration budget split) would need a new field there. **This file is off-limits this session** (concurrent-ownership constraint) — not read beyond confirming existence. Flag for design: any approach needing new config surface must hardcode sane defaults and defer `config.py` wiring to a follow-up, or get explicit coordination first.

## Candidate approaches

**A. Reuse `MemoryRepository` only (facts + events), no new storage.**
Write a structured checkpoint fact/event after each turn (or on iteration-limit-hit), always injected in `_build_messages` regardless of relevance ranking; persist `session_id` itself as a fact so CLI can auto-resume.
Pros: zero new schema/storage, reuses existing SQLite+Chroma infra, consistent across CLI/MCP/cockpit.
Cons: fact/event schema wasn't designed for "current state" semantics; must avoid crowding the existing token budget; new `EventType` enum value is a migration-ish concern (reuse existing type via `meta` instead).
Effort: SMALL–MEDIUM.

**B. New file-based session store** (`.aki/sessions/<id>.json`, the user's original idea).
Pros: matches original mental model, inspectable, no DB schema changes, richer structured state possible.
Cons: second source of truth alongside SQLite/Chroma, needs its own consistency/locking story, fully greenfield (no precedent), duplicates the git-root project-detection question already solved elsewhere.
Effort: MEDIUM–LARGE.

**C. Hybrid — durable state in facts, automatic `session_id` resolution (no separate file).**
Persist checkpoint via facts (per A) *and* make `session_id` auto-resume from a `last_session_id` fact when `--session` is omitted, so both `aki chat` and `aki interactive` naturally continue without the user pasting an id.
Pros: gets ~90% of the outcome with the smallest surface — fixes the actual observed bug (random session_id churn) plus adds structured checkpoint content.
Cons: same schema-fit caveat as A; no bespoke plan/task object format.
Effort: SMALL–MEDIUM. Closest to "minimal session persistence + rehydration" as originally scoped, without inventing a parallel store.

## Recommendation

Approach C. Directly addresses both observed symptoms (session_id churn, weak inter-turn context) without duplicating storage the project already has. Approach B is over-scoped relative to the actual bug and introduces a second source of truth.

## Scope estimate: MEDIUM

Suggested phase boundaries:
1. **Design decision needed**: how to represent "checkpoint" content without a new `EventType` enum migration — likely reuse `EventType.OUTCOME`/`DECISION` with `meta={"kind": "checkpoint"}` (mirrors `capsule.py`'s existing `_event_kind` pattern), or a reserved-key `MemoryFact` under `scope=project:{name}:session:{id}`. Explicit call needed, no silent default.
2. **Auto-resume session_id** (small, high-value, low-risk — could ship as its own PR): default `session_id` resolution in `cli/main.py` (`chat` + `interactive`) to the last-used session via fact lookup, with an explicit `--new-session` escape hatch.
3. **Checkpoint write**: after each turn (or on iteration-limit exhaustion), write/update the structured checkpoint (goal, open items, last tool-result summary).
4. **Checkpoint read**: `_build_messages`/`assemble_context` always includes the current session's checkpoint as a dedicated system message, bypassing relevance filtering and the existing budget-fit truncation that has no reserved slice today.
5. **Config surface** (deferred/flagged): any new knobs coordinated separately, not bundled into this cycle's first slice.

## Where

`src/agentos/agent/core.py` (`AgentOS.chat`, `_build_messages`, `_reasoning_loop`), `src/agentos/cli/main.py` (`chat`, `interactive`, session_id sourcing), `src/agentos/memory/repository.py` (`assemble_context`, new checkpoint read/write helpers), `src/agentos/memory/models.py` (EventType/MemoryFact usage — no new tables required), `src/agentos/memory/capsule.py` (reusable bounded-render pattern, not directly wired in).

`src/agentos/core/config.py` is **out of scope this session** (flagged, not touched).

## Learned

The user's original symptom framing ("only a growing transcript is passed to the model") doesn't match the code — there's no growing transcript across turns at all. The actual mechanism is per-turn memory *retrieval*, which is arguably a subtler bug (silent, relevance-dependent context loss) than a runaway-transcript problem. Also confirmed `session_id` is never persisted anywhere, including within a single `interactive` process — it's just a local Python variable.
