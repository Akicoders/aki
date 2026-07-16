"""About tab — keyboard reference and feature guide for Aki Cockpit."""
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Markdown

ABOUT_CONTENT = """\
# 🚀 Aki Cockpit

> **Aki** — AI-powered development cockpit built with [Textual](https://textual.textualize.io/).
> Your terminal-native workspace for code, tasks, and AI assistance.

---

## ⌨️ Global Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit the cockpit |
| `Ctrl+S` | Save the current file (Explorer tab) |
| `1` `2` `3` `4` `5` `6` | Jump directly to tab by number |
| `[` | Move active tab one position left |
| `]` | Move active tab one position right |
| `Tab` / `Shift+Tab` | Cycle through interactive elements |
| `Enter` / `Space` | Activate focused button or item |
| `↑` `↓` | Navigate lists |

---

## 📁 Explorer Tab  `1`

File tree + IDE-style editor with syntax highlighting.

| Key | Action |
|-----|--------|
| `Enter` | Open selected file in editor |
| `Ctrl+S` | Save current file |
| `←` `→` | Collapse / expand directory |

**Supported syntax highlighting:** Python, JS/TS, CSS, HTML, JSON, YAML, TOML, SQL, Go, Rust, Java, Bash, XML, Markdown

---

## 💬 Chat Tab  `2`

Multi-session AI agent chat with persistent per-session history.

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `+ New` button | Create a new chat session |
| `🗑 Del` button | Delete active session |
| Click session | Switch to that session |

- Each session stores its **full message history**
- The right sidebar shows a **live task progress summary**
- Message count shown next to each session name

---

## 🗂 Kanban Tab  `3`

Drag-style task board with three columns: **📥 Todo → ⚡ In Progress → ✅ Done**

| Key | Action |
|-----|--------|
| `→` | Promote card to next column |
| `←` | Demote card to previous column |
| `D` | Delete selected card |
| `Enter` in input | Add new card |

- Type card **title** + **category** in the bottom bar and press `+ Add`
- Stats header shows overall progress

---

## 🏃 Runner Tab  `4`

IDE-style file runner with syntax highlighting.

| Key | Action |
|-----|--------|
| `Ctrl+R` | Run selected Python file |
| `▶ Run` button | Same as Ctrl+R |

- Select `.py` → loads in editor with **Python highlighting**, run with Ctrl+R
- Select `.md` → **live Markdown preview** updates as you edit
- Select any other file → loads with auto-detected syntax (if supported)

**Supported languages for run:** Python only (for now).

---

## 📖 SDD Hub Tab  `5`

Read-only architectural document viewer. Navigate your `docs/` folder and render Markdown specs.

| Action | How |
|--------|-----|
| View a doc | Click any `.md` file in the tree |
| Scroll | Mouse wheel or `↑` `↓` |

---

## 🩺 Doctor Tab  `6`

Project health checker — runs async diagnostics and shows results.

| Check | What it verifies |
|-------|-----------------|
| **Structure** | `pyproject.toml`, `README.md`, `.env.example`, `src/`, `tests/` |
| **Syntax** | Compiles all `.py` in `src/` and reports syntax errors |
| **Dependencies** | `textual`, `fastapi`, `httpx`, `pydantic`, `pytest` — with versions |
| **Tests** | Test file count + `pytest --collect-only` summary |
| **Git** | Branch, uncommitted changes, last commit |

Press **🔄 Run Checks** or switch to the tab to run diagnostics.

---

## 🖥️ CLI Commands

```bash
aki cockpit -i            # Launch the interactive TUI
aki cockpit health        # Run health checks (CLI mode)
aki chat                  # Chat with the agent (CLI mode)
aki memory show           # Show agent memory
aki sdd status            # SDD change status
```

---

## 🛠️ About

- **Version:** 0.1.0-beta
- **Framework:** [Textual](https://github.com/Textualize/textual) 8.x
- **Agent:** Qwen via OpenRouter
- **Memory:** Engram MCP
- **Branch:** `feature/cockpit-ui-ux`

*Built for the Qwen Hackathon 2025 🏆*
"""


class AboutTab(Widget):
    """About / help screen for the Aki Cockpit."""

    DEFAULT_CSS = """
    AboutTab {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }
    #about-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 1 4;
    }
    #about-content { height: auto; }
    """

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="about-scroll"):
            yield Markdown(ABOUT_CONTENT, id="about-content")
