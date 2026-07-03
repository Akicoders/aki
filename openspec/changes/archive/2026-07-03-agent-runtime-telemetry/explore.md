## Exploration: agent-runtime-telemetry

### Current State
Aki is currently a single-agent runtime: `AgentOS.chat()` builds one message list, retrieves all enabled tools through `SkillRegistry.get_all_tools()`, then delegates to one `_reasoning_loop()` with `tool_choice="auto"` and `AgentConfig.max_iterations` defaulting to 5. There is no native sub-agent, router, or specialized-agent orchestration layer in the current runtime path.

The CLI already has a minimal status mechanism for one-shot `aki chat`: `chat()` wraps execution in `console.status(...)`, passes a `status_callback`, and `AgentOS.chat()` emits coarse statuses such as "Collecting project context", "Reasoning with Qwen", and "Saving conversation". The interactive path does not use that callback: `_async_interactive()` calls `agent.chat(user_input, project, session_id)` directly and only prints the final Markdown response, so users get no live runtime feedback while an agent turn is working.

The reasoning loop tracks iteration count internally, counts total tool calls, records recent tool names, and persists per-tool events via `create_event(...)`. On exhaustion it returns `_format_exhaustion_message(max_iterations, total_tool_calls, last_tools_used)`, and session checkpoint writing records `iterations_exhausted=True`. The current exhaustion message is honest and actionable, but it is only visible after failure and does not expose progress while the loop is running.

Relevant archived work already closed adjacent issues: session persistence/checkpoint rehydration, session list/contextual help, project metadata store, and scaffolding clarification. This change should therefore stay focused on lightweight runtime visibility and exhaustion UX, not persistence, project discovery, or multi-agent architecture.

### Affected Areas
- `src/agentos/agent/core.py` — owns `StatusCallback`, `AgentOS.chat()`, `_reasoning_loop()`, tool execution, iteration counting, and `_format_exhaustion_message()`.
- `src/agentos/cli/main.py` — owns `aki chat` status rendering and `_async_interactive()`; one-shot chat already has status plumbing, interactive does not.
- `src/agentos/core/config.py` — defines `AgentConfig.max_iterations`; this change should read existing config only, not add new tuning unless later design proves it necessary.
- `tests/unit/test_cli_chat.py` — existing coverage for one-shot status updates; likely place to extend status assertions.
- `tests/unit/test_agent_status.py` / `tests/unit/test_agent_exhaustion.py` / `tests/unit/test_reasoning_outcome.py` — existing unit-test surface for status, exhaustion, and reasoning-loop outcomes.
- `openspec/changes/archive/2026-07-02-session-persistence/` — confirms checkpoint/exhaustion persistence is already solved and should not be reworked here.
- `openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/` — confirms premature destructive-tool gating is already solved separately; telemetry should not reopen that scope.

### Approaches
1. **Callback-only runtime status enrichment** — Keep the existing string callback shape, but emit more informative messages from `_reasoning_loop()` before each model iteration and before/after tool execution.
   - Pros: Smallest change; uses existing CLI status path; no new public model or config; easy unit tests.
   - Cons: String-only callback can become ad hoc; interactive still needs local wiring; not ideal if future UIs need structured telemetry.
   - Effort: Low

2. **Structured runtime event callback** — Replace or supplement `StatusCallback` with typed runtime events carrying phase, iteration, max_iterations, active tool, total_tool_calls, and budget remaining.
   - Pros: Cleaner foundation for future cockpit/web UI; avoids parsing status strings; better separates runtime facts from presentation.
   - Cons: Larger API change; more tests and call sites; can overbuild for the immediate CLI UX need.
   - Effort: Medium

3. **Persist runtime telemetry to memory/events only** — Rely on existing per-tool `create_event(...)` records and add richer metadata without changing live CLI display.
   - Pros: Useful for post-run observability and debugging; minimal UI churn.
   - Cons: Does not solve the user-visible "is it working or stuck?" problem; users still wait blindly during an active turn.
   - Effort: Low/Medium

4. **Multi-agent/runtime orchestrator telemetry** — Design telemetry around future specialized agents, worker names, routing, and per-agent budgets.
   - Pros: Aligns with the larger multi-agent ambition.
   - Cons: Wrong scope for this change; current architecture has no sub-agent layer, and coupling telemetry to a future architecture would delay the simple UX fix.
   - Effort: High

### Recommendation
Proceed with Approach 1, with a narrow compatibility seam toward Approach 2: enrich the existing status callback messages now, but keep the emitted facts centralized enough that a later structured callback can reuse them.

The first implementation slice should be deliberately modest:
- emit iteration progress such as `Reasoning with Qwen (iteration 2/5)`;
- emit active tool information such as `Using tool filesystem.read (tool 3)`;
- emit a near-budget warning when entering the final iteration;
- wire `_async_interactive()` through `console.status(...)` and pass the same `status_callback` used by one-shot `aki chat`;
- improve exhaustion copy to include what happened, what was last attempted, and concrete next steps without implying that simply increasing the limit is the primary fix.

This keeps the change separate from multi-agent architecture, avoids new persistence/schema/config work, and gives users live feedback with the smallest safe blast radius.

### Risks
- Status strings can become UX/API debt if future UIs need structured telemetry; mitigate by centralizing formatting and keeping tests behavior-focused.
- Too many status updates could flicker or distract in Rich; keep updates to phase/iteration/tool boundaries only.
- Exhaustion messaging can overpromise recovery; wording must be honest that the current turn stopped and the user can narrow scope or continue from checkpoint.
- Interactive-mode status handling must not swallow Ctrl-C/EOF behavior or break command handling.
- Tool-call arguments can contain sensitive or long content; status must show tool names and counts, not raw args.

### Ready for Proposal
Yes. Proposal should scope this as a lightweight single-agent runtime telemetry UX change: live status for load/iteration/tool use plus clearer max-iteration exhaustion copy. It should explicitly exclude specialized/multi-agent routing, new persistence models, and broad observability infrastructure.
