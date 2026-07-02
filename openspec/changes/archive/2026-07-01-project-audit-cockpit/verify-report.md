# Verify Report: project-audit-cockpit

**Verdict: PASS WITH WARNINGS**

## Test Execution Evidence

`python -m pytest -q` → **136 passed, 0 failed, 0 skipped** (32.80s). Independently confirmed the apply-progress claim of 136/136.

## Task Completion

`openspec/changes/project-audit-cockpit/tasks.md`: 32/32 checkboxes `[x]`, 0 unchecked.

## File Existence Check (no hallucination found)

All claimed files exist with claimed content:
- `src/agentos/memory/models.py` — `ProjectRefModel` (line 169), `ProjectRefRecord` (line 215)
- `src/agentos/cockpit/registry.py` (83 lines)
- `src/agentos/cockpit/navigation.py` (234 lines) — `CockpitUIState`, `run_cockpit_loop`
- `src/agentos/cockpit/audit/base.py` (90 lines)
- `src/agentos/cockpit/audit/passes.py` (233 lines) — 6 passes + `PASS_REGISTRY`
- `src/agentos/cockpit/audit/report.py` (260 lines) — `render_markdown`, `write_markdown_report`, `persist_to_engram`, `persist_audit`
- `tests/unit/test_project_registry.py`, `test_cockpit.py`, `test_navigation.py`, `test_audit_base.py`, `test_audit_passes.py`, `test_audit_report.py`, `test_cli_audit.py` — all present

## Spec Compliance Matrix

### project-registry.md
| Requirement | Status | Evidence |
|---|---|---|
| Persistent ProjectRef Registry | PASS | `ProjectRefModel` table `project_refs`, `registry.py` CRUD, covered by test_project_registry.py |
| `aki projects browse` Listing | PASS | covered in test_cockpit.py browse tests |
| Search and Filter (browse) | PASS | browse-level filter distinct from nav `/` key — covered |
| Select-to-Open | PASS | covered |

### drill-down-nav.md
| Requirement | Status | Evidence |
|---|---|---|
| Prompt-Loop Navigation Mechanism | PASS | `run_cockpit_loop` re-renders via existing Rich helpers; test_navigation.py |
| Keymap (Tab/j/k/Enter/b/g/r/q) | PASS | all keys implemented and exercised in navigation.py lines 179-234 |
| `/` filter key | **WARNING** | `filter_query` is captured on `CockpitUIState` but never applied to `_panel_item_count` or any rendered list — no actual filtering occurs. The nav spec's Keymap requirement says `/` "opens search/filter when relevant" but has **no explicit Given/When/Then scenario** requiring narrowing behavior (unlike the separate browse-level "Search and Filter" requirement, which does have such scenarios and is correctly implemented). Because the spec provides no testable scenario for nav-level filtering, this is not a scenario failure, but it is a real functional gap versus the design intent and is likely to surprise an operator who presses `/` expecting the list to narrow. Flagged as WARNING, not CRITICAL.
| Header Persistence | PASS | `_render_state` always calls `_render_header` first, for every view |

### audit-engine.md
| Requirement | Status | Evidence |
|---|---|---|
| Read-Only Audit Passes | PASS | 6 passes reuse existing helpers; TestsPass bridges CodeIntelSkill via asyncio.run; no unrelated writes confirmed |
| Uniform AuditFinding Schema | PASS | test_audit_passes.py parametrized contract test over full registry |
| Pass execution failure isolation | PASS | `run_registered_passes` wraps each pass, covered by test_audit_base.py |
| Deterministic Merge and Priority Ranking | PASS | `merge_findings` sorts by priority/category/title; determinism test in test_audit_base.py |
| Markdown Report Generation (6 sections in order) | PASS | render_markdown produces sections in order; verified in test_audit_report.py |
| Dual-Sink Persistence | **WARNING (design deviation, not a spec failure)** | See analysis below |
| Non-zero exit on partial persistence failure | PASS | Verified via existing tests: `test_audit_report.py` (`outcome.exit_code != 0` for both local-write and engram-failure paths) and `test_cli_audit.py::test_audit_command_engram_failure_exits_nonzero_but_keeps_markdown` (CLI-level, confirms exit_code != 0 AND markdown file still present). Both failure modes are independently covered — no additional test was needed. |
| Error Handling — Failure Classes | PASS | project resolution failure tested in test_cli_audit.py; health probe failure marked unknown/failing per `_health_to_findings` |

## Dual-Sink Persistence Deviation Analysis (explicitly requested check)

The spec requires persistence to "Engram" as a named external sink. The implementation instead adds a second `scope="audit"` row set inside the *same* `MemoryFactModel` SQLite table already used for the project registry — there is no call to any real external Engram client, because **no such client exists in `aki`'s own runtime** (Engram is only available to the agent building `aki`, not to `aki` itself). This is documented candidly in the apply-progress notes as a "Learned" item.

Assessment: this is a **WARNING**, not a CRITICAL, for these reasons:
- The behavioral contract's four testable properties are all satisfied by the current implementation: (1) immutable timestamped record (`audit/<project>/<timestamp>`, never overwritten — code only inserts if `existing is None`), (2) "latest" pointer record (`audit/<project>/latest`, upserted), (3) failure isolation (persist_audit wraps each sink in its own try/except with distinct failed_stage messages), (4) non-zero exit on partial failure (verified above).
- The only true deviation is the *storage backend identity* — "Engram" is simulated as a second local SQLite scope rather than an independent second datastore. This means the two sinks are not actually independent failure domains (a full disk or DB corruption would take both down together), which weakens the "dual-sink resilience" intent behind the spec, even though the literal scenarios pass.
- Given the absence of a real Engram client anywhere in this codebase's runtime dependencies, and that the design doc's own author flagged this as the single intentional interpretation seam, this is a reasonable and disclosed scope decision rather than a hidden gap. Recommend documenting this explicitly as a known limitation in user-facing docs/help text before archiving, and treating `persist_to_engram` as the swap point if/when a real Engram client is added to `aki`.

## Cross-Cutting Constraint Check (env/config isolation)

`EnvPass.run` calls `_build_env_health(ctx.root_path, ctx.generated_at)`, a pre-existing read-only helper in `cli/cockpit.py` that only inspects `.env`/`.env.example`/`config.yaml` paths, Python version, and `uv` binary presence — it does not import or call `agentos.core.config`'s load/write mechanism (`get_config` is used elsewhere in the codebase, not by this helper). No collision with the concurrent .env-handling agent's work. PASS.

## Naming Collision Check

`ProjectRef` (in-memory dataclass, `cli/cockpit.py:46`) vs. `ProjectRefModel`/`ProjectRefRecord` (persisted SQLAlchemy/Pydantic types, `memory/models.py:169,215`) — three distinct names, no collision. PASS.

## Issues

### CRITICAL
None.

### WARNING
1. **Nav `/` filter is a no-op** (`navigation.py`) — `filter_query` captured but never applied to any panel item list. No spec scenario requires actual filtering at the nav level, so not a scenario failure, but a real functional gap operators will notice. Recommend either implementing it or removing the `/` key from the footer hint until it does something, to avoid operator confusion.
2. **Dual-sink "Engram" persistence is simulated as a second local SQLite scope**, not an independent external store. All testable behavioral properties (immutable + latest + failure isolation + non-zero exit) pass, but the two sinks share a single failure domain, which weakens the spec's implicit resilience intent. Disclosed and reasoned in apply-progress; recommend a follow-up note in user docs.

### SUGGESTION
1. Multiple `datetime.utcnow()` deprecation warnings surfaced during the full suite run (pre-existing in `memory/repository.py`, `registry.py`, and SQLAlchemy's own default binding) — not introduced by this change but visible in the audit's own test run; worth a future cleanup pass since Python 3.14 will eventually remove `utcnow()`.
2. Consider adding a short paragraph to `aki audit --help` or the generated report's Appendix noting that "Engram" persistence currently means a local SQLite `scope=audit` fallback, so operators don't assume it's synced to a remote store.

## Final Verdict

**PASS WITH WARNINGS** — 136/136 tests pass (independently verified), all 32 tasks complete, no CRITICAL issues, no hallucinated files/claims found. Two WARNINGs (nav filter no-op, simulated dual-sink) are disclosed, testable-contract-compliant deviations that should be tracked but do not block archival.
