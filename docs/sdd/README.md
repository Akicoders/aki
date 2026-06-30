# Spec-Driven Development (SDD) — Aki

This project was developed using **Spec-Driven Development (SDD)**, a structured methodology that ensures architectural clarity, testability, and incremental delivery.

## What is SDD?

SDD is a development workflow that breaks complex changes into five phases:

1. **Explore** — Investigate the problem space, analyze references, and identify opportunities
2. **Propose** — Define intent, scope, and approach with explicit success criteria
3. **Specify** — Write testable requirements with Given/When/Then scenarios
4. **Design** — Make architectural decisions with documented tradeoffs
5. **Implement** — Execute tasks in phases with continuous verification

Each phase produces artifacts that inform the next, creating a traceable decision chain from idea to code.

## Aki's SDD Artifacts

This project's SDD artifacts are organized in `docs/sdd/`:

| Artifact | File | Purpose |
|----------|------|---------|
| **Exploration** | [`explore.md`](explore.md) | Initial analysis of memory agent landscape and differentiation opportunities |
| **Ecosystem Exploration** | [`explore-ecosystem.md`](explore-ecosystem.md) | Deep dive into MCP, OpenCode, Claude Code, and target integrations |
| **Proposal** | [`proposal.md`](proposal.md) | Scope definition, capabilities, risks, and success criteria |
| **Specification** | [`spec.md`](spec.md) | Testable requirements with scenarios for all 5 MCP tools |
| **Design** | [`design.md`](design.md) | Architecture decisions, data flow, interfaces, and testing strategy |
| **Tasks** | [`tasks.md`](tasks.md) | Phased implementation plan with acceptance criteria |
| **Apply Progress** | [`apply-progress.md`](apply-progress.md) | Implementation status and verification results |

## Development Timeline

| Phase | Duration | Status | Commits |
|-------|----------|--------|---------|
| Phase 1: Blocker fixes | Day 1 | ✅ Complete | `18ffcfd` |
| Phase 2: MCP server core | Day 2 | ✅ Complete | `e7925f0` |
| Phase 3: Qwen extraction | Day 3 | ✅ Complete | `1a6d89c`, `8afcb04` |
| Phase 4: Polish + demo | Day 4 | ✅ Complete | `be2d2a0` → `0518b23` |

## Key Architectural Decisions

1. **MCP-first delivery** — Local stdio server, not REST API or chat interface
2. **Five-tool surface** — Compact, focused API for coding agents
3. **Qwen-powered extraction** — Structured JSON with deterministic fallback
4. **Embedder protocol injection** — Testable without real sentence-transformers
5. **Project detection** — Git root → cwd → default, for seamless MCP host integration

## Testing Strategy

- **Unit tests**: Project detection, capsule formatting, extraction parsing
- **Repository tests**: FakeEmbedder + temp SQLite/Chroma (no model downloads)
- **MCP tests**: Direct handler calls with fake Qwen responses
- **CLI tests**: Typer runner assertions

**Result**: 51 tests passing in <5 seconds

## Why SDD?

For a 4-day hackathon, SDD provided:

- **Scope discipline** — Explicit cut lines prevented feature creep
- **Testability first** — FakeEmbedder designed before real implementation
- **Traceable decisions** — Every architectural choice documented with tradeoffs
- **Incremental delivery** — Each phase independently verifiable
- **Demo confidence** — Fallback paths designed alongside primary flows

## Learn More

- [SDD methodology](https://github.com/Gentleman-Programming/gentle-ai) — Gentle-AI's SDD implementation
- [Engram](https://github.com/engram-ai/engram) — Persistent memory for SDD artifacts
- [OpenSpec](https://openspec.dev) — Alternative artifact store
