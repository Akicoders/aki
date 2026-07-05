# Delta for SDD Scaffolding Flow Suggestion

## ADDED Requirements

### Requirement: New-Product Keyword Detection

The system MUST define a new bilingual `NEW_PRODUCT_KEYWORDS` constant in `src/agentos/agent/core.py`, distinct from and independent of the existing `SCAFFOLDING_KEYWORDS`. `NEW_PRODUCT_KEYWORDS` targets coarse, whole-project/whole-product framing — a request to stand up an entire application or system from nothing — rather than `SCAFFOLDING_KEYWORDS`'s narrower per-file/per-component scaffolding intent. The two constants MUST NOT be merged, and matching one MUST NOT imply a match on the other.

Illustrative (non-exhaustive, spec-level; design MAY refine) bilingual list:

- English: `"build me a new app"`, `"build a new project"`, `"start a new project"`, `"create a whole new product"`, `"we need the whole app built"`, `"set up the entire project"`, `"build the whole thing from scratch"`
- Spanish: `"necesitamos que esté hecho el proyecto"`, `"armar toda la app"`, `"arrancar desde cero"`, `"necesitamos ya poder tener el [x] hecho"`, `"poné en marcha el proyecto"`, `"hacer todo el proyecto nuevo"`

Matching MUST be case-insensitive substring/phrase matching against `user_input`, mirroring the existing keyword-check structure used for `SCAFFOLDING_KEYWORDS` (`core.py:193-200`).

#### Scenario: New-product phrase is recognized as distinct from scaffolding intent

- GIVEN a user input containing "necesitamos ya poder tener el astro hecho"
- WHEN the input is checked against `NEW_PRODUCT_KEYWORDS`
- THEN it matches `NEW_PRODUCT_KEYWORDS`
- AND it does NOT need to match `SCAFFOLDING_KEYWORDS` for the suggestion flow in this spec to apply (the two checks are independent)

#### Scenario: Narrow scaffolding phrase does not trigger the new-product path

- GIVEN a user input containing "creá un componente nuevo" (a `SCAFFOLDING_KEYWORDS` match from the archived `agent-scaffolding-clarification` change)
- WHEN the input is checked against `NEW_PRODUCT_KEYWORDS`
- THEN it does NOT match `NEW_PRODUCT_KEYWORDS`, and the SDD-suggestion short-circuit in this spec does not fire on this basis

### Requirement: First-Turn Detection via Checkpoint Absence

The system MUST treat the absence of a session checkpoint as the first-turn signal: `read_checkpoint(project, session_id) is None` means this is turn 1 of the session. Checkpoints are written unconditionally at the end of every turn (`write_checkpoint`, `core.py:278`) and are already read back during message assembly (`_build_messages`, `core.py:322`), so no new state, column, or flag is required.

#### Scenario: No checkpoint exists — this is the first turn

- GIVEN a session with no prior checkpoint recorded for `(project, session_id)`
- WHEN the agent evaluates whether the SDD suggestion is eligible to fire
- THEN `read_checkpoint(project, session_id)` returns `None`
- AND the turn is treated as the first turn, making the suggestion eligible (subject to the other requirements in this spec)

#### Scenario: A checkpoint already exists — this is not the first turn

- GIVEN a session where a checkpoint was written at the end of a prior turn
- AND the current user input is an exact `NEW_PRODUCT_KEYWORDS` match
- WHEN the agent evaluates whether the SDD suggestion is eligible to fire
- THEN `read_checkpoint(project, session_id)` returns a non-`None` value
- AND the SDD suggestion does NOT fire, and the turn proceeds through the reasoning loop normally

### Requirement: Suggestion Suppressed When Memory Scope Is Disabled

When `profile.memory.scope == "disabled"`, no checkpoint is ever written for the session, so checkpoint-absence cannot reliably distinguish "first turn" from "memory is off." In this configuration the system MUST suppress the SDD suggestion entirely — it MUST NOT fire, regardless of keyword match or apparent turn number.

#### Scenario: Memory scope disabled suppresses the suggestion even on an exact keyword match, first apparent turn

- GIVEN `profile.memory.scope == "disabled"` for the current session
- AND the user input is an exact `NEW_PRODUCT_KEYWORDS` match
- AND no checkpoint exists (as would be expected for every turn under disabled memory, not only the first)
- WHEN the agent evaluates whether the SDD suggestion is eligible to fire
- THEN the suggestion does NOT fire, and the turn proceeds through the reasoning loop normally with tool calls permitted

### Requirement: Zero-Tool-Call Short-Circuit on Trigger

When `NEW_PRODUCT_KEYWORDS` matches AND this is confirmed the first turn (checkpoint absent) AND `profile.memory.scope != "disabled"`, the system MUST short-circuit before any tool calls are made for that turn. No tool is executed. The system MUST return a plain-text SDD-suggestion response, reusing the existing no-tool-call `ReasoningOutcome` return shape already used by the destructive-tool gate (`core.py:480-484`): `ReasoningOutcome(response=<suggestion text>, exhausted=False)`. `exhausted` MUST be `False`, since the turn ends by design and not by iteration exhaustion.

#### Scenario: Trigger conditions met — suggestion returned with zero tool calls

- GIVEN a session with no existing checkpoint, `profile.memory.scope != "disabled"`, and a user input matching `NEW_PRODUCT_KEYWORDS`
- WHEN the agent processes this turn
- THEN no tool is executed (`self.skills.execute(...)` is never called for this turn)
- AND the returned `ReasoningOutcome.response` is a plain-text SDD-suggestion message
- AND `ReasoningOutcome.exhausted` is `False`

### Requirement: SDD-Status Enrichment via `detect_sdd_artifacts()`

When the short-circuit in this spec fires, the system MUST call `detect_sdd_artifacts()` (`src/agentos/sdd/detector.py`) against the target project and fold the result into the suggestion text, producing one of two distinct message branches depending on whether the project already has SDD artifacts.

#### Scenario: Project already has SDD artifacts — suggestion offers to continue

- GIVEN the short-circuit conditions are met
- AND `detect_sdd_artifacts()` reports that SDD artifacts already exist for the target project (e.g. an active change under `openspec/changes/` or an equivalent engram-backed change)
- WHEN the suggestion message is composed
- THEN the message mentions continuing with the existing SDD workflow (e.g. resuming or continuing the in-progress change) rather than starting from zero

#### Scenario: Project has no SDD artifacts — suggestion offers to bootstrap

- GIVEN the short-circuit conditions are met
- AND `detect_sdd_artifacts()` reports no existing SDD artifacts for the target project
- WHEN the suggestion message is composed
- THEN the message mentions bootstrapping SDD via `sdd-init` as the way to start

### Requirement: Independence from Existing Scaffolding-Clarification Mechanisms

The narrower `SCAFFOLDING_KEYWORDS` prompt addendum (`core.py:361-373`) and the per-call destructive-tool gate (`core.py:476-484`), both introduced by the archived `agent-scaffolding-clarification` change, MUST remain unmodified by this change and MUST continue to fire independently of the `NEW_PRODUCT_KEYWORDS` short-circuit — on later turns of the same session, and on any destructive tool call with under-specified arguments regardless of whether `NEW_PRODUCT_KEYWORDS` ever matched.

#### Scenario: Scaffolding addendum and destructive gate still fire independently on a later turn

- GIVEN a session whose first turn triggered the `NEW_PRODUCT_KEYWORDS` short-circuit in this spec (so no tool calls occurred on turn 1)
- AND the user's next turn contains a `SCAFFOLDING_KEYWORDS` match (e.g. "creá un componente nuevo") and/or the model emits a destructive tool call with an empty `path`
- WHEN the agent processes this second turn
- THEN the scaffolding-intent prompt addendum is appended as before, and/or the destructive-tool gate fires as before
- AND neither mechanism's behavior differs from its behavior prior to this change

### Requirement: No Worker/Delegation Vocabulary

The SDD-suggestion feature added by this change MUST NOT introduce or rely on worker/delegation vocabulary (e.g. `delegate`, `worker`, sub-agent dispatch). This remains a single-turn, supervisor-only mechanism; multi-agent/delegation semantics are owned exclusively by the archived `multi-agent-orchestration` change and are out of scope here.

#### Scenario: Suggestion text and implementation avoid delegation terminology

- GIVEN the SDD-suggestion short-circuit fires
- WHEN the suggestion message and its implementation are reviewed
- THEN no delegation/worker vocabulary is used, and no nested reasoning loop or sub-agent dispatch is introduced
