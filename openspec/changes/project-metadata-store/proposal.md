# Proposal: Project Metadata Store (last-project breadcrumb)

## Intent

Close the remaining gap in QA issue #4: `.env` loading is still cwd-relative for the case where Aki is launched from a directory with **zero** relation to any project. Commit `7f8044b` anchored `load_runtime_env` on git-root, fixing the "launched from a repo subdirectory" case, but there is no ancestor path to walk when cwd is unrelated to the repo. We add a persisted "last known project" breadcrumb so resolution can bootstrap in that case.

## Scope

### In Scope
- New single-purpose breadcrumb module: read/write one small JSON file `{"root_path": "...", "updated_at": "..."}` (nothing else).
- **Additive** last-resort read in `src/agentos/core/config.py` `_iter_env_search_roots`: yield the breadcrumb `root_path` as a candidate before falling back to plain cwd/no-op.
- Write the breadcrumb wherever a project is **already** positively resolved today: `resolve_project_ref` (cli/cockpit.py) and `detect_project` (mcp/project.py). Design phase finalizes exact wiring.

### Out of Scope
- **Option 1 — anchoring `MemoryConfig.db_path` to a fixed global location** (e.g. `~/.aki/agentos.db`). Superior long-term fix, but structurally modifies off-limits `config.py` defaults and carries DB-location migration implications. Tracked as a separate follow-up change requiring explicit sign-off.
- No new EventType, no DB schema change, no general `.aki/` metadata store, no session/checkpoint format.

## Capabilities

### New Capabilities
- `project-breadcrumb`: persist and read a single "last resolved project root" pointer to bootstrap `.env` discovery from an unrelated cwd.

### Modified Capabilities
- None (config.py touched additively only; no existing spec-level requirement changes).

## Approach

Exploration Option 2. A minimal breadcrumb file justified because the DB path itself is cwd-relative and unresolved *before* project identity is known — a genuine bootstrap chicken-and-egg the DB cannot solve for itself (distinct from the earlier-rejected session file store, where the DB was already reachable). The breadcrumb is a pointer, not a project-metadata model, so it does not compete with the DB-backed cockpit registry.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/core/project_breadcrumb.py` (name TBD) | New | Read/write single-JSON breadcrumb helpers |
| `src/agentos/core/config.py` `_iter_env_search_roots` | Modified (additive only) | New last-resort candidate branch reading breadcrumb — NO default/db_path changes; narrower than the already-authorized git-root-anchor edit |
| `src/agentos/cli/cockpit.py` `resolve_project_ref` | Modified | Write breadcrumb on positive resolve |
| `src/agentos/mcp/project.py` `detect_project` | Modified | Write breadcrumb on positive resolve |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Stale breadcrumb points at a moved/deleted project | Med | Treat as candidate only; skip if path missing, then fall back to existing behavior |
| Scope creep into a general `.aki/` store | Low | Single field enforced; explicit non-goal |
| Corrupt/unreadable breadcrumb JSON | Low | Fail-soft: ignore and fall back, never raise |

## Rollback Plan

Revert the new module and the additive branches. `config.py` change is purely additive (new fallback candidate), so removing it restores exact prior behavior with no migration.

## Dependencies

- None external. Fully greenfield global-storage location (no `~/.aki` precedent today).

## Delivery

**SMALL — single PR, not stacked.** One small new module plus three additive edits; no >400-line risk expected. No delivery-mechanics decisions needed at proposal time.

## Success Criteria

- [ ] Launching Aki from a cwd unrelated to any repo resolves `.env` via the breadcrumb `root_path`.
- [ ] Breadcrumb is written on positive project resolution in cli and mcp paths.
- [ ] `config.py` change is additive only — no default value or `db_path` changes.
- [ ] Missing/corrupt breadcrumb fails soft to prior behavior.
