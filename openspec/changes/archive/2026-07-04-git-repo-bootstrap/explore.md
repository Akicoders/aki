## Exploration: git-repo-bootstrap

### Current State
`GitOpsSkill` supports status/diff/commit/push/log/branch/remote, but it has no repository-initialization capability. `_build_messages` only adds a scaffolding-intent warning, so version-control requests are not steered toward `git_ops`. When the model misses repo state, the only obvious creation-capable tool is `filesystem.write`, which is how QA ended up with attempted writes inside `.git/objects`.

### Affected Areas
- `src/agentos/skills/git_ops.py` - add a real git bootstrap capability and more honest repo detection.
- `src/agentos/agent/core.py` - inject a version-control intent addendum that prefers `git_ops.status` and `git_ops.init` over filesystem writes.
- `tests/unit/test_build_messages_scaffolding.py` or a sibling test file - cover version-control intent prompt wiring.
- `tests/unit/` git skill tests - cover repo exists and repo missing/bootstrap behavior.
- `tests/unit/test_agent_destructive_gate.py` or a sibling behavior test - prove the agent/tool path can stay on git tools instead of filesystem writes.

### Approaches
1. **Prompt steering + real git init capability** - add `git_ops.init` and a dedicated prompt addendum for repo/version-control intents.
   - Pros: minimal, honest, uses a real git capability, preserves existing reasoning loop.
   - Cons: still model-driven; no deterministic auto-rewrite of bad tool choices.
   - Effort: Medium.

2. **Reasoning-loop interception for repo intent** - detect repo-status intent and rewrite/force tool calls in `_reasoning_loop`.
   - Pros: stronger enforcement.
   - Cons: much more invasive, mixes product intent routing into runtime orchestration, higher regression risk.
   - Effort: High.

### Recommendation
Choose approach 1. The failure mode came from a missing capability plus missing prompt guidance, not from a broken execution engine. Adding `git_ops.init`, making repo detection explicit, and steering version-control asks toward git tools eliminates the unsafe filesystem path with much lower blast radius.

### Risks
- Prompt steering is advisory, so the tests must cover the injected instruction clearly.
- GitPython behavior around bare/no-commit repos needs explicit handling for `active_branch` and staged diff against `HEAD`.
- `multi-agent-orchestration` must stay untouched; this change should remain single-agent only.

### Ready for Proposal
Yes - the scope is narrow, additive, and already mapped to concrete files/tests.
