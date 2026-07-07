# Aki Submission Summary

## One-paragraph version

Aki is a portable project memory agent for AI coding assistants. It runs as a local MCP server and gives tools like OpenCode or Claude Code a shared memory layer for project facts, decisions, and procedures. Aki stores memory locally in SQLite and ChromaDB, uses Qwen Cloud to extract structured memory from architecture or workflow text, and still supports core memory operations without cloud credentials. The main demo is simple: save a project decision, ask a follow-up coding question, and show that the agent changes its answer because it retrieved durable project memory first. The project is in the MemoryAgent track and is deployed on Alibaba Cloud for the submission.

## Short form version

Aki gives AI coding agents durable project memory through MCP. It stores facts, decisions, and procedures locally, uses Qwen Cloud for structured extraction, and helps agents answer with project-specific context instead of guessing.

## Grounded feature points

- Local MCP server for AI coding hosts.
- Five memory tools: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`.
- Project-scoped memory for facts, decisions, and procedures.
- Local storage with SQLite and ChromaDB.
- Qwen-powered extraction from free-form project text.
- Deterministic fallback for core save, search, and context flows when Qwen credentials are not available.

## Safe wording for the submission form

Use this wording if the form asks what makes the project strong:

"Aki focuses on a concrete MemoryAgent problem: AI coding tools forget project decisions between sessions. Instead of building another general chat memory layer, Aki adds project-scoped memory through MCP so coding agents can retrieve decisions before editing and save new knowledge after useful work. The demo shows a measurable behavior change in the agent response after memory is stored."
