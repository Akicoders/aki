# Delta for Drill-Down Keyboard Navigation

## ADDED Requirements

### Requirement: Prompt-Loop Navigation Mechanism

The system MUST implement keyboard navigation as a lightweight interactive prompt loop that re-renders Rich panels after each input, not a persistent full-screen TUI framework. Existing snapshot-based render functions (`render_cockpit_detail`, `render_projects_browse`, overview render) remain the rendering seam; the loop drives which one is invoked next and passes updated `CockpitUIState`.

#### Scenario: Loop renders overview then re-renders on input

- GIVEN the cockpit overview is rendered
- WHEN the operator presses a navigation key
- THEN the loop computes the next `CockpitUIState`, re-invokes the corresponding render function, and redraws the panel

#### Scenario: Non-interactive invocation is unaffected

- GIVEN a Typer subcommand is invoked directly (e.g. `aki cockpit health`)
- WHEN it runs without entering the prompt loop
- THEN the existing static one-shot render output is unchanged (Phase 1/2 behavior preserved)

### Requirement: Keymap

The system MUST support this keymap during the prompt loop: `Tab`/arrow keys move between top-level panels; `j`/`k` move within a panel list; `Enter` opens the selected item/detail view; `b` returns to the previous view; `g` returns to overview; `r` refreshes the current snapshot; `/` opens search/filter when relevant; `q` exits.

#### Scenario: Enter drills into a panel

- GIVEN the overview is shown with a panel focused
- WHEN the operator presses `Enter`
- THEN the corresponding panel detail view renders (overview -> panel detail)

#### Scenario: Enter on a detail item drills further

- GIVEN a panel detail view is shown with an item selected
- WHEN the operator presses `Enter`
- THEN the item detail view renders (panel detail -> item detail), and navigation depth does not exceed this level

#### Scenario: Back returns one level

- GIVEN an item detail view is shown
- WHEN the operator presses `b`
- THEN the previous view (panel detail) renders

#### Scenario: g jumps to overview from any depth

- GIVEN an item detail view is shown
- WHEN the operator presses `g`
- THEN the overview renders directly, skipping intermediate levels

#### Scenario: r refreshes without losing navigation position

- GIVEN a panel detail view is shown
- WHEN the operator presses `r`
- THEN the snapshot is rebuilt and the same view re-renders with updated data

#### Scenario: q exits the loop

- WHEN the operator presses `q` at any view
- THEN the prompt loop exits cleanly with exit code 0

### Requirement: Header Persistence During Navigation

Every drill-down view MUST keep the current project header (name, root path, branch, dirty state, last refresh time) visible.

#### Scenario: Header remains visible in item detail

- GIVEN the operator has drilled into an item detail view
- WHEN that view renders
- THEN the project header panel is still displayed above or alongside the detail content
