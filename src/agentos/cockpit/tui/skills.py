"""Skills tab — read-only browser/search for the agent's runtime skills & tools."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static

from agentos.skills.base import Skill, get_skill_registry


def _skill_tools(skill: Skill) -> list[dict]:
    """Return the OpenAI-style tool definitions exposed by a skill."""
    tools = []
    for fn_name in skill.functions:
        tool = skill.get_openai_tool(fn_name)
        if tool:
            tools.append(tool)
    return tools


class SkillCard(ListItem):
    """A single skill entry in the list."""

    def __init__(self, skill: Skill) -> None:
        super().__init__()
        self.skill = skill

    def compose(self) -> ComposeResult:
        status = "[$success]●[/]" if self.skill.enabled else "[$text-muted]○[/]"
        yield Label(
            f"{status} [bold]{self.skill.name}[/bold]\n"
            f"[dim]{self.skill.description or 'No description'}[/dim]",
            markup=True,
        )


class SkillsTab(Widget):
    """Read-only browser for registered skills/tools, with live search."""

    DEFAULT_CSS = """
    SkillsTab {
        height: 1fr;
        width: 1fr;
        layout: vertical;
    }
    #skills-header {
        height: 3;
        background: $panel;
        border-bottom: solid $accent;
        padding: 1 2;
        color: $text;
    }
    #skills-search {
        height: 3;
        background: $panel;
        border-bottom: solid $accent-darken-1;
        padding: 0 1;
    }
    #skills-body {
        height: 1fr;
        layout: horizontal;
    }
    #skills-list-pane {
        width: 40%;
        height: 1fr;
        border-right: solid $accent-darken-1;
    }
    #skills-list-pane ListView {
        height: 1fr;
        overflow-y: auto;
    }
    SkillCard {
        margin: 0 0 1 0;
        padding: 1 1;
        border: solid $panel-lighten-1;
    }
    #skills-detail-pane {
        width: 60%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    .skills-empty {
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._registry = get_skill_registry()
        self._filter = ""

    def compose(self) -> ComposeResult:
        skills = self._registry.list(enabled_only=False)
        yield Static(
            f"[bold]🧩 Skills[/bold]  [white]{len(skills)}[/white] registered",
            id="skills-header",
            markup=True,
        )
        with Horizontal(id="skills-search"):
            yield Input(placeholder="Search skills / tools…", id="skills-search-input")
        with Horizontal(id="skills-body"):
            with Vertical(id="skills-list-pane"):
                yield ListView(*self._build_cards(skills), id="skills-list")
            with ScrollableContainer(id="skills-detail-pane"):
                yield Static(self._detail_text(skills[0] if skills else None), markup=True)

    def _build_cards(self, skills: list[Skill]) -> list[SkillCard]:
        return [SkillCard(s) for s in skills]

    def _matching_skills(self) -> list[Skill]:
        skills = self._registry.list(enabled_only=False)
        q = self._filter.strip().lower()
        if not q:
            return skills
        out = []
        for s in skills:
            haystack = f"{s.name} {s.description}".lower()
            if q in haystack:
                out.append(s)
                continue
            for fn_name in s.functions:
                if q in fn_name.lower():
                    out.append(s)
                    break
        return out

    def _detail_text(self, skill: Skill | None) -> str:
        if skill is None:
            return "[dim]No skill selected.[/dim]"

        status = "[$success]enabled[/]" if skill.enabled else "[$text-muted]disabled[/]"
        lines = [
            f"[bold $accent]{skill.name}[/bold $accent]  ({status})",
            "",
            skill.description or "[dim]No description[/dim]",
            "",
            "[bold]Tools[/bold]",
        ]
        tools = _skill_tools(skill)
        if not tools:
            lines.append("[dim]No callable tools exposed.[/dim]")
        for tool in tools:
            fn = tool.get("function", {})
            name = fn.get("name", "?")
            desc = fn.get("description", "") or "[dim]No description[/dim]"
            destructive = " [$error](destructive)[/]" if fn.get("destructive") else ""
            lines.append(f"\n[bold]• {name}[/bold]{destructive}")
            lines.append(f"  {desc}")
            params = fn.get("parameters", {}).get("properties", {})
            required = set(fn.get("parameters", {}).get("required", []))
            if params:
                lines.append("  [dim]Parameters:[/dim]")
                for pname, pschema in params.items():
                    ptype = pschema.get("type", "any")
                    req = " [dim](required)[/dim]" if pname in required else ""
                    lines.append(f"    - {pname}: {ptype}{req}")
        return "\n".join(lines)

    def _refresh_list(self) -> None:
        skills = self._matching_skills()
        lv = self.query_one("#skills-list", ListView)
        lv.clear()
        for card in self._build_cards(skills):
            lv.append(card)
        detail = self.query_one("#skills-detail-pane Static", Static)
        detail.update(self._detail_text(skills[0] if skills else None))

    @on(Input.Changed, "#skills-search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._filter = event.value
        self._refresh_list()

    @on(ListView.Highlighted, "#skills-list")
    def _on_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if isinstance(item, SkillCard):
            detail = self.query_one("#skills-detail-pane Static", Static)
            detail.update(self._detail_text(item.skill))
