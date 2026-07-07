# Aki Video Script

Target length: about 90 to 120 seconds.

Use short pauses.
Keep each line on screen as a subtitle if needed.

## Script

Hello.

This project is Aki.

Aki gives AI coding agents project memory.

It works through MCP.

So tools like OpenCode or Claude Code can read and save memory.

The problem is simple.

AI coding assistants forget project decisions between sessions.

That creates repeated mistakes.

With Aki, the agent can remember facts, decisions, and procedures for one project.

The memory is stored locally in SQLite and ChromaDB.

Qwen Cloud is used to extract structured memory from normal text.

Now I will show the core demo.

First, I save one project decision.

We use `pnpm` in this project.

That decision is now stored in Aki.

Next, I ask the coding agent a simple question.

How should I install dependencies for this repo?

This is the important moment.

Without memory, the agent may guess.

With Aki, it reads project memory first.

So it answers with `pnpm`.

That is the value of the system.

Memory changes agent behavior.

Aki also supports search, context retrieval, memory explanation, and Qwen-based extraction from project documents.

For deployment, this project is also running on Alibaba Cloud.

Thank you.

## Shot List

1. Title card or README header with the project name `Aki`.
2. Terminal showing `uv run aki mcp-config opencode` or the MCP setup snippet.
3. OpenCode or another MCP host saving the decision: `We use pnpm in this project.`
4. Result of the save operation.
5. Follow-up question: `How should I install dependencies for this repo?`
6. Response showing `pnpm` because memory was retrieved.
7. Optional quick flash of `memory_extract` or the five MCP tools.
8. Alibaba Cloud deployment proof screenshot or short screen capture.

## Recording Notes

- Speak slowly.
- Keep one idea per sentence.
- If pronunciation feels hard, keep the product terms only: `Aki`, `MCP`, `Qwen`, `pnpm`, `Alibaba Cloud`.
- If the Qwen extraction demo is unstable, skip it and keep the memory save plus memory retrieval story. That is enough for a strong MemoryAgent demo.
