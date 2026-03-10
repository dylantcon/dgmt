"""Color picker widget for Google Calendar colors."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from dgmt.calendar.colors import GOOGLE_COLORS


class ColorSwatch(Static):
    """A single color swatch that can be selected."""

    class Selected(Message):
        """Emitted when this swatch is selected."""

        def __init__(self, color_id: str, color_name: str) -> None:
            super().__init__()
            self.color_id = color_id
            self.color_name = color_name

    can_focus = True

    def __init__(self, color_id: str, color_name: str, hex_color: str) -> None:
        super().__init__()
        self.color_id = color_id
        self.color_name = color_name
        self.hex_color = hex_color

    def render(self) -> str:
        return f"████ {self.color_name}"

    def on_mount(self) -> None:
        self.styles.color = self.hex_color
        self.styles.padding = (0, 1)
        self.styles.min_width = 20

    def on_click(self) -> None:
        self.post_message(self.Selected(self.color_id, self.color_name))

    def on_key(self, event) -> None:
        if event.key in ("enter", "space"):
            self.post_message(self.Selected(self.color_id, self.color_name))


class ColorPicker(Widget):
    """Widget for selecting a Google Calendar color."""

    class ColorSelected(Message):
        """Emitted when a color is selected."""

        def __init__(self, color_id: str, color_name: str) -> None:
            super().__init__()
            self.color_id = color_id
            self.color_name = color_name

    selected_color_id: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Select Color:", id="color-picker-title")
            with Vertical(id="color-grid"):
                for cid, (name, hex_color, _) in GOOGLE_COLORS.items():
                    yield ColorSwatch(cid, name, hex_color)
            yield Label("[dim]No color (none)[/dim]", id="color-none")

    def on_mount(self) -> None:
        self.styles.border = ("round", "white")
        self.styles.padding = (1, 2)

    def on_color_swatch_selected(self, message: ColorSwatch.Selected) -> None:
        self.selected_color_id = message.color_id
        self.post_message(self.ColorSelected(message.color_id, message.color_name))

    def on_click(self, event) -> None:
        # Check if "No color" label was clicked
        none_label = self.query_one("#color-none", Label)
        if none_label.region.contains_point(event.screen_offset):
            self.selected_color_id = None
            self.post_message(self.ColorSelected("", "None"))
