"""Daily timeline view widget."""

from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import GOOGLE_COLORS, ColorRuleEngine


class DailyView(Widget):
    """Vertical hour-by-hour timeline for a single day."""

    current_date: reactive[datetime] = reactive(datetime.now)
    events: reactive[list[CalendarEvent]] = reactive(list, always_update=True)

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

    .hour-row {
        height: 3;
        width: 1fr;
    }

    .time-now {
        color: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="day-header", classes="day-header")
        yield VerticalScroll(id="timeline")

    def watch_current_date(self, date: datetime) -> None:
        self._refresh_header()

    def watch_events(self, events: list[CalendarEvent]) -> None:
        self._refresh_timeline()

    def _refresh_header(self) -> None:
        header = self.query_one("#day-header", Static)
        header.update(f"[bold]{self.current_date.strftime('%A, %B %d, %Y')}[/bold]")

    def _refresh_timeline(self) -> None:
        timeline = self.query_one("#timeline", VerticalScroll)
        timeline.remove_children()

        now = datetime.now()
        is_today = self.current_date.date() == now.date()

        # Build event lookup by hour
        events_by_hour: dict[int, list[CalendarEvent]] = {h: [] for h in range(24)}
        all_day_events: list[CalendarEvent] = []

        for event in self.events:
            if event.all_day:
                all_day_events.append(event)
            elif event.start:
                events_by_hour[event.start.hour].append(event)

        lines: list[str] = []

        # All-day events section
        if all_day_events:
            lines.append("┌─── All Day ──────────────────────────────────┐")
            for ev in all_day_events:
                style = self._event_style(ev)
                lines.append(f"│ [{style}]{ev.summary}[/{style}]")
            lines.append("└──────────────────────────────────────────────┘")
            lines.append("")

        # Hour-by-hour timeline
        for hour in range(6, 24):  # 6 AM to 11 PM
            time_label = self._format_hour(hour)
            slot_events = events_by_hour[hour]

            # Current time indicator
            if is_today and hour == now.hour:
                indicator = f"─── ▶ {now.strftime('%I:%M %p')} ───"
                lines.append(f"[bold $accent]{time_label} {indicator}[/bold $accent]")
            else:
                lines.append(f"[cyan]{time_label}[/cyan] ├{'─' * 40}┤")

            if slot_events:
                for ev in slot_events:
                    style = self._event_style(ev)
                    time_range = ""
                    if ev.start and ev.end:
                        time_range = (
                            f"{ev.start.strftime('%I:%M')}-{ev.end.strftime('%I:%M %p')}"
                        )
                    lines.append(f"         │ [{style}]{ev.summary}[/{style}] {time_range}")
                    if ev.location:
                        lines.append(f"         │  📍 {ev.location}")
                    lines.append(f"         │")

        content = "\n".join(lines)
        timeline.mount(Static(content, id="timeline-content"))

        # Scroll to current hour if today
        if is_today:
            self.call_after_refresh(self._scroll_to_now)

    def _scroll_to_now(self) -> None:
        timeline = self.query_one("#timeline", VerticalScroll)
        now = datetime.now()
        # Approximate: each hour block is ~3 lines, starting from hour 6
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
