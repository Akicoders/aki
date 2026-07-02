# Explore: project-audit-cockpit

## Key finding

An approved design doc already exists at
`docs/superpowers/specs/2026-07-01-aki-cockpit-operational-design.md` and is the
authoritative spec for this feature. It defines a 5-phase plan:

- Phase 1 (foundation) — done in `src/agentos/cli/cockpit.py`
- Phase 2 (overview screen) — done
- Phase 3 (drill-downs + `aki projects browse`) — partial, browse is a placeholder
- Phase 4 (`aki audit`) — not started
- Phase 5 (`--autofix` and web) — explicitly a non-goal for this slice

## Scope decision

User confirmed: follow the approved plan. This change covers Phase 3 (drill-down
navigation + `aki projects browse` + keyboard shortcuts) and Phase 4 (read-only
audit engine). Web and `--autofix` remain out of scope, deferred to a later change.

## "Rich keyboard navigation" clarification

Current `cockpit.py` is Typer-command-driven (static Rich output per invocation),
not a live TUI. The design doc's keymap (Tab/j/k/Enter/b/g/r/q, section 6) implies
a persistent-screen TUI. No TUI library (textual/urwid/prompt-toolkit) is in
`pyproject.toml` yet — this is an architecture decision for `sdd-design`.

## Audit engine hook point

`src/agentos/skills/code_intel.py` already exposes `run_tests`, `run_lint`,
`get_coverage` as an async Skill — natural building block for audit passes
instead of reimplementing subprocess calls.

## Relevant files

- `src/agentos/cli/cockpit.py`
- `src/agentos/cli/main.py`
- `src/agentos/cli/mcp_hosts.py`
- `tests/unit/test_cockpit.py`
- `docs/superpowers/specs/2026-07-01-aki-cockpit-operational-design.md`
- `src/agentos/skills/code_intel.py`
- `pyproject.toml`

## Recommended approach

Extend the existing Typer-command pattern (Option A) rather than a full live-TUI
rewrite (Option B, requires introducing `textual` and redoing the Rich-panel
testing strategy). Keyboard navigation for this slice means fast subcommand
shortcuts and a lightweight interactive prompt loop for drill-downs, not a
persistent full-screen TUI, unless design phase finds strong reason otherwise.
