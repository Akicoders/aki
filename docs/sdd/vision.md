# Aki SDD Vision

Aki should preserve more than isolated memories. It should preserve development continuity.

## First-class artifacts

- `proposal`: problem framing and intended outcome
- `spec`: product or behavior contract
- `design`: technical approach and tradeoffs
- `tasks`: implementation breakdown
- `apply-log`: what changed while implementing
- `verify-report`: evidence and gaps after validation

## Why this matters

Portable memory is most valuable when an agent can recover *why* a system looks the way it does, not just *what* was said.

## Near-term direction

1. Keep artifact references under a stable change key.
2. Reuse `memory_save`, `memory_search`, and `memory_context` for artifact recovery.
3. Prefer cheap extraction models for ingestion and stronger consolidation models for synthesis.
4. Keep docs and PRs aligned with the same artifact vocabulary.
