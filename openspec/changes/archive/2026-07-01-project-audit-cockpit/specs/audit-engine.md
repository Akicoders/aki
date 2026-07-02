# Delta for `aki audit <project>` Read-Only Audit Engine

## ADDED Requirements

### Requirement: Read-Only Audit Passes

The system MUST run named specialized audit passes (test/runtime, SDD completeness, git hygiene, env/config, MCP readiness, memory posture), each owning one technical area, with no code modification or side effects other than the audit's own artifact outputs.

#### Scenario: Test/runtime pass reuses CodeIntelSkill

- WHEN the test/runtime pass runs
- THEN it invokes `CodeIntelSkill.run_tests`, `run_lint`, and `get_coverage` rather than shelling out independently

#### Scenario: Audit performs no unrelated writes

- GIVEN `aki audit <project>` runs to completion
- WHEN the project's filesystem is inspected afterward
- THEN the only new/modified files are the audit's own markdown report and any explicit persistence artifacts

### Requirement: Uniform AuditFinding Schema

Every audit pass MUST emit findings using the same `AuditFinding` schema: `priority`, `category`, `title`, `evidence`, `recommendation`, `autofixable_later`.

#### Scenario: All passes conform to schema

- GIVEN any audit pass produces one or more findings
- WHEN the findings are collected
- THEN each finding has all six `AuditFinding` fields populated (not null/missing)

#### Scenario: Empty pass produces no findings without error

- GIVEN a pass finds no issues in its area
- WHEN the merger runs
- THEN that pass contributes zero findings and does not fail the overall audit

#### Scenario: Pass execution failure is isolated

- GIVEN one audit pass raises an internal error
- WHEN the audit runs
- THEN that pass's failure is captured as an `audit pass failure`, other passes still run, and the report notes the failed pass and area

### Requirement: Deterministic Merge and Priority Ranking

The system MUST merge findings from all passes deterministically into P0-P3 priority groups, independent of pass execution order.

#### Scenario: Same findings produce same report ordering across runs

- GIVEN an identical set of findings from two audit runs
- WHEN each run's report is generated
- THEN the priority table ordering is identical between runs

### Requirement: Markdown Report Generation

The system MUST write a markdown report to `docs/audits/YYYY-MM-DD-<project>-audit.md` containing: executive summary, snapshot metadata, P0-P3 priority tables, findings by area, recommended next actions, and an evidence appendix.

#### Scenario: Report contains all required sections

- WHEN `aki audit <project>` completes successfully
- THEN the generated markdown file contains all six required sections in order

### Requirement: Dual-Sink Persistence

The system MUST persist the audit to both a local markdown file and Engram (`audit/<project>/<timestamp>` immutable record plus `audit/<project>/latest` pointer). If either sink fails, the command MUST exit non-zero and report the failed stage while preserving whatever partial artifact was produced.

#### Scenario: Both sinks succeed

- GIVEN both markdown write and Engram write succeed
- WHEN `aki audit <project>` completes
- THEN the command exits 0 and both artifacts are retrievable

#### Scenario: Local write succeeds, Engram write fails

- GIVEN the markdown file is written successfully
- WHEN the Engram persistence call fails
- THEN the command exits non-zero, reports "Engram persistence failed" as the failed stage, and the markdown file remains on disk

#### Scenario: Engram write succeeds, local write fails

- GIVEN the Engram record is persisted successfully
- WHEN the local markdown write fails
- THEN the command exits non-zero and reports "local markdown persistence failed" as the failed stage

### Requirement: Error Handling — Failure Classes

The system MUST classify audit-time failures into: project resolution failure, health probe failure, audit pass failure, and persistence failure, each surfacing a precise operator-facing message and impacted area.

#### Scenario: Project resolution failure

- GIVEN `aki audit <project>` is invoked with an unresolvable project reference
- WHEN resolution fails
- THEN the command exits non-zero with a "project resolution failure" message and does not attempt any passes

#### Scenario: Health probe failure during audit context build

- GIVEN one health probe used to build snapshot metadata fails
- WHEN the audit runs
- THEN that probe's status is marked `unknown`/`failing` in snapshot metadata, and the audit still proceeds with remaining passes
