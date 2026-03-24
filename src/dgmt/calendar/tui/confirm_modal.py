"""Generic confirmation modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Label


class ConfirmModalScreen(Screen[bool]):
    """Modal asking the user to confirm a destructive action.

    Dismisses with ``True`` (confirmed) or ``False`` (cancelled).
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    ConfirmModalScreen {
        align: center middle;
    }

    #confirm-container {
        width: 60;
        height: auto;
        border: round white;
        padding: 1 2;
        background: $surface;
    }

    #confirm-label {
        width: 1fr;
        text-align: center;
        margin-bottom: 1;
    }

    #confirm-buttons {
        height: 3;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label(self._message, id="confirm-label")
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="default", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        elif event.button.id == "confirm-no":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
