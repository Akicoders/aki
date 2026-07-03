# Specialized Agents Specification

## Purpose

Define declarative specialized agent profiles and registry behavior for selecting one scoped agent identity inside the existing single `AgentOS` loop.

## Requirements

### Requirement: AgentProfile Contract

The system MUST define an `AgentProfile` contract for agent identity and runtime policy. A profile MUST include stable `id`, display `name`, `description`, `role`, prompt configuration, optional model configuration, tool policy, and memory policy.

#### Scenario: Valid profile is accepted (`unit`)

- GIVEN a profile with required identity fields and scoped policies
- WHEN profile validation runs
- THEN the profile SHALL be accepted
- AND its fields SHALL be available to the selected agent turn

#### Scenario: Invalid profile is rejected (`unit`)

- GIVEN a profile missing `id`, prompt policy, tool policy, or memory policy
- WHEN profile validation runs
- THEN validation MUST fail with a specific error

### Requirement: AgentRegistry Responsibilities

The system MUST provide an `AgentRegistry` that discovers, validates, and resolves built-in or configured `AgentProfile` entries. The registry MUST remain separate from `SkillRegistry`; it SHALL NOT execute tools or own skill implementation details.

#### Scenario: Selected profile resolves deterministically (`unit`)

- GIVEN registered profiles and a requested profile id
- WHEN the registry resolves the selection
- THEN it MUST return exactly one matching `AgentProfile`

#### Scenario: Unknown profile fails safely (`unit`)

- GIVEN no registered profile matches a requested id
- WHEN profile resolution runs
- THEN the request MUST fail before agent execution starts

### Requirement: Profile-Scoped Prompt and Model Policy

The selected profile MUST define or reference the prompt template used for the turn. A profile MAY override model, temperature, and max-iterations; omitted values MUST inherit the existing global defaults.

#### Scenario: Profile prompt is applied (`unit`)

- GIVEN a selected reviewer profile with a custom prompt template
- WHEN the agent turn is prepared
- THEN the effective system prompt MUST include that profile prompt

#### Scenario: Defaults are preserved (`integration`)

- GIVEN no profile is selected
- WHEN `aki chat` or `aki interactive` starts
- THEN current default prompt and model behavior MUST remain unchanged

### Requirement: Profile-Scoped Tool Policy

The selected profile MUST declare allowed skills/functions or an explicit deny-all policy. Agent execution MUST NOT call tools outside the selected profile scope, and destructive-tool safeguards MUST continue to apply.

#### Scenario: Allowed tool can run (`integration`)

- GIVEN a selected profile allows a skill/function
- WHEN the agent requests that tool
- THEN the existing `SkillRegistry` path MAY execute it

#### Scenario: Disallowed tool is blocked (`unit`)

- GIVEN a selected profile does not allow a requested tool
- WHEN the agent requests that tool
- THEN execution MUST be denied before tool invocation

### Requirement: Profile-Scoped Memory Policy

The selected profile MUST declare memory scope rules for project, session, global, or disabled memory. Memory reads and writes MUST be constrained to the effective profile policy, and persisted metadata MUST NOT imply ownership of data outside that scope.

#### Scenario: Scoped memory access (`integration`)

- GIVEN a selected profile limited to session memory
- WHEN the agent reads or writes memory
- THEN only session-scoped memory operations SHALL be allowed

#### Scenario: Cross-profile leakage is prevented (`unit`)

- GIVEN memory entries associated with another profile scope
- WHEN the selected profile queries memory
- THEN out-of-scope entries MUST NOT be returned

### Requirement: Metadata-Only Delegation Boundary

This change MUST NOT introduce a full autonomous supervisor/worker runtime, recursive delegation, parallel agents, worker spawning, or external process orchestration. Delegation-related fields MAY exist only as inert metadata for future staged changes.

#### Scenario: Delegation metadata does not execute (`unit`)

- GIVEN a profile contains future delegation metadata
- WHEN an agent turn runs
- THEN no worker, subprocess, or parallel agent SHALL be created

#### Scenario: Runtime stays single-agent (`e2e`)

- GIVEN a selected specialized profile
- WHEN the user completes one CLI chat turn
- THEN execution MUST use the existing single `AgentOS` loop
