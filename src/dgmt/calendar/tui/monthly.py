"""Monthly calendar grid view widget."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import GOOGLE_COLORS


class MonthlyView(Widget):
    """6x7 month grid with day numbers and truncated event summaries."""

    current_date: reactive[datetime] = reactive(datetime.now)
    events: reactive[list[CalendarEvent]] = reactive(list, always_update=True)

    class DaySelected(Message):
        """Emitted when user selects a day to drill into daily view."""

        def __init__(self, date: datetime) -> None:
            super().__init__()
            self.date = date

    DEFAULT_CSS = """
    MonthlyView {
        height: 1fr;
        width: 1fr;
    }

    .month-header {
        text-align: center;
        text-style: bold;
        padding: 1 0;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="month-header", classes="month-header")
        yield VerticalScroll(id="month-grid")

    def watch_current_date(self, date: datetime) -> None:
        self._refresh()

    def watch_events(self, events: list[CalendarEvent]) -> None:
        self._refresh()

    def _refresh(self) -> None:
        header = self.query_one("#month-header", Static)
        header.update(f"[bold]{self.current_date.strftime('%B %Y')}[/bold]")

        grid = self.query_one("#month-grid", VerticalScroll)
        grid.remove_children()

        year, month = self.current_date.year, self.current_date.month
        cal = calendar.Calendar(firstweekday=6)  # Sunday start
        month_days = list(cal.itermonthdays2(year, month))
        today = datetime.now().date()

        # Group events by day
        events_by_day: dict[int, list[CalendarEvent]] = {}
        for event in self.events:
            if event.start:
                d = event.start.day
                events_by_day.setdefault(d, []).append(event)

        # Build calendar text with box drawing
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        col_width = 12

        lines: list[str] = []

        # Header row
        header_line = "┌" + "┬".join("─" * col_width for _ in range(7)) + "┐"
        lines.append(header_line)
        names_line = "│" + "│".join(f" {d:^{col_width - 1}}" for d in day_names) + "│"
        lines.append(f"[bold]{names_line}[/bold]")
        lines.append("├" + "┼".join("─" * col_width for _ in range(7)) + "┤")

        # Week rows
        weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]
        for week_idx, week in enumerate(weeks):
            # Day numbers row
            num_parts = []
            for day_num, _ in week:
                if day_num == 0:
                    num_parts.append(" " * col_width)
                else:
                    is_today = (
                        year == today.year
                        and month == today.month
                        and day_num == today.day
                    )
                    if is_today:
                        cell = f"[bold $accent] {day_num:<{col_width - 1}}[/bold $accent]"
                    else:
                        cell = f" {day_num:<{col_width - 1}}"
                    num_parts.append(cell)
            lines.append("│" + "│".join(num_parts) + "│")

            # Event rows (up to 2 per cell)
            for row in range(2):
                event_parts = []
                for day_num, _ in week:
                    if day_num == 0:
                        event_parts.append(" " * col_width)
                    else:
                        day_evts = events_by_day.get(day_num, [])
                        if row < len(day_evts):
                            ev = day_evts[row]
                            summary = ev.summary[:col_width - 2]
                            style = self._event_style(ev)
                            event_parts.append(f" [{style}]{summary:<{col_width - 1}}[/{style}]")
                        elif row == 2 and len(day_evts) > 2:
                            extra = f" +{len(day_evts) - 2} more"
                            event_parts.append(f"[dim]{extra:<{col_width}}[/dim]")
                        else:
                            event_parts.append(" " * col_width)
                lines.append("│" + "│".join(event_parts) + "│")

            # Row separator
            if week_idx < len(weeks) - 1:
                lines.append("├" + "┼".join("─" * col_width for _ in range(7)) + "┤")

        # Bottom border
        lines.append("└" + "┴".join("─" * col_width for _ in range(7)) + "┘")

        content = "\n".join(lines)
        grid.mount(Static(content, id="month-content"))

    @staticmethod
    def _event_style(event: CalendarEvent) -> str:
        if event.color_id and event.color_id in GOOGLE_COLORS:
            _, hex_color, _ = GOOGLE_COLORS[event.color_id]
            return f"bold {hex_color}"
        return "bold"
