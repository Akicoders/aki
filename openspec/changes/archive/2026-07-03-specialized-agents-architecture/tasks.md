# Tasks: Specialized Agents Architecture

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450-650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 profiles/registry → PR 2 runtime policy → PR 3 CLI/docs/e2e |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Profile contracts, config parsing, registry resolution | PR 1 | Include unit tests; no runtime behavior change. |
| 2 | AgentOS prompt/model/tool/memory policy wiring | PR 2 | Depends on PR 1; include integration tests. |
| 3 | CLI profile option, docs, regression/e2e proof | PR 3 | Depends on PR 2; verify single-agent boundary. |

## Phase 1: Profiles and Registry

- [x] 1.1 RED: Add `tests/unit/test_agent_profiles.py` cases for valid/invalid `AgentProfile`, stable ids, required prompt/tools/memory, deny-all policy, and inert delegation metadata.
- [x] 1.2 GREEN: Create `src/agentos/agents/profiles.py` with Pydantic `AgentProfile`, `ToolPolicy`, `MemoryPolicy`, and `DelegationMetadata` contracts.
- [x] 1.3 RED: Add registry tests for duplicate ids, unknown profile failure, and deterministic selected-profile resolution.
- [x] 1.4 GREEN: Create `src/agentos/agents/registry.py` plus `src/agentos/agents/__init__.py`; keep it separate from `SkillRegistry` and free of tool execution.
- [x] 1.5 Add `AgentProfilesConfig` parsing in `src/agentos/core/config.py`, with absent `agent_profiles` preserving current defaults.

## Phase 2: Agent Runtime Policy Wiring

- [x] 2.1 RED: Add integration tests in `tests/integration/test_agent_profile_runtime.py` proving no-profile `AgentOS.chat()` and `stream_chat()` behavior remains unchanged.
- [x] 2.2 Modify `src/agentos/agent/core.py` to accept optional `profile_id`, resolve it before user input persistence/Qwen calls, and merge model/temperature/max-iterations defaults.
- [x] 2.3 Apply profile prompt templates in message construction while preserving the existing default prompt when no profile is selected.
- [x] 2.4 Filter advertised tools and validate requested tool calls before `SkillRegistry.execute()`; keep destructive safeguards after allow-policy checks.
- [x] 2.5 Add memory-policy adapter logic around context reads, event creation, and checkpoint metadata; prevent cross-profile/session leakage without DB/vector migrations.

## Phase 3: CLI, Docs, and Regression Proof

- [x] 3.1 RED: Add CLI tests for `aki chat --profile` and `aki interactive --profile`, including unknown profile failure before agent execution.
- [x] 3.2 Update `src/agentos/cli/main.py` with optional `--profile` for `chat` and `interactive`, and display the selected profile in command headers.
- [x] 3.3 Add docs/config examples for `agent_profiles`, allowed tools, memory scopes, and delegation metadata as non-executing future metadata.
- [x] 3.4 Add regression tests proving delegation metadata creates no worker, subprocess, parallel agent, or recursive delegation path.
- [x] 3.5 Run `pytest -xvs`, targeted marker runs for unit/integration/e2e scenarios, `ruff check .`, and `mypy src/agentos`; fix regressions in-slice.
