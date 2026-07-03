# Exploration: agent fires tool calls too early on scaffolding requests

## Complaint

Agent executes tools too early in simple scaffolding flows ("create a new
file/component/project structure"). Wastes iterations, fails before closing
out requirements, gives bad UX.

## Where the loop lives

- `src/agentos/agent/core.py:69` `AgentOS.chat()` — entry point per turn.
- `src/agentos/agent/core.py:207-291` `_reasoning_loop()` — the actual
  tool-calling loop.
- `src/agentos/agent/core.py:220` `for iteration in range(max_iterations):`
  — one Qwen call per iteration, `tool_choice="auto"` (line 226). The model
  decides on every single turn, starting with turn 1, whether to call a
  tool or answer. There is no gate before the first tool-call opportunity.
- `src/agentos/agent/core.py:238` `if not response.tool_calls: return` — the
  ONLY way the loop exits early with a plain-text answer is if the model
  itself chooses not to call a tool. Nothing in the loop nudges the model
  toward asking a clarifying question before acting; the loop is agnostic
  to intent, it just executes whatever the model requested every iteration.
- `src/agentos/core/config.py:151-153` — `max_iterations: int = 5`,
  `temperature: float = 0.3`, `system_prompt_template: str = ""` (empty by
  default).

## System prompt / tool framing

- `src/agentos/agent/core.py:147-151` — default system prompt (used only
  when `system_prompt_template` is unset) is generic: "Be concise,
  practical, and careful with context budgets." No language about
  clarifying before acting, no distinction between read-only vs structural
  (destructive) tools, no scaffolding-specific guidance.
- `src/agentos/agent/core.py:193-200` — the only conditional prompt
  augmentation is SDD-keyword detection (spec/design/proposal/tasks/sdd/
  specification/architecture), which injects SDD context. Scaffolding
  requests ("create a new component", "set up a project structure") don't
  match these keywords, so they get zero special framing.
- `src/agentos/skills/filesystem.py:16` — `FilesystemSkill.description =
  "File operations: read, write, search, glob, list"`. Read and write/
  delete operations are all lumped into one flat description with no
  destructive/structural signal. `write()` at line 60 defaults
  `create_dirs=True`, silently creating directory trees — a structural
  side effect the model isn't warned to gate behind confirmation.
- `src/agentos/skills/base.py:160` `get_all_tools()` — tool schemas are
  built from function docstrings/signatures (per skill), there is no
  metadata field for risk tier or "ask before calling" hints anywhere in
  the `Skill` / `SkillResult` classes (`src/agentos/skills/base.py:19-35`).

## Root causes

1. **No clarification gate before first tool call.** `_reasoning_loop`
   (core.py:220-243) treats iteration 1 exactly like iteration N: model
   sees `tool_choice="auto"` and full tool list from turn zero. Nothing
   encourages "ask first, act second" for structural/creation requests.
2. **System prompt has no task-shape awareness.** The only prompt branching
   is SDD-keyword detection (core.py:193-200); ad hoc scaffolding asks
   ("crea un componente nuevo", "arma la estructura del proyecto") never
   trigger any requirements-gathering framing, unlike the recently added
   SDD path.
3. **Tool descriptions don't signal blast radius.** `FilesystemSkill`
   description conflates `read`/`list`/`glob` (safe) with `write`/`delete`
   (structural/destructive) under one line (filesystem.py:16). The model
   has no signal to treat file-creation differently from a read, so it
   applies the same eagerness to both.
4. **Iteration budget has no reserved "clarify" turn.** `max_iterations = 5`
   (config.py:151) is spent entirely on tool-call/response turns; if the
   model scaffolds against ambiguous requirements, gets a wrong/partial
   result, and needs to ask + redo, it can burn the whole budget and hit
   the honest-exhaustion message from `_format_exhaustion_message`
   (core.py:293-309, added in cc4f535) instead of ever asking a question.
   The cc4f535 fix made the failure message honest, but did not address why
   the loop reaches exhaustion on ambiguous scaffolding tasks in the first
   place.

## Concrete failure shape

Turn 1: model receives vague scaffolding ask + full tool list with
`tool_choice="auto"` → immediately calls `filesystem.write` with guessed
path/content → `create_dirs=True` silently creates structure → result may
not match what user wanted → subsequent iterations try to patch/redo →
budget of 5 iterations exhausted → user gets the (now honest, but still
late) `_format_exhaustion_message`. The waste is real work already done
(files written) plus wasted iterations, not just a bad message.

## Prior art worth inspiration (not to copy)

- Claude Code's own `brainstorming` skill (per this session's available
  skills list) models "explore user intent, requirements, and design
  before implementation" as a mandatory pre-step for creative/feature work.
  The pattern worth borrowing: a lightweight, skill-like or prompt-level
  precondition that fires specifically on task shapes matching creation/
  scaffolding intent (new file, new component, new project structure)
  and requires an explicit "requirements resolved" signal before the loop
  is allowed to reach a structural tool call — distinct from the existing
  SDD-keyword branch, which is proposal/spec-oriented, not simple
  scaffolding-oriented.

## Candidate fix approaches

1. **Pre-tool-call clarification gate in the loop.**
   Add a lightweight classification step before iteration 1 of
   `_reasoning_loop` (or as a first system-prompt instruction) that detects
   scaffolding-shaped intent (new file/component/structure, ambiguous scope)
   and forces the model's first response to be tool-free (`tool_choice
   ="none"` for iteration 0 conditionally) unless the user request already
   contains sufficient specifics (path, name, structure).
   - Pros: structural, does not rely on prompt-following alone; directly
     prevents premature writes.
   - Cons: needs a reliable classifier (keyword heuristic will be fragile,
     similar problem to the existing SDD-keyword check); adds one guaranteed
     non-tool turn even for well-specified requests, costing an iteration
     when not needed unless conditioned carefully.

2. **Scaffolding-specific system prompt addendum.**
   Extend `_build_messages` (core.py:139-205) with a branch parallel to the
   SDD-keyword branch (core.py:193-200): detect scaffolding verbs
   ("create", "crear", "generate", "set up", "scaffold", "new project/
   component/file") and inject an instruction: "If the request is missing
   key structural details (target path, framework, naming, file layout),
   ask a clarifying question before calling any write/delete tool."
   - Pros: cheap, consistent with existing pattern (SDD keyword injection),
     no loop-structure change, easy to test.
   - Cons: relies entirely on the model honoring prompt instructions with
     `tool_choice="auto"` still in effect — no hard guarantee, keyword
     detection is brittle (misses paraphrases, false-positives on unrelated
     asks mentioning "create").

3. **Tag structural/destructive tools + require explicit confirmation
   step.** Add a `risk` or `destructive: bool` field to `Skill`/tool schema
   (`src/agentos/skills/base.py:19-35`) for `write`/`delete`/`append` in
   `FilesystemSkill`, and have the loop intercept the first destructive
   tool call per turn: if requirements look incomplete (e.g., no prior
   assistant turn in this session, ambiguous args), synthesize a
   confirmation/dry-run response instead of executing, prompting the user
   to confirm plan details.
   - Pros: works at the tool layer regardless of prompt-following quality;
     generalizable to any future skill, not just filesystem; can reuse
     `SkillResult`/`tool_call` plumbing already in the loop.
   - Cons: more invasive change (touches `Skill` base class + all skill
     tool schemas + loop dispatch logic); risk of over-blocking legitimate
     one-shot requests that already have enough detail, unless paired with
     a "sufficient detail" heuristic (likely still needs approach 2's
     detection logic underneath).

**Recommendation for follow-up SDD phases:** combine (2) as the
low-cost first slice (prompt-level scaffolding framing, mirroring the
existing SDD-keyword pattern) with (3) applied narrowly to just
`filesystem.write`/`delete`/`append` as a second slice, since those are the
concrete destructive calls implicated in the complaint. Approach (1) is the
most robust but the costliest to get right (classification reliability) and
can be deferred.
