"""Main Calendar TUI application."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static
from textual.worker import Worker, WorkerState

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
        # View switching
        Binding("d", "switch_view('daily')", "Daily", priority=True),
        Binding("w", "switch_view('weekly')", "Weekly", priority=True),
        Binding("m", "switch_view('monthly')", "Monthly", priority=True),
        # Vim-style day navigation
        Binding("h", "nav_day(-1)", "-1 day", priority=True),
        Binding("l", "nav_day(1)", "+1 day", priority=True),
        # Vim-style unit navigation (week/month depending on view)
        Binding("H", "nav_unit(-1)", "-1 unit", priority=True, key_display="Shift+H"),
        Binding("L", "nav_unit(1)", "+1 unit", priority=True, key_display="Shift+L"),
        # CRUD
        Binding("n", "new_event", "New", priority=True),
        Binding("e", "edit_event", "Edit", priority=True),
        Binding("x", "delete_event", "Delete", priority=True),
        # Navigation
        Binding("t", "go_today", "Today", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._api = CalendarAPI()
        self._current_view = "weekly"
        self._current_date = datetime.now()
        self._events: list[CalendarEvent] = []
        self._color_engine = self._load_color_engine()
        # Cache: (start, end) -> events list
        self._cache: dict[tuple[str, str], list[CalendarEvent]] = {}
        # Track the currently loaded date range so we know when to re-fetch
        self._loaded_start: Optional[datetime] = None
        self._loaded_end: Optional[datetime] = None
        self._fetching = False

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
        # Eagerly build the service object in a worker so first fetch is faster
        self.run_worker(self._warm_api, thread=True)
        self._switch_to_view(self._current_view)
        self._fetch_events()

    def _warm_api(self) -> None:
        """Pre-build the API service object in a background thread."""
        self._api._get_service()

    def _update_status(self, loading: bool = False) -> None:
        """Update the status bar with current date range and view mode."""
        status = self.query_one("#status-bar", Static)
        view_label = self._current_view.capitalize()
        date_str = self._current_date.strftime("%B %d, %Y")
        nav_hint = "h/l=day  H/L="
        if self._current_view == "daily":
            nav_hint += "day"
        elif self._current_view == "weekly":
            nav_hint += "week"
        else:
            nav_hint += "month"
        loading_str = "  [dim italic]loading...[/dim italic]" if loading else ""
        status.update(
            f" [bold]{view_label} View[/bold] | {date_str}  "
            f"[dim]({nav_hint})[/dim]{loading_str}"
        )

    def _get_view_range(self) -> tuple[datetime, datetime]:
        """Calculate start/end for the current view and date."""
        start = self._current_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._current_view == "daily":
            end = start + timedelta(days=1)
        elif self._current_view == "weekly":
            weekday = start.weekday()
            start = start - timedelta(days=(weekday + 1) % 7)
            end = start + timedelta(days=7)
        else:  # monthly
            start = start.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)

        return start, end

    def _date_in_loaded_range(self) -> bool:
        """Check if the current date is within the already-loaded range."""
        if self._loaded_start is None or self._loaded_end is None:
            return False
        current = self._current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._loaded_start <= current < self._loaded_end

    def _fetch_events(self, force: bool = False) -> None:
        """Fetch events, using cache when possible, async worker for network."""
        start, end = self._get_view_range()
        cache_key = (start.isoformat(), end.isoformat())

        # Check cache first
        if not force and cache_key in self._cache:
            self._events = self._cache[cache_key]
            self._loaded_start = start
            self._loaded_end = end
            self._push_events_to_view()
            return

        # For day navigation within an already-loaded range, just update the view
        # (the events are already loaded, we just need to re-render with new selected date)
        if not force and self._date_in_loaded_range() and self._events:
            self._push_events_to_view()
            return

        # Need to fetch from API — do it in a background worker
        self._update_status(loading=True)
        self._fetching = True

        def do_fetch(start_dt: datetime, end_dt: datetime) -> list[CalendarEvent]:
            return self._api.list_events(start=start_dt, end=end_dt)

        worker = self.run_worker(
            lambda: do_fetch(start, end),
            thread=True,
            name="fetch_events",
        )
        # Store range info for the callback
        worker._dgmt_start = start  # type: ignore[attr-defined]
        worker._dgmt_end = end  # type: ignore[attr-defined]
        worker._dgmt_cache_key = cache_key  # type: ignore[attr-defined]

    def _push_events_to_view(self) -> None:
        """Update the current view widget with events."""
        container = self.query_one("#view-container", Vertical)
        children = list(container.children)
        if children:
            view = children[0]
            if hasattr(view, "current_date"):
                view.current_date = self._current_date
            if hasattr(view, "events"):
                view.events = self._events
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

        # Store the data on the widget before mounting — the on_mount handler
        # will pick it up once the DOM is ready (via _composed flag)
        view._pending_date = self._current_date
        view._pending_events = self._events
        container.mount(view)
        self._update_status()

    def _invalidate_cache(self) -> None:
        """Clear the cache (after mutations)."""
        self._cache.clear()
        self._loaded_start = None
        self._loaded_end = None

    def action_switch_view(self, view_name: str) -> None:
        """Switch between daily/weekly/monthly views."""
        if self._current_view != view_name:
            self._switch_to_view(view_name)
            self._fetch_events()

    def action_nav_day(self, direction: int) -> None:
        """Navigate by day (h/l). Always moves by one day regardless of view."""
        self._current_date += timedelta(days=direction)
        self._fetch_events()

    def action_nav_unit(self, direction: int) -> None:
        """Navigate by view unit (H/L). Day in daily, week in weekly, month in monthly."""
        if self._current_view == "daily":
            self._current_date += timedelta(days=direction)
        elif self._current_view == "weekly":
            self._current_date += timedelta(weeks=direction)
        else:
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
                self._update_status(loading=True)

                def do_create():
                    return self._api.create_event(result)

                def on_created(worker: Worker) -> None:
                    if worker.state == WorkerState.SUCCESS:
                        self.notify(f"Created: {result.summary}", severity="information")
                        self._invalidate_cache()
                        self._fetch_events(force=True)
                    elif worker.state == WorkerState.ERROR:
                        self.notify(f"Failed to create: {worker.error}", severity="error")
                        self._update_status()

                self.run_worker(do_create, thread=True, name="create_event")

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
                self._update_status(loading=True)

                def do_update():
                    return self._api.update_event(result)

                self.run_worker(do_update, thread=True, name="update_event")

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
            self._update_status(loading=True)
            event_id = event.id
            event_summary = event.summary

            def do_delete():
                self._api.delete_event(event_id)
                return event_summary

            self.run_worker(do_delete, thread=True, name="delete_event")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle async worker completion."""
        worker = event.worker

        if worker.name == "fetch_events":
            if event.state == WorkerState.SUCCESS:
                result = worker.result
                start = getattr(worker, "_dgmt_start", None)
                end = getattr(worker, "_dgmt_end", None)
                cache_key = getattr(worker, "_dgmt_cache_key", None)

                if result is not None:
                    self._events = result
                    self._loaded_start = start
                    self._loaded_end = end
                    if cache_key:
                        self._cache[cache_key] = result
                        while len(self._cache) > 10:
                            oldest = next(iter(self._cache))
                            del self._cache[oldest]

                self._fetching = False
                self._push_events_to_view()

            elif event.state == WorkerState.ERROR:
                self._fetching = False
                self.notify(f"Failed to fetch events: {worker.error}", severity="error")
                self._update_status()

        elif worker.name == "create_event":
            if event.state == WorkerState.SUCCESS:
                self.notify(f"Created event", severity="information")
                self._invalidate_cache()
                self._fetch_events(force=True)
            elif event.state == WorkerState.ERROR:
                self.notify(f"Failed to create: {worker.error}", severity="error")
                self._update_status()

        elif worker.name == "update_event":
            if event.state == WorkerState.SUCCESS:
                self.notify(f"Updated event", severity="information")
                self._invalidate_cache()
                self._fetch_events(force=True)
            elif event.state == WorkerState.ERROR:
                self.notify(f"Failed to update: {worker.error}", severity="error")
                self._update_status()

        elif worker.name == "delete_event":
            if event.state == WorkerState.SUCCESS:
                self.notify(f"Deleted: {worker.result}", severity="information")
                self._invalidate_cache()
                self._fetch_events(force=True)
            elif event.state == WorkerState.ERROR:
                self.notify(f"Failed to delete: {worker.error}", severity="error")
                self._update_status()

    def on_monthly_view_day_selected(self, message: MonthlyView.DaySelected) -> None:
        """Handle day selection in monthly view -> switch to daily."""
        self._current_date = message.date
        self._switch_to_view("daily")
        self._fetch_events()
