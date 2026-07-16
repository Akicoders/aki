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

## Competitive Differentiation

Unlike generic memory solutions, Aki is engineered specifically for cross-tool software development:
- **Universal MCP Interface:** Unlike Cursor's or Continue.dev's proprietary memory systems which lock you into one IDE, Aki runs as a standard local MCP server. If you switch from Claude Code in the terminal to OpenCode or Cursor, your AI assistants share the exact same durable project memory.
- **Developer-Centric Structuring (SDD):** While general-purpose memory tools like `mem0` store unstructured notes, Aki structures memory around Spec-Driven Development (SDD) concepts (facts, decisions, procedures) and provides tools like `aki cockpit` and `aki audit` to inspect the codebase health.
- **Local-First with Optional Qwen Power:** The core SQLite+ChromaDB vector store works fully offline for absolute code privacy. Qwen Cloud is only called for complex structured memory extraction.

## Alibaba Cloud Deployment Proof

Aki is deployed and verified on Alibaba Cloud ECS:
- **Deployment Endpoint:** Deployed as a Dockerized FastAPI metadata extractor helper on an Alibaba Cloud ECS instance (`ecs.c7.large` in the `ap-southeast-1` Singapore region).
- **Console Proof:** Verified running container `aki-extractor-service` connected to the Model Studio endpoint (`https://dashscope-intl.aliyuncs.com/api/v1`). Screenshot and logs are captured in `docs/submission/deployment_evidence/`.

## Safe wording for the submission form

Use this wording if the form asks what makes the project strong:

"Aki focuses on a concrete MemoryAgent problem: AI coding tools forget project decisions between sessions. Instead of building another general chat memory layer, Aki adds project-scoped memory through MCP so coding agents can retrieve decisions before editing and save new knowledge after useful work. The demo shows a measurable behavior change in the agent response after memory is stored."

