# Delta for Session Listing & Contextual Interactive Help

## ADDED Requirements

### Requirement: Session Listing Query

The system MUST expose `MemoryRepository.list_sessions(project, limit=20)` that derives a project's session list from existing checkpoint facts, without any schema change or migration.

The query MUST select `MemoryFactModel` rows where `scope == "project:{project}"` and `key LIKE "session:%:checkpoint"`, ordered by `updated_at desc`, capped at `limit`. Each row's JSON `value` MUST be parsed to extract `session_id`, `goal`, `iterations_exhausted`, and `updated_at` (falling back to the fact row's own `updated_at` column if the payload lacks it). The method MUST return a list of plain structures (e.g. dicts or a small dataclass) — not raw ORM models.

#### Scenario: Sessions are listed newest-first

- GIVEN a project has three sessions with checkpoint facts written at different times
- WHEN `list_sessions(project)` is called
- THEN it returns all three, ordered by `updated_at` descending

#### Scenario: A session with no checkpoint is absent from the list

- GIVEN a project has a `session:last` pointer to a session that never completed a turn (no `session:{id}:checkpoint` fact exists)
- WHEN `list_sessions(project)` is called
- THEN that session does not appear in the results
- AND this is expected, correct behavior per the checkpoint-write contract — not a defect to fix in this change

#### Scenario: A corrupt checkpoint row does not crash the list

- GIVEN one of a project's `session:%:checkpoint` facts has a `value` that fails to JSON-decode (e.g. truncated or hand-edited)
- WHEN `list_sessions(project)` is called
- THEN the malformed row is skipped (logged, not raised) and the method still returns the remaining valid sessions
- AND no exception propagates to the caller

#### Scenario: Empty project has no sessions

- GIVEN a project has zero `session:%:checkpoint` facts
- WHEN `list_sessions(project)` is called
- THEN it returns an empty list, not an error

### Requirement: Interactive `/sessions` Command

The system MUST provide a `/sessions` command inside `aki chat` / `aki interactive` (via `_handle_command`) that renders the current project's sessions as a Rich table, following the existing `/facts` and `/skills` rendering pattern. This command MUST NOT be exposed as a top-level Typer CLI command (e.g. no `aki sessions`) — session listing is interactive-mode-only per this change's scope.

The table MUST include columns for `session_id`, a goal/label preview (falling back to session_id + timestamp when `goal` is blank, matching the pattern already used for fact value truncation), and `updated_at`.

#### Scenario: `/sessions` lists sessions for the current project

- GIVEN the current project has two sessions with checkpoints
- WHEN the user types `/sessions` in interactive mode
- THEN a table is printed with one row per session, newest first, showing session_id, goal preview, and updated_at

#### Scenario: `/sessions` empty state

- GIVEN the current project has no sessions with checkpoints
- WHEN the user types `/sessions`
- THEN a dim "no sessions" message is printed (matching the style of `_show_facts`'s empty state) instead of an empty or malformed table

#### Scenario: `/sessions` is wired into command dispatch

- GIVEN the interactive command loop already dispatches `/facts`, `/skills`, `/sdd`, `/clear` via `_handle_command`
- WHEN `/sessions` is entered
- THEN `_handle_command` routes it to the new session-listing handler via an additive `elif` branch, without altering existing branches

### Requirement: Contextual Interactive Help

`_show_help` MUST accept `project` and `session_id` parameters (threaded from the existing call site at the interactive loop, `main.py:759`) and render session-aware state in addition to the static command list.

The contextual section MUST report: whether the current `session_id` was resumed from a prior `session:last` pointer or is newly minted, and the last known `goal` from `read_checkpoint(project, session_id)` when a checkpoint exists. The command list already shown today (`/help`, `/memory`, `/facts`, `/skills`, `/sdd`, `/clear`, `exit`/`quit`) MUST remain, and `/sessions` MUST be added to it.

#### Scenario: Help reflects a resumed session with a prior goal

- GIVEN `session_id` was resolved via auto-resume (`session:last`) and a checkpoint exists with `goal = "refactor auth"`
- WHEN the user runs `/help`
- THEN the help panel states the session was resumed and shows "refactor auth" as the last goal, alongside the full command list

#### Scenario: Help does not break for a brand-new session with no checkpoint

- GIVEN `session_id` is freshly minted and no `session:{id}:checkpoint` fact exists yet
- WHEN the user runs `/help`
- THEN `_show_help` calls `read_checkpoint` (or equivalent), receives `None`, and renders a "new session, no history yet" state instead of raising or printing a stale/garbled goal
- AND the full command list is still shown

#### Scenario: `_show_help` signature change does not break its single call site

- GIVEN `_show_help`'s only caller is the interactive loop at `main.py:759`, which already has `project` and `session_id` in scope
- WHEN the signature changes to `_show_help(project, session_id)`
- THEN the call site is updated to pass both, and no other caller exists to break
