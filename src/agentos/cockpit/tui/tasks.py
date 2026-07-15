from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ListView, ListItem, Label

class TaskBoardTab(Vertical):
    """The interactive Task Board tab."""
    
    def compose(self) -> ComposeResult:
        # Interactive placeholder tasks for demonstration
        yield ListView(
            ListItem(Label("[x] Setup Textual environment")),
            ListItem(Label("[x] Create interactive tabs")),
            ListItem(Label("[ ] Connect agent backend to Chat Tab")),
            ListItem(Label("[ ] Implement persistent task storage")),
            id="task-list"
        )
        
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Toggle the checkbox when a task is selected."""
        label = event.item.query_one(Label)
        text = str(label.renderable)
        if text.startswith("[ ]"):
            label.update("[x]" + text[3:])
        elif text.startswith("[x]"):
            label.update("[ ]" + text[3:])
