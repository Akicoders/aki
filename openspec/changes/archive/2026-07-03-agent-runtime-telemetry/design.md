# Design: Agent Runtime Telemetry

## Technical Approach

Keep the current single-agent loop and `StatusCallback = Callable[[str], None]` as the public seam. `AgentOS.chat()` owns turn-level phase messages; `_reasoning_loop()` owns iteration/tool/exhaustion messages; CLI commands only format strings through existing Rich `console.status()`. No persistence schema, MCP, worker, routing, or orchestration behavior changes.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|----------|--------|-------------------------|-----------|
| Telemetry seam | Reuse optional string `status_callback` | New structured event bus or persisted telemetry table | Lowest blast radius; preserves `chat()`/`stream_chat()` compatibility and avoids premature observability infrastructure. |
| Formatting owner | Add small private helpers in `agent/core.py` for status and exhaustion text | Duplicate text in CLI or expose Rich objects to agent | Keeps UI-independent facts centralized; CLI remains a renderer. |
| Safety boundary | Emit tool display name/count only; never arguments/results | Show full call details for debugging | Meets privacy spec and avoids leaking prompts, paths, keys, memory payloads, or tool outputs. |
| Interactive integration | Wrap each prompt turn with the same `console.status()` callback used by `aki chat` | Print line-by-line progress | Reuses existing Rich path and avoids noisy interactive output. |
| Multi-agent future | Keep copy generic: "iteration", "tool", "turn" | Introduce worker/delegation language now | Later multi-agent telemetry can add structured events without teaching users false architecture today. |

## Data Flow

```text
aki chat / interactive
    └─ creates Rich status.update callback
        └─ AgentOS.chat(status_callback)
            ├─ context/build/save phase status
            └─ _reasoning_loop(status_callback)
                ├─ iteration i/n status
                ├─ final-iteration warning when i == max_iterations
                ├─ tool k/m starting: safe_name only
                └─ exhaustion summary if no final answer
```

Async execution remains one coroutine chain: CLI `asyncio.run(...)` awaits `agent.chat()`, which awaits Qwen calls and tool execution sequentially. MCP/tool internals are unchanged.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/agentos/agent/core.py` | Modify | Pass `status_callback` into `_reasoning_loop()`, add bounded iteration/tool/final/exhaustion status helpers, enrich `_format_exhaustion_message()`. |
| `src/agentos/cli/main.py` | Modify | In `_async_interactive()`, create a Rich status context per user prompt and pass `status_callback` to `agent.chat()`. Preserve `/` command, Ctrl-C, EOF, and Markdown response flow. |
| `src/agentos/core/config.py` | Read-only | Continue using `AgentConfig.max_iterations` as the only iteration budget. No new config. |
| `tests/unit/test_agent_status.py` | Modify | Assert turn/iteration/final/tool/completion status sequence and safe redaction behavior. |
| `tests/unit/test_agent_exhaustion.py`, `tests/unit/test_reasoning_outcome.py` | Modify | Cover actionable exhaustion text with and without tools. |
| `tests/unit/test_cli_chat.py` | Modify | Assert one-shot and interactive pass callbacks without breaking command-loop handling. |

## Interfaces / Contracts

No new Pydantic schemas or validation models. Existing contract remains:

```python
StatusCallback = Callable[[str], None]
```

Private status strings SHOULD be factual and bounded:
- `Starting turn`
- `Reasoning iteration {i}/{max_iterations}`
- `Final iteration {i}/{max_iterations}; no automatic retry remains`
- `Running tool {ordinal}/{total}: {skill}.{function}`
- `Saving conversation`, `Turn complete`, `Turn exhausted`

`_format_exhaustion_message(max_iterations, total_tool_calls, last_tools_used)` MUST include budget reached, no final answer produced, last safe phase/tool if known, and next steps. It MUST NOT mention workers, delegation, routing, orchestration, raw arguments, or results.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_reasoning_loop()` status sequence, final warning, safe tool labels | Fake Qwen responses and fake `SkillRegistry.execute()`; capture callback strings. |
| Unit | Exhaustion message contract | Direct helper tests plus exhausted loop tests for tool/no-tool cases. |
| CLI unit | `chat` and `_async_interactive()` callback wiring | Monkeypatch agent/Prompt/console status; verify Ctrl-C/EOF remain unchanged. |
| Integration/E2E | Not required | No external persistence, MCP, or database behavior changes. |

## Migration / Rollout

No migration required. Rollout is additive: if no callback is provided, behavior remains silent except returned response text. Rollback is limited to removing helper emissions and the interactive wrapper.

## Open Questions

- None.
