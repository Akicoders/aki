# Explore: SDD Flow Suggestion for New-Project Requests

## Problem

Real failure: user said "necesitamos ya poder tener el astro hecho" (a vague,
large-scope new-project-creation ask). The agent skipped straight to
filesystem tool calls (read/write/exists) with no scoping plan and exhausted
its iteration budget without producing a coherent result. The user wants the
agent to auto-detect "this is a new-product/scaffolding request" and SUGGEST
starting an SDD flow (ask scope questions / propose an SDD change) — NOT force
mandatory SDD on every scaffolding request without exception (explicitly
rejected).

## 1. What `agent-scaffolding-clarification` already covers (and doesn't)

Archived at
`openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/`,
spec at `openspec/specs/agent-scaffolding-clarification/spec.md`. Two
mechanisms, both narrower than what's needed here:

**a) Prompt addendum** — `src/agentos/agent/core.py:35-45` defines
`SCAFFOLDING_KEYWORDS`, a bilingual tuple (`create`, `generate`, `set up`,
`scaffold`, `new project`, `bootstrap`, `crear`, `generar`, `armar la
estructura`, etc.). In `_build_messages` (`core.py:361-373`), if any keyword
matches `user_input.lower()`, a system message is appended telling the model:
before calling a destructive tool, verify you have target path,
framework/stack, naming convention, file layout — and if missing, ask ONE
clarifying question instead of writing blind.

**b) Destructive-call gate** — a `destructive: bool` flag on tool metadata
(`src/agentos/skills/base.py`, `src/agentos/skills/filesystem.py`) tags
`write`/`append`/`delete`. Inside `_reasoning_loop` (`core.py:246-261` per the
spec doc), before executing any `destructive: true` call, a deterministic
heuristic (`_is_under_specified`) checks whether `path` or `content` is
missing/empty/placeholder. If so, the tool is not executed and the turn ends
with a plain-text clarifying question, `exhausted=False`.

**The gap**: both mechanisms fire only around an *individual tool call*'s
argument completeness. Neither evaluates conversation-level task scope. The
"astro hecho" request never necessarily produced an under-specified
destructive call — the model could call `filesystem_exists`, `filesystem_read`
repeatedly (non-destructive, ungated) while building a mental plan, then
proceed to writes with technically-complete-looking arguments for each
individual file, none of which trip the per-call gate. There is no signal at
all for "this whole task is too big/vague to attack without a plan" — that is
a request-level judgment, not a call-level one. `agent-scaffolding-clarification`
would NOT have prevented this failure.

## 2. Where a broader "whole-new-project" detection could live

Two viable spots, both upstream of tool execution:

- **Reuse/extend `_build_messages`** (`core.py:292-378`): add a second,
  coarser keyword/phrase heuristic alongside `SCAFFOLDING_KEYWORDS` — e.g.
  phrases signaling *whole-product* scope rather than a narrow edit:
  "necesitamos que esté hecho", "nuevo proyecto", "armar toda la app",
  "build me a [tech] app/project", "arrancar desde cero", "poné en marcha".
  This wants to be a **separate constant** (e.g. `PROJECT_SCOPE_KEYWORDS` or
  similar) from `SCAFFOLDING_KEYWORDS` — the existing one is intentionally
  about *file/component-level* scaffolding intent (narrow), this new one is
  about *whole-project* intent (broad). Conflating them would make the
  existing narrow addendum fire on cases it wasn't designed for.

- **A pre-loop request classifier** in `chat()`/`_reasoning_loop` entry
  (`core.py:240-261`, before the loop's first iteration): a short-circuit that,
  if the broad heuristic matches AND (optionally) this looks like the first
  user turn of the session, returns a `ReasoningOutcome` with no tool calls at
  all — mirroring the exact mechanism already used for the destructive-gate
  short-circuit (`response` is plain text, `exhausted=False`, existing
  no-tool-call return path at `core.py:238-243` per the archived spec).

Both spots are compatible; in practice the second *is* the mechanism, the
first is where the trigger condition lives.

## 3. What "suggesting SDD" should mean in a single-turn tool-calling loop

This is not an interactive wizard — one user message, one model turn, then
either tool calls or a text response. Concrete options:

- **(a) First-response scoping message, no tool calls.** When the broad
  heuristic fires, inject a system message instructing the model: this looks
  like a new-product/whole-project request; before touching the filesystem,
  respond with a short scoping message that names the ambiguity (stack,
  target dir, feature scope, non-goals) and proposes running an SDD
  explore→proposal cycle, then STOP — do not call any tool this turn. This is
  structurally identical to the existing destructive-gate short-circuit, just
  triggered earlier (before any tool call, not after an under-specified one).
  Cheapest to build, reuses established pattern, no new subsystem.

- **(b) Actually invoke `sdd_detector`/`sdd-init` capability.** Call
  `detect_sdd_artifacts()` (`src/agentos/sdd/detector.py:29-47`) against the
  *target* project directory when the broad heuristic fires. If
  `has_sdd=False`, fold that fact into the system message from (a): "this
  project has no SDD artifacts yet — suggest running sdd-init first." This is
  the same detector already used standalone at CLI startup
  (`src/agentos/cli/main.py:232-239`, prints a `Panel` in the `interactive`
  command) and at `main.py:723` and `main.py:1075` for other commands — but
  that startup panel is a **separate, CLI-level, always-on print**, unrelated
  to the model's own reasoning turn. It is not "reused" by the agent loop
  today; the agent's `_build_messages`/`_reasoning_loop` never call
  `detect_sdd_artifacts` currently — only CLI command bodies do. Wiring it
  into the prompt path would be new, but mechanically trivial (import +
  one function call already used elsewhere).

- **(c) Both** — scoping message always (a), enriched with concrete SDD-status
  context (b) when available, still ending the turn without tool calls.

## 4. Interaction with existing/archived work

- Must NOT touch or weaken the per-call destructive gate from
  `agent-scaffolding-clarification` — that stays as an unconditional backstop
  regardless of whether the new broader detection fires (per that spec's own
  language: "the gate fires independently of the scaffolding-intent prompt
  addendum's success").
- Must NOT introduce worker/delegation vocabulary — `multi-agent-orchestration`
  (archived, `openspec/changes/archive/2026-07-04-multi-agent-orchestration/`)
  already owns `delegate` tool/worker semantics; this change is single-turn,
  supervisor-only, no nested loop involved.
- Telemetry (`status_callback`) stays untouched — a no-tool-call early return
  produces no new event types, same as the existing destructive-gate
  short-circuit.

## Recommendation

Option **(c)**: a new, narrowly-scoped, coarser keyword/phrase constant
(e.g. `NEW_PRODUCT_KEYWORDS`) checked in `_build_messages` alongside (not
merged into) `SCAFFOLDING_KEYWORDS`, paired with a pre-loop short-circuit in
`_reasoning_loop` that: (1) fires only when the broad heuristic matches, (2)
calls `detect_sdd_artifacts()` for extra context when available, (3) returns
a plain-text scoping/suggestion response with zero tool calls, `exhausted=
False`, using the exact same return shape as the current destructive-gate
short-circuit. This is the cheapest correct fix: no new subsystem, reuses two
already-built, already-spec'd mechanisms (`_build_messages` addendum pattern,
no-tool-call return path) plus one already-existing detector function, and
it is trivially an auto-detect-and-suggest, never a mandatory gate — the
model can still proceed with tools next turn once the user answers or says
"just do it."

Open question for proposal phase: should the broad heuristic be gated to
"first user turn of session only" (avoids re-triggering mid-conversation on
every message containing "crear"), or evaluated per-turn like the existing
narrow one? Recommend first-turn-only or a session-level "already suggested
once" flag, since the failure mode is specifically about the *initial* framing
of a large task, not every mention of a keyword.
