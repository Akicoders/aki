# Web Endpoints Specification

## Purpose

Defines the read-only HTTP surface of the Aki Cockpit Web UI: project list,
health check, per-project drill-down, and audit report rendering. All
endpoints in this spec are strictly read-only — no request path may mutate
registry state, trigger a persisted audit run, or invoke autofix.

## Requirements

### Requirement: Health check endpoint

The system MUST expose a health check endpoint that confirms the server is
running and can reach the cockpit domain layer.

#### Scenario: Health check succeeds

- GIVEN the web server is running
- WHEN a client requests the health endpoint
- THEN the response has a 200 status
- AND the response body indicates the service is healthy

### Requirement: Project list endpoint

The system MUST expose a JSON endpoint that returns the list of registered
projects using the existing `registry.list_projects` domain function,
without modification to that function's behavior.

#### Scenario: List registered projects

- GIVEN one or more projects exist in the registry
- WHEN a client requests the project list endpoint
- THEN the response has a 200 status
- AND the response body contains a JSON array of project entries matching
  the data returned by `registry.list_projects`

#### Scenario: Empty registry

- GIVEN no projects are registered
- WHEN a client requests the project list endpoint
- THEN the response has a 200 status
- AND the response body contains an empty JSON array

### Requirement: Project drill-down endpoint

The system MUST expose a per-project detail endpoint (JSON and/or
server-rendered HTML) that mirrors the information shown in the 4-panel
terminal cockpit layout, sourced from existing reusable domain data.

#### Scenario: View an existing project's detail

- GIVEN a project identified by `{key}` exists in the registry
- WHEN a client requests the drill-down endpoint for `{key}`
- THEN the response has a 200 status
- AND the response contains the project's panel data (equivalent to the
  terminal cockpit's 4 panels)

#### Scenario: Project not found

- GIVEN no project identified by `{key}` exists in the registry
- WHEN a client requests the drill-down endpoint for `{key}`
- THEN the response has a 404 status
- AND the response body indicates the project was not found

### Requirement: Audit report view endpoint

The system MUST expose a read-only endpoint that renders an existing audit
report (produced by `run_registered_passes` / `render_markdown`) as HTML or
returns it as markdown/JSON, without triggering a new persisted audit run or
any autofix action as a side effect of the GET request.

#### Scenario: View audit report for a project with findings

- GIVEN a project has at least one prior audit finding available via the
  audit domain layer
- WHEN a client requests the audit report endpoint for that project
- THEN the response has a 200 status
- AND the rendered content reflects the existing audit findings
- AND no write, persistence, or autofix action occurs as a result of the
  request

#### Scenario: Audit report requested for unknown project

- GIVEN no project identified by `{key}` exists in the registry
- WHEN a client requests the audit report endpoint for `{key}`
- THEN the response has a 404 status

### Requirement: No mutation endpoints exist

The system MUST NOT expose any endpoint capable of writing to the registry,
persisting a new audit run, or invoking autofix. This applies to all HTTP
methods across all phases of this change.

#### Scenario: No POST/PUT/PATCH/DELETE routes for cockpit data

- GIVEN the full set of routes registered by the web cockpit application
- WHEN the route table is inspected
- THEN no route accepts POST, PUT, PATCH, or DELETE against registry,
  audit, or autofix resources
- AND all cockpit data routes are GET-only

#### Scenario: Autofix is unreachable from the Web UI

- GIVEN the terminal cockpit supports an `--autofix` capability
- WHEN the web cockpit's route table and rendered views are inspected
- THEN no route, form, or link triggers autofix
- AND no autofix-related domain function is invoked from any web handler

### Requirement: Unhandled server errors return a safe response

The system MUST catch unexpected errors in request handlers and return a
generic 500 response rather than leaking stack traces or internal paths to
the client.

#### Scenario: Domain layer raises an unexpected exception

- GIVEN a request triggers an unhandled exception in the domain layer
- WHEN the server processes the request
- THEN the response has a 500 status
- AND the response body does not include a raw Python traceback or internal
  file paths
