# Tasks: Git Repo Bootstrap

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 180-280 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Add git bootstrap capability, prompt guidance, and tests | PR 1 | Self-contained single slice |

## Phase 1: RED - Git Skill Tests

- [x] 1.1 Create `tests/unit/test_git_ops.py` covering existing repo status and missing-repo bootstrap flow.
- [x] 1.2 Create `tests/unit/test_build_messages_git_intent.py` covering Spanish repo/version-control intent guidance.
- [x] 1.3 Create `tests/unit/test_agent_git_bootstrap_flow.py` covering `git_ops_status` then `git_ops_init` without `filesystem.write`.

## Phase 2: GREEN - Product Code

- [x] 2.1 Update `src/agentos/skills/git_ops.py` with safe repo lookup, honest status reporting, and `init(path, initial_branch="main")`.
- [x] 2.2 Update `src/agentos/agent/core.py` with version-control keywords and a git-guidance system message.

## Phase 3: REFACTOR - Cleanups

- [x] 3.1 Refine git result payloads/messages so repos with no commits still report cleanly.
- [x] 3.2 Keep destructive/scaffolding guardrails intact and ensure `git_ops.init` is tagged destructive.

## Phase 4: Verification Prep

- [x] 4.1 Run targeted pytest files for the new git/bootstrap coverage.
- [x] 4.2 Run repo-level verify commands required by `openspec/config.yaml`.
