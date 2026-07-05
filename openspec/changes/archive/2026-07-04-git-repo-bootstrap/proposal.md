# Proposal: Git Repo Bootstrap

## Intent

Eliminate the QA failure where Aki claimed it could not inspect repo state and then attempted filesystem writes into `.git/objects`. Version-control requests need a real git bootstrap path, not filesystem scaffolding.

## Scope

### In Scope
- Add a real `git_ops.init` capability for safe repository initialization.
- Improve repo detection/status handling so existing repos still use the normal git status flow.
- Inject version-control intent guidance so the agent prefers `git_ops.status` / `git_ops.init` over filesystem writes.
- Add unit tests for repo exists, repo missing/bootstrap, and agent behavior guidance.

### Out of Scope
- No changes to delegation, workers, or `multi-agent-orchestration`.
- No automatic commits, remotes, or branch protection setup.
- No weakening of destructive/scaffolding guardrails.

## Capabilities

### New Capabilities
- `git-repo-bootstrap`: inspect repository state honestly and initialize git safely when version control is requested in a non-repo folder.

### Modified Capabilities
- None.

## Approach

Extend `GitOpsSkill` with an initialization function backed by GitPython, return explicit non-repo signals from status lookup, and add a prompt addendum in `_build_messages` for version-control intents (for example `quiero versionamiento`, `poné git en el proyecto`, `revisar el estado del repo`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/skills/git_ops.py` | Modified | Add repo bootstrap/init support and clearer repo-state reporting. |
| `src/agentos/agent/core.py` | Modified | Inject version-control intent guidance without changing orchestration flow. |
| `tests/unit/test_git_ops.py` | New | Cover repo exists and repo missing/bootstrap paths. |
| `tests/unit/test_build_messages_git_intent.py` | New | Cover version-control prompt guidance. |
| `tests/unit/test_agent_git_bootstrap_flow.py` | New | Cover model-selected git tool path avoiding filesystem writes. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Git status on a repo with no commits can raise HEAD/branch errors | Med | Handle unborn HEAD explicitly in `git_ops.status`. |
| Prompt guidance could drift from actual skill names | Low | Keep tests asserting `git_ops.status` / `git_ops.init` guidance text. |

## Rollback Plan

Remove `git_ops.init`, remove the version-control prompt addendum, and delete the related tests. No persisted data migration is involved.

## Dependencies

- Existing `GitPython` dependency in `pyproject.toml`.
- Existing destructive-tool gate and scaffolding clarification behavior remain adjacent constraints.

## Success Criteria

- [ ] The product exposes a real git initialization capability.
- [ ] Repo-status checks still work for existing repos.
- [ ] Non-repo folders are reported honestly and can be initialized through git tooling, not filesystem writes.
- [ ] Version-control intent guidance points the agent at git tools.
- [ ] Tests cover repo exists, repo missing/bootstrap, and agent behavior choice.
