## Exploration: specialized-agents-architecture

### Current State
Aki is currently a single-agent runtime with richer skills/tools, not a true multi-agent system. `AgentOS.chat()` creates one message history, retrieves all enabled tools from `SkillRegistry.get_all_tools()`, and runs one `_reasoning_loop()` against Qwen with `tool_choice="auto"`. Tool execution is synchronous inside that loop through `SkillRegistry.execute()`, with per-tool memory events and a checkpoint written at the end of each turn.

Skills are the only specialization surface today. Built-in skills are registered from `BUILTIN_SKILLS`, enabled through `SkillsConfig.enabled`, and each `Skill` exposes async public methods as OpenAI-compatible tools. The persisted `SkillModel` stores skill metadata (`name`, `description`, `functions`, `enabled`, `config`) for memory/context display, but it is not an agent registry and does not define prompts, models, tool scopes, delegation rules, or per-agent memory boundaries.

Prompt/model configuration is also single-agent. `AgentConfig` has one `max_iterations`, `temperature`, `system_prompt_template`, `memory_injection_template`, and `skill_injection_template`; Qwen calls can receive a model override, but the active runtime does not route turns to different agent profiles. Existing archived work solved adjacent foundations: session persistence/checkpoint rehydration, session list/help, project metadata store, and scaffolding clarification. The active `agent-runtime-telemetry` change is already scoped to single-agent load/tool/iteration visibility and should stay separate from specialized-agent architecture.

### Affected Areas
- `src/agentos/agent/core.py` — central single-agent orchestration, message construction, reasoning loop, destructive-tool gate, checkpoint writes, and the seam where a future orchestrator/router would either wrap or split execution.
- `src/agentos/core/config.py` — current `AgentConfig` and `SkillsConfig` are global; a future design needs separate config models for agent profiles, tool scopes, models, prompts, and memory policy.
- `src/agentos/skills/base.py` — `SkillRegistry` is a tool registry only; it can be reused by agents but should not be stretched into an agent registry without clear boundaries.
- `src/agentos/skills/__init__.py` — built-in skill loading is static and config-driven; useful migration input for default agent toolsets.
- `src/agentos/memory/models.py` — existing persisted `SkillModel` proves metadata persistence patterns, but agent profile storage would need different semantics and possibly migrations.
- `src/agentos/cli/main.py` — CLI commands expose single chat/interactive entry points and `/skills`; future specialized agents may need agent selection, visibility, and help without breaking current commands.
- `openspec/changes/agent-runtime-telemetry/` — adjacent active change for runtime visibility; specialized-agent work must consume or align with it later, not duplicate it.
- `openspec/changes/archive/2026-07-02-session-persistence/` — checkpoint/session recovery foundation that any delegated agent handoff must respect.
- `openspec/changes/archive/2026-07-03-agent-scaffolding-clarification/` — destructive-tool safety gate that must remain effective across any future delegation boundary.
- `openspec/changes/archive/2026-07-02-project-metadata-store/` — project identity/context foundation likely needed for project-scoped agent registries.

### Approaches
1. **Stay single-agent; enrich skills and prompt policy** — Keep one `AgentOS` runtime and add stronger skills, prompt sections, and tool-gating rules for specialized behaviors.
   - Pros: Lowest blast radius; preserves current session/checkpoint/tool flow; avoids premature orchestration complexity; compatible with telemetry work.
   - Cons: Does not create independent agent identities; no per-agent model/tool/memory isolation; prompt grows into a policy dumping ground; weak fit for reviewer/planner/builder separation.
   - Effort: Low

2. **Declarative agent profiles over the existing single loop** — Add an `AgentProfile` registry with per-profile prompt, model, tools, max_iterations, and memory scope, then run one selected profile through the existing `AgentOS` loop per turn.
   - Pros: Real user-facing specialized agents without nested delegation; small migration from skills; clear config surface; can keep checkpoints and telemetry mostly intact; good first milestone.
   - Cons: Still only one active agent per turn; handoff is explicit selection/routing, not autonomous multi-agent collaboration; shared loop may need careful parameterization.
   - Effort: Medium

3. **Supervisor-router with bounded handoff to specialized worker profiles** — Add a lightweight orchestrator that selects or delegates to worker profiles with scoped prompts/tools/memory, then returns a summarized result to the main session.
   - Pros: True specialized-agent behavior; supports planner/reviewer/builder boundaries; enables per-agent model/tool policies; aligns with future telemetry once single-agent telemetry exists.
   - Cons: High complexity; needs handoff contracts, loop budgets, memory scoping, failure propagation, and user-visible trace semantics; easy to blur with `agent-runtime-telemetry` if done too early.
   - Effort: High

4. **External multi-agent process orchestration** — Spawn separate agent processes or sessions for specialized work and coordinate through filesystem/session artifacts.
   - Pros: Strong isolation; useful for long-running autonomous missions and parallel coding lanes.
   - Cons: Too heavy for Aki's in-process product architecture now; complex lifecycle/security story; risks duplicating external-agent tooling rather than improving Aki core.
   - Effort: High

### Recommendation
Proceed with a staged architecture that starts with **Approach 2: declarative agent profiles over the existing single loop**, while designing the data model and interfaces so **Approach 3** can be added later without rewriting the runtime.

The first proposal should NOT implement full multi-agent delegation immediately. That would be coding a second building before checking the foundation, and here the foundation is still single-agent. Instead, define a minimal `AgentProfile` / `AgentRegistry` concept with these boundaries:

- profile identity: `id`, `name`, `description`, `role`;
- runtime config: `system_prompt_template`, optional `model`, `temperature`, `max_iterations`;
- tool policy: allowlist of skill/function names, reusing `SkillRegistry` as the execution backend;
- memory policy: project/session/global scope rules and whether profile outputs are persisted as conversation, checkpoint, or summary events;
- delegation boundary: initial version supports explicit profile selection or deterministic router decision, not recursive worker spawning;
- telemetry boundary: expose profile/agent name as future metadata only after `agent-runtime-telemetry` lands, keeping detailed load/tool/iteration visibility in that separate change.

This gives Aki "specialized agents can be created" as a product capability while avoiding immediate multi-agent orchestration debt. The proposal should explicitly preserve the current default single-agent behavior: if no profile is selected, `AgentOS.chat()` behaves as it does today.

### Risks
- Overloading `SkillRegistry` into an agent registry would mix tool discovery with actor identity; keep separate registries.
- Full autonomous delegation before profile isolation would create unclear memory ownership, duplicate tool budgets, and hard-to-debug handoffs.
- Per-agent model configuration can fragment Qwen/client behavior unless model overrides remain explicit and validated.
- Memory scope is the dangerous boundary: worker summaries, raw tool results, and checkpoints must not leak across project/session scopes.
- Existing Spanish runtime prompt fragments and SDD injection behavior may become inconsistent across agents if prompt composition is duplicated instead of centralized.
- `agent-runtime-telemetry` is adjacent and active; specialized-agent artifacts must avoid specifying telemetry internals beyond the minimal metadata needed for later integration.

### Ready for Proposal
Yes. The proposal should scope this as an architectural foundation for declarative specialized agent profiles, not full autonomous multi-agent execution. It should include a migration path from current skills-based architecture, preserve single-agent default behavior, and defer detailed runtime visibility to `agent-runtime-telemetry`.
