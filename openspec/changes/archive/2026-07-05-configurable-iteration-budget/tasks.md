# Tasks: Configurable Iteration Budget

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 40-70 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a |

Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Low

Three small, low-risk edits: one `Field` default/bound change on a single
line of `src/agentos/core/config.py:152`, a new README documentation block,
and a handful of unit-level regression tests. No new files beyond tests, no
new mechanism, no behavior change to precedence or worker/supervisor pool
independence. Comfortably under the 400-line budget; a single PR is
appropriate — no design.md needed for this change (config default + bound +
docs, no architectural decision left unresolved).

## Phase 1: Default, Ceiling, and Env Override

- [x] 1.1 RED: In a new or existing `tests/unit/test_config.py`, add/update
      unit tests asserting: (a) `AgentConfig()` constructed with no
      `AGENT_MAX_ITERATIONS` set resolves `max_iterations == 20`; (b) with
      `AGENT_MAX_ITERATIONS=10` set, `max_iterations == 10`. Run to confirm
      RED (current default is `5`, so test (a) fails against the new
      expectation).
- [x] 1.2 GREEN: In `src/agentos/core/config.py:152`, change the
      `max_iterations` field default from `5` to `20`. Run 1.1 to confirm
      GREEN.
- [x] 1.3 RED: In `tests/unit/test_config.py`, add unit tests asserting:
      (a) `AGENT_MAX_ITERATIONS=150` raises a pydantic validation error on
      `AgentConfig()` construction; (b) `AGENT_MAX_ITERATIONS=0` raises a
      pydantic validation error. Run to confirm RED (no bound exists yet,
      both values currently construct successfully).
- [x] 1.4 GREEN: In `src/agentos/core/config.py:152`, constrain the
      `max_iterations` field with `Field(gt=0, le=100)` (or equivalent
      pydantic constraint) alongside the new default. Run 1.3 to confirm
      GREEN.

## Phase 2: Regression Guards (Precedence and Pool Independence)

- [x] 2.1 Audit existing tests for a hardcoded literal `5` in any
      `max_iterations` / exhaustion-message / budget assertion (per
      proposal's called-out risk). Grep
      `tests/` for `max_iterations` and iteration-count literals tied to the
      old default. Update any found assertions to the new default (`20`) —
      this is a value update, not a behavior change. If none found, record
      that explicitly in the apply-progress notes.
- [x] 2.2 RED/GREEN as needed: Confirm (add a regression test if none
      exists) that a profile-level `max_iterations` override still wins
      over the new global default at `core.py:398-402` — e.g. profile sets
      `max_iterations=3`, effective resolved budget for that profile is `3`,
      not `20`. This proves Out-of-Scope item "no change to precedence"
      holds after the default bump.
- [x] 2.3 RED/GREEN as needed: Confirm (add a regression test if none
      exists) that a depth=1 worker's iteration pool
      (`core.py:572-580`) still resolves and tracks independently from the
      depth=0 supervisor's pool after the default bump — no shared or
      combined counter.

## Phase 3: Documentation and Final Verification

- [x] 3.1 In `README.md`'s existing `## Configuration` section
      (README.md:134), add an "Agent behaviour" env-var block documenting
      `AGENT_MAX_ITERATIONS` alongside the existing Qwen/Memory blocks:
      default `20`, ceiling `100`, and a one-line explanation that one
      iteration equals one model round-trip and higher values allow more
      tool-heavy tasks.
- [x] 3.2 Full verification pass: run the full unit test suite plus
      `tests/unit/test_config.py` explicitly; run `ruff check .` and
      `mypy src/agentos`. Confirm:
      - No test hardcodes the old literal default (`5`) in a passing
        assertion.
      - `_format_exhaustion_message` and `iterations_exhausted` /
        `outcome.exhausted` telemetry contracts are byte-for-byte
        unchanged (diff confirms zero lines touched there).
      - README `## Configuration` section renders the new block correctly
        (visual/diff check, no markdown lint errors).
