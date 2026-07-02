# Web Server Specification

## Purpose

Defines the lifecycle, binding, and safety guarantees of the local HTTP
server that powers `aki cockpit --web`. This spec covers startup, shutdown,
network exposure boundaries, and port-conflict handling. It does not cover
specific endpoint contracts (see `web-endpoints.md`).

## Requirements

### Requirement: CLI entrypoint starts a local web server

The system MUST provide `aki cockpit --web` as a CLI flag symmetric to the
existing `--interactive`/`-i` flag on `cockpit_callback`, which starts a
uvicorn-served FastAPI application instead of the terminal cockpit UI.

#### Scenario: User starts the web cockpit

- GIVEN the `aki` CLI is installed with the web UI dependencies present
- WHEN the user runs `aki cockpit --web`
- THEN a local HTTP server starts and serves the cockpit web application
- AND the terminal cockpit is not launched

#### Scenario: Terminal cockpit remains unaffected

- GIVEN the `aki cockpit --web` flag has been added
- WHEN the user runs `aki cockpit` or `aki cockpit -i` without `--web`
- THEN the existing terminal cockpit behavior is unchanged

### Requirement: Server binds to localhost only by default

The system MUST bind the web server to `127.0.0.1` by default and MUST NOT
bind to `0.0.0.0` or any non-loopback interface unless a future explicit
security-reviewed change opts in.

#### Scenario: Default bind address

- GIVEN no host override is supplied
- WHEN `aki cockpit --web` starts the server
- THEN the server listens only on `127.0.0.1`
- AND the server is unreachable from other hosts on the local network

#### Scenario: Host/port override via additive config surface

- GIVEN the user supplies a host or port override through the dedicated CLI
  flags or settings object (not `core/config.py`)
- WHEN `aki cockpit --web` starts the server
- THEN the server binds to the overridden host/port
- AND the override does not modify `src/agentos/core/config.py`

### Requirement: Server startup reports a clear error on port conflict

The system MUST detect that the target port is already in use and MUST exit
with a clear, actionable error message rather than a raw stack trace.

#### Scenario: Port already bound

- GIVEN another process is already listening on the default or configured
  port
- WHEN the user runs `aki cockpit --web`
- THEN the CLI exits with a non-zero status
- AND prints a message identifying the port conflict and suggesting an
  alternate port flag

### Requirement: Server shuts down cleanly on interrupt

The system MUST stop the uvicorn server and release the bound port when the
user sends an interrupt signal (e.g. Ctrl+C).

#### Scenario: User stops the server

- GIVEN `aki cockpit --web` is running
- WHEN the user sends SIGINT (Ctrl+C)
- THEN the server stops accepting new connections
- AND the process exits
- AND the port is released for reuse

### Requirement: No non-localhost exposure without explicit rationale

The system MUST NOT expose the web cockpit beyond localhost as a default
behavior in this change. Any LAN/remote binding is out of scope for this
change and MUST be a separate, explicitly security-reviewed change.

#### Scenario: Attempt to reach server from another host

- GIVEN `aki cockpit --web` is running with default localhost binding
- WHEN a request originates from a different host on the local network
- THEN the request cannot reach the server (connection refused at the OS
  network layer)
