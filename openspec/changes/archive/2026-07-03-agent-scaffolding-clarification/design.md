# Design: Agent Scaffolding Clarification

## Status

Design phase for change `agent-scaffolding-clarification`. Inputs: `proposal.md`,
`specs/agent-scaffolding-clarification.md`. Validated against the real code in
`src/agentos/agent/core.py` (reasoning loop + `_build_messages`),
`src/agentos/skills/base.py` (`Skill` / `SkillRegistry` / `get_all_tools`), and
`src/agentos/skills/filesystem.py` (`FilesystemSkill`). `src/agentos/core/config.py`
is OFF-LIMITS this cycle — NOT read, NOT modified; any tunable lands as a module
constant next to its consumer, wiring deferred (same discipline as the
session-persistence change).

Two orthogonal layers, each independently shippable:

1. **Prompt nudge** — a scaffolding-intent branch in `_build_messages`, structurally
   identical to the existing SDD-keyword branch (`core.py:193-200`).
2. **Tool-layer backstop** — `destructive` metadata on skills + a deterministic gate
   in `_reasoning_loop` that short-circuits an under-specified destructive call into a
   clarifying-question turn.

The gate is the load-bearing guarantee; the prompt is best-effort. They are fully
independent (ADR-4).

## 1. Architecture Approach

```
_build_messages()        scaffolding-keyword branch → appends 1 system message (nudge)
   │ (no coupling)
_reasoning_loop()        per tool_call, BEFORE self.skills.execute():
   │                       is this call destructive?  ── SkillRegistry.is_destructive()
   │                       if yes AND under-specified  → return ReasoningOutcome(question)
   │ queries
SkillRegistry            is_destructive(skill, fn) — reads per-skill destructive set
   │ + get_all_tools() surfaces `destructive` in each tool's function object
Skill (base)             destructive_functions: frozenset[str] = frozenset()  (default empty)
FilesystemSkill          destructive_functions = {"write", "append", "delete"}
```

Nothing depends on conversation history, turn number, or the prompt branch having
fired. The gate reads only the current call's parsed args and the static destructive
flag.

## 2. Key Decision: what counts as "generic content" (RESOLVED)

The spec left this open and listed illustrative-but-uncommitted examples (`TODO`,
`...`, `"contenido"`, `"content"`, whitespace). This design commits to **Option A —
a fixed placeholder set matched by case-insensitive EXACT match after `strip()`.**

**Decision.** `content` is under-specified when, after `str(content).strip()`:
- it is empty (`""`), OR
- its `.lower()` is a member of a fixed frozenset of placeholder tokens.

```python
# src/agentos/agent/core.py  (near the gate, marked deferred config)
GENERIC_CONTENT_PLACEHOLDERS: frozenset[str] = frozenset({
    "todo", "tbd", "fixme", "...", "…",
    "placeholder", "content", "contenido",
    "content here", "contenido aqui", "your content here",
    "tu contenido aqui",
})
```

### Why Option A and NOT B or C

- **House-style precedent.** The only fuzzy-matching precedent in this codebase is the
  SDD-keyword branch (`core.py:193-200`): a fixed literal tuple checked with `.lower()`.
  A fixed placeholder set is the same shape — predictable, greppable, trivially
  unit-testable, no magic numbers. Option B (length threshold `N`) introduces exactly
  the kind of tuned constant this codebase avoids in the detection layer.
- **False positives are the headline risk** (proposal risk row #1). Option B gates
  legitimately short real content — a one-line config value like `port=8080`, a single
  `export default App`, a `.gitignore` line — which would turn a correct well-specified
  write into an annoying stall. Option A cannot false-positive on real content: a real
  one-liner is never lexically equal to `"todo"` or `"content"`.
- **EXACT match, deliberately NOT substring** (this is the one intentional divergence
  from the SDD branch, which uses `kw in user_input`). `content` is arbitrary
  source/text; a legitimate Python file literally containing the identifier `content`
  or a comment `# TODO` would be gated forever under substring matching. `user_input`
  is a short natural-language ask where substring is safe; `content` is a payload where
  it is not. Exact-match-after-strip is the safe, deterministic rule for payloads.
- **Path check stays trivial.** `path` is under-specified when missing/`None`/empty or
  whitespace-only after strip — no placeholder set needed (a real path is never
  ambiguous the way prose content is).

Option C (set OR length-threshold pattern) was rejected as over-engineering for the
explicitly "simple" heuristic the spec mandates; it reintroduces Option B's
false-positive surface for marginal recall gain.

**Testability note for tasks/apply:** because the rule is pure over `fn_args`, every
gate scenario is a table-driven unit test (`_is_under_specified(fn_name, fn_args)`)
with zero LLM, zero I/O, zero history. See §7.

## 3. Destructive Metadata (RESOLVED)

### 3a. Where the flag lives

Per-function, declared **statically per skill class** — not per-call, not in config.
Add to `Skill` base (`base.py`):

```python
class Skill(ABC):
    ...
    destructive_functions: frozenset[str] = frozenset()  # default: nothing destructive

    def is_destructive(self, fn_name: str) -> bool:
        return fn_name in self.destructive_functions
```

`FilesystemSkill` (`filesystem.py`) declares:

```python
class FilesystemSkill(Skill):
    name = "filesystem"
    destructive_functions = frozenset({"write", "append", "delete"})
```

All other `FilesystemSkill` methods (`read`, `list`, `glob`, `search`, `exists`) and
every other built-in skill inherit the empty default → `destructive: False`,
preserving current behavior for all previously-untagged tools (spec scenario
"Untagged skills default to non-destructive").

Rationale for a class attribute over per-method decoration: `_discover_functions`
already keys on method name, and the destructive set is small and static. A frozenset
is the minimal, greppable, override-friendly mechanism — mirrors how `functions` is
already a class-level list. No new decorator machinery.

### 3b. Surfacing in the tool schema (`get_all_tools`)

`get_openai_tool` (`base.py:109-121`) adds the flag to the emitted function object:

```python
def get_openai_tool(self, fn_name: str) -> Optional[dict[str, Any]]:
    schema = self.get_function_schema(fn_name)
    if not schema:
        return None
    return {
        "type": "function",
        "function": {
            "name": schema.name.replace(".", "_"),
            "description": schema.description,
            "parameters": schema.parameters,
            "destructive": self.is_destructive(fn_name),   # NEW
        },
    }
```

`SkillRegistry.get_all_tools()` is unchanged in logic — it already iterates
`skill.functions` and calls `get_openai_tool`, so the flag rides along automatically.
This satisfies the spec's "report `destructive: true/false` in the tool schema"
scenarios.

**Model-visibility stance (spec says internal-primary):** the flag is placed on the
function object but is advisory metadata for the model, not something the model must
act on — the enforcement is 100% the loop-side gate (§4). The gate does NOT read the
schema; it queries the registry directly (§3c), so correctness never depends on the
model reading or respecting `destructive`. If a downstream OpenAI-compat validator
ever rejects unknown keys on the `function` object, the fallback is to move the flag
under `parameters` metadata or drop it from the wire entirely — the gate is unaffected
because it uses the registry path. Tasks should include a smoke check that the Qwen
client tolerates the extra key.

### 3c. Registry accessor for the gate

Add to `SkillRegistry` so the loop can ask without re-parsing the schema:

```python
def is_destructive(self, skill_name: str, fn_name: str) -> bool:
    skill = self.get(skill_name)
    return bool(skill and skill.is_destructive(fn_name))
```

This is the "queryable by the reasoning loop before a tool call executes (not only
visible in the schema)" requirement from the spec.

## 4. The Gate in `_reasoning_loop` (RESOLVED)

### 4a. Interception point

Inside the existing `for tool_call in response.tool_calls:` loop
(`core.py:246-261`), AFTER the `skill_name` / `fn_name` split (line 252-255) and
BEFORE `self.skills.execute(...)` (line 261). `fn_args` is already the parsed
arguments dict at this point (it is passed straight to `execute` as `**arguments`), so
no JSON parsing is needed.

```python
# after: skill_name, fn_name = fn_name.split("_", 1)   (line ~253)

if self.skills.is_destructive(skill_name, fn_name) and \
        _is_under_specified(fn_name, fn_args):
    logger.info(f"Destructive gate fired: {skill_name}.{fn_name} under-specified")
    return ReasoningOutcome(
        response=_build_clarifying_question(skill_name, fn_name, fn_args),
        last_tool_summary=", ".join(last_tools_used[-3:]),
        exhausted=False,          # turn ends by design, not exhaustion
    )
```

Reuses the **exact same return mechanism** as the no-tool-call path at
`core.py:238-243` — a `ReasoningOutcome` with `exhausted=False`. `chat()` (line
~129-137) then persists the checkpoint and returns `outcome.response` verbatim, so the
clarifying question becomes the assistant turn with zero new plumbing. No CLI prompt,
no blocking stdin, no `tool_choice` change.

Placing the gate INSIDE the per-tool-call loop (not before it) means: if the model
emits a batch of tool calls, the FIRST destructive-and-under-specified one
short-circuits the whole turn. Non-destructive calls earlier in the same batch have
already executed and appended their tool results — acceptable, and matches the spec
("first action of a turn" intent while staying purely arg-driven). Reads are never
gated.

### 4b. The pure helpers

Both are module-level pure functions (mirrors how session-persistence extracted
`render_checkpoint` / `_resolve_session_id` as pure, table-testable units):

```python
def _is_under_specified(fn_name: str, fn_args: dict[str, Any]) -> bool:
    """True when a destructive call's args are too vague to execute safely.
    Pure over fn_args — no history, no turn count (spec: the 'simple' heuristic)."""
    path = fn_args.get("path")
    if path is None or not str(path).strip():
        return True
    if fn_name in ("write", "append"):
        content = fn_args.get("content")
        if content is None or not str(content).strip():
            return True
        if str(content).strip().lower() in GENERIC_CONTENT_PLACEHOLDERS:
            return True
    return False  # delete: path presence is sufficient specificity
```

```python
def _build_clarifying_question(skill_name: str, fn_name: str, fn_args: dict) -> str:
    path = fn_args.get("path")
    if path is None or not str(path).strip():
        return (
            "Antes de escribir necesito el destino exacto. "
            "¿En qué ruta (path) querés que cree/modifique el archivo, "
            "y con qué stack/estructura?"
        )
    return (
        f"Voy a escribir en `{path}` pero el contenido está vacío o es un "
        "placeholder genérico. ¿Qué contenido concreto querés que ponga?"
    )
```

- `delete` intentionally only checks `path` (no `content` param) — an empty path is the
  only ambiguity for a delete.
- The question is Spanish, matching the existing user-facing strings in this file
  (`_format_exhaustion_message` is Spanish). Artifact language follows the surrounding
  code, per house convention.

## 5. Scaffolding-Intent Prompt Addendum (RESOLVED)

A branch in `_build_messages`, placed right after the SDD-keyword branch
(`core.py:200`) and before the user message is appended (line 203), structurally
identical to the SDD branch:

```python
SCAFFOLDING_KEYWORDS = (
    # English
    "create", "generate", "set up", "setup", "scaffold", "bootstrap",
    "new project", "new component", "new file", "new module", "boilerplate",
    "start a project", "initialize",
    # Spanish
    "crear", "creá", "crea", "generar", "generá", "genera", "armar",
    "armá", "arma", "estructura", "andamiaje", "nuevo proyecto",
    "nuevo componente", "nuevo archivo", "inicializar", "montar",
)

if any(kw in user_input.lower() for kw in SCAFFOLDING_KEYWORDS):
    messages.append({
        "role": "system",
        "content": (
            "El pedido parece de scaffolding/creación de estructura. "
            "Antes de llamar a cualquier herramienta destructiva "
            "(filesystem.write / append / delete), verificá que tengas los "
            "detalles estructurales clave: ruta destino, framework/stack, "
            "convención de nombres y layout de archivos. Si falta alguno, "
            "hacé UNA pregunta aclaratoria concreta en tu respuesta en lugar "
            "de crear archivos a ciegas."
        ),
    })
```

- Substring `.lower()` matching, identical to the SDD branch — safe here because
  `user_input` is a short NL ask (contrast with §2, where `content` payloads require
  exact match).
- This branch and the gate share NO state. If the keyword misses (paraphrase), the
  gate still fires on the under-specified args. If the keyword hits but the model
  produces a well-specified call anyway, the gate passes it through. Independence is
  the whole point (ADR-4, spec "gate fires independently" requirement).

## 6. Assumptions validated against real code

- `fn_args` is already a parsed dict at the interception point (passed to
  `execute(**arguments)` at line 261) — no JSON decode in the gate. CONFIRMED.
- `_discover_functions` filters on method name and the `Skill` base attr set; adding a
  class attribute `destructive_functions` and a method `is_destructive` will be swept
  into `base_attrs` (excluded from tool discovery) and will NOT leak as a fake tool.
  CONFIRMED (both are on the base class, so `name not in base_attrs` excludes them).
- The `ReasoningOutcome(exhausted=False)` early return flows through `chat()`'s
  checkpoint write and returns `outcome.response` unchanged. CONFIRMED (core.py
  ~129-137).

## 7. Test Strategy (strict TDD, pytest) (RESOLVED)

Tests FIRST. Bulk of coverage is pure-unit — the two helpers and the metadata are
I/O-free and LLM-free.

### Tier A — pure unit: `_is_under_specified` (table-driven)

- empty path (`""`, `None`, `"   "`) → gated, for `write`/`append`/`delete`.
- valid path + valid content → NOT gated.
- valid path + empty/whitespace content (`write`/`append`) → gated.
- valid path + each placeholder token (`"TODO"`, `"todo"`, `" ... "`, `"content"`,
  `"contenido"`, `"Content Here"`) case/space-insensitive → gated.
- valid path + real short content (`"port=8080"`, `"export default App"`) → NOT gated
  (the anti-false-positive guarantee — this is the test that justifies Option A over B).
- `delete` with valid path + no content param → NOT gated.

### Tier A — pure unit: metadata

- `FilesystemSkill().is_destructive("write"/"append"/"delete")` → True.
- `is_destructive("read"/"list"/"glob"/"search"/"exists")` → False.
- `get_all_tools()` entries: `filesystem_write/append/delete` carry
  `destructive: True`; `filesystem_read/list/glob/search/exists` carry
  `destructive: False`.
- A second built-in skill's tools all report `destructive: False` (default preserved).
- `SkillRegistry.is_destructive("filesystem","write")` True;
  unknown skill/fn → False.

### Tier A — pure unit: prompt branch and clarifier

- `_build_messages` with `"creá un componente nuevo"` → exactly one extra system
  message containing the scaffolding instruction.
- `_build_messages` with `"leé el archivo config.py"` → no scaffolding system message.
- `_build_clarifying_question` picks the path-question vs content-question branch.

### Tier B — loop wiring (spy the executor)

- destructive + under-specified call → `self.skills.execute` NOT called; returned
  `response` is the clarifying question; `exhausted is False`.
- destructive + well-specified call → `execute` called as today.
- non-destructive call with empty args → NOT gated (proceeds to `execute`).
- gate fires even when the scaffolding keyword did NOT match the input (independence
  scenario from the spec) — assert `execute` not called though no addendum injected.

Use a fake `QwenClient` returning a scripted `tool_calls` payload (same approach the
session-persistence Tier-C tests use for a fake qwen) so no real model runs.

## 8. Architecture Decisions (ADR-style)

### ADR-1: "Generic content" = fixed placeholder frozenset, exact match after strip
- **Decision:** Option A. Under-specified content = empty OR `strip().lower()` ∈
  `GENERIC_CONTENT_PLACEHOLDERS`.
- **Rationale:** matches the only fuzzy-match precedent (SDD-keyword tuple), no tuned
  numeric threshold, cannot false-positive on legit short real content.
- **Rejected:** Option B (length threshold — false-positives real one-liners);
  Option C (set OR threshold — reintroduces B's surface for marginal recall).
- **Divergence noted:** exact match (not substring) for `content`, because payloads
  legitimately contain placeholder words; substring is only safe for the short NL
  `user_input` in the prompt branch.

### ADR-2: Destructive flag as a static per-skill frozenset + `is_destructive`
- **Decision:** `destructive_functions: frozenset[str]` on `Skill`, overridden by
  `FilesystemSkill`; `is_destructive` on both `Skill` and `SkillRegistry`.
- **Rationale:** minimal, greppable, override-friendly; auto-excluded from tool
  discovery (base-class attrs); default empty preserves all existing tools.
- **Rejected:** per-method decorator (new machinery for a 3-item static set);
  config-driven tagging (config.py off-limits, and this is code-intrinsic).

### ADR-3: Enforcement is loop-side gate via registry, schema flag is advisory
- **Decision:** the gate calls `SkillRegistry.is_destructive`, never reads the wire
  schema. `destructive` on the function object is advisory for the model only.
- **Rationale:** correctness must not depend on the model reading/respecting the flag;
  keeps a clean fallback if an OpenAI-compat validator rejects the extra key.

### ADR-4: Prompt addendum and gate are fully independent
- **Decision:** no shared state; the gate evaluates every destructive call regardless
  of whether the scaffolding keyword matched.
- **Rationale:** the prompt is a best-effort nudge under `tool_choice="auto"`; the gate
  is the deterministic backstop. Independence is the reliability guarantee.

## 9. Assumptions & Risks for downstream phases

- **Risk (false positive):** a user who genuinely wants a literal `TODO`-only file is
  gated. Accepted — vanishingly rare, and one clarifying turn is cheap; documented in
  the clarifier text so the user can restate.
- **Risk (schema key rejection):** the extra `destructive` key on the function object
  could be rejected by a strict OpenAI-compat endpoint. Mitigation: gate uses the
  registry path, so enforcement survives; tasks add a Qwen-client tolerance smoke test
  and note the fallback (move under `parameters` / drop from wire).
- **Risk (batch tool calls):** a non-destructive call preceding the gated destructive
  one in the same batch executes before the short-circuit. Accepted — reads are safe;
  gating is per-call and arg-driven by design.
- **Assumption:** `stream_chat` routes through `chat`/the loop the same way and is
  unaffected by the new early-return branch — verify in apply.
- **Deferred:** length/semantic content heuristics, LLM intent classification,
  `tool_choice="none"` hard gate, `config.py` wiring of `SCAFFOLDING_KEYWORDS` /
  `GENERIC_CONTENT_PLACEHOLDERS` — all out of scope this cycle.
</content>
</invoke>
