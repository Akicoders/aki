# Tasks: Agent Runtime Telemetry

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 300-450 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR with reviewable work-unit commits |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Agent status helpers and tests | PR 1 | Keep helper copy, privacy checks, and status sequence tests together. |
| 2 | CLI interactive wiring and tests | PR 1 | Add Rich status callback path without changing loop controls. |
| 3 | Exhaustion copy and regression coverage | PR 1 | Prove single-agent, actionable, non-leaking failure text. |

## Phase 1: Agent Status Foundation

- [x] 1.1 RED: Extend `tests/unit/test_agent_status.py` for turn start, iteration `i/max`, final-iteration warning, tool `k/m`, completion, and failure statuses.
- [x] 1.2 GREEN: Add private formatting/emission helpers in `src/agentos/agent/core.py` using only `StatusCallback` strings and `AgentConfig.max_iterations`.
- [x] 1.3 REFACTOR: Centralize status copy in `core.py`; do not add config knobs, schemas, persistence, logs, workers, routing, or multi-agent concepts.

## Phase 2: Reasoning Loop Telemetry

- [x] 2.1 RED: Add exhausted-loop tests in `tests/unit/test_reasoning_outcome.py` proving iteration progress and final warning before budget exhaustion.
- [x] 2.2 GREEN: Pass `status_callback` through `AgentOS.chat()` into `_reasoning_loop()` and emit bounded iteration/tool-boundary updates.
- [x] 2.3 RED: Add privacy tests where tool args/results include API keys, private paths, prompts, or memory payloads and must not appear in statuses.
- [x] 2.4 GREEN: Ensure tool telemetry includes only safe tool display name, ordinal/count, and phase; never raw arguments or result payloads.

## Phase 3: CLI Integration

- [x] 3.1 RED: Update `tests/unit/test_cli_chat.py` for one-shot `chat` callback rendering and `_async_interactive()` per-prompt Rich status callback wiring.
- [x] 3.2 GREEN: Modify `src/agentos/cli/main.py` so interactive prompts use `console.status().update` like one-shot chat while preserving `/` commands, Ctrl-C, EOF, and Markdown output.
- [x] 3.3 REFACTOR: Keep CLI as renderer only; avoid duplicating telemetry copy outside `core.py`.

## Phase 4: Exhaustion Contract

- [x] 4.1 RED: Extend `tests/unit/test_agent_exhaustion.py` for actionable exhaustion with budget, no-final-answer statement, last safe phase/tool, and next steps.
- [x] 4.2 GREEN: Enrich `_format_exhaustion_message()` in `src/agentos/agent/core.py` for tool and no-tool exhaustion without inventing tool names.
- [x] 4.3 REGRESSION: Assert all status and exhaustion text avoids worker, sub-agent, delegation, routing, orchestration, secrets, prompt content, raw paths, and tool payloads.

## Phase 5: Verification

- [x] 5.1 Run focused unit tests: `pytest -xvs tests/unit/test_agent_status.py tests/unit/test_agent_exhaustion.py tests/unit/test_reasoning_outcome.py tests/unit/test_cli_chat.py`.
- [x] 5.2 Run project verification from config: `pytest -v --cov=src/agentos --cov-report=xml`, `ruff check .`, and `mypy src/agentos`. (Reconciled at archive time: `verify-report.md` proves this was executed and passed — full suite 356/357 with one pre-existing unrelated failure, ruff clean, mypy 200 pre-existing project-wide errors. Checkbox was stale in the persisted tasks artifact; verify-report is the completion evidence per the archive stale-checkbox reconciliation policy.)
