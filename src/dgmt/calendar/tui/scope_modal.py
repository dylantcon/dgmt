"""Recurring event scope selection modal."""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Label


class ScopeModalScreen(Screen[Optional[str]]):
    """Modal asking the user how to apply an edit/delete to a recurring event.

    Dismisses with ``"this"``, ``"all"``, or ``None`` (cancelled).
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    ScopeModalScreen {
        align: center middle;
    }

    #scope-container {
        width: 50;
        height: auto;
        border: round white;
        padding: 1 2;
        background: $surface;
    }

    #scope-label {
        width: 1fr;
        text-align: center;
        margin-bottom: 1;
    }

    #scope-buttons {
        height: 3;
        align: center middle;
    }

    #scope-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, action_label: str = "edit") -> None:
        super().__init__()
        self.action_label = action_label

    def compose(self) -> ComposeResult:
        with Vertical(id="scope-container"):
            yield Label(
                f"[bold]This is a recurring event.\n"
                f"How would you like to {self.action_label} it?[/bold]",
                id="scope-label",
            )
            with Horizontal(id="scope-buttons"):
                yield Button("This event", variant="primary", id="scope-this")
                yield Button("All events", variant="warning", id="scope-all")
                yield Button("Cancel", variant="default", id="scope-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scope-this":
            self.dismiss("this")
        elif event.button.id == "scope-all":
            self.dismiss("all")
        elif event.button.id == "scope-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
