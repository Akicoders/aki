# Proposal: Agent Scaffolding Clarification

## Intent

Aki fires destructive tool calls too early on scaffolding requests ("create a new component", "set up the project structure"). The reasoning loop treats iteration 1 exactly like iteration N — `tool_choice="auto"` from turn zero, no distinction between safe reads and structural writes — so the model guesses a path/layout, `filesystem.write` silently creates directory trees (`create_dirs=True`), the result misses the user's intent, and follow-up iterations burn the whole `max_iterations=5` budget patching it. The user ends up with unwanted files on disk plus the honest-but-late exhaustion message. Fix the eagerness at two layers: nudge the model to gather requirements first via a scaffolding-intent prompt addendum, and tag destructive filesystem tools so ambiguous structural calls resolve to a clarifying question instead of an immediate write.

## Scope

### In Scope
- **Scaffolding-intent prompt addendum**: extend `_build_messages` (core.py:139-205) with a branch parallel to the existing SDD-keyword branch (core.py:193-200). Detect scaffolding verbs/phrases ("create", "crear", "generate", "generar", "set up", "scaffold", "new project/component/file", "armar la estructura") and inject a system instruction: if the request is missing key structural details (target path, framework, naming, file layout), ask a clarifying question before calling any write/delete/append tool.
- **Destructive-tool tagging**: add a `destructive: bool` (default `False`) field to the `Skill`/tool metadata (`src/agentos/skills/base.py`) and tag `filesystem.write`, `filesystem.delete`, `filesystem.append` as destructive. Surface the flag in the tool schema built by `get_all_tools()` so the model can see blast radius, and make it available to the loop for gating.
- **Confirmation gating (soft, in-loop)**: when a destructive tool call is the first action of a turn AND the requirements look incomplete (heuristic: no prior assistant turn in this session for this ask / scaffolding-intent detected with under-specified args), the loop does NOT execute the call. Instead it returns a clarifying question as the turn's response. See "What confirmation means" below.

### Out of Scope
- **Full `tool_choice="none"` structural clarification gate (Approach 1)** — deferred. A hard pre-tool-call classification turn is the most robust fix but the costliest to get right (classifier reliability, a guaranteed extra iteration on well-specified asks). Not in this cycle.
- LLM-based intent classification — keep detection keyword/heuristic-based this cycle, consistent with the existing SDD-keyword branch.
- `max_iterations` / reserved-clarify-turn changes in `config.py` — `config.py` is off-limits; iteration-budget tuning deferred.
- Extending destructive tagging beyond `FilesystemSkill` (no other built-in skill has destructive ops today).
- Any interactive human-in-the-loop CLI y/n prompt (see below).

## What "Confirmation" Means (operationally)

Aki is a **single-turn LLM agent loop** (`_reasoning_loop`), not a human-in-the-loop CLI blocker, and there is **no existing confirmation-prompt pattern** in the codebase (verified: the loop executes every `tool_call` immediately at core.py:246-261; no interception, no dry-run, no y/n path). So "confirmation" here is NOT an interactive prompt that blocks the process waiting for stdin.

Instead: when the gate fires, the loop **short-circuits the destructive tool call and ends the turn with a plain-text clarifying question as the assistant response**. The user answers on their next turn (which, with session persistence already in place, rehydrates as context), and by then the request carries the missing structural details — so the destructive call proceeds normally. Confirmation = "ask in the response, act next turn," which fits the existing turn/checkpoint model and reuses the same `ReasoningOutcome`-return path already used when the model chooses not to call a tool (core.py:238-243). No new CLI surface, no blocking I/O.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modified | Scaffolding branch in `_build_messages`; destructive-first-call gate in `_reasoning_loop` returning a clarifying question |
| `src/agentos/skills/base.py` | Modified | `destructive` metadata on tool/skill; expose in `get_all_tools()` schema |
| `src/agentos/skills/filesystem.py` | Modified | Tag `write`/`delete`/`append` as destructive; sharpen description to separate safe reads from structural writes |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| False positives block legitimate well-specified quick scaffolding | Med | Gate only fires when args look under-specified AND it's the first turn's first destructive call; specified path+content passes through |
| Prompt-following unreliable under `tool_choice="auto"` | Med | Prompt addendum is a nudge, not a guarantee; the tool-layer destructive gate backstops it independently of prompt adherence |
| Keyword detection brittle (misses paraphrases, false-positives on "create") | Med | Mirror the accepted SDD-keyword brittleness tradeoff; bilingual keyword set; design phase refines the "under-specified" heuristic |
| Clarifying-question turn feels like a stall to the user | Low | Question is specific and actionable; next turn proceeds; consistent with brainstorming-before-build UX |

## Rollback Plan

Fully additive. Reverting the prompt branch restores prior framing; the `destructive` field defaults `False` so untagged tools behave exactly as today; removing the gate restores immediate execution. No schema, no migration, no `config.py` change to undo.

## Dependencies

None external. Builds on the existing skill registry, reasoning loop, and session/checkpoint infra.

## Success Criteria

- [ ] A vague scaffolding ask ("creá un componente nuevo") yields a clarifying question, not an immediate `filesystem.write`.
- [ ] A well-specified ask (explicit path + content) still writes on the first turn without a clarification stall.
- [ ] `write`/`delete`/`append` carry `destructive: true` in their tool schema; reads/list/glob/search do not.
- [ ] No `config.py` change, no `tool_choice="none"` gate, no blocking CLI prompt introduced.
