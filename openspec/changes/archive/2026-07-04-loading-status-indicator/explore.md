# Explore: loading-status-indicator

## User ask (translated)

"I want a loading animation, or something that tells me what it's doing and
which tools it's using while I wait for the response."

## What already exists today

### 1. `StatusCallback` contract (`src/agentos/agent/core.py:46`)

```python
StatusCallback = Callable[[str], None]
```

Invoked via `_notify_status(status_callback, message)` (`core.py:58-60`). Call
sites inside `chat()` (`core.py:190-281`):

- `"Starting turn"` — `core.py:204`
- `"Collecting project context"` — `core.py:219`
- `"Saving conversation"` — `core.py:253`
- `"Turn exhausted"` / `"Turn complete"` — `core.py:280`

Call sites inside `_reasoning_loop()` (`core.py:372` onward):

- `_format_iteration_status(i, max_iterations)` → `"Reasoning iteration i/n"`
  (`core.py:63-64`)
- `_format_final_iteration_status(...)` → final-iteration warning
  (`core.py:67-68`)
- `_format_tool_status(ordinal, total, safe_tool_name)` →
  `"Running tool k/m: skill.function"` (`core.py:71-72`, emitted at
  `core.py:485-488` right before `self.skills.execute(...)` at `core.py:490`)

So **the callback already reports the specific tool name and ordinal** for
every tool call, plus iteration progress and turn-level phases. This is a
richer signal than the user's ask assumes is missing — the plumbing is not
the gap.

### 2. CLI wiring — both `chat` and `interactive` already use it

Contrary to the task brief's hypothesis, `_async_interactive` **does** wire
`status_callback`. Checked directly:

- One-shot `chat` command (`main.py:163-193`): wraps the turn in
  `console.status(_format_status("Collecting project context"))`, defines
  `update_status(message)` that calls `status.update(_format_status(message))`,
  passes `status_callback=update_status` into `agent.stream_chat(...)` /
  `agent.chat(...)`.
- `_async_interactive` (`main.py:788-819`, confirmed via codegraph call-path
  trace `_async_interactive → chat → _reasoning_loop`): identical pattern —
  `with console.status(_format_status("Starting turn")) as status:` at
  `main.py:802`, `update_status` closure at `main.py:803-804`, passed as
  `status_callback=update_status` into `agent.chat(...)` at `main.py:810`.

`_format_status` (`main.py:77-78`) just wraps text in
`[bold cyan]{message}...[/bold cyan]` — Rich markup, no separate glyph/spinner
config.

**Rich components in use**: only `console.status(...)` (a `rich.console.Console.status`
context manager, which itself renders a built-in spinner + the message text).
Checked imports (`main.py:15-19`): `Console`, `Markdown`, `Panel`, `Prompt`,
`Table` — **no `rich.progress.Progress` or `rich.live.Live` imported**
anywhere in `main.py` (`rg` for `Progress|Live\(` returned nothing).

`console.status(...)` already renders an animated spinner (Rich's default
"dots" spinner) next to the message and updates it live via `status.update(...)`
— so a genuine per-tool-call animated indicator already exists in both paths
today, not just static text.

### 3. So what's actually missing?

Given the above, the real gaps are narrower than the brief assumed:

- **Nothing structurally missing between `chat` and `interactive`** — both
  wire the identical `console.status` + `update_status` pattern. This removes
  candidate (a)'s main premise (wiring `interactive`) as already done.
- **Depth/latency between status updates**: `_format_tool_status` fires once
  per tool call, but if a single tool call itself takes a long time (e.g. a
  slow skill), there is no finer-grained progress — this is unavoidable
  without instrumenting individual skills and is out of scope for a
  today-shippable slice.
- **Multi-agent delegation status is unlabeled by design.** Per
  `openspec/specs/agent-runtime-telemetry/spec.md` (Single-Agent Scope
  Boundary requirement, lines 72-81) and
  `openspec/specs/multi-agent-orchestration/spec.md` (Requirement: Telemetry
  Contract Untouched in Phase 1, lines 230-255): status text MUST NOT
  distinguish supervisor vs. worker, and the worker's nested loop **reuses
  the same `status_callback` instance** with no `run_id`/`parent_run_id`.
  This is an explicit, tested contract from the just-archived
  `multi-agent-orchestration` change — **do not add worker/supervisor
  labeling to status text**; doing so would directly violate a shipped spec
  scenario ("Status copy avoids orchestration language").
- **Visual polish**: the spinner exists, but it's the same undifferentiated
  cyan dots spinner for every phase (context collection, iteration, tool
  execution, saving). There's no visual distinction between "thinking"
  (waiting on the model) vs. "using tool X" — currently both are just text
  changes on the same spinner. A user glancing at the terminal sees animation
  either way, but has to actually read the text to know if a tool is running.

## Candidate approaches

### (a) Enrich message text only — no new Rich components

Keep `console.status(...)` exactly as-is in both commands; only change is
richer text via existing `_format_status` / `_format_tool_status`, e.g. bold
the tool name distinctly or add an emoji/icon per phase type (thinking vs.
tool vs. saving).

- **Pros**: zero new surface area, touches only string formatting, cannot
  break the multi-agent contract (still generic `_notify_status` calls, no
  new callback shape), trivially testable (string assertions already exist
  in `tests/unit/test_agent_status.py`, `tests/unit/test_cli_chat.py`).
- **Cons**: doesn't add anything users don't already have — `_format_tool_status`
  already names the tool. Risks being a no-op relative to the actual ask.

### (b) Rich `Progress`/`Live` component for a genuinely richer live view

Replace `console.status(...)` with a `rich.progress.Progress` or
`rich.live.Live` panel that keeps a running list of completed steps (e.g.
"✓ iteration 1", "✓ tool: memory.search", "→ tool: git_ops.status (running)")
visible simultaneously, not just the latest line.

- **Pros**: closest to "tell me what it's doing" in a rich, glanceable way;
  reuses the same `StatusCallback` signature (`Callable[[str], None]`) — the
  `agent/core.py` side needs zero changes, only the CLI-side callback
  implementation changes from `status.update(...)` to appending to a
  `Progress`/`Live` renderable.
- **Cons**: `Live`/`Progress` context managers do not nest cleanly with
  `console.print(...)` calls happening elsewhere in the same command (e.g.
  the final `console.print(Markdown(...))`), and interactive mode prints
  `console.print("[dim]Interrupted[/dim]")` on `KeyboardInterrupt` inside the
  same loop — needs care to stop/exit the `Live` region cleanly before
  printing, otherwise output can visually corrupt. More surface to test
  (new Rich component wiring in both `chat` and `_async_interactive`), higher
  risk of a same-day regression in the two commands' existing passing tests
  (`tests/unit/test_cli_chat.py`).

### (c) Minimal — print each status line as it happens, no animation

Drop `console.status(...)` entirely; just `console.print(f"[dim]{message}...[/dim]")`
once per callback invocation.

- **Pros**: simplest possible change, no Rich component risk at all.
- **Cons**: regresses today's UX — currently there IS an animated spinner
  (`console.status` renders one). Switching to flat prints would be a
  downgrade, not an improvement, and contradicts the "loading animation" part
  of the ask.

## Recommendation

**(a), scoped narrowly to visually differentiating phase types within the
existing `console.status` spinner text**, given this is meant to ship today.

Rationale:

- The foundation (animated spinner + specific-tool-name reporting, in BOTH
  `chat` and `interactive`) already fully satisfies the literal ask — "tells
  me what it's doing and which tools it's using" is already true today. The
  actual, real gap is closer to "make it more visually obvious/readable,"
  not "build the plumbing."
- Zero risk to the `agent-runtime-telemetry` spec's safety/scope contract
  (tool name/count only, no worker vocabulary) since no new data crosses the
  `StatusCallback` boundary — only how `_format_status`/CLI-side rendering
  presents already-safe strings.
- Zero risk to the `multi-agent-orchestration` spec's telemetry-untouched
  guarantee, since worker delegation reuses the identical callback and no
  new distinguishing field is introduced.
- (b) is the "more correct" long-term answer (a persistent step list reads
  better than a single replaced line) but carries real same-day regression
  risk against two already-passing CLI test files for a same-day ship, and
  should be proposed as a fast-follow once (a) is confirmed to under-deliver
  on user expectations in practice.

If the user pushes back that (a) doesn't feel like enough of a change
(since the underlying signal already existed), that pushback itself is the
signal to escalate straight to (b) in the actual proposal phase — but the
explore-phase recommendation for a same-day ship is (a).
