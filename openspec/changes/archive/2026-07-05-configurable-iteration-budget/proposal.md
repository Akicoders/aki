# Proposal: Configurable Iteration Budget (Raise Default, Document Env Var, Add Ceiling)

## Intent

A real user scaffolding request — "necesitamos ya poder tener el astro hecho" —
hit the agent's iteration budget and returned an exhaustion message with **no
final answer**. The turn logged 12 tool calls but exhausted after only 5
iterations, because one iteration is one model round-trip and the model batches
multiple tool calls (`fs.exists` / `fs.read` / `fs.write`) inside a single
iteration (`src/agentos/agent/core.py:445-446`). Five iterations is simply too
low for routine multi-file scaffolding.

Exploration established that `max_iterations` is **already configurable**,
contrary to the initial "hardcoded" framing. It lives on
`AgentConfig(BaseSettings, env_prefix="AGENT_")` at
`src/agentos/core/config.py:152`, so `AGENT_MAX_ITERATIONS` already binds from
the environment and `.env` via pydantic-settings — nobody wired it explicitly,
it is the same env-binding every other `*Config` in the file relies on. The
real gap is therefore **"undiscoverable + too low," not "not configurable"**:
the shipped default (5) is too small, and no README or doc tells a user the
env var exists.

The user confirmed direction: raise the default to a much higher, still
**bounded** number — explicitly **NOT unlimited**.

## Scope

### In Scope
- **Bump the default from 5 to 20** in `src/agentos/core/config.py:152`
  (`max_iterations: int = 5` → the new default). 20 is 4x headroom, matching
  the observed 5-iteration / 12-tool-call ratio from the failed run scaled up
  with margin for a harder task and tool-error retries. Still bounded: a
  pathological loop fails loud with the same honest exhaustion message within a
  finite number of model round-trips instead of becoming an unbounded cost/time
  sink.
- **Add an upper-bound validator** on `max_iterations`. Today the field has no
  bounds, so a typo in `AGENT_MAX_ITERATIONS` (e.g. `10000`) silently creates
  an effectively-unlimited budget — exactly the runaway the user rejected.
  Constrain it with a pydantic `Field(gt=0, le=100)`: reject non-positive
  values and anything above a ceiling of **100**. This keeps "configurable,
  high default" honest while making accidental runaway config a startup error,
  not a surprise API bill.
- **Document `AGENT_MAX_ITERATIONS`** in the README's existing `## Configuration`
  section (README.md:134), alongside the Qwen and Memory env-var blocks — an
  "Agent behaviour" block showing `AGENT_MAX_ITERATIONS=20` with a one-line
  explanation (one iteration = one model round-trip; higher allows more
  tool-heavy tasks; capped at 100).

### Out of Scope
- **No unlimited / no-cap option.** Explicitly rejected by the user. The whole
  point of the ceiling validator is to keep the budget bounded.
- **No "detect no progress and stop early" heuristic.** Stopping a stalled turn
  before the budget is exhausted is a different, more complex feature (progress
  detection) — not this change. This change only moves and bounds a number.
- **No change to per-profile override precedence.** The resolution order at
  `core.py:398-402` (profile `max_iterations` wins, else global default) stays
  exactly as-is. A worker profile that sets `max_iterations: 3`
  (`docs/agent-profiles.md:25`) is unaffected by the new global default.
- **No change to worker/supervisor iteration-pool independence.** The nested
  worker loop (`core.py:572-580`, depth=1) keeps resolving its own budget
  independently from `multi-agent-orchestration`. We only note the cost
  implication (see below); we do not alter the pools.
- **No telemetry-contract change.** The exhaustion message format
  (`_format_exhaustion_message`) and the `iterations_exhausted` /
  `outcome.exhausted` flags from `agent-runtime-telemetry` are untouched; only
  how often the exhaustion path is reached changes (less often for equally
  complex tasks).

## Capabilities

### New Capabilities
- `configurable-iteration-budget`: a documented, bounded, environment-tunable
  reasoning-iteration budget with a sensible high default (20) and a hard
  ceiling (100).

### Modified Capabilities
- None. Precedence, telemetry, and multi-agent contracts are unchanged.

## Approach

Three small, low-risk edits: change one literal default, add a bounded `Field`
on the same line's field, and add a documentation block to an existing README
section. No new configuration mechanism is introduced — the env var already
works; this change makes it correct-by-default, safe against runaway values,
and discoverable.

## Decisions (made autonomously — small, low-risk change)

The exploration's three open questions are resolved here with the most
conservative choice:

- **Final default value → 20.** No in-repo doc argues for a specific supervisor
  default; the only existing guidance is a *lower* worker override (3). 20 is
  the explored recommendation and directly clears the failed run's observed
  need. Cost/latency tradeoff acknowledged (worst-case turn is longer than at
  5), but bounded by the ceiling and still far from unlimited.
- **Documentation location → README `## Configuration`.** A Configuration
  section already exists (README.md:134) with per-subsystem env-var blocks;
  adding an agent block there is the least-surprise choice, no new file needed.
- **Upper-bound validator → yes, ceiling 100.** `Field(gt=0, le=100)`. The
  field has no bounds today; a ceiling turns an accidental effectively-unlimited
  value into an immediate, legible config error, which is squarely the user's
  stated intent (bounded, not unlimited).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/agentos/core/config.py` | Modified | `max_iterations` default 5 → 20; add `Field(gt=0, le=100)` bound. |
| `README.md` | Modified | Add `AGENT_MAX_ITERATIONS` to the `## Configuration` section. |
| `tests/` | Modified (verify) | Confirm no test hardcodes literal `5` in an exhaustion-message / budget assertion; add coverage for the new default and the ceiling validator. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Longer worst-case turn latency/cost at 20 vs 5 | Med | Bounded by the 100 ceiling; per-profile and env override let cost-sensitive setups lower it. |
| Higher global default compounds across delegation (supervisor + each worker each get their own pool) | Med | Documented explicitly; worker profiles that set their own `max_iterations` are unaffected; env var can lower the global default. |
| A test hardcodes the old default (5) in an exhaustion assertion | Low | Called out for `/sdd-verify`; update to the new default — a value change, not a behavior break. |
| Ceiling validator rejects a previously-accepted large env value at startup | Low | Intentional — that is the runaway config the user asked to prevent; error message names the ceiling. |

## Rollback Plan

Revert the `config.py` default to `5`, drop the `Field` bound, and remove the
README block. No data, checkpoint, or contract migration is involved.

## Dependencies

- Existing pydantic-settings env-binding on `AgentConfig` (`env_prefix="AGENT_"`).
- Existing precedence resolution at `core.py:398-402` (unchanged).
- Archived `agent-runtime-telemetry`, `agent-scaffolding-clarification`, and
  `multi-agent-orchestration` specs remain unchanged adjacent constraints.

## Success Criteria

- [ ] Default `max_iterations` is 20 with no env var set.
- [ ] `AGENT_MAX_ITERATIONS` overrides the default (already works; add coverage).
- [ ] Configuring `max_iterations` above 100 (or ≤ 0) is rejected at load time.
- [ ] `AGENT_MAX_ITERATIONS` is documented in the README `## Configuration` section.
- [ ] Per-profile override precedence and worker/supervisor pool independence
      are unchanged.
- [ ] Telemetry exhaustion message/flag contracts are unchanged.
