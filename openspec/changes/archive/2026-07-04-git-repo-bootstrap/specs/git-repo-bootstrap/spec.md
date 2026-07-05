# Git Repo Bootstrap Specification

## Purpose

Define safe, first-class repository inspection and bootstrap behavior for version-control requests inside the existing single-agent runtime.

## Requirements

### Requirement: Honest Repository Status Inspection

The system MUST inspect repository state through `GitOpsSkill` and MUST report when a target path is not a git repository without pretending that status was read successfully.

#### Scenario: Existing repo uses status flow (`unit`)

- GIVEN a path inside an existing git repository
- WHEN `git_ops.status` is called
- THEN the result MUST report `success: true`
- AND it MUST include repository state fields usable by the current status flow

#### Scenario: Missing repo is reported honestly (`unit`)

- GIVEN a path that exists but is not a git repository
- WHEN `git_ops.status` is called
- THEN the result MUST report `success: false`
- AND the error MUST clearly state that the path is not a git repository

### Requirement: Safe Git Repository Initialization

The system MUST expose a real git initialization capability backed by git tooling, not filesystem writes into `.git/*` paths.

#### Scenario: Initialize repo in non-repo folder (`unit`)

- GIVEN an existing folder that is not a git repository
- WHEN `git_ops.init` is called for that folder
- THEN the result MUST report `success: true`
- AND a subsequent `git_ops.status` call for that folder MUST succeed

#### Scenario: Existing repo is not reinitialized unsafely (`unit`)

- GIVEN a path that is already a git repository
- WHEN `git_ops.init` is called
- THEN the result MUST report `success: true`
- AND it MUST indicate the repository already existed instead of rewriting `.git` manually

### Requirement: Version-Control Intent Guidance

The system MUST detect repo/version-control intent phrasing in `_build_messages` and add guidance that prefers `git_ops.status` and `git_ops.init` over filesystem writes.

#### Scenario: Spanish version-control phrase injects git guidance (`unit`)

- GIVEN a user input containing `quiero versionamiento` or `poné git en el proyecto`
- WHEN `_build_messages` assembles the turn
- THEN it MUST append a system message instructing the model to inspect repo state with `git_ops.status`
- AND when the folder is not a repo and the user wants version control enabled, it MUST prefer `git_ops.init` over `filesystem.write`/`append`/`delete`

#### Scenario: Repo-status phrasing injects the same guidance (`unit`)

- GIVEN a user input containing `revisar el estado del repo`
- WHEN `_build_messages` assembles the turn
- THEN the git-guidance system message MUST be appended

### Requirement: Agent Git Tool Path Stays Off Filesystem Bootstrap

For version-control bootstrap flows, the agent MUST be able to complete a model-selected git status/init path without invoking filesystem write tools.

#### Scenario: Status then init avoids filesystem writes (`unit`)

- GIVEN a reasoning loop where the model first emits `git_ops_status` for a non-repo folder and then emits `git_ops_init`
- WHEN the loop executes those tool calls
- THEN the git tools MUST be executed in order
- AND `filesystem.write` MUST NOT be executed as part of the bootstrap flow
