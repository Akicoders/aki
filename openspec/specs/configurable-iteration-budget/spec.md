# Configurable Iteration Budget Specification

## Purpose

Define the resolved default, environment override, and upper-bound validation
behavior of `AgentConfig.max_iterations` (`src/agentos/core/config.py:152`,
`BaseSettings` with `env_prefix="AGENT_"`). This raises the shipped default
from 5 to 20, adds a hard ceiling so a misconfigured environment value fails
fast instead of creating an unbounded budget, and documents the existing
`AGENT_MAX_ITERATIONS` env var. Per-profile override precedence
(`core.py:398-402`) and worker/supervisor iteration-pool independence
(`core.py:572-580`) are unchanged and are captured here only as regression
guards.

## Requirements

### Requirement: Default Iteration Budget

`AgentConfig` MUST resolve `max_iterations` to `20` when no
`AGENT_MAX_ITERATIONS` environment value is set.

#### Scenario: Fresh config with no env override resolves to the new default (`unit`)

- GIVEN no `AGENT_MAX_ITERATIONS` environment variable is set
- WHEN `AgentConfig()` is constructed
- THEN `config.max_iterations` MUST equal `20`

### Requirement: Environment Override Still Resolves

`AgentConfig` MUST continue to accept `AGENT_MAX_ITERATIONS` from the
environment (or `.env`) via pydantic-settings, overriding the default.

#### Scenario: Env var override resolves to the configured value (`unit`, regression)

- GIVEN `AGENT_MAX_ITERATIONS=10` is set in the environment
- WHEN `AgentConfig()` is constructed
- THEN `config.max_iterations` MUST equal `10`

### Requirement: Upper-Bound Validation

`AgentConfig.max_iterations` MUST be constrained to `gt=0, le=100`. A value
outside this range MUST fail config construction with a clear validation
error rather than being silently clamped or accepted.

#### Scenario: Value above the ceiling fails construction (`unit`)

- GIVEN `AGENT_MAX_ITERATIONS=150` is set in the environment
- WHEN `AgentConfig()` is constructed
- THEN construction MUST raise a pydantic validation error
- AND no `AgentConfig` instance with `max_iterations=150` SHALL be produced

#### Scenario: Non-positive value fails construction (`unit`)

- GIVEN `AGENT_MAX_ITERATIONS=0` is set in the environment
- WHEN `AgentConfig()` is constructed
- THEN construction MUST raise a pydantic validation error

### Requirement: Per-Profile Override Precedence Unchanged

The resolution order at `core.py:398-402` MUST be unaffected by this change:
a profile-level `max_iterations` override MUST still take precedence over
`AgentConfig.max_iterations`.

#### Scenario: Profile override wins over the new global default (`unit`, regression)

- GIVEN `AgentConfig.max_iterations` resolves to `20` (the new default)
- AND an `AgentProfile` sets `max_iterations=3`
- WHEN `_reasoning_loop()` resolves the effective budget for that profile
- THEN the effective `max_iterations` MUST equal `3`, not `20`

### Requirement: Multi-Agent Pool Independence Unchanged

A depth=1 worker loop spawned by delegation (`core.py:572-580`) MUST
continue to resolve its own `max_iterations` independently from the
depth=0 supervisor's pool, per the archived `multi-agent-orchestration`
contract.

#### Scenario: Worker's iteration pool is independent of the supervisor's (`integration`, regression)

- GIVEN a supervisor loop is running at `depth=0` with its own resolved
  `max_iterations`
- AND it delegates to a worker profile with a different `max_iterations`
- WHEN the worker's nested `_reasoning_loop()` runs at `depth=1`
- THEN the worker's iteration count and budget MUST be tracked separately
  from the supervisor's, with no shared or combined counter

## Documentation Note

`AGENT_MAX_ITERATIONS` MUST be documented in the README's existing
`## Configuration` section (README.md:134), alongside the other subsystem
env-var blocks, including the default (20), the ceiling (100), and a
one-line explanation of what one iteration means. This is a docs-presence
check at verify time, not a pytest scenario.
