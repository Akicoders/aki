# Verify Report: agent-scaffolding-clarification

## Verdict: PASS (with one WARNING to track, not blocking archive)

Implementation matches spec and design across all 4 phases. Full suite run
independently: 317 collected, 316 passed, 1 failed, 0 errors. The 1 failure
is confirmed pre-existing and unrelated (see below). Reported counts (237
baseline / 307 after / 70 new) differ slightly from what I observe (317
total) because two other uncommitted, unrelated changes are also present in
the working tree (`session-list-and-help` change: `test_cli_sessions_and_help.py`,
`test_list_sessions_repository.py`, and a `main.py`/`repository.py` diff) —
these add tests outside this change's scope and explain the delta. Not a
regression caused by this change.

## Spec-scenario verification

- **Destructive tool metadata** (`base.py:39,110-112,125`, `filesystem.py:17`):
  `Skill.destructive_functions` frozenset default empty, `is_destructive`
  correct; `FilesystemSkill.destructive_functions = {"write","append","delete"}`;
  `SkillRegistry.is_destructive` (`base.py:160-163`) returns `False` safely for
  unknown skill/fn. `get_openai_tool` embeds `"destructive": self.is_destructive(fn_name)`
  (`base.py:125`) — verified test coverage in `test_skill_destructive_metadata.py`
  (8 tests) matches all three spec scenarios (write/append/delete = true, reads
  = false, other skills default false).

- **Generic-content heuristic is exact-match, not substring** (`core.py:62-74`):
  confirmed — `str(content).strip().lower() in GENERIC_CONTENT_PLACEHOLDERS` is
  a set membership check (exact match after normalize), not `in` as substring
  search on a string. `test_agent_gate_helpers.py:39-42`
  (`test_is_under_specified_real_short_content_not_gated`) proves the
  anti-false-positive case (`"port=8080"`, `"export default App"` not gated) —
  this only works because the check is exact-match; a substring check would
  false-positive on any content containing "content" as a fragment.

- **Gate fires independent of prompt-branch match** (ADR-4): found and
  inspected `test_reasoning_loop_gate_fires_without_scaffolding_keyword`
  (`test_agent_destructive_gate.py:134-154`). It never calls `_build_messages`
  at all — it drives `_reasoning_loop` directly with a scripted tool call —
  so it correctly demonstrates the gate (`core.py:322-329`) is wired at the
  tool-call layer and has zero dependency on the prompt addendum branch in
  `_build_messages` having run or matched. Structurally sound proof of
  independence.

- **Batch-ordering scenario** (`test_agent_destructive_gate.py:157-185`,
  `test_reasoning_loop_batch_nondestructive_before_gated_destructive`):
  confirmed a non-destructive `filesystem_read` executes
  (`skills.execute.assert_called_once_with("filesystem", "read", ...)`)
  before the loop hits the under-specified `filesystem_write` and
  short-circuits. Matches the accepted design tradeoff (design §4a) exactly.

- **Scaffolding keyword branch mirrors SDD-keyword branch** (`core.py:242-263`):
  confirmed structurally identical — same `any(kw in user_input.lower() for
  kw in KEYWORDS)` pattern, same system-message-append shape, placed
  immediately after the SDD branch and before the user message is appended.
  Bilingual keyword set (`core.py:34-43`) covers both English and Spanish;
  `test_build_messages_scaffolding.py` (3 tests) covers Spanish match,
  no-match, and English match.

## MagicMock deviation — verified legitimate, not weakening

Diffed `tests/unit/test_agent_exhaustion.py` and `test_reasoning_outcome.py`.
Both pre-existing tests build a bare `skills = MagicMock()` around
non-destructive tool-call scenarios (`filesystem_read`/generic reads). Before
this change, `is_destructive` didn't exist, so the mock's default truthy
attribute access was harmless. After adding the gate
(`skills.is_destructive(...) and _is_under_specified(...)`), the bare mock's
`is_destructive` call returns a truthy `MagicMock` instance, which would make
the gate fire unconditionally and break these tests for a reason unrelated
to what they actually test (tool-call execution flow / exhaustion behavior).
The fix — `skills.is_destructive = MagicMock(return_value=False)` — only
restores the pre-change behavior (non-destructive path) explicitly; no
assertions were touched, weakened, or removed in either file. Confirmed
legitimate.

## Pre-existing failure — confirmed unrelated

`tests/unit/test_cli_update.py::TestUpdateCommand::test_update_runs_git_pull_and_uv_sync_in_source_dir`
fails because it asserts the exact argv passed to `uv tool install`. The
working tree has an uncommitted, unrelated edit to `src/agentos/cli/main.py`
(`--all-extras` flag added to the `uv tool install` call, plus an unrelated
`_show_help` signature change for session-list-and-help) that the test
wasn't updated for. Confirmed via `git diff -- src/agentos/cli/main.py`: this
touches only the `update()` command and `_show_help`/`/sessions` help text —
nothing in the destructive-gate or scaffolding-prompt code paths. Unrelated
to this change.

## WARNING: destructive key on the live wire path is unverified

Design flagged (§3b) that the extra `"destructive"` key on `get_openai_tool()`'s
output might need a fallback if the OpenAI-compat API rejects unknown fields,
and made task 1.4's smoke check explicitly non-blocking. I verified via two
independent checks:

- `AgentOS.chat()` → `self.skills.get_all_tools()` (`core.py:156`) → each
  skill's `get_openai_tool()` (embeds `destructive` at `base.py:125`) → this
  list is passed directly as `tools=` to `QwenClient.chat()`
  (`client.py:81-88`), which forwards it unmodified to
  `AsyncOpenAI().chat.completions.create(tools=tools, ...)`. This is the real
  production path (not the separate, apparently-dead `build_tools_schema` in
  `client.py:199-211`, which uses `get_function_schema` and never includes
  `destructive` — that path is unused by `chat()`).
- No test in the suite exercises `get_all_tools()`'s output against a real or
  mocked `AsyncOpenAI`/`chat.completions.create` call to confirm the extra
  key is tolerated. `test_skill_destructive_metadata.py` only checks the flag
  is present/absent correctly in the dict — it never asserts wire compatibility.

This means task 1.4's "smoke check" checkbox is unverified in practice — no
artifact proves Qwen's endpoint accepts the extra field. Per design this is
explicitly non-blocking (fallback: move under `parameters` or drop from wire
if it turns out to reject), so this is a WARNING, not a CRITICAL — but it
should be tracked as a follow-up before relying on this in a live session
against the real API, since most OpenAI-compatible providers ignore unknown
fields but this is unconfirmed here.

## Suggestions

- Add a lightweight test (mock `AsyncOpenAI.chat.completions.create`, assert
  it's called without raising when passed a `tools` list containing the
  `destructive` key) to close the gap on the WARNING above.
- Consider removing or documenting the apparently-dead `build_tools_schema`
  method in `client.py:199-211`, since it duplicates `get_all_tools()`'s
  purpose via a different, now-inconsistent code path (no `destructive` key,
  uses `get_function_schema` directly).

## Summary

| Check | Result |
|---|---|
| Destructive metadata (Phase 1) | PASS |
| Pure gate helpers, exact-match heuristic (Phase 2) | PASS |
| Gate wiring + independence + batch-ordering (Phase 3) | PASS |
| Scaffolding prompt addendum (Phase 4) | PASS |
| MagicMock test-fixture fix | PASS (legitimate) |
| Full suite | 316/317 passing, 1 pre-existing unrelated failure confirmed |
| destructive key wire compatibility | WARNING — unverified, non-blocking per design |

**Ready for sdd-archive**: Yes. No CRITICAL findings. The one WARNING is
explicitly scoped as non-blocking by the change's own design and does not
affect correctness of the implemented behavior — recommend tracking as a
fast follow-up rather than gating archive on it.
