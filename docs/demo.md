# Aki evaluator walkthrough

This walkthrough is designed for a hackathon judge, reviewer, or open-source evaluator.

## What this demo proves

By the end of the flow, you should have evidence that Aki is more than a memory toy:

- it provides **durable project memory**;
- it tracks **sessions and checkpoints**;
- it exposes **operational posture** through cockpit and audit views;
- it supports **specialized agent profiles**;
- it is ready to **bootstrap into MCP hosts**;
- it is aligned with **Qwen / DashScope** as a concrete Alibaba integration path.

## 0. Prepare the repository

```bash
uv sync --all-extras
cp .env.example .env
```

Optional for Qwen-powered extraction/explanations:

```bash
export QWEN_API_KEY=your_qwen_api_key_here
export QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export QWEN_MODEL=qwen3.7-max
export QWEN_EXTRACTION_MODEL=qwen3.7-plus
export QWEN_CONSOLIDATION_MODEL=qwen3.7-max
```

## 1. Show the product entry point

```bash
uv run aki
```

What to call out:

- Aki opens as an **operational cockpit**, not just a raw CLI.
- The view summarizes project health, action items, memory posture, and SDD status.
- This positions Aki as a repo operating surface for AI agents.

## 2. Show project audit

```bash
uv run aki audit aki
```

What to call out:

- The audit is **read-only**.
- It evaluates tests, SDD completeness, git hygiene, env/config, MCP readiness, and memory posture.
- Reports are saved in `docs/audits/`, which is useful for async review and demo follow-up.

## 3. Show specialized agent profiles

```bash
uv run aki agents
```

What to call out:

- Profiles let the project define planner / builder / reviewer-style behavior.
- Tool access and memory scope are configurable per profile.
- This gives Aki a strong product story beyond “store some notes.”

## 4. Show MCP bootstrap

Generate host configuration:

```bash
uv run aki mcp-config opencode
uv run aki mcp-config claude-code
```

Optional dry-run setup:

```bash
uv run aki mcp-setup opencode --dry-run
```

What to call out:

- Aki is built around **stdio MCP**, which is the right interface for coding-agent hosts.
- `mcp-setup` makes onboarding faster for demos and real use.

## 5. Show session continuity

```bash
uv run aki interactive --new-session
```

Inside the interactive shell, show:

- `/help`
- `/sessions`
- `/sdd`

What to call out:

- Aki keeps a durable `session:last` pointer and per-session checkpoints.
- The session model is useful for long-running coding tasks, not only one-off prompts.

## 6. Optional: show live memory behavior through MCP tools

If you have an MCP host connected, demonstrate this flow:

1. save a decision such as “we use pnpm”; 
2. query memory before asking for install guidance; 
3. show that the answer changes because the agent consulted project memory first.

Suggested prompt:

```text
Before suggesting install commands for this repository, read project memory.
How should dependencies be installed?
```

What to call out:

- Without memory, an agent may guess.
- With Aki, the answer is shaped by stored project context.
- That behavior change is the core product proof.

## 7. Optional: show Qwen / Alibaba alignment

Call out the default endpoint in config and docs:

```text
https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

What to say:

> Aki is open source and local-first, but its cloud-assisted extraction path is already aligned with Qwen through DashScope-compatible configuration.

## Fast review path

If a reviewer only has 90 seconds, use this sequence:

```bash
uv run aki
uv run aki audit aki
uv run aki agents
uv run aki mcp-config opencode
```

## Supporting docs

- [`README.md`](../README.md)
- [`docs/integration.md`](integration.md)
- [`docs/agent-profiles.md`](agent-profiles.md)
- [`docs/demo-script.md`](demo-script.md)
