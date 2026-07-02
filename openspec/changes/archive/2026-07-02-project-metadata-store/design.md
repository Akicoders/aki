# Design: Project Metadata Store (last-project breadcrumb)

## 0. Summary

A single-purpose, fail-soft breadcrumb file records the last positively-resolved
project root. `load_runtime_env` reads it as the **lowest-priority** candidate
root so `.env` discovery can bootstrap when the process cwd has zero relation to
any repo. No DB, no schema, no general metadata store. Additive-only wiring.

Architecture style: a thin, side-effect-isolated **adapter module** (pure
read/write helpers) plugged into three existing resolution flows. It follows the
existing hexagonal grain of the codebase — I/O and format concerns live in one
small module; callers depend only on `Path` in/out.

---

## 1. Breadcrumb file location — DECISION

**Chosen: `~/.aki/last-project.json`** (`Path.home() / ".aki" / "last-project.json"`).

**Rejected: XDG-compliant** (`$XDG_CONFIG_HOME` / `~/.config/aki/last-project.json`).

Rationale:
- No XDG precedent exists anywhere in `src/` (confirmed by exploration §4).
  Introducing XDG resolution for a **single-field breadcrumb** is ceremony
  disproportionate to the payload — it would be the first and only XDG consumer
  in the codebase, creating an inconsistent convention rather than following one.
- `Path.home()` is already the established pattern for user-global paths
  (`mcp_hosts.py`, `update.py`, `FilesystemConfig.allowed_roots`). Staying on
  `Path.home()` matches the codebase and the user's own ".aki/ storage layer"
  framing.
- Test-friendliness: `Path.home()` honors a monkeypatched `HOME`, so unit tests
  isolate cleanly via `monkeypatch.setenv("HOME", tmp_path)` with no env-var
  juggling.
- This is deliberately NOT a general `.aki/` store. The directory holds exactly
  one file today; if a real global-config need emerges later, migrating to XDG
  is a localized change inside this one module.

No environment-variable override is added — an override would itself have to live
in the `.env` we are trying to locate (the same circularity noted for
`MEMORY_DB_PATH` in exploration §1), so it would be useless for bootstrapping.

---

## 2. JSON schema — CONFIRMED (minimal)

```json
{
  "root_path": "/absolute/resolved/path/to/project",
  "updated_at": "2026-07-02T14:03:21.512+00:00"
}
```

- `root_path`: absolute, `resolve(strict=False)`-normalized string.
- `updated_at`: timezone-aware ISO 8601, `datetime.now(timezone.utc).isoformat()`.
  Diagnostic/staleness signal only — **not** read back for logic in this change.

No other fields. Adding `key`, `source`, or history would drift toward the
DB-backed `ProjectRefModel` registry, which is the explicit non-goal. The single
load-bearing field is `root_path`; `updated_at` exists purely for human/debug
inspection and future staleness policy without a format bump.

---

## 3. New module — `src/agentos/core/project_breadcrumb.py`

Pure helpers, stdlib-only (`json`, `pathlib`, `datetime`). No dependency on
`config.py` (avoids an import cycle: `config` → `project_breadcrumb`, one way).

```python
"""Last-resolved-project breadcrumb: bootstrap .env discovery from an
unrelated cwd. Single JSON pointer, fail-soft, never raises into callers."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_BREADCRUMB_PATH = Path.home() / ".aki" / "last-project.json"


def _breadcrumb_path() -> Path:
    # Recomputed per call so a monkeypatched HOME is honored in tests.
    return Path.home() / ".aki" / "last-project.json"


def write_breadcrumb(root_path: Path) -> None:
    """Best-effort persist of the last resolved project root. Never raises."""
    try:
        resolved = root_path.resolve(strict=False)
        target = _breadcrumb_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "root_path": str(resolved),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        target.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        return  # fail-soft: breadcrumb is an optimization, never a hard dep


def read_breadcrumb() -> Optional[Path]:
    """Return the stored project root if present AND still on disk, else None."""
    try:
        raw = _breadcrumb_path().read_text(encoding="utf-8")
        root = Path(json.loads(raw)["root_path"])
        return root if root.is_dir() else None
    except Exception:
        return None
```

Design notes:
- `read_breadcrumb` performs the on-disk existence check (`is_dir()`) so the
  config integration stays a single additive branch and the "stale/deleted
  project" risk (proposal risk table row 1) is handled at the source.
- Every failure mode — missing file, corrupt JSON, missing key, unreadable dir,
  unwritable HOME — collapses to `None` (read) or a no-op (write). No exception
  ever crosses the boundary. This is the load-bearing invariant the write call
  sites rely on to remain safe.
- `_breadcrumb_path()` is recomputed each call (not the module-level constant) so
  `HOME` monkeypatching works; the module constant is kept only for readability.

---

## 4. Write call sites — DECISION (both, each narrowed to genuine roots)

The proposal lists two write sites. Design refines each so a breadcrumb is
written **only when a real filesystem project root is positively resolved**,
never on name-only fallbacks.

### 4a. Cockpit — `build_cockpit_snapshot`, NOT `resolve_project_ref`

`resolve_project_ref()` (cockpit.py:189) is a **pure resolver** — callers invoke
it to decide, and it may run in read-only contexts. Writing there couples a side
effect to a query.

The correct write moment is `build_cockpit_snapshot(...)` under the existing
`if record_open:` gate (cockpit.py:210-211), co-located with
`registry.upsert_project(...)`. That gate already means "the user is opening this
project" — the precise, already-established positive-resolution + open event, and
it has `project.root_path` in hand. This mirrors the registry write exactly.

```python
    if record_open:
        registry.upsert_project(project.key, project.root_path, source=project.source)
        write_breadcrumb(project.root_path)   # best-effort, fail-soft
```

### 4b. MCP — `detect_project`, guarded to the git-root branch only

`detect_project()` (mcp/project.py:10) is a pure, side-effect-free resolver **and
returns a name (str), not a path**. Its cwd-name and `"default"` fallbacks are
NOT real project roots, so they must not seed a breadcrumb.

We add a write **only inside the `if git_root and git_root.name:` branch**, where
a genuine repository root is proven, using `git_root` (a `Path`) as `root_path`:

```python
    git_root = _find_git_root(current)
    if git_root and git_root.name:
        write_breadcrumb(git_root)   # best-effort, fail-soft
        return git_root.name
```

Justification for accepting a controlled side effect in an otherwise-pure MCP
resolver: MCP servers are the flow **most likely** to be launched from an
arbitrary cwd, so MCP-only sessions are exactly the bootstrap case this change
targets. Skipping MCP would leave MCP-only users without a breadcrumb forever.
The side effect is fail-soft (cannot raise, cannot slow the caller meaningfully)
and fires only on a proven root — an acceptable, bounded exception to the purity
of this function, documented here as an ADR (§7, ADR-3).

Both writes are additive single lines; neither changes existing return values or
control flow.

---

## 5. Read integration — `_iter_env_search_roots` (config.py, ADDITIVE ONLY)

Add the breadcrumb as the **final** candidate, after cwd ancestors and git-root,
because those are more precise and reflect the *current* location; the breadcrumb
is a *historical* guess and must only win when nothing current matches.

Exact edit — one new branch appended immediately before `return roots`:

```python
    git_root = _find_git_root(cwd)
    if git_root is not None:
        add_root(git_root)

    breadcrumb_root = read_breadcrumb()        # NEW: last-resort candidate
    if breadcrumb_root is not None:            # NEW
        add_root(breadcrumb_root)              # NEW

    return roots
```

Plus one import at module top: `from agentos.core.project_breadcrumb import read_breadcrumb`.

This is the entire authorized edit to `config.py`: one import + one three-line
branch. No change to `MemoryConfig.db_path`, no default changes, no restructuring
of `_iter_env_search_roots`. `add_root` already dedups (resolved-path `seen` set),
so if the breadcrumb equals an already-added root it is harmlessly skipped, and
it always lands last in `roots`, giving it lowest `.env` search priority. Removing
these four lines restores exact prior behavior (rollback plan holds).

---

## 6. Data flow

```
Positive resolution (write side)
  cockpit: build_cockpit_snapshot(record_open=True) ─┐
  mcp:     detect_project() [git_root branch]        ├─▶ write_breadcrumb(root)
                                                      │        │
                                                      ▼        ▼
                                          ~/.aki/last-project.json

Bootstrap (read side)
  load_runtime_env(start)
    └─ _iter_env_search_roots(start)
         1. start ancestors        (most precise)
         2. cwd ancestors
         3. git-root of cwd
         4. read_breadcrumb()      (last resort ← NEW)
    └─ first root containing .env wins → load_dotenv(...)
```

Precedence is strictly monotonic: the breadcrumb can only supply a root when the
current cwd/git context yields no `.env`, exactly the "unrelated cwd" case.

---

## 7. ADR log

**ADR-1 — File breadcrumb over reusing the DB registry.**
Chosen: single JSON file. Rejected: `ProjectRefModel` DB registry, and anchoring
`db_path` globally (Option 1). The DB path is itself cwd-relative and unresolved
*before* project identity is known — a genuine bootstrap chicken-and-egg the DB
cannot solve for itself (exploration §5). Option 1 is the superior long-term fix
but structurally edits off-limits `config.py` defaults and carries DB-migration
implications; deferred to a separate signed-off change.

**ADR-2 — `~/.aki/last-project.json`, not XDG.**
See §1. Disproportionate ceremony for one field; no XDG precedent; matches
existing `Path.home()` convention and user framing.

**ADR-3 — Write from MCP `detect_project` despite its pure-resolver design.**
Accepted a bounded, fail-soft side effect on the proven-git-root branch only,
because MCP is the flow most likely launched from an unrelated cwd and thus the
primary bootstrap beneficiary. Name-only fallbacks deliberately excluded.

**ADR-4 — Write from `build_cockpit_snapshot`, not `resolve_project_ref`.**
Keeps the resolver pure; co-locates the write with the existing `record_open`
registry write, the true "project opened" event, which already holds `root_path`.

**ADR-5 — Existence check lives in `read_breadcrumb`, not config.**
Keeps the `config.py` edit to a single additive branch and centralizes the
stale-pointer mitigation in the module that owns the format.

---

## 8. Test strategy (strict TDD, `.venv/bin/python -m pytest -q`)

### Unit — `project_breadcrumb` in isolation (`tmp_path` + `monkeypatch` HOME)
Write tests first; each drives one behavior of the new module:
1. `write` then `read` round-trips to the same resolved `root_path`.
2. `read` returns `None` when no file exists.
3. `read` returns `None` on corrupt/invalid JSON.
4. `read` returns `None` when stored `root_path` no longer exists on disk.
5. `write` creates `~/.aki/` when absent.
6. `write` is best-effort: an unwritable target (e.g. HOME pointing at a file, or
   `mkdir`/`write_text` patched to raise) does NOT raise — caller sees a no-op.
7. `updated_at` is present and parses as ISO 8601.

### Unit — config candidate ordering (`monkeypatch` HOME + `cwd`)
8. `_iter_env_search_roots` yields the breadcrumb root **last** and only when the
   breadcrumb resolves; asserts additivity + lowest priority.

### Unit — write call sites
9. `detect_project` writes a breadcrumb on the git-root branch; asserts NO write
   on the cwd-name and `"default"` fallbacks.
10. `build_cockpit_snapshot(record_open=True)` writes; `record_open=False` does not.

### Integration — end-to-end bootstrap (`load_runtime_env`)
11. Create a repo dir with a real `.env`; write a breadcrumb pointing at it;
    `chdir` to an **unrelated** tmp dir with no `.git` ancestor and no `.env`;
    assert `load_runtime_env()` loads the repo's `.env` via the breadcrumb.
12. Precedence guard: when the current cwd/git context DOES contain a `.env`, that
    one wins over the breadcrumb (breadcrumb never overrides current context).

Fail-soft assertions (tests 2-6) are the safety contract the write sites depend
on; they are non-negotiable and written before the module body.

---

## 9. Rollback

Delete `project_breadcrumb.py`, the two single-line write calls, and the
four-line config branch (+ its import). `config.py` change is purely additive, so
removal restores exact prior behavior with zero migration.
