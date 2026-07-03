# Archive Report: Agent Scaffolding Clarification

## Change Summary

**agent-scaffolding-clarification** adds two safeguards to Aki's reasoning loop to prevent premature destructive filesystem operations during scaffolding requests. Aki now detects scaffolding intent and, when structural details are missing, asks for clarification before writing/deleting/appending files.

1. **Scaffolding-Intent Prompt Addendum** — new system-message branch in `_build_messages` that detects phrases like "create", "crear", "generate", "set up", "scaffold", and injects an instruction to prefer clarification over immediate writes when details are missing.
2. **Destructive-Tool Tagging & Gate** — `Skill` metadata now tracks `destructive: bool` (default False). `FilesystemSkill.write`, `.delete`, `.append` are tagged destructive. The reasoning loop intercepts destructive calls with incomplete args (`path` missing/empty or `content` generic/empty) and returns a clarifying question instead of executing.

## Scope

### In Scope
- `src/agentos/agent/core.py`: scaffolding-keyword branch in `_build_messages` + destructive-call gate in `_reasoning_loop`
- `src/agentos/skills/base.py`: `destructive: bool` metadata on `Skill`; expose in `get_all_tools()` schema
- `src/agentos/skills/filesystem.py`: tag write/delete/append as destructive
- Full test coverage (Phase 1–4 scenarios + MagicMock fixture adjustments)

### Out of Scope (per design)
- Full `tool_choice="none"` structural clarification (deferred)
- LLM-based intent classification (keyword/heuristic-based this cycle)
- `config.py` tuning; iteration-budget changes deferred
- Interactive CLI confirmation prompt (gate returns clarifying question as response, next-turn rehydration)

## Verification

**Verdict: PASS** (all spec scenarios satisfied, 316/317 tests passing, 1 pre-existing unrelated failure confirmed)

- ✓ Destructive metadata (Phase 1): `Skill.destructive_functions` frozenset, `is_destructive` query method, `get_openai_tool` embeds flag
- ✓ Generic-content heuristic (Phase 2): exact-match-after-strip, not substring; false-positives ruled out
- ✓ Gate wiring + independence + batch-ordering (Phase 3): gate fires independently of prompt-branch success
- ✓ Scaffolding prompt addendum (Phase 4): bilingual keyword set, system-message append structure mirrors SDD-keyword branch
- ✓ MagicMock test-fixture fixes (legitimate; restore pre-change behavior on non-destructive path)

### Known Limitation — WARNING (non-blocking per design)

The extra `"destructive"` key on the wire path (passed to Qwen's OpenAI-compatible endpoint) was not verified against a real or fully-mocked `AsyncOpenAI.chat.completions.create` call. No test exercises `get_all_tools()`'s output through the actual chat completion endpoint. Per design this is explicitly non-blocking (fallback: move under `parameters` or drop from wire if rejected), but recommend verifying with the live Qwen endpoint as a fast-follow before relying on this in production.

## Tasks Completed

All 18 tasks from `tasks.md` marked complete and implemented:
- Metadata infrastructure (Skill.destructive_functions, is_destructive, get_all_tools integration)
- Scaffolding-keyword detection + system-message injection
- Generic-content detection (exact-match heuristic with placeholder set)
- Destructive-call gate in reasoning loop (before execute, returns clarifying question)
- Full test coverage: Phase 1–4 scenarios, MagicMock adjustments, edge cases

## Files Modified

| File | Change | Purpose |
|------|--------|---------|
| `src/agentos/agent/core.py` | Scaffolding branch + gate | Scaffolding detection, destructive-call interception |
| `src/agentos/skills/base.py` | Metadata + query method | Destructive flag infrastructure |
| `src/agentos/skills/filesystem.py` | Tag write/delete/append | Mark dangerous ops |
| Test files (multiple) | Full coverage | 4 phases, gate scenarios, edge cases |

## Rollback Plan

Fully additive and defensive. To revert:
1. Remove scaffolding-keyword branch from `_build_messages`
2. Remove destructive-call gate from `_reasoning_loop`
3. Remove `destructive_functions` and `is_destructive` from base.py
4. Remove destructive tags from FilesystemSkill
5. Remove/adjust MagicMock fixtures to restore bare `MagicMock()` behavior
6. No migration, schema, or config cleanup needed

## Archival Action

- Merged delta spec into `openspec/specs/agent-scaffolding-clarification/spec.md`
- Copied all artifacts (proposal, explore, design, tasks, specs, verify-report) to `openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/`
- Original change folder `openspec/changes/agent-scaffolding-clarification/` removed
- Ready for next change cycle

### Fast-Follow Recommendation

Test `get_all_tools()` output wire compatibility against the live Qwen endpoint (or a full mock of `AsyncOpenAI.chat.completions.create`) to confirm the extra `"destructive"` key is accepted. This closes the WARNING and completes the gate's end-to-end path validation.

**Status: Archived 2026-07-03**
