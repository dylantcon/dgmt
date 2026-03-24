"""Daily timeline view widget."""

from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import GOOGLE_COLORS, ColorRuleEngine

# Background tint for the selected day header
SELECTED_BG = "#2d2030"

# Background tint for the selected *event* — a cooler blue-ish tone
# that is visually distinct from the warm day-selection magenta
SELECTION_BG = "#3a3a5c"


class DailyView(Widget):
    """Vertical hour-by-hour timeline for a single day."""

    current_date: reactive[datetime] = reactive(datetime.now)
    events: reactive[list[CalendarEvent]] = reactive(list, always_update=True)
    selected_event_id: reactive[str | None] = reactive(None)
    loading: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    DailyView {
        height: 1fr;
        width: 1fr;
    }

    .day-header {
        text-align: center;
        text-style: bold;
        padding: 1 0;
        width: 1fr;
    }

    .day-header-today {
        background: #2d2030;
    }

    .hour-row {
        height: 3;
        width: 1fr;
    }

    .time-now {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._composed = False

    def compose(self) -> ComposeResult:
        yield Static("", id="day-header", classes="day-header")
        yield VerticalScroll(id="timeline")

    def on_mount(self) -> None:
        # Set pending data BEFORE marking _composed so watchers skip refresh,
        # then do a single render pass at the end.
        if hasattr(self, "_pending_date"):
            self.current_date = self._pending_date
        if hasattr(self, "_pending_events"):
            self.events = self._pending_events
        if hasattr(self, "_pending_selected_event_id"):
            self.selected_event_id = self._pending_selected_event_id
        if hasattr(self, "_pending_loading"):
            self.loading = self._pending_loading
        self._composed = True
        self._refresh_header()
        self._refresh_timeline()

    def watch_current_date(self, date: datetime) -> None:
        if self._composed:
            self._refresh_header()
            self._refresh_timeline()

    def watch_events(self, events: list[CalendarEvent]) -> None:
        if self._composed:
            self._refresh_timeline()

    def watch_selected_event_id(self, event_id: str | None) -> None:
        if self._composed:
            self._refresh_timeline()

    def watch_loading(self, loading: bool) -> None:
        if self._composed:
            self._refresh_timeline()

    def _refresh_header(self) -> None:
        try:
            header = self.query_one("#day-header", Static)
        except NoMatches:
            return
        is_today = self.current_date.date() == datetime.now().date()
        date_str = self.current_date.strftime("%A, %B %d, %Y")

        if is_today:
            header.update(f"[bold $accent on {SELECTED_BG}] {date_str} [/bold $accent on {SELECTED_BG}]")
            header.add_class("day-header-today")
        else:
            header.update(f"[bold on {SELECTED_BG}] {date_str} [/bold on {SELECTED_BG}]")
            header.remove_class("day-header-today")

    def _refresh_timeline(self, scroll_to_now: bool = True) -> None:
        try:
            timeline = self.query_one("#timeline", VerticalScroll)
        except NoMatches:
            return

        timeline.remove_children()

        now = datetime.now()
        is_today = self.current_date.date() == now.date()

        # Build event lookup by hour
        events_by_hour: dict[int, list[CalendarEvent]] = {h: [] for h in range(24)}
        all_day_events: list[CalendarEvent] = []

        current_day = self.current_date.date()
        for event in self.events:
            if event.all_day:
                if event.start:
                    start_date = event.start.date()
                    end_date = (
                        event.end.date() if event.end else start_date + timedelta(days=1)
                    )
                    if start_date <= current_day < end_date:
                        all_day_events.append(event)
            elif event.start and event.start.date() == current_day:
                events_by_hour[event.start.hour].append(event)

        lines: list[str] = []

        # All-day events section
        if all_day_events:
            lines.append("┌─── All Day ──────────────────────────────────┐")
            for ev in all_day_events:
                is_sel = ev.id is not None and ev.id == self.selected_event_id
                style = self._event_style(ev)
                if is_sel:
                    style += f" on {SELECTION_BG}"
                marker = "▸" if is_sel else " "
                lines.append(f"│{marker}[{style}]{ev.summary}[/{style}]")
            lines.append("└──────────────────────────────────────────────┘")
            lines.append("")

        # Hour-by-hour timeline
        for hour in range(6, 24):  # 6 AM to 11 PM
            time_label = self._format_hour(hour)
            slot_events = events_by_hour[hour]

            # Current time indicator
            if is_today and hour == now.hour:
                indicator = f"─── > {now.strftime('%I:%M %p')} ───"
                lines.append(f"[bold $accent]{time_label} {indicator}[/bold $accent]")
            else:
                lines.append(f"[cyan]{time_label}[/cyan] ├{'─' * 40}┤")

            if slot_events:
                for ev in slot_events:
                    is_sel = ev.id is not None and ev.id == self.selected_event_id
                    style = self._event_style(ev)
                    if is_sel:
                        style += f" on {SELECTION_BG}"
                    marker = "▸" if is_sel else " "
                    time_range = ""
                    if ev.start and ev.end:
                        time_range = (
                            f"{ev.start.strftime('%I:%M')}-{ev.end.strftime('%I:%M %p')}"
                        )
                    lines.append(f"         │{marker}[{style}]{ev.summary}[/{style}] {time_range}")
                    if ev.location:
                        loc_bg = f" on {SELECTION_BG}" if is_sel else ""
                        lines.append(f"         │  [dim{loc_bg}] @ {ev.location}[/dim{loc_bg}]")
                    lines.append(f"         │")

        content = "\n".join(lines)
        timeline.mount(Static(content))

        # Scroll to current hour if today (skip on timer ticks to preserve scroll)
        if is_today and scroll_to_now:
            self.call_after_refresh(self._scroll_to_now)

    def _scroll_to_now(self) -> None:
        try:
            timeline = self.query_one("#timeline", VerticalScroll)
        except NoMatches:
            return
        now = datetime.now()
        target_line = max(0, (now.hour - 6)) * 3
        timeline.scroll_to(y=target_line, animate=False)

    @staticmethod
    def _format_hour(hour: int) -> str:
        if hour == 0:
            return "12:00 AM"
        elif hour < 12:
            return f"{hour:2d}:00 AM"
        elif hour == 12:
            return "12:00 PM"
        else:
            return f"{hour - 12:2d}:00 PM"

    @staticmethod
    def _event_style(event: CalendarEvent) -> str:
        if event.color_id and event.color_id in GOOGLE_COLORS:
            _, hex_color, _ = GOOGLE_COLORS[event.color_id]
            return f"bold {hex_color}"
        return "bold"
