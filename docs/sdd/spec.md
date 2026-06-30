# Specification: Hackathon MVP

## Purpose

Deliver Qwen Memory Bridge as a July 1 hackathon MVP: a local stdio MCP memory server for AI coding agents, with Qwen-powered extraction, green core checks, and demo-ready docs.

## Requirements

### Requirement: MCP Memory Server Tools

The system MUST expose exactly five MVP MCP tools: `memory_context`, `memory_search`, `memory_save`, `memory_extract`, and `memory_explain`. Tool responses MUST be compact, structured, and safe for coding-agent context.

#### Scenario: Coding agent reads project context
- GIVEN a project with saved memories
- WHEN `memory_context` is called with that project
- THEN the response includes recent decisions, facts, procedures, and source metadata
- AND the response is bounded to a compact capsule

#### Scenario: Coding agent searches memory
- GIVEN memories exist for multiple topics
- WHEN `memory_search` is called with a query and limit
- THEN matching memories are returned in relevance order
- AND each result includes id/title/kind/summary/project metadata

#### Scenario: Coding agent saves memory
- GIVEN a valid kind of `fact`, `decision`, or `procedure`
- WHEN `memory_save` is called with title, content, project, and optional confidence
- THEN the memory is persisted and is retrievable by context and search

#### Scenario: Invalid tool input
- GIVEN missing required arguments or an unsupported memory kind
- WHEN any MCP tool is called
- THEN the tool returns a structured error
- AND no partial memory is written

### Requirement: Qwen Extraction and Explanation

The system MUST use Qwen to extract structured memory candidates from text and explain why retrieved memories are relevant. Tests MUST support deterministic fake Qwen responses.

#### Scenario: Extract memory candidates
- GIVEN text containing a decision, fact, and procedure
- WHEN `memory_extract` is called
- THEN it returns structured candidates grouped by kind
- AND each candidate includes title, content, confidence, and provenance

#### Scenario: Explain relevance
- GIVEN a query and retrieved memories
- WHEN `memory_explain` is called
- THEN it returns a concise rationale for each relevant memory
- AND it does not invent facts absent from stored memory

#### Scenario: Qwen unavailable
- GIVEN Qwen credentials are absent or the API fails
- WHEN extraction or explanation is requested
- THEN the tool returns a clear recoverable error
- AND local save/search/context tools remain usable

### Requirement: Hackathon Blocker and CI Readiness

The repository MUST be credible for public evaluation: lint configuration, dependencies, tests, git/GitHub readiness, and hanging integrations MUST be fixed or explicitly gated.

#### Scenario: Core checks pass quickly
- GIVEN a fresh checkout using documented setup
- WHEN lint and test commands run in CI
- THEN Ruff configuration is valid, required dependencies resolve, and core tests complete without hanging on real embeddings

#### Scenario: Integration tests are safe
- GIVEN tests require embeddings or Qwen
- WHEN tests run without external credentials
- THEN fake clients or explicit skip markers prevent network/model downloads
- AND CI reports a deterministic result

#### Scenario: Public repo readiness
- GIVEN the hackathon evaluator opens the repository
- WHEN they inspect project state
- THEN the default branch, initial commit history, and GitHub remote are present or documented as setup prerequisites

### Requirement: Coding Agent Integration

The system MUST provide OpenCode-first MCP integration and SHOULD document Claude Code and Antigravity equivalents.

#### Scenario: OpenCode connects to local server
- GIVEN the documented OpenCode config is installed
- WHEN OpenCode starts MCP discovery
- THEN the local stdio server starts with `agentos mcp`
- AND all five memory tools are listed as enabled

#### Scenario: Secondary host docs
- GIVEN a user of Claude Code or Antigravity
- WHEN they read integration docs
- THEN they can identify the required local MCP command and config shape
- AND unsupported host-specific details are clearly labeled

### Requirement: README and Demo Assets

The system MUST present the MVP as portable project memory for AI coding agents, not a generic chatbot or multi-channel assistant.

#### Scenario: README explains value fast
- GIVEN a first-time evaluator
- WHEN they open the README
- THEN they see setup, architecture, Qwen usage, MCP tools, OpenCode config, and demo flow
- AND skipped scope excludes WhatsApp, Telegram, voice, REST API, multi-user, and autonomous skill creation

#### Scenario: Demo proves behavior change
- GIVEN the demo script is followed
- WHEN a memory is saved/extracted and later queried from an AI coding agent
- THEN the agent receives relevant project memory that changes its answer or action
- AND the script includes a fallback path for Qwen/API instability
