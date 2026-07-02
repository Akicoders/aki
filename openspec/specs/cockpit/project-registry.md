# Delta for Project Registry & `aki projects browse`

## ADDED Requirements

### Requirement: Persistent ProjectRef Registry

The system MUST persist `ProjectRef` records in the same SQLite database used by `agentos.memory.database.Database` (SQLAlchemy `Base`/`DeclarativeBase` convention, new `__tablename__ = "project_refs"` table), keyed on canonical `root_path`, not directory name.

Fields: `key`, `root_path` (canonical, resolved), `source` (`detected|remembered|audited|manual`), `last_opened_at`, `last_audit_at`, `last_memory_activity_at`.

#### Scenario: Opening a project registers or updates its ProjectRef

- GIVEN a resolvable current project at canonical root path `/repo`
- WHEN the cockpit opens that project
- THEN a `ProjectRef` row for `/repo` is inserted if absent, or `last_opened_at` is updated if present

#### Scenario: Two different directory names resolving to the same root do not duplicate

- GIVEN a `ProjectRef` already exists for canonical root `/repo`
- WHEN the project is opened again via a symlinked or relative path that resolves to `/repo`
- THEN no duplicate `ProjectRef` row is created

#### Scenario: Audit run updates registry timestamps

- WHEN `aki audit <project>` completes for a known project
- THEN its `ProjectRef.last_audit_at` is updated to the audit's generated timestamp

### Requirement: `aki projects browse` Listing

The system MUST list all known `ProjectRef` rows with columns: key, root path, branch, git dirty summary, SDD completeness, last memory activity, last audit date.

#### Scenario: Listing known projects

- GIVEN two `ProjectRef` rows exist
- WHEN the operator runs `aki projects browse`
- THEN both projects render as rows with the required columns populated or marked `unknown`

#### Scenario: Onboarding empty state

- GIVEN no `ProjectRef` rows exist
- WHEN the operator runs `aki projects browse`
- THEN the system SHOULD show onboarding guidance explaining how a project becomes known, instead of an empty table

### Requirement: Search and Filter

The system MUST support filtering the browse list by a text query matching project key or root path substring.

#### Scenario: Filter narrows the list

- GIVEN three known projects, one containing "aki" in its key
- WHEN the operator filters by "aki"
- THEN only the matching project row(s) remain visible

#### Scenario: Filter with no matches

- WHEN the operator filters by a query matching no project
- THEN the system SHOULD show an explicit "no matches" message, not a silent empty panel

### Requirement: Select-to-Open

The system MUST let the operator select a listed project and open its cockpit overview.

#### Scenario: Selecting a project opens its cockpit

- GIVEN the browse list is showing selectable projects
- WHEN the operator selects one and confirms
- THEN the cockpit overview for that project's root path renders next
