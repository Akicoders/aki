# Agent Runtime Telemetry Specification

## Purpose

Define live, safe, single-agent runtime status and exhaustion behavior for CLI turns in `aki chat` and `aki interactive`.

## Requirements

### Requirement: Live CLI Turn Status

The system MUST emit bounded runtime status updates for each single-agent turn. Status updates MUST cover turn start, reasoning iteration progress, tool execution boundaries, final-iteration warning, completion, and failure/exhaustion states.

#### Scenario: One-shot chat shows iteration progress

- GIVEN `aki chat` starts a turn with `max_iterations` greater than one
- WHEN the reasoning loop enters iteration 1
- THEN the Rich status indicator MUST show the current iteration and total iteration budget
- AND this behavior MUST be covered by unit tests marked `pytest.mark.unit` or the repository's unit-test convention

#### Scenario: Interactive mode uses the same status path

- GIVEN `aki interactive` accepts a user prompt
- WHEN the prompt is processed as an agent turn
- THEN the same status callback behavior used by `aki chat` MUST render live progress
- AND Ctrl-C/EOF loop handling MUST remain unchanged

### Requirement: Tool Telemetry Contract

The system MUST display only factual tool telemetry: tool name, ordinal/count, and phase. It MUST NOT display raw tool arguments, secrets, prompt content, memory payloads, tokens, environment values, or full tool results.

#### Scenario: Tool call status is safe and useful

- GIVEN a turn invokes two tools named `search_memory` and `read_file`
- WHEN each tool starts
- THEN status text MUST include the tool name and count such as `tool 1/2`
- AND status text MUST NOT include tool argument values or result payloads

#### Scenario: Sensitive data stays private

- GIVEN a tool argument contains an API key, filesystem path with private names, or user prompt text
- WHEN status is rendered
- THEN none of those values MUST appear in status output, logs introduced by this change, or exhaustion guidance

### Requirement: Final-Iteration Warning

The system MUST warn before consuming the last configured reasoning iteration. The warning MUST be based on `AgentConfig.max_iterations` and MUST NOT introduce new runtime budget configuration.

#### Scenario: Last iteration warning appears before exhaustion

- GIVEN `max_iterations` is 3
- WHEN the reasoning loop enters iteration 3 without a final answer
- THEN status MUST indicate this is the final available iteration before exhaustion

### Requirement: Exhaustion Message Contract

When a turn exhausts its iteration budget, the user-facing response MUST explain: the iteration budget was reached, the last safe attempted phase/tool name if known, that no final answer was produced, and safe next steps such as simplifying the request or increasing clarity. It MUST NOT imply worker agents, delegation, or multi-agent orchestration.

#### Scenario: Exhaustion response is actionable

- GIVEN a turn reaches `max_iterations` without a final answer
- WHEN the CLI presents the failure message
- THEN the message MUST name the exhausted iteration budget
- AND it MUST include the last attempted phase or safe tool name when available
- AND it MUST include at least one safe next step

#### Scenario: Exhaustion without tool activity remains accurate

- GIVEN a turn exhausts during reasoning without calling tools
- WHEN the message is generated
- THEN it MUST describe the last attempted phase without inventing a tool name

### Requirement: Single-Agent Scope Boundary

This capability MUST remain single-agent only. It MUST NOT add worker names, specialized-agent routing, delegation status, persistent telemetry schemas, dashboards, database migrations, or multi-agent orchestration behavior.

#### Scenario: Status copy avoids orchestration language

- GIVEN any runtime status or exhaustion message is rendered
- WHEN the text is inspected
- THEN it MUST NOT contain claims about workers, sub-agents, delegation, routing, or orchestration
