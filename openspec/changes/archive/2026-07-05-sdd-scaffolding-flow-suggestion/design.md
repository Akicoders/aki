# Design: SDD Scaffolding Flow Suggestion

## Status

Design phase for change `sdd-scaffolding-flow-suggestion`. Inputs: `proposal.md`,
`specs/sdd-scaffolding-flow-suggestion/spec.md`. Validated against the real code in
`src/agentos/agent/core.py` (`chat`, `_reasoning_loop`, `_build_messages`,
`_run_delegation`), `src/agentos/memory/repository.py` (`read_checkpoint` /
`write_checkpoint`), and `src/agentos/sdd/detector.py` (`detect_sdd_artifacts`).
`src/agentos/core/config.py` is OFF-LIMITS this cycle — NOT read, NOT modified; the new
keyword tuple lands as a module constant next to `SCAFFOLDING_KEYWORDS` (`core.py:35`),
wiring deferred (same discipline as `agent-scaffolding-clarification` and
`session-persistence`).

This change adds ONE request-level signal: a first-turn, memory-enabled,
supervisor-only short-circuit that returns a plain-text SDD-scoping suggestion with zero
tool calls. It is fully additive and shares NO state with the archived
`agent-scaffolding-clarification` mechanisms (prompt addendum + destructive gate), which
remain untouched and continue to fire independently.

## 1. Architecture Approach

```
chat(user_input, project, session_id, profile_id)
   │  resolves session_id, profile               (core.py:208-211)
   │  stores user event, assembles context        (core.py:214-237)
   │  builds messages, filters tools              (core.py:239-247)
   │
   ├── NEW: request-level short-circuit  ── _should_suggest_sdd_flow(user_input, profile, project, session_id)
   │        if fires → outcome = ReasoningOutcome(_build_new_product_suggestion(has_sdd), exhausted=False)
   │        else     → outcome = await self._reasoning_loop(...)   (unchanged)
   │
   │  step 6 / 6b: store response + write checkpoint  (core.py:260-286, UNCHANGED)
   ▼
(_reasoning_loop, _run_delegation, depth threading — ALL UNCHANGED)
```

The short-circuit lives in `chat()`, immediately before the `_reasoning_loop` call
(`core.py:250`). It does NOT enter, wrap, or modify the loop. On a normal turn `chat()`
is byte-for-byte its current self.

## 2. Key Decision: placement — `chat()` BEFORE `_reasoning_loop` (RESOLVED)

The proposal left this open (`chat()` pre-loop vs. first-iteration entry inside
`_reasoning_loop`). This design commits to **`chat()`, immediately before the
`_reasoning_loop` call at `core.py:250`.**

### Why `chat()` and NOT inside `_reasoning_loop`

- **Every input the check needs is already a local in `chat()`, and cleanly.**
  `chat()` has `user_input` as a raw string parameter (`core.py:200`), `session_id`
  resolved (`core.py:208-209`), `profile` resolved (`core.py:211`), and `self.memory`
  for `read_checkpoint`. Inside `_reasoning_loop` the user text is buried in the
  `messages` list (last `role:"user"` entry) and would have to be re-extracted — an
  ugly, fragile inversion of `_build_messages`. `chat()` needs NOTHING new threaded in.
- **DECISIVE — worker exclusion is structural and free (see §3).** Workers spawned by
  delegation call `self._reasoning_loop(...)` directly from `_run_delegation`
  (`core.py:572`, `depth=1`) and NEVER pass through `chat()`. Placing the check in
  `chat()` means a worker physically cannot reach it — no explicit `depth` guard, no
  risk of ever disturbing the `multi-agent-orchestration` depth parameter or the
  `delegate`-tool schema gating at `core.py:408-409`.
- **DECISIVE — the checkpoint write must still run so the suggestion does not repeat.**
  Success criterion #2 requires that the SAME phrasing on turn 2 proceeds normally.
  That only holds if a checkpoint is written at the end of the suggestion turn (so
  turn 2 sees `read_checkpoint(...) is not None`). By setting `outcome` and SKIPPING the
  loop — rather than early-`return`ing out of `chat()` — the existing steps 6/6b
  (`core.py:260-286`) run unchanged and persist the checkpoint from
  `outcome.response` / `outcome.exhausted`. An early `return` before step 6b would leave
  the checkpoint absent and re-fire the suggestion on every subsequent turn forever — a
  correctness bug. The set-outcome-and-skip shape avoids it with zero new persistence
  code.
- **Status-callback sequence is undisturbed.** The suggestion path reuses the existing
  `_notify_status` calls that already bracket the loop in `chat()` (`Starting turn`,
  context, `_format_saving_status`, `_format_terminal_status`). It emits NO new event
  types — identical to the destructive-gate short-circuit (proposal "no new telemetry").
  The loop's internal thinking/tool status calls simply never run because the loop never
  runs — same as any turn the model answers in one shot.

The alternative (`_reasoning_loop` first-iteration entry) was rejected: it keeps all
"pre-tool-call intelligence" co-located with the destructive gate (a mild plus) but
requires re-extracting `user_input`, an explicit `depth == 0` guard, and careful
reasoning about whether the worker path also writes a checkpoint (it does not —
`_run_delegation` never calls `write_checkpoint`). Every one of those is a way to get it
wrong; `chat()` sidesteps all three.

## 3. Key Decision: worker (depth>0) exclusion — structural via `chat()` (RESOLVED)

The spec did not explicitly cover whether a worker (`depth == 1`) should be excluded.
This design resolves it: **workers MUST NEVER trigger the suggestion, and this is
guaranteed structurally by the `chat()` placement — no explicit `depth` check is
written.**

Rationale: a worker is executing a delegated sub-task on behalf of a supervisor; from the
end user's perspective it is not "starting a new product," and a worker independently
suggesting a fresh SDD scoping cycle would be incoherent (and would surface
worker/delegation-adjacent behavior the proposal explicitly forbids). Because
`_run_delegation` invokes `_reasoning_loop` directly (`core.py:572`) and only `chat()`
carries the short-circuit, the exclusion falls out for free. Additionally, worker
sessions (`worker_sid`, `core.py:557`) never get a checkpoint written for them
(`_run_delegation` has no `write_checkpoint` call), so even a hypothetical future worker
path through `chat()` would need the memory-scope and checkpoint reasoning re-derived —
another reason to keep the trigger anchored to the single top-level entry point.

Mechanism of record: **no `depth` parameter is referenced by this feature at all.** The
`chat()` entry point is depth-0 by definition. This is the exact mechanism — anchoring to
`chat()` — rather than gating on `depth == 0` inside the loop.

## 4. `NEW_PRODUCT_KEYWORDS` constant (RESOLVED)

Declared as a module-level tuple immediately after `SCAFFOLDING_KEYWORDS` (`core.py:44`),
same shape (bilingual, `# deferred config` marker), matched case-insensitively by
substring against `user_input.lower()` — identical structure to the `SCAFFOLDING_KEYWORDS`
check (`core.py:361`). The two tuples are SEPARATE constants and MUST NOT be merged.

```python
# deferred config
NEW_PRODUCT_KEYWORDS = (
    # English — whole-product / whole-app framing only
    "build me a new app", "build me an app", "build a new project",
    "start a new project", "create a whole new product", "whole new app",
    "the whole app built", "set up the entire project", "the entire project",
    "build the whole thing", "from scratch", "entire application",
    # Spanish — whole-product / whole-app framing only
    "toda la app", "toda la aplicación", "todo el proyecto",
    "proyecto nuevo", "nuevo desde cero", "desde cero",
    "arrancar desde cero", "poné en marcha el proyecto",
    "poner en marcha el proyecto", "tener el proyecto hecho",
    "necesitamos ya poder tener", "que esté hecho el proyecto",
    "armar toda la app",
)
```

### Design rationale — coarser intent than, and independent of, SCAFFOLDING_KEYWORDS

- `SCAFFOLDING_KEYWORDS` is a set of SHORT, single-verb tokens (`"create"`, `"crear"`,
  `"armar"`, `"new file"`, `"new component"`) that fire on narrow per-file/per-component
  intent. `NEW_PRODUCT_KEYWORDS` is a set of LONGER multi-word PHRASES that only match
  when the user frames the ask at whole-product scale (`"toda la app"`,
  `"todo el proyecto"`, `"from scratch"`, `"the entire project"`). Using phrases rather
  than bare verbs is what keeps the two non-overlapping: `"creá un componente nuevo"`
  contains `SCAFFOLDING_KEYWORDS` tokens but none of these phrases, so it does NOT match
  `NEW_PRODUCT_KEYWORDS` (spec scenario "Narrow scaffolding phrase does not trigger").
- **Correction (found during verify):** a few `NEW_PRODUCT_KEYWORDS` phrases do contain
  a bare `SCAFFOLDING_KEYWORDS` token as a substring — e.g. `"armar toda la app"`
  contains `"armar"`, `"start a new project"` / `"build a new project"` contain
  `"new project"`, and `"set up the entire project"` contains `"set up"`. This is
  harmless, not a bug: the two lists are consumed by entirely separate mechanisms —
  `NEW_PRODUCT_KEYWORDS` only feeds `_should_suggest_sdd_flow`, checked in `chat()`
  *before* `_reasoning_loop` (and thus before `SCAFFOLDING_KEYWORDS`) ever runs, so
  there is no ambiguous double-match at runtime, only incidental substring overlap in
  the source lists. The design goal is non-overlapping *intent* (whole-product framing
  vs. single-file framing), not zero shared substrings.
- `"necesitamos ya poder tener el astro hecho"` (the canonical failure case) matches via
  `"necesitamos ya poder tener"` (spec scenario "New-product phrase is recognized").
- Substring `.lower()` matching is safe here for the same reason it is safe for the
  scaffolding branch: `user_input` is a short natural-language ask, not a payload.

## 5. Function signatures and call-site integration (RESOLVED)

Three additions, all in `src/agentos/agent/core.py`. Two are module-level pure helpers
(table-testable, no I/O — mirrors `_is_under_specified` / `_build_clarifying_question`
from the archived change); the eligibility decision is a small private method on
`AgentOS` because it needs `self.memory`.

### 5a. Pure keyword matcher (module-level)

```python
def _is_new_product_request(message: str) -> bool:
    """True when the message frames a whole-new-product/app ask.

    Pure over `message` — coarse bilingual phrase match, independent of
    SCAFFOLDING_KEYWORDS. No history, no I/O.
    """
    lowered = message.lower()
    return any(kw in lowered for kw in NEW_PRODUCT_KEYWORDS)
```

### 5b. Pure suggestion-message builder (module-level)

```python
def _build_new_product_suggestion(has_sdd: bool) -> str:
    """Compose the SDD-scoping suggestion; branch on detect_sdd_artifacts()."""
    ...  # exact wording in §6
```

### 5c. Eligibility method (on `AgentOS`, needs `self.memory`)

```python
def _should_suggest_sdd_flow(
    self,
    user_input: str,
    profile: Optional[AgentProfile],
    project: str,
    session_id: str,
) -> bool:
    """All three gate conditions for the request-level SDD suggestion.

    Fires only when: memory is not disabled, this is the first turn
    (no checkpoint), and the input reads like a whole-new-product ask.
    Order is cheapest-and-most-suppressive first.
    """
    if profile is not None and profile.memory.scope == "disabled":
        return False
    if not _is_new_product_request(user_input):
        return False
    return self.memory.read_checkpoint(project, session_id) is None
```

Guard ordering rationale: the `disabled`-scope check is first and cheapest — it fully
suppresses under disabled memory (spec "Suggestion Suppressed When Memory Scope Is
Disabled") without ever touching the DB. The keyword check is next (pure, in-memory). The
`read_checkpoint` DB read runs last, only when the other two pass — so a non-matching
turn pays no extra I/O.

### 5d. Call-site integration in `chat()` (replaces the direct loop call at core.py:250)

```python
# 5. Reasoning loop (or request-level SDD short-circuit)
if self._should_suggest_sdd_flow(user_input, profile, project, session_id):
    sdd_status = detect_sdd_artifacts()
    outcome = ReasoningOutcome(
        response=_build_new_product_suggestion(sdd_status.has_sdd),
        last_tool_summary="",
        exhausted=False,
    )
else:
    outcome = await self._reasoning_loop(
        messages, tools, project, session_id,
        status_callback=status_callback, profile=profile,
    )
response = outcome.response
```

`detect_sdd_artifacts` is imported at module top (`from agentos.sdd.detector import
detect_sdd_artifacts`) — the same call `main.py:232` already uses with default
`project_dir=None` (→ `Path.cwd()`), matching how `summarize_sdd_context()` is already
invoked from `_build_messages`. Steps 6/6b below the call are UNCHANGED and write the
checkpoint from `outcome`, closing the "don't repeat on turn 2" requirement.

## 6. Suggestion message wording — both branches (RESOLVED)

Spanish, matching the surrounding user-facing strings in this file
(`_format_exhaustion_message`, the scaffolding addendum). Advisory, short, explicitly
optional, and free of any worker/delegation vocabulary.

```python
def _build_new_product_suggestion(has_sdd: bool) -> str:
    if has_sdd:
        return (
            "Esto parece el arranque de un proyecto/app completo. Ya hay artefactos "
            "SDD en este proyecto, así que antes de tirar comandos sueltos conviene "
            "retomar el flujo SDD en curso (continuar la propuesta/spec/tareas "
            "existentes) para no perder el hilo del plan. "
            "Si preferís que lo haga directo igual, decímelo en el próximo mensaje "
            "y sigo sin SDD."
        )
    return (
        "Esto parece el arranque de un proyecto/app completo. Todavía no hay "
        "artefactos SDD en este proyecto; en vez de crear archivos a ciegas conviene "
        "arrancar un flujo SDD con `sdd-init` para acotar el alcance y planificar "
        "antes de escribir código. "
        "Si preferís que lo haga directo igual, decímelo en el próximo mensaje "
        "y sigo sin SDD."
    )
```

- `has_sdd=True` branch → offers to CONTINUE the in-progress SDD workflow (spec
  "Project already has SDD artifacts — suggestion offers to continue").
- `has_sdd=False` branch → offers to BOOTSTRAP via `sdd-init` (spec "Project has no SDD
  artifacts — suggestion offers to bootstrap").
- Both branches restate that the suggestion is optional and the next turn proceeds
  normally, satisfying "does NOT force SDD" and the control-stays-with-user intent.

## 7. Independence from `agent-scaffolding-clarification` (RESOLVED)

- The `SCAFFOLDING_KEYWORDS` prompt addendum (`core.py:361-373`) and the destructive gate
  (`core.py:476-484`) are NOT read, moved, or modified. `NEW_PRODUCT_KEYWORDS`,
  `_is_new_product_request`, `_build_new_product_suggestion`, and
  `_should_suggest_sdd_flow` are all new symbols with no shared state.
- The addendum lives in `_build_messages` and still fires on every turn (including turn
  2+) whose input matches `SCAFFOLDING_KEYWORDS`; the gate still fires per destructive
  tool call. Neither depends on whether the new short-circuit fired. On the suggestion
  turn the loop never runs, so the gate simply has no tool call to evaluate — that is the
  designed behavior, not a change to the gate (spec "Independence" requirement).

## 8. Assumptions validated against real code

- `chat()` has `user_input: str`, resolved `session_id`, resolved `profile`, and
  `self.memory` before `core.py:250`. CONFIRMED.
- `_run_delegation` calls `_reasoning_loop` directly with `depth=1` and never routes
  through `chat()`, so worker turns cannot reach the short-circuit. CONFIRMED
  (`core.py:572`).
- Worker sessions never get a checkpoint written (`_run_delegation` has no
  `write_checkpoint`), so the checkpoint-absence signal is a supervisor-session concept.
  CONFIRMED.
- `chat()` steps 6/6b write the checkpoint from `outcome` for any non-disabled scope,
  regardless of whether the loop ran — so set-outcome-and-skip persists the checkpoint
  and prevents re-firing. CONFIRMED (`core.py:262-286`).
- `read_checkpoint(project, session_id) -> Optional[dict]` returns `None` when absent.
  CONFIRMED (`repository.py:391-402`).
- `detect_sdd_artifacts()` takes an optional `project_dir` defaulting to `Path.cwd()` and
  returns `SDDStatus` with a `has_sdd: bool`. CONFIRMED (`detector.py:29`).

## 9. Test Strategy (strict TDD, pytest) (RESOLVED)

Tests FIRST. Most coverage is pure-unit.

### Tier A — pure unit: `_is_new_product_request` (table-driven)

- `"necesitamos ya poder tener el astro hecho"` → True.
- `"armar toda la app"`, `"build me a new app"`, `"todo el proyecto desde cero"`,
  `"set up the entire project"` → True (case-insensitive variants included).
- `"creá un componente nuevo"` → False (SCAFFOLDING match, NOT new-product).
- `"leé el archivo config.py"` → False.

### Tier A — pure unit: `_build_new_product_suggestion`

- `has_sdd=True` → text mentions continuing existing SDD workflow, no `sdd-init`.
- `has_sdd=False` → text mentions `sdd-init` bootstrap.
- Neither branch contains delegation/worker vocabulary (assert absence of
  `delegate` / `worker`).

### Tier B — `_should_suggest_sdd_flow` (fake/spy memory)

- disabled scope + exact keyword + no checkpoint → False (suppressed); assert
  `read_checkpoint` NOT called.
- enabled + keyword + `read_checkpoint → None` → True.
- enabled + keyword + `read_checkpoint → {...}` → False (later turn).
- enabled + non-keyword → False; assert `read_checkpoint` not reached.

### Tier C — `chat()` wiring (fake QwenClient, spy loop/executor)

- first-turn new-product ask → `_reasoning_loop` NOT awaited, `self.skills.execute`
  never called; returned response is the suggestion; a checkpoint IS written (spy
  `write_checkpoint`).
- second turn same phrasing (checkpoint now present) → `_reasoning_loop` IS awaited
  (no re-suggestion) — success criterion #2.
- disabled memory + new-product ask → `_reasoning_loop` IS awaited (suggestion
  suppressed), no checkpoint written.
- delegation path (`_run_delegation` → worker `_reasoning_loop` depth=1) never emits the
  suggestion even when the worker `task` string matches `NEW_PRODUCT_KEYWORDS`.

Use a fake `QwenClient` returning scripted responses, the same approach the
session-persistence and destructive-gate suites already use.

## 10. Architecture Decisions (ADR-style)

### ADR-1: Short-circuit lives in `chat()` before `_reasoning_loop`, set-outcome-and-skip
- **Decision:** compute the suggestion in `chat()` at `core.py:250`, set `outcome`, skip
  the loop, and let existing steps 6/6b persist the checkpoint.
- **Rationale:** `user_input`/`profile`/`session_id`/`self.memory` are all local there;
  structurally excludes workers; keeps the checkpoint write so the suggestion cannot
  repeat on turn 2; emits no new status events.
- **Rejected:** first-iteration entry inside `_reasoning_loop` — needs `user_input`
  re-extraction, an explicit `depth == 0` guard, and re-derivation of the worker
  checkpoint story; early-`return` from `chat()` before step 6b — leaves no checkpoint
  and re-fires forever.

### ADR-2: Worker exclusion is structural, not a `depth` check
- **Decision:** anchor the trigger to `chat()`; reference no `depth` parameter.
- **Rationale:** `_run_delegation` calls `_reasoning_loop` directly at `depth=1`, so
  workers never reach `chat()`; this keeps the `multi-agent-orchestration` depth
  parameter and `delegate`-schema gating completely undisturbed.
- **Rejected:** `depth == 0` guard inside the loop — more code, more coupling, same
  effect.

### ADR-3: `NEW_PRODUCT_KEYWORDS` = long bilingual phrases, separate constant
- **Decision:** multi-word whole-product phrases, independent of
  `SCAFFOLDING_KEYWORDS`'s bare verbs (a few phrases do contain a `SCAFFOLDING_KEYWORDS`
  token as a substring — see "Correction" above; this is harmless since the two
  constants feed separate, non-competing mechanisms); substring `.lower()` match.
- **Rationale:** phrase-level matching is what keeps narrow scaffolding asks
  (`"creá un componente nuevo"`) from firing the request-level path; substring is safe
  on short NL input.
- **Rejected:** merging with or reusing `SCAFFOLDING_KEYWORDS` tokens — would make the
  narrow addendum and the broad short-circuit contaminate each other (proposal forbids).

### ADR-4: Three symbols — two pure helpers + one `self`-bound eligibility method
- **Decision:** `_is_new_product_request` and `_build_new_product_suggestion` are pure
  module functions; `_should_suggest_sdd_flow` is a method because it reads
  `self.memory`.
- **Rationale:** mirrors the archived change's `_is_under_specified` /
  `_build_clarifying_question` split; maximizes table-testable pure surface, isolates the
  single DB read.

## 11. Assumptions & Risks for downstream phases

- **Risk (false positive):** a coarse phrase false-positives on a legitimate quick
  first-turn ask. Mitigation: first-turn-only gate limits exposure to one message per
  session; the very next turn proceeds normally; phrases are deliberately multi-word.
- **Risk (checkpoint write-order dependency):** the "don't repeat on turn 2" guarantee
  depends on `chat()` step 6b writing the checkpoint unconditionally for non-disabled
  scope. If a future change makes checkpoint writes conditional on tool activity, the
  suggestion could re-fire. Tasks/apply MUST keep the checkpoint write on the suggestion
  turn and cover it with the Tier-C "second turn proceeds" test.
- **Assumption:** `stream_chat` (if present) routes through the same `chat()` entry;
  verify in apply that the short-circuit is reached there too, or scope it to `chat()`
  explicitly.
- **Deferred:** `config.py` wiring of `NEW_PRODUCT_KEYWORDS`, any LLM-based scope
  classification, and any per-project keyword tuning — all out of scope this cycle.
