# Proposal: SDD Scaffolding Flow Suggestion

## Intent

Aki has no request-level scope awareness before it starts calling tools. On a genuinely large "make me a whole new project" ask, the reasoning loop dives straight into per-call work — reads, existence checks, then writes — each individual call technically complete, none tripping the per-call destructive gate, and the whole `max_iterations` budget drains without a coherent result. The real failure: "necesitamos ya poder tener el astro hecho" produced 12 tool calls and no working project, because the agent never paused to notice the *task itself* was too big and vague to attack without a plan.

The archived `agent-scaffolding-clarification` change fixed *call-level* eagerness (the prompt addendum and the destructive-tool gate both reason about a single tool call's argument completeness). It does not — and by design cannot — evaluate whole-conversation task scope. This change adds the missing *request-level* signal: when the first message of a session reads like a new/large product ask, suggest starting an SDD scoping flow instead of launching a runaway tool-call spree. Auto-detect and *suggest* — never force SDD. The user stays in control and can say "just do it" on the next turn.

## Scope

### In Scope
- **`NEW_PRODUCT_KEYWORDS` constant** (`src/agentos/agent/core.py`): a new, bilingual, deliberately *coarser* keyword/phrase tuple, distinct from and independent of the existing `SCAFFOLDING_KEYWORDS`. It targets whole-product framing ("nuevo proyecto", "armar toda la app", "arrancar desde cero", "build me a … app/project", "necesitamos … hecho", "poné en marcha", etc.) rather than the narrower file/component-level scaffolding intent `SCAFFOLDING_KEYWORDS` already covers. The two constants must not be merged — conflating them would make the narrow addendum fire on cases it was not designed for, and vice versa.
- **First-turn-gated pre-loop short-circuit** in `_reasoning_loop` (or in `chat()` immediately before it, `core.py:249-257`): when the broad heuristic matches **AND** this is the first turn of the session, the agent returns a plain-text SDD-suggestion response with **zero tool calls**, reusing the exact no-tool-call return shape the destructive gate already uses (`ReasoningOutcome(response=…, exhausted=False)`, core.py:480-484). The turn ends; nothing is written to disk.
- **First-turn detection via existing checkpoint state**: `read_checkpoint(project, session_id) is None`. Checkpoints are written at the end of *every* turn (`write_checkpoint`, core.py:278, step 6b) and read back in `_build_messages` (core.py:322). Therefore on turn 1 no checkpoint exists yet, and its absence is an already-wired, coherent first-turn signal consistent with the session-persistence mechanism from the archived `session-persistence` / `session-list-and-help` work. No new state, no new column, no new flag is needed.
- **Optional SDD-status enrichment**: when the short-circuit fires, call `detect_sdd_artifacts()` (`src/agentos/sdd/detector.py`) and fold the result into the suggestion text (e.g. "this project has no SDD artifacts yet — consider running sdd-init" vs. "an SDD change is already in progress"). This detector already runs standalone in CLI command bodies (main.py:232, 723, 1075) but is *never* wired into the agent's own reasoning path today; wiring it here is new but mechanically trivial (import + one call).

### Out of Scope
- **Does NOT force SDD.** The suggestion is advisory. A matching first turn ends with a suggestion; the user's next turn proceeds normally through the loop even if it repeats the same keywords.
- **Does NOT invoke `sdd_init.py` or any SDD phase automatically.** It only *suggests*; the user must act.
- **Does NOT fire on every matching turn.** Once the first turn is past (a checkpoint exists), the broad heuristic is not evaluated again for the rest of the session — the failure mode is about the *initial framing* of a large task, not every later mention of "crear".
- **Does NOT touch, weaken, replace, or merge with `agent-scaffolding-clarification`.** The narrower `SCAFFOLDING_KEYWORDS` prompt addendum (core.py:361-373) and the per-call destructive gate (core.py:476-484) remain independent, always-active mechanisms and continue to act as backstops on later turns.
- **Does NOT change telemetry.** A no-tool-call early return emits no new `status_callback` event types, identical to the existing destructive-gate short-circuit.
- **Does NOT introduce worker/delegation vocabulary.** This is single-turn, supervisor-only; `multi-agent-orchestration` (archived) owns `delegate`/worker semantics, and no nested loop is involved.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modified | New `NEW_PRODUCT_KEYWORDS` constant; first-turn-gated pre-loop short-circuit returning an SDD-suggestion response with zero tool calls |
| `src/agentos/sdd/detector.py` | Read-only reuse | `detect_sdd_artifacts()` called from the agent path for the first time (no change to the detector itself) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Broad keywords false-positive on legitimate quick first-turn asks | Med | First-turn-only gate limits exposure to one message per session; user proceeds unchanged next turn; coarse keyword set tuned at spec phase |
| Suggestion feels like a stall on a small task the user wanted done now | Low | Message is short and explicitly optional; the very next turn proceeds with tools; consistent with brainstorming-before-build UX |
| Overlap/confusion with the existing narrow `SCAFFOLDING_KEYWORDS` addendum | Low | Separate constant, separate trigger point (pre-loop vs. per-call), separate first-turn gate; both coexist by design |
| `read_checkpoint`-as-first-turn signal breaks if checkpoint write order changes | Low | Checkpoint is written unconditionally at every turn end today; spec pins this assumption and the memory-scope `disabled` edge case |

## Rollback Plan

Fully additive. Removing `NEW_PRODUCT_KEYWORDS` and the short-circuit restores current behavior exactly. No schema, no migration, no `config.py` change, and the reused detector is untouched.

## Dependencies

None external. Builds on the existing reasoning loop, the session/checkpoint infra (`read_checkpoint`/`write_checkpoint`), and the existing `detect_sdd_artifacts()` detector.

## Open Questions (for spec/design)

- **Exact `NEW_PRODUCT_KEYWORDS` membership** and how to keep it coarse enough to catch whole-product framing without swallowing narrow edits — the precise bilingual list is a spec deliverable.
- **Exact suggestion message wording** (bilingual), and how to template the two `detect_sdd_artifacts()` branches (SDD present vs. absent) into it.
- **Where the short-circuit physically lives**: `chat()` before `_reasoning_loop`, or the first-iteration entry of `_reasoning_loop`. Both are viable; design should pick the one that keeps first-turn detection and the return-shape reuse cleanest.
- **Memory-scope interaction**: when `profile.memory.scope == "disabled"` no checkpoint is written, so *every* turn would read as "first turn". Design must decide whether the suggestion is suppressed under disabled memory or gated by a separate in-loop signal.

## Success Criteria

- [ ] A first-turn whole-project ask ("necesitamos ya poder tener el astro hecho") yields an SDD-suggestion response with zero tool calls, `exhausted=False`.
- [ ] The same phrasing on a later turn of the same session proceeds through the loop normally (no re-suggestion).
- [ ] The narrow `SCAFFOLDING_KEYWORDS` addendum and the per-call destructive gate still fire independently and unchanged.
- [ ] The suggestion text reflects `detect_sdd_artifacts()` state (present vs. absent) for the target project.
- [ ] No `config.py` change, no forced SDD, no automatic `sdd-init` invocation, no new telemetry events.
