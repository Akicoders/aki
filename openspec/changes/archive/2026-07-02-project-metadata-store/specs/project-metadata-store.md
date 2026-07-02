# Delta for Project Breadcrumb (last-project bootstrap pointer)

## ADDED Requirements

### Requirement: Breadcrumb Write on Positive Project Resolution

The system MUST write (create or overwrite) a single-purpose breadcrumb file at `.aki/last-project` containing `{"root_path": "...", "updated_at": "..."}` whenever a project is positively resolved via `resolve_project_ref` (`src/agentos/cli/cockpit.py`) or `detect_project` (`src/agentos/mcp/project.py`). `root_path` MUST be the canonical (resolved) project root; `updated_at` MUST be the resolution timestamp.

#### Scenario: CLI resolves a project and updates the breadcrumb

- GIVEN no breadcrumb file exists yet
- WHEN `resolve_project_ref` positively resolves a project at canonical root `/repo`
- THEN `.aki/last-project` is created with `root_path: /repo` and a fresh `updated_at`

#### Scenario: MCP detects a project and updates the breadcrumb

- GIVEN a breadcrumb file already points to `/old-repo`
- WHEN `detect_project` positively resolves a project at canonical root `/new-repo`
- THEN `.aki/last-project` is overwritten (upserted, not appended) with `root_path: /new-repo` and a fresh `updated_at`

#### Scenario: No breadcrumb write on failed or absent resolution

- GIVEN cwd has no resolvable project
- WHEN `resolve_project_ref` or `detect_project` fails to positively resolve a project
- THEN the breadcrumb file is left unchanged (not written, not cleared)

### Requirement: Breadcrumb as Last-Resort `.env` Search Candidate

The system MUST treat the breadcrumb's `root_path` as an additional, lowest-priority candidate search root in `_iter_env_search_roots`/`load_runtime_env` (`src/agentos/core/config.py`), yielded only after cwd-ancestor walk and git-root anchoring have been exhausted and none produced a usable `.env`.

#### Scenario: Breadcrumb resolves `.env` when cwd is unrelated to any project

- GIVEN cwd has no relation to any git repo or existing `.env` via ancestor walk
- AND a breadcrumb file exists pointing to canonical root `/repo` which contains a valid `.env`
- WHEN `load_runtime_env` searches for `.env`
- THEN `/repo/.env` is loaded via the breadcrumb-derived candidate root

#### Scenario: Breadcrumb is not consulted when an earlier candidate already succeeds

- GIVEN cwd is a subdirectory of a git repo whose root contains a valid `.env`
- AND a breadcrumb file exists pointing to a different, unrelated root
- WHEN `load_runtime_env` searches for `.env`
- THEN the git-root `.env` is loaded and the breadcrumb candidate is never consulted

#### Scenario: Breadcrumb root path no longer contains an `.env`

- GIVEN no earlier candidate root produces a usable `.env`
- AND the breadcrumb points to a root path that exists but contains no `.env`
- WHEN `load_runtime_env` searches for `.env`
- THEN no `.env` is loaded (behaves as if the breadcrumb candidate were absent), with no error raised

### Requirement: Fail-Soft Breadcrumb Handling

The system MUST treat a missing, corrupt, unreadable, or stale (pointing to a nonexistent path) breadcrumb file as simply "no candidate available," continuing with existing cwd-only / git-root behavior. Breadcrumb read or write failures MUST NOT raise an exception that interrupts startup, project resolution, or `.env` loading.

#### Scenario: Missing breadcrumb file

- GIVEN `.aki/last-project` does not exist
- WHEN `load_runtime_env` reaches the breadcrumb fallback step
- THEN it is skipped silently and normal cwd-only/git-root behavior continues

#### Scenario: Corrupt breadcrumb JSON

- GIVEN `.aki/last-project` exists but contains invalid JSON
- WHEN `load_runtime_env` reaches the breadcrumb fallback step
- THEN the corrupt file is ignored, no exception propagates, and normal cwd-only/git-root behavior continues

#### Scenario: Breadcrumb points to a deleted or moved project

- GIVEN `.aki/last-project` contains a `root_path` that no longer exists on disk
- WHEN `load_runtime_env` reaches the breadcrumb fallback step
- THEN the stale path is skipped as a candidate, no exception propagates, and normal cwd-only/git-root behavior continues

#### Scenario: Breadcrumb write failure does not block project resolution

- GIVEN the `.aki` directory is not writable (e.g. permissions error)
- WHEN `resolve_project_ref` or `detect_project` positively resolves a project and attempts to write the breadcrumb
- THEN the write failure is caught and ignored, and project resolution still returns its normal successful result

## Non-Goals

These are explicit exclusions, not deferred work:

- No general-purpose project-metadata store. The breadcrumb file holds exactly one pointer (`root_path`, `updated_at`) and nothing else.
- No reuse of, or coupling to, the session/checkpoint `MemoryFact` format defined in `openspec/specs/session-persistence/spec.md`. The breadcrumb is a plain JSON file, not a `MemoryFact`.
- No structural change to `src/agentos/core/config.py` beyond the additive last-resort candidate branch described above. `MemoryConfig.db_path` and all other config defaults remain untouched.
- No new `EventType` and no database schema change. The breadcrumb never touches `agentos.memory.database.Database` or the cockpit `ProjectRefModel` registry.
