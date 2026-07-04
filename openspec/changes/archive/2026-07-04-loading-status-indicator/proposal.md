# Proposal: Loading Status Indicator (Phase 1 — Status Text Polish)

## Intent

The user asked for visibility into what the agent is doing and which tools it
is using while a response is pending: "I want a loading animation, or
something that tells me what it's doing and which tools it's using while I
wait."

Exploration established that this capability **already exists structurally**.
Both the one-shot `chat` command (`src/agentos/cli/main.py:163-193`) and the
`interactive` command (`_async_interactive`, `main.py:788-819`) wire a
`status_callback` into `console.status(...)`, which renders Rich's animated
spinner and updates live. `_reasoning_loop()` (`src/agentos/agent/core.py:372`)
already emits per-tool status via `_format_tool_status` (`core.py:71-72`,
called at `core.py:485-488`), e.g. `"Running tool 2/3: memory.search"`, plus
iteration and turn-phase status. The animated spinner and specific tool names
are both live today, in both commands.

So the real gap is **not** plumbing — it is visual polish. Every phase
(context collection, thinking, tool execution, saving) renders as the same
undifferentiated cyan text next to the same spinner; a user must read the
words to know whether a tool is running versus the model thinking. This
change is a **differentiation pass over the existing status text**, not new
plumbing and not a new component.

## Scope

### In Scope (Phase 1 only)
- Differentiate the existing `console.status` message text **by phase type**,
  reusing the current mechanism unchanged in both `chat` and `interactive`.
  No new callback shape, no new data crossing the `StatusCallback` boundary.
- A per-phase glyph + verb scheme applied at the formatting layer
  (`_format_status` / the status-string formatters in
  `src/agentos/agent/core.py:63-72` and `_format_status` at `main.py:77-78`).
  The concrete scheme decided for this slice (see Decisions):
  - Thinking / model turn (e.g. "Starting turn", iteration status):
    `🧠 Thinking — iteration {i}/{n}`
  - Tool execution (`_format_tool_status`):
    `🔧 Running {skill.function} ({k}/{m})`
  - Context collection: `📚 Collecting project context`
  - Saving conversation: `💾 Saving conversation`
  - Terminal phases ("Turn complete" / "Turn exhausted"):
    `✅ Turn complete` / `⏳ Turn exhausted`
- Keep every status string generic and safe: only tool name, ordinal, and
  iteration counts already permitted by the telemetry contract.
- Update the existing string-assertion tests
  (`tests/unit/test_agent_status.py`, `tests/unit/test_cli_chat.py`) to
  match the new formatted strings.

### Out of Scope
- **Rich `Progress`/`Live` persistent step-list panel** (exploration
  candidate (b)). A panel that keeps completed steps visible simultaneously is
  better long-term UX but carries same-day regression risk against two
  already-passing CLI test files and has known nesting hazards with
  `console.print(...)`/`KeyboardInterrupt` paths. **Flagged as a Phase 2
  fast-follow.**
- **Any telemetry-contract change.** No `run_id`/`parent_run_id`, no change to
  the `StatusCallback` signature (`Callable[[str], None]`).
- **Any worker/supervisor/delegation vocabulary in status text.** Hard
  constraint from the archived `agent-runtime-telemetry` spec (Single-Agent
  Scope Boundary) and `multi-agent-orchestration` spec (Telemetry Contract
  Untouched in Phase 1) — status copy MUST NOT distinguish supervisor vs.
  worker. The chosen verbs ("Thinking", "Running", "Collecting", "Saving")
  are deliberately orchestration-neutral.
- **Finer-grained intra-tool progress** (instrumenting slow individual
  skills) — unavailable without per-skill instrumentation; out of scope.
- **Flat prints replacing the spinner** (candidate (c)) — rejected as a UX
  downgrade.

## Capabilities

### New Capabilities
- `loading-status-indicator`: Phase-differentiated status text over the
  existing `console.status` spinner — a presentation-only refinement of
  already-emitted, contract-safe status strings.

### Modified Capabilities
- None. Telemetry and multi-agent contracts are unchanged; this only alters
  how existing safe strings are formatted.

## Approach

Change is confined to the status-formatting layer. The `StatusCallback`
boundary, its call sites, and the CLI wiring stay identical; only the string
each formatter produces gains a leading glyph and a phase-specific verb.
Because no new data crosses the callback and no new Rich component is
introduced, the two shipped spec contracts cannot be affected — worker
delegation still reuses the identical callback and emits the identical
generic strings.

Candidate (b) (Rich `Progress`/`Live` panel) is deferred: it is the more
correct long-term answer but is riskier for a same-day ship. Candidate (c)
(flat prints) is rejected as a downgrade from today's animated spinner.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modified | Add per-phase glyph/verb to `_format_iteration_status`, `_format_final_iteration_status`, `_format_tool_status`, and turn-phase status strings. |
| `src/agentos/cli/main.py` | Modified | Update `_format_status` (`main.py:77-78`) to preserve/pass through the new formatting; no wiring change. |
| `tests/unit/test_agent_status.py` | Modified | Update string assertions to new formatted output. |
| `tests/unit/test_cli_chat.py` | Modified | Update any status-string assertions. |

## Decisions (made autonomously — same-day loop)

Because this is an autonomous same-day loop, the following conservative,
lowest-risk calls were made rather than blocking on the user:

- **Emoji glyphs are included** (🧠/🔧/📚/💾/✅/⏳). Rationale: they give the
  at-a-glance visual differentiation the user asked for at zero contract risk.
  If a target terminal renders emoji poorly, the verb prefix alone still
  differentiates phases, so this degrades gracefully. **Fork flagged:** a
  user preferring ASCII-only output would want plain markers (e.g.
  `[tool]`) instead — trivially swappable at the formatting layer if
  requested.
- **Iteration count IS shown** (`iteration {i}/{n}`) — it already exists in
  today's output, so retaining it is the no-regression choice.
- **Distinct color per phase is NOT added** in this slice; the existing
  `bold cyan` is kept for all phases. Glyph + verb already provide the
  differentiation, and per-phase colors add markup surface for marginal gain.
  Left to Phase 2 alongside the panel if desired.
- **No change to update cadence** — one status update per existing callback
  invocation; sub-tool granularity stays out of scope.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Telemetry/scope contract violation via status text | Low | No callback/signature change; verbs are orchestration-neutral; no worker vocabulary. |
| Existing status-string tests break | High (expected) | Tests are updated in the same slice to the new strings — the change is a controlled string update, not a behavior change. |
| Emoji render poorly in some terminals | Low | Verb prefix differentiates phases even if the glyph fails to render. |
| Perceived as too small a change vs. the ask | Med | Documented: the plumbing already satisfied the literal ask; if (a) under-delivers in practice, escalate to Phase 2 panel (candidate b). |

## Rollback Plan

Revert the formatter strings to their prior values (drop the glyphs/verbs) and
restore the original test assertions. No data, checkpoint, or contract
migration is involved.

## Dependencies

- Existing `StatusCallback`, `_format_status`, `_format_tool_status`,
  `_format_iteration_status`, and the `console.status` wiring in both `chat`
  and `_async_interactive`.
- Archived `agent-runtime-telemetry` and `multi-agent-orchestration` specs
  remain unchanged adjacent constraints — neither is modified.

## Success Criteria

- [ ] Status text visually distinguishes thinking, tool execution, context
      collection, and saving phases in both `chat` and `interactive`.
- [ ] Tool-execution status still names the specific `skill.function` and
      ordinal.
- [ ] No worker/supervisor/delegation vocabulary appears in any status string.
- [ ] `StatusCallback` signature and telemetry contract are unchanged.
- [ ] `tests/unit/test_agent_status.py` and `tests/unit/test_cli_chat.py`
      pass against the new formatted strings.
