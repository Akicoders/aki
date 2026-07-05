# Archive Report: git-repo-bootstrap

## Summary

`git-repo-bootstrap` adds first-class git repository bootstrap support to Aki. The change introduces a real `git_ops.init` capability, teaches `_build_messages` to steer repo/version-control asks toward `git_ops.status` and `git_ops.init`, and keeps the destructive/scaffolding guardrails intact by avoiding filesystem fabrication of `.git` internals.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `git-repo-bootstrap` | Created | New source-of-truth spec copied to `openspec/specs/git-repo-bootstrap/spec.md`. |

## Verification Basis

- `uv run --extra dev --extra web pytest -v --cov=src/agentos --cov-report=xml`: 420 passed.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra dev mypy src/agentos`: warnings only due pre-existing repository baseline.

## Intentional Warnings

- Archive is performed with warnings because the repository still has a large pre-existing `mypy` baseline unrelated to this feature.

## Files in Archive

- `explore.md`
- `proposal.md`
- `specs/git-repo-bootstrap/spec.md`
- `design.md`
- `tasks.md`
- `verify-report.md`
- `archive-report.md`
