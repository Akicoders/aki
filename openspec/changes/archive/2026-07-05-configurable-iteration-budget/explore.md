# Explore: configurable-iteration-budget

## Complaint

User ran a real scaffolding request ("necesitamos ya poder tener el astro
hecho") that needed multiple file reads/writes/exists checks. The turn hit
the iteration budget after only 5 iterations (but 12 tool calls — see
mechanic below) and returned an exhaustion message with no final answer.
User wants the budget raised and configurable, explicitly NOT unlimited.

## 1. Where `max_iterations` lives today

It is **already configurable**, contrary to the initial "hardcoded" framing
— the value that's actually fixed is the *default*, not the mechanism:

- `src/agentos/core/config.py:149-154` — `AgentConfig` is a
  `pydantic_settings.BaseSettings` subclass with
  `model_config = SettingsConfigDict(env_prefix="AGENT_")` and
  `max_iterations: int = 5`. Because it's a `BaseSettings` model, it already
  reads `AGENT_MAX_ITERATIONS` from the environment (and from `.env`, via
  `load_runtime_env`, `config.py:54-61`) — nobody wired that up explicitly,
  it's pydantic-settings' default env-binding behavior for any field on a
  `BaseSettings` subclass with `env_prefix` set. **This was not verified in
  a live run in this exploration** (no test exercised `AGENT_MAX_ITERATIONS`
  directly) but is consistent with every other `*Config` class in the file
  (`QwenConfig` env_prefix `QWEN_`, `MemoryConfig` env_prefix `MEMORY_`,
  etc. — same pattern, same library, same mechanism).
- `src/agentos/agents/profiles.py:56` — `AgentProfile.max_iterations:
  int | None = None`. Per-profile override, already exists, already used:
  `docs/agent-profiles.md:25` shows a worker profile with
  `max_iterations: 3`.
- `src/agentos/agent/core.py:398-402` — precedence at read time:
  `profile.max_iterations if profile and profile.max_iterations is not None
  else self.config.max_iterations`. Profile override wins when present,
  else falls back to the global `AgentConfig.max_iterations` default (5).

So the real gap is: **the shipped default is 5, and there is no documented
way for a user to know `AGENT_MAX_ITERATIONS` exists.** The "hardcoded"
complaint is really "undiscoverable + too low," not "not configurable."

## 2. `_reasoning_loop` mechanics (`src/agentos/agent/core.py:380-528`)

- Loop bound: `for iteration in range(max_iterations)` (line 413) — one
  iteration = one round-trip to the model (`self.qwen.chat(...)`, line 421).
- **Multiple tool calls per iteration confirmed.** Line 445:
  `total_tools_in_response = len(response.tool_calls)`, then line 446 loops
  `for tool_ordinal, tool_call in enumerate(response.tool_calls, start=1)`
  and executes each one before looping back to the model. This is exactly
  why the user's failed run logged 12 tool calls across only 5 iterations:
  the model was batching multiple tool calls (e.g. several `fs.exists` /
  `fs.read` checks) inside single iterations, and the *iteration* count,
  not the *tool-call* count, is what's bounded.
- Exhaustion path: if the loop runs `max_iterations` times without the
  model returning a response with no `tool_calls`, it falls through to
  lines 523-528, calling `_format_exhaustion_message` (lines 644-660):
  `f"The turn reached the {max_iterations}-iteration budget. No final
  answer was produced. Last attempted: {last_attempted}. Tool calls
  completed: {total_tool_calls}; recent safe tool names: {recent_str}."`
  — this exact string format is stable and already covered by
  `agent-runtime-telemetry` (see section 5).
- Early-exit paths that return before exhaustion and do NOT consume the
  full budget: no tool calls in response (line 437-442, success),
  profile tool-policy denial (line 468-474), destructive-tool
  under-specified gate (line 476-484, see `agent-scaffolding-clarification`
  below).

## 3. Sensible new default

Given the user's own failed run needed >12 tool calls across 5 iterations
for a routine scaffold task (several `fs.exists`/`fs.read`/`fs.write` calls
per iteration is normal for multi-file project init), and the explicit
rejection of "unlimited": a **default of 20** iterations is proposed.

Reasoning:
- 5 → 20 is 4x headroom, matching the ratio observed between iterations (5)
  and tool calls (12) in the failed run scaled up with margin for a still
  harder task (more scaffolding steps, retries after tool errors).
- Not unlimited: still bounded, still surfaces the same honest exhaustion
  message if something loops pathologically (e.g. destructive-clarification
  ping-pong, see section 5) — a runaway task fails loud within a bounded
  number of model round-trips instead of an unbounded API-cost/time sink.
- No competing guidance found in-repo: `docs/agent-profiles.md` only shows
  a *lower* override (worker profile at 3, intentionally tighter than the
  supervisor default) — no doc anywhere argues for a specific supervisor
  default, so this is a judgment call to make explicitly in the proposal
  phase, not a value discovered in existing docs.
- Left as an open question for `/sdd-propose`: whether 20 is the right
  number for cost/latency reasons (20 iterations × up-to-N tool calls per
  iteration × model round-trip latency could be a meaningfully longer worst
  case turn than today's 5) — flag this tradeoff explicitly rather than
  bake in 20 as final.

## 4. Configuration mechanism

No new mechanism is required — the existing pydantic-settings env-binding
already works. The proposal should:

- Keep `AGENT_MAX_ITERATIONS` (implied by `env_prefix="AGENT_"` +
  field name `max_iterations`) as the env var name — this is not a new
  var, it already works today, it's just undocumented.
- Change the default in `src/agentos/core/config.py:152` from `5` to the
  agreed new value (proposed: 20).
- Keep the existing precedence order as-is (`core.py:398-402`):
  1. `profile.max_iterations` (per-specialized-agent-profile override, YAML
     config under `agent_profiles`, e.g. `docs/agent-profiles.md:25`)
  2. `AgentConfig.max_iterations` (global default, settable via
     `AGENT_MAX_ITERATIONS` env var or `.env`)
  3. Pydantic field default (proposed: 20, was: 5)
- Documentation gap to close in the proposal/design phase: neither
  `docs/agent-profiles.md` nor any README documents `AGENT_MAX_ITERATIONS`
  as a user-facing knob — add it so users don't have to read
  `config.py` to discover it exists.

## 5. Interaction with archived changes

- **`agent-runtime-telemetry`**
  (`openspec/changes/archive/2026-07-03-agent-runtime-telemetry/`): the
  exhaustion message format and `iterations_exhausted` flag
  (`core.py:284`, `outcome.exhausted`) are already telemetry surfaces.
  Raising the default does not change the message format, the flag
  semantics, or the field names — it only changes how often the exhaustion
  path is hit (less often, for equally-complex tasks). No changes needed
  to telemetry code; verify in `/sdd-verify` that no test hardcodes the
  literal "5" in an exhaustion-message assertion (would need updating to
  match the new default, not a behavior break).
- **`agent-scaffolding-clarification`**
  (`openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/`):
  the destructive-tool gate (`core.py:476-484`, `_is_under_specified`) exits
  the loop immediately with a clarifying question rather than consuming
  iterations in a loop — so raising the budget does NOT fix a bad
  clarification loop by itself, as the user's own framing anticipated. It
  does give more room for the *user's follow-up* turn (a fresh call to
  `_reasoning_loop`, iterations reset) to complete after the clarification
  round-trip, since each user turn gets its own fresh `max_iterations`
  budget — the gate returns immediately (line 481), it does not recurse or
  retry internally.
- **`multi-agent-orchestration`**
  (`openspec/changes/archive/2026-07-04-multi-agent-orchestration/`): a
  worker's nested loop is a **separate, independently-configured** call to
  `_reasoning_loop` (`core.py:572-580`, `depth=1`). It resolves its own
  `max_iterations` via the *worker's own profile* (`profile=worker_profile`
  at line 578, read at line 398-402 against `worker_profile.max_iterations`
  first, falling back to the same global `AgentConfig.max_iterations` if
  the worker profile doesn't set one). Concretely: the supervisor (depth=0)
  and each delegated worker (depth=1) each get their own budget from the
  same precedence rule, evaluated independently. Raising the global default
  raises it for BOTH the supervisor and any worker that doesn't set its own
  `max_iterations` override (e.g. the example worker profile at
  `docs/agent-profiles.md:25` explicitly overrides to 3 and would be
  unaffected by a global default change). No structural change needed here;
  just note in the proposal that a higher global default compounds across
  delegation (supervisor budget + each worker's budget are independent
  pools, not shared), which is relevant to worst-case latency/cost
  estimates for a delegated turn.

## Open questions for `/sdd-propose`

1. Confirm final default value (20 proposed) — cost/latency tradeoff not
   fully modeled here.
2. Should the proposal also add an explicit doc section for
   `AGENT_MAX_ITERATIONS` in `docs/agent-profiles.md` or a new
   `docs/configuration.md`?
3. Should there be an upper sanity bound/validator on `max_iterations`
   (e.g. pydantic `Field(gt=0, le=100)`) to guard against a user setting an
   effectively-unlimited value by mistake via env var? Currently
   `max_iterations: int = 5` has no bounds.
