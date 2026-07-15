from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog

class ChatTab(Vertical):
    """The Agent Chat tab."""
    
    def compose(self) -> ComposeResult:
        self.log_widget = RichLog(id="chat-log", highlight=True, markup=True)
        self.input_widget = Input(placeholder="Type a message to the agent...", id="chat-input")
        yield self.log_widget
        yield self.input_widget
        
    def on_mount(self) -> None:
        self.log_widget.write("[bold green]Agent:[/bold green] Hello! I am the Aki interactive agent. How can I help you today?")
        
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.log_widget.write(f"[bold cyan]You:[/bold cyan] {event.value}")
            self.input_widget.value = ""
            # Placeholder for agent response logic
            self.log_widget.write("[bold green]Agent:[/bold green] I received your message! (I am a UI placeholder for now)")
