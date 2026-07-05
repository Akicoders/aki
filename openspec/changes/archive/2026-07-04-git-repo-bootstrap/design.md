# Design: Git Repo Bootstrap

## Technical Approach

Add one new git skill function plus one prompt-assembly branch. The runtime stays single-agent and tool-driven: the model chooses git tools, but `_build_messages` will now explicitly frame version-control asks around repo inspection and safe initialization.

## Architecture Decisions

### Decision: Bootstrap in `GitOpsSkill`

**Choice**: add `init(path, initial_branch="main")` to `GitOpsSkill`.
**Alternatives considered**: shelling out from the agent loop; filesystem writes into `.git`.
**Rationale**: keeps bootstrap in the existing git capability boundary and uses GitPython's real repo initialization.

### Decision: Prompt steering instead of loop interception

**Choice**: add a version-control intent addendum in `_build_messages`.
**Alternatives considered**: forcing tool rewrites in `_reasoning_loop`.
**Rationale**: much smaller blast radius, preserves current orchestration, and directly targets the QA failure mode.

## Data Flow

User asks for repo status/bootstrap
  -> `_build_messages` detects version-control intent
  -> system guidance tells model to call `git_ops.status`
  -> if repo exists: status flow continues
  -> if repo missing and intent is to enable git: model can call `git_ops.init`
  -> tool result returns as ordinary tool message

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/agentos/skills/git_ops.py` | Modify | Add repo init, improve repo lookup/status handling, mark init destructive. |
| `src/agentos/agent/core.py` | Modify | Add version-control keyword set and prompt addendum. |
| `tests/unit/test_git_ops.py` | Create | Unit tests for repo exists and repo bootstrap flows. |
| `tests/unit/test_build_messages_git_intent.py` | Create | Unit tests for git intent guidance injection. |
| `tests/unit/test_agent_git_bootstrap_flow.py` | Create | Unit test for reasoning-loop git tool path staying off filesystem writes. |

## Interfaces / Contracts

```python
async def init(self, path: str, initial_branch: str = "main") -> SkillResult: ...
```

Expected payload shape:

```python
{
    "path": str,
    "git_dir": str,
    "created": bool,
    "branch": str | None,
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `GitOpsSkill.status/init` | Temporary directories with GitPython-backed repos. |
| Unit | `_build_messages` git guidance | Assert injected system message content for Spanish repo-intent phrases. |
| Unit | Reasoning-loop tool path | Mock Qwen + skill registry; assert git tools run and filesystem write does not. |

## Migration / Rollout

No migration required.

## Open Questions

- [ ] None.
