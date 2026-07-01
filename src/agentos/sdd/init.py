"""Initialize SDD directory structure and template files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


TEMPLATES = {
    "proposal.md": """# Proposal: [Change Name]

## Intent
[What problem are you solving and why?]

## Scope
[What is in scope? What is explicitly out?]

## Approach
[High-level technical approach]

## Risks
- [Known risks and mitigations]
""",
    "spec.md": """# Specification: [Change Name]

## Requirements

### Requirement: [Name]
[Description of the requirement]

#### Scenario: [Scenario name]
- **Given** [precondition]
- **When** [action]
- **Then** [expected outcome]
""",
    "design.md": """# Design: [Change Name]

## Technical Approach
[Detailed technical design]

## Architecture Decisions
| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| [decision] | [why] | [what else was considered] |

## Data Model
[Schema changes, new models]

## API Changes
[New or modified endpoints]
""",
    "tasks.md": """# Tasks: [Change Name]

## Phase 1: [Phase name]
- [ ] 1.1 [Task description]
- [ ] 1.2 [Task description]

## Phase 2: [Phase name]
- [ ] 2.1 [Task description]
- [ ] 2.2 [Task description]
""",
}


def init_sdd_project(project_dir: Optional[Path] = None) -> tuple[Path, list[str]]:
    root = project_dir or Path.cwd()
    sdd_dir = root / "docs" / "sdd"
    sdd_dir.mkdir(parents=True, exist_ok=True)

    created = []
    for filename, content in TEMPLATES.items():
        filepath = sdd_dir / filename
        if not filepath.exists():
            filepath.write_text(content, encoding="utf-8")
            created.append(filename)

    return sdd_dir, created
