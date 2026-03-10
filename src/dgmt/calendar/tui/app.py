"""Main Calendar TUI application."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from dgmt.calendar.api import CalendarAPI
from dgmt.calendar.colors import ColorRule, ColorRuleEngine
from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.tui.daily import DailyView
from dgmt.calendar.tui.weekly import WeeklyView
from dgmt.calendar.tui.monthly import MonthlyView
from dgmt.calendar.tui.event_form import EventFormScreen
from dgmt.core.config import load_config


class CalendarApp(App):
    """Interactive Google Calendar TUI."""

    TITLE = "dgmt cal"
    CSS = """
    Screen {
        layout: vertical;
    }

    #status-bar {
        height: 1;
        dock: top;
        background: $primary-background;
        padding: 0 2;
    }

    #view-container {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("d", "switch_view('daily')", "Daily", priority=True),
        Binding("w", "switch_view('weekly')", "Weekly", priority=True),
        Binding("m", "switch_view('monthly')", "Monthly", priority=True),
        Binding("n", "new_event", "New Event", priority=True),
        Binding("e", "edit_event", "Edit", priority=True),
        Binding("delete", "delete_event", "Delete", priority=True),
        Binding("t", "go_today", "Today", priority=True),
        Binding("left", "navigate(-1)", "Prev", priority=True),
        Binding("right", "navigate(1)", "Next", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._api = CalendarAPI()
        self._current_view = "weekly"
        self._current_date = datetime.now()
        self._events: list[CalendarEvent] = []
        self._color_engine = self._load_color_engine()

    def _load_color_engine(self) -> ColorRuleEngine:
        """Load color rules from config."""
        try:
            config = load_config()
            rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
            return ColorRuleEngine(rules)
        except Exception:
            return ColorRuleEngine()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status-bar")
        yield Vertical(id="view-container")
        yield Footer()

    def on_mount(self) -> None:
        self._switch_to_view(self._current_view)
        self._fetch_events()

    def _update_status(self) -> None:
        """Update the status bar with current date range and view mode."""
        status = self.query_one("#status-bar", Static)
        view_label = self._current_view.capitalize()
        date_str = self._current_date.strftime("%B %d, %Y")
        status.update(f" [bold]{view_label} View[/bold] │ {date_str}")

    def _fetch_events(self) -> None:
        """Fetch events for the current view range."""
        start = self._current_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._current_view == "daily":
            end = start + timedelta(days=1)
        elif self._current_view == "weekly":
            # Start from Sunday
            weekday = start.weekday()
            start = start - timedelta(days=(weekday + 1) % 7)
            end = start + timedelta(days=7)
        else:  # monthly
            start = start.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)

        try:
            self._events = self._api.list_events(start=start, end=end)
        except Exception as e:
            self.notify(f"Failed to fetch events: {e}", severity="error")
            self._events = []

        self._push_events_to_view()

    def _push_events_to_view(self) -> None:
        """Update the current view widget with events."""
        container = self.query_one("#view-container", Vertical)
        children = list(container.children)
        if children:
            view = children[0]
            if hasattr(view, "events"):
                view.events = self._events
            if hasattr(view, "current_date"):
                view.current_date = self._current_date
        self._update_status()

    def _switch_to_view(self, view_name: str) -> None:
        """Switch to a different view widget."""
        self._current_view = view_name
        container = self.query_one("#view-container", Vertical)
        container.remove_children()

        if view_name == "daily":
            view = DailyView()
        elif view_name == "weekly":
            view = WeeklyView()
        else:
            view = MonthlyView()

        container.mount(view)
        view.current_date = self._current_date
        view.events = self._events
        self._update_status()

    def action_switch_view(self, view_name: str) -> None:
        """Switch between daily/weekly/monthly views."""
        if self._current_view != view_name:
            self._switch_to_view(view_name)
            self._fetch_events()

    def action_navigate(self, direction: int) -> None:
        """Navigate forward or backward in time."""
        if self._current_view == "daily":
            self._current_date += timedelta(days=direction)
        elif self._current_view == "weekly":
            self._current_date += timedelta(weeks=direction)
        else:
            # Monthly: move by month
            month = self._current_date.month + direction
            year = self._current_date.year
            if month > 12:
                month = 1
                year += 1
            elif month < 1:
                month = 12
                year -= 1
            self._current_date = self._current_date.replace(year=year, month=month, day=1)

        self._fetch_events()

    def action_go_today(self) -> None:
        """Jump to today."""
        self._current_date = datetime.now()
        self._fetch_events()

    def action_new_event(self) -> None:
        """Open new event form."""

        def on_result(result: Optional[CalendarEvent]) -> None:
            if result:
                try:
                    self._api.create_event(result)
                    self.notify(f"Created: {result.summary}", severity="information")
                    self._fetch_events()
                except Exception as e:
                    self.notify(f"Failed to create: {e}", severity="error")

        screen = EventFormScreen(
            color_engine=self._color_engine,
            default_date=self._current_date,
        )
        self.push_screen(screen, on_result)

    def action_edit_event(self) -> None:
        """Edit the first event (simplified - a full impl would track selection)."""
        if not self._events:
            self.notify("No events to edit", severity="warning")
            return

        event = self._events[0]

        def on_result(result: Optional[CalendarEvent]) -> None:
            if result:
                try:
                    self._api.update_event(result)
                    self.notify(f"Updated: {result.summary}", severity="information")
                    self._fetch_events()
                except Exception as e:
                    self.notify(f"Failed to update: {e}", severity="error")

        screen = EventFormScreen(
            event=event,
            color_engine=self._color_engine,
        )
        self.push_screen(screen, on_result)

    def action_delete_event(self) -> None:
        """Delete the first event (simplified)."""
        if not self._events:
            self.notify("No events to delete", severity="warning")
            return

        event = self._events[0]
        if event.id:
            try:
                self._api.delete_event(event.id)
                self.notify(f"Deleted: {event.summary}", severity="information")
                self._fetch_events()
            except Exception as e:
                self.notify(f"Failed to delete: {e}", severity="error")

    def on_monthly_view_day_selected(self, message: MonthlyView.DaySelected) -> None:
        """Handle day selection in monthly view -> switch to daily."""
        self._current_date = message.date
        self._switch_to_view("daily")
        self._fetch_events()
