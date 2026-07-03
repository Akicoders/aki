# Delta for Agent Scaffolding Clarification

## ADDED Requirements

### Requirement: Scaffolding-Intent Prompt Addendum

The system MUST detect scaffolding-intent phrasing in the user input inside `_build_messages` (`src/agentos/agent/core.py:139-205`), using a bilingual keyword/phrase set (e.g. "create", "crear", "generate", "generar", "set up", "scaffold", "new project", "new component", "new file", "armar la estructura") checked case-insensitively against `user_input`, mirroring the structure of the existing SDD-keyword branch (`core.py:193-200`). When a match is found, the system MUST append a dedicated system message instructing the model: if the request is missing key structural details (target path, framework/stack, naming, file layout), ask a clarifying question before calling any write/delete/append tool.

#### Scenario: Scaffolding phrase triggers the prompt addendum

- GIVEN a user input containing "creá un componente nuevo"
- WHEN `_build_messages` assembles the message list
- THEN a system message instructing the model to prefer clarification over an immediate destructive call is appended, in addition to the existing system/context messages

#### Scenario: Non-scaffolding input does not trigger the addendum

- GIVEN a user input containing no scaffolding keyword (e.g. "leé el archivo config.py")
- WHEN `_build_messages` assembles the message list
- THEN no scaffolding-intent system message is appended

### Requirement: Destructive Tool Metadata

The system MUST expose a `destructive: bool` field (default `False`) on skill/tool metadata (`src/agentos/skills/base.py`), and `FilesystemSkill.write`, `FilesystemSkill.append`, and `FilesystemSkill.delete` (`src/agentos/skills/filesystem.py`) MUST be tagged `destructive: True`. All other `FilesystemSkill` functions (`read`, `list`, `glob`, `search`, `exists`) and all other built-in skills' functions MUST default to `destructive: False`. `SkillRegistry.get_all_tools()` MUST surface this flag in the tool schema returned to the model, and the flag MUST also be queryable by the reasoning loop before a tool call executes (not only visible in the schema sent to the model).

#### Scenario: Write/delete/append carry the destructive flag

- GIVEN the registered `filesystem` skill
- WHEN `get_all_tools()` builds the tool schema
- THEN the entries for `filesystem_write`, `filesystem_append`, and `filesystem_delete` report `destructive: true`

#### Scenario: Reads and listings do not carry the destructive flag

- GIVEN the registered `filesystem` skill
- WHEN `get_all_tools()` builds the tool schema
- THEN the entries for `filesystem_read`, `filesystem_list`, `filesystem_glob`, `filesystem_search`, and `filesystem_exists` report `destructive: false`

#### Scenario: Untagged skills default to non-destructive

- GIVEN a built-in skill other than `filesystem` that does not explicitly set `destructive` on any function
- WHEN `get_all_tools()` builds the tool schema
- THEN those functions report `destructive: false`, preserving current behavior for all previously-untagged tools

### Requirement: Destructive-Call Gate in the Reasoning Loop

The system MUST intercept a destructive tool call (`destructive: true`) inside `_reasoning_loop` (`src/agentos/agent/core.py:246-261`) BEFORE executing it via `self.skills.execute(...)`, and evaluate a simple, deterministic heuristic over the call's parsed `fn_args`:

- the call is considered under-specified if **either**:
  1. the `path` argument is missing, `None`, or an empty/whitespace-only string, **or**
  2. the `content` argument (where applicable — `write`/`append`) is missing, `None`, empty/whitespace-only, or a generic placeholder value (see Scenario below for the concrete placeholder set).

This heuristic MUST NOT depend on conversation history, turn number, or whether this is the session's first user turn — it evaluates only the current call's arguments. It is explicitly the "simple" heuristic (missing/empty args), not the more aggressive "first turn with no prior user context" variant, which is out of scope for this change.

The gate MUST fire independently of the scaffolding-intent prompt addendum's success — i.e., it MUST evaluate every destructive tool call regardless of whether the prompt-based keyword detection matched the user input or successfully steered the model toward clarification. The gate is a backstop, not a confirmation that requires agreement from the prompt-branch detection.

When the gate fires, the system MUST:
1. NOT call `self.skills.execute(...)` for that tool call,
2. NOT append further tool-call iterations for this turn,
3. immediately return a `ReasoningOutcome` whose `response` is a plain-text clarifying question describing the missing detail(s), using the same no-tool-call return path already used at `core.py:238-243` (i.e., no new CLI prompt, no blocking stdin read),
4. leave `exhausted=False`, since the turn ends by design, not by iteration exhaustion.

The user's answer to the clarifying question is a normal next-turn user input; existing session/checkpoint persistence rehydrates the missing context so the retried call can pass the gate.

#### Scenario: Destructive call with complete arguments proceeds normally

- GIVEN a `filesystem_write` tool call with `path="/home/user/project/src/app.py"` and `content="print('hello')"`
- WHEN the reasoning loop evaluates the call before execution
- THEN the gate does not fire, and `self.skills.execute("filesystem", "write", ...)` is called as today

#### Scenario: Destructive call with empty path is gated

- GIVEN a `filesystem_write` tool call with `path=""` (or missing) and any `content`
- WHEN the reasoning loop evaluates the call before execution
- THEN the gate fires, the tool is not executed, and the turn ends with a clarifying question asking for the target path

#### Scenario: Destructive call with generic/empty content is gated

- GIVEN a `filesystem_write` tool call with a valid `path` but `content=""` or `content` equal to a recognized generic placeholder (e.g. `"TODO"`, `"..."`, `"contenido"`, `"content"`, or whitespace-only)
- WHEN the reasoning loop evaluates the call before execution
- THEN the gate fires, the tool is not executed, and the turn ends with a clarifying question asking what content to write

#### Scenario: Non-destructive tool calls are never gated

- GIVEN a `filesystem_read`, `filesystem_search`, `filesystem_glob`, or `filesystem_list` tool call with missing or empty arguments
- WHEN the reasoning loop evaluates the call before execution
- THEN the gate does not fire (it only applies to calls where `destructive: true`), and the call proceeds to `self.skills.execute(...)` (or fails downstream on its own validation, unrelated to this gate)

#### Scenario: Tool-layer gate catches an incomplete destructive call even when prompt-based detection misses

- GIVEN a user input that does not match any scaffolding keyword (so the scaffolding-intent system message from `_build_messages` is NOT injected)
- AND the model nonetheless emits a `filesystem_delete` tool call with an empty `path`
- WHEN the reasoning loop evaluates the call before execution
- THEN the gate still fires and the turn ends with a clarifying question, demonstrating the gate operates independently of the prompt-branch detection succeeding or even running
