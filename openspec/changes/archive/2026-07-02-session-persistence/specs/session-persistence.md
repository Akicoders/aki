# Delta for Session Persistence & Context Rehydration

## ADDED Requirements

### Requirement: Durable Last-Session Pointer

The system MUST persist the most recently used `session_id` per project as a reserved-key `MemoryFact` (e.g. key `session:last`, scope `project:{name}`) with upsert semantics, updated whenever a session is created or resumed.

#### Scenario: First-ever invocation with no prior session

- GIVEN no `session:last` fact exists for the current project
- WHEN the operator runs `aki chat` or `aki interactive` without `--session`
- THEN a new `session_id` is minted, used for that invocation, and persisted as `session:last`

#### Scenario: Last-used session pointer is updated on new session

- GIVEN `session:last` currently points to `sess_aaaaaaaa`
- WHEN the operator runs `aki chat --new-session` (or otherwise starts a fresh session)
- THEN `session:last` is updated (upserted) to the newly minted `session_id`

### Requirement: Auto-Resume Session on `aki chat`

The system MUST resolve `session_id` for `aki chat` by reading the durable `session:last` fact when `--session` is not passed on the command line, instead of minting a random id per invocation.

#### Scenario: Second `aki chat` call resumes the same session

- GIVEN a prior `aki chat` invocation (no `--session`) resulted in `session:last` = `sess_aaaaaaaa`
- WHEN the operator runs `aki chat` again without `--session`
- THEN the invocation uses `session_id = sess_aaaaaaaa`, not a newly generated id

#### Scenario: Explicit `--session` overrides auto-resume

- GIVEN `session:last` = `sess_aaaaaaaa`
- WHEN the operator runs `aki chat --session sess_bbbbbbbb`
- THEN the invocation uses `session_id = sess_bbbbbbbb`, and `session:last` is updated to `sess_bbbbbbbb`

### Requirement: Auto-Resume Session on `aki interactive`

The system MUST resolve `session_id` for `aki interactive` by reading the durable `session:last` fact at process start when `--session` is not passed, instead of always minting a fresh id.

#### Scenario: Restarting `aki interactive` resumes the prior session

- GIVEN a prior `aki interactive` process exited with `session:last` = `sess_aaaaaaaa`
- WHEN the operator restarts `aki interactive` without `--session`
- THEN the new process resumes `session_id = sess_aaaaaaaa`

### Requirement: Explicit New-Session Escape Hatch

The system MUST provide a `--new-session` flag on both `aki chat` and `aki interactive` that mints and persists a fresh `session_id`, bypassing auto-resume, even when a `session:last` fact exists.

#### Scenario: `--new-session` bypasses auto-resume

- GIVEN `session:last` = `sess_aaaaaaaa`
- WHEN the operator runs `aki chat --new-session`
- THEN a newly minted `session_id` (not `sess_aaaaaaaa`) is used, and `session:last` is updated to it

#### Scenario: `--new-session` and `--session` are mutually exclusive

- WHEN the operator passes both `--new-session` and `--session <id>` to `aki chat` or `aki interactive`
- THEN the system MUST reject the invocation with a clear error, rather than silently picking one

### Requirement: Structured Checkpoint Write

The system MUST persist a structured per-session checkpoint (fields: `goal`, `open_items`, `last_tool_result_summary`) as a reserved-key `MemoryFact` (e.g. key `session:{id}:checkpoint`, scope `project:{name}`) with upsert semantics, written after each turn completes or when the reasoning loop is exhausted by hitting `max_iterations`.

#### Scenario: Checkpoint is written after a normal turn

- GIVEN a session with no existing checkpoint
- WHEN `AgentOS.chat()` completes a turn for that session
- THEN a `session:{id}:checkpoint` fact is created/updated reflecting the current `goal`, `open_items`, and `last_tool_result_summary`

#### Scenario: Checkpoint is written on iteration-limit exhaustion

- GIVEN a turn's reasoning loop reaches `max_iterations` without a final answer
- WHEN the loop exits due to exhaustion
- THEN the checkpoint fact is still written/updated with the best-known `goal`, `open_items`, and `last_tool_result_summary` at that point, so the next turn does not restart from nothing

#### Scenario: Checkpoint upserts rather than accumulates

- GIVEN a session already has a checkpoint fact from a prior turn
- WHEN a new turn completes and writes an updated checkpoint
- THEN the existing `session:{id}:checkpoint` fact is overwritten in place (upsert), not duplicated as a new fact row

### Requirement: Guaranteed Checkpoint Rehydration

The system MUST inject the current session's checkpoint (if one exists) into the model's context on every subsequent turn as a dedicated system message, independent of `assemble_context()` relevance-ranking, and placed in a reserved slot that budget-fit truncation cannot drop.

#### Scenario: Checkpoint appears regardless of query relevance

- GIVEN a session has a checkpoint fact with `open_items` unrelated (textually) to the next user message
- WHEN `_build_messages` assembles context for the next turn
- THEN the checkpoint content is present in the assembled messages even though it would not have been retrieved by keyword/vector relevance matching

#### Scenario: Checkpoint survives budget-fit truncation

- GIVEN the assembled context (facts + events from `assemble_context()`) is large enough that budget-fit truncation would normally drop lower-priority items
- WHEN `_build_messages` composes the final message list
- THEN the checkpoint's reserved slot content is still present in full (up to its own bounded cap), unaffected by truncation applied to the relevance-retrieved facts/events

#### Scenario: No checkpoint yet for a brand-new session

- GIVEN a session has no `session:{id}:checkpoint` fact (e.g. its first turn)
- WHEN `_build_messages` assembles context
- THEN no checkpoint system message is injected (or an empty/no-op one), and no error occurs

#### Scenario: Checkpoint content stays within its bounded slice

- GIVEN a checkpoint fact whose serialized content exceeds the reserved slot's hardcoded size cap
- WHEN `_build_messages` injects the checkpoint
- THEN the injected content is truncated to fit the reserved slot's cap deterministically, rather than silently expanding the overall context budget
