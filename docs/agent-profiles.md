# Specialized agent profiles

Specialized agent profiles let Aki run one existing `AgentOS` turn with a selected identity, prompt, tool policy, and memory scope. They do not create workers, subprocesses, parallel agents, recursive delegation, or a supervisor runtime.

## Quick path

1. Add one or more profiles under `agent_profiles.profiles` in your Aki YAML config.
2. Inspect configured profiles with `aki agents`.
3. Select one profile with `aki chat --profile <id>` or `aki interactive --profile <id>`.

## Example config

```yaml
agent_profiles:
  default: reviewer
  profiles:
    - id: reviewer
      name: Reviewer
      description: Reviews changes for correctness and risk before shipping.
      role: reviewer
      prompt_template: |
        You are a careful reviewer. Focus on correctness, regressions, and scope control.
      model: qwen-plus
      temperature: 0.1
      max_iterations: 3
      tools:
        allowed:
          - memory.recall
          - filesystem.read
          - git.diff
      memory:
        scope: session
      delegation:
        enabled: false
        strategy: future-review-chain

    - id: planner
      name: Planner
      description: Produces implementation plans without tool execution.
      role: planner
      prompt_template: |
        You are a planner. Clarify requirements and produce small reviewable work units.
      tools:
        deny_all: true
      memory:
        scope: project
```

## Policy reference

| Policy | Values | Effect |
|--------|--------|--------|
| `tools.allowed` | Tool names like `memory.recall` or `filesystem.read` | Only these tools are advertised and allowed before execution. |
| `tools.deny_all` | `true` | No tools are advertised or executed for this profile. |
| `memory.scope` | `project`, `session`, `global`, `disabled` | Controls which memory context and writes are available during the selected turn. |
| `delegation` | Metadata object | Stored as inert future metadata only; it does not create workers or delegate execution. |

## CLI usage

```bash
aki agents
aki chat --profile reviewer "Review my current diff"
aki interactive --profile planner
```

Unknown profile ids fail before the agent turn starts, so no user message is persisted and no model call is made for that request.
