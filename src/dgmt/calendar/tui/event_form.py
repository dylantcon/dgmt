"""Event create/edit form modal."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static, Select

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import ColorRuleEngine, GOOGLE_COLORS, color_id_from_name, fuzzy_color_match
from dgmt.calendar.tui.color_picker import ColorPicker


# Recurrence presets mapping display name -> RRULE
RECURRENCE_PRESETS: list[tuple[str, str]] = [
    ("None", ""),
    ("Daily", "RRULE:FREQ=DAILY"),
    ("Weekdays (Mon-Fri)", "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
    ("Weekly", "RRULE:FREQ=WEEKLY"),
    ("Biweekly", "RRULE:FREQ=WEEKLY;INTERVAL=2"),
    ("Monthly", "RRULE:FREQ=MONTHLY"),
    ("Yearly", "RRULE:FREQ=YEARLY"),
    ("Custom...", "CUSTOM"),
]


def _parse_recurrence_for_display(recurrence: list[str]) -> tuple[str, str]:
    """Try to match existing recurrence to a preset. Returns (preset_name, raw_rule)."""
    if not recurrence:
        return ("None", "")
    rule = recurrence[0] if recurrence else ""
    for name, rrule in RECURRENCE_PRESETS:
        if rrule and rrule == rule:
            return (name, rule)
    return ("Custom...", rule)


class EventFormScreen(Screen):
    """Modal screen for creating or editing an event."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    EventFormScreen {
        align: center middle;
    }

    #form-container {
        width: 70;
        max-height: 46;
        border: round white;
        padding: 1 2;
        background: $surface;
    }

    .form-row {
        height: 3;
        margin-bottom: 1;
    }

    .form-label {
        width: 14;
        padding: 1 1 0 0;
    }

    .form-input {
        width: 1fr;
    }

    #button-row {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }

    #color-suggestion {
        height: 1;
        margin-bottom: 1;
        color: $accent;
    }

    #color-match-hint {
        height: 1;
        margin-bottom: 1;
        color: $accent;
    }

    #recurrence-custom-row {
        height: 3;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        event: Optional[CalendarEvent] = None,
        color_engine: Optional[ColorRuleEngine] = None,
        default_date: Optional[datetime] = None,
    ) -> None:
        super().__init__()
        self.event = event
        self.color_engine = color_engine or ColorRuleEngine()
        self.default_date = default_date or datetime.now()
        self.selected_color_id: Optional[str] = event.color_id if event else None
        self._is_edit = event is not None and event.id is not None

        # Parse existing recurrence
        existing_recurrence = event.recurrence if event else []
        self._preset_name, self._recurrence_rule = _parse_recurrence_for_display(
            existing_recurrence
        )
        self._show_custom = self._preset_name == "Custom..."
        self._until_value = ""
        self._count_value = ""

        # Try to extract UNTIL or COUNT from existing rule
        if self._recurrence_rule:
            if "UNTIL=" in self._recurrence_rule:
                parts = self._recurrence_rule.split(";")
                for p in parts:
                    if p.startswith("UNTIL="):
                        self._until_value = p.split("=")[1][:10]  # YYYYMMDD -> keep raw
            if "COUNT=" in self._recurrence_rule:
                parts = self._recurrence_rule.split(";")
                for p in parts:
                    if p.startswith("COUNT="):
                        self._count_value = p.split("=")[1]

    def compose(self) -> ComposeResult:
        title = "Edit Event" if self._is_edit else "New Event"
        with Vertical(id="form-container"):
            yield Label(f"[bold]-- {title} --[/bold]", id="form-title")

            with Horizontal(classes="form-row"):
                yield Label("Summary:", classes="form-label")
                yield Input(
                    value=self.event.summary if self.event else "",
                    placeholder="Event title",
                    id="summary-input",
                    classes="form-input",
                )

            yield Static("", id="color-suggestion")

            with Horizontal(classes="form-row"):
                yield Label("Date:", classes="form-label")
                date_val = ""
                if self.event and self.event.start:
                    date_val = self.event.start.strftime("%Y-%m-%d")
                elif self.default_date:
                    date_val = self.default_date.strftime("%Y-%m-%d")
                yield Input(
                    value=date_val,
                    placeholder="YYYY-MM-DD",
                    id="date-input",
                    classes="form-input",
                )

            with Horizontal(classes="form-row"):
                yield Label("Start Time:", classes="form-label")
                start_val = ""
                if self.event and self.event.start and not self.event.all_day:
                    start_val = self.event.start.strftime("%H:%M")
                yield Input(
                    value=start_val,
                    placeholder="HH:MM (24h), blank=all day",
                    id="start-input",
                    classes="form-input",
                )

            with Horizontal(classes="form-row"):
                yield Label("End Time:", classes="form-label")
                end_val = ""
                if self.event and self.event.end and not self.event.all_day:
                    end_val = self.event.end.strftime("%H:%M")
                yield Input(
                    value=end_val,
                    placeholder="HH:MM (24h), blank=start+1h",
                    id="end-input",
                    classes="form-input",
                )

            with Horizontal(classes="form-row"):
                yield Label("Description:", classes="form-label")
                yield Input(
                    value=self.event.description if self.event else "",
                    placeholder="Optional description",
                    id="desc-input",
                    classes="form-input",
                )

            with Horizontal(classes="form-row"):
                yield Label("Location:", classes="form-label")
                yield Input(
                    value=self.event.location if self.event else "",
                    placeholder="Optional location",
                    id="location-input",
                    classes="form-input",
                )

            with Horizontal(classes="form-row"):
                yield Label("Color:", classes="form-label")
                color_name = ""
                if self.selected_color_id and self.selected_color_id in GOOGLE_COLORS:
                    color_name = GOOGLE_COLORS[self.selected_color_id][0]
                yield Input(
                    value=color_name,
                    placeholder="Color name (e.g. Peacock, Tomato)",
                    id="color-input",
                    classes="form-input",
                )

            yield Static("", id="color-match-hint")

            # Recurrence
            with Horizontal(classes="form-row"):
                yield Label("Repeat:", classes="form-label")
                options = [(name, name) for name, _ in RECURRENCE_PRESETS]
                yield Select(
                    options,
                    value=self._preset_name,
                    id="recurrence-select",
                    classes="form-input",
                )

            # Recurrence end condition (until date or count)
            with Horizontal(id="recurrence-custom-row"):
                yield Label("Until:", classes="form-label")
                yield Input(
                    value=self._until_value,
                    placeholder="YYYY-MM-DD (end date) or blank",
                    id="until-input",
                )
                yield Label(" Count:", classes="form-label")
                yield Input(
                    value=self._count_value,
                    placeholder="N times or blank",
                    id="count-input",
                )

            # Custom RRULE input (shown when Custom... is selected)
            with Horizontal(id="custom-rrule-row", classes="form-row"):
                yield Label("RRULE:", classes="form-label")
                yield Input(
                    value=self._recurrence_rule if self._show_custom else "",
                    placeholder="RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR",
                    id="custom-rrule-input",
                    classes="form-input",
                )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        self._update_recurrence_visibility()

    def _update_recurrence_visibility(self) -> None:
        """Show/hide custom RRULE row based on selection."""
        custom_row = self.query_one("#custom-rrule-row")
        custom_row.display = self._show_custom

        # Show until/count row when any recurrence is selected
        until_row = self.query_one("#recurrence-custom-row")
        until_row.display = self._preset_name != "None"

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "recurrence-select":
            self._preset_name = str(event.value)
            self._show_custom = self._preset_name == "Custom..."

            # Look up the RRULE for the selected preset
            for name, rrule in RECURRENCE_PRESETS:
                if name == self._preset_name:
                    if rrule != "CUSTOM":
                        self._recurrence_rule = rrule
                    break

            self._update_recurrence_visibility()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "summary-input":
            summary = event.value
            suggestion = self.query_one("#color-suggestion", Static)
            if summary:
                matches = self.color_engine.match(summary)
                if len(matches) == 1:
                    name = ColorRuleEngine.get_color_name(matches[0].color_id)
                    suggestion.update(f"  Auto-color: {name}")
                    self.selected_color_id = matches[0].color_id
                elif len(matches) > 1:
                    names = ", ".join(ColorRuleEngine.get_color_name(m.color_id) for m in matches)
                    suggestion.update(f"  Multiple matches: {names} (set manually)")
                    self.selected_color_id = None
                else:
                    suggestion.update("")
            else:
                suggestion.update("")

        elif event.input.id == "color-input":
            hint = self.query_one("#color-match-hint", Static)
            match = fuzzy_color_match(event.value)
            if match:
                self.selected_color_id = match.color_id
                if match.match_type == "exact":
                    hint.update(f"  Color: {match.color_name}")
                elif match.match_type == "prefix":
                    hint.update(f"  Matched: {match.color_name}")
                else:
                    hint.update(f"  Did you mean: {match.color_name}?")
            else:
                self.selected_color_id = None
                hint.update("")

        elif event.input.id == "custom-rrule-input":
            self._recurrence_rule = event.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def _build_recurrence(self) -> list[str]:
        """Build recurrence list from form state."""
        if self._preset_name == "None":
            return []

        if self._show_custom:
            rule = self.query_one("#custom-rrule-input", Input).value.strip()
        else:
            rule = self._recurrence_rule

        if not rule:
            return []

        # Append UNTIL or COUNT if specified
        until_str = self.query_one("#until-input", Input).value.strip()
        count_str = self.query_one("#count-input", Input).value.strip()

        if until_str:
            try:
                until_date = datetime.strptime(until_str, "%Y-%m-%d")
                until_formatted = until_date.strftime("%Y%m%dT235959Z")
                if "UNTIL=" not in rule and "COUNT=" not in rule:
                    rule = f"{rule};UNTIL={until_formatted}"
            except ValueError:
                pass  # ignore invalid until date
        elif count_str:
            try:
                count = int(count_str)
                if count > 0 and "COUNT=" not in rule and "UNTIL=" not in rule:
                    rule = f"{rule};COUNT={count}"
            except ValueError:
                pass

        return [rule]

    def _save(self) -> None:
        summary = self.query_one("#summary-input", Input).value.strip()
        if not summary:
            self.notify("Summary is required", severity="error")
            return

        date_str = self.query_one("#date-input", Input).value.strip()
        start_str = self.query_one("#start-input", Input).value.strip()
        end_str = self.query_one("#end-input", Input).value.strip()
        desc = self.query_one("#desc-input", Input).value.strip()
        location = self.query_one("#location-input", Input).value.strip()

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.notify("Invalid date format (use YYYY-MM-DD)", severity="error")
            return

        all_day = not start_str
        if all_day:
            start = date
            end = date + timedelta(days=1)
        else:
            try:
                h, m = map(int, start_str.split(":"))
                start = date.replace(hour=h, minute=m)
            except (ValueError, TypeError):
                self.notify("Invalid start time (use HH:MM)", severity="error")
                return

            if end_str:
                try:
                    h, m = map(int, end_str.split(":"))
                    end = date.replace(hour=h, minute=m)
                except (ValueError, TypeError):
                    self.notify("Invalid end time (use HH:MM)", severity="error")
                    return
            else:
                end = start + timedelta(hours=1)

        recurrence = self._build_recurrence()

        result = CalendarEvent(
            id=self.event.id if self.event else None,
            summary=summary,
            description=desc,
            start=start,
            end=end,
            all_day=all_day,
            location=location,
            color_id=self.selected_color_id,
            calendar_id=self.event.calendar_id if self.event else "primary",
            recurrence=recurrence,
            recurring_event_id=self.event.recurring_event_id if self.event else None,
        )

        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)
