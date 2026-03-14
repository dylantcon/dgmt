"""Monthly calendar grid view widget."""

from __future__ import annotations

import calendar
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import GOOGLE_COLORS

# Background tint for the selected day
SELECTED_BG = "#2d2030"

# Background tint for the selected *event*
SELECTION_BG = "#3a3a5c"


class MonthlyView(Widget):
    """6x7 month grid with day numbers and truncated event summaries."""

    current_date: reactive[datetime] = reactive(datetime.now)
    events: reactive[list[CalendarEvent]] = reactive(list, always_update=True)
    selected_event_id: reactive[str | None] = reactive(None)
    loading: reactive[bool] = reactive(False)

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

    def __init__(self) -> None:
        super().__init__()
        self._composed = False

    def compose(self) -> ComposeResult:
        yield Static("", id="month-header", classes="month-header")
        yield VerticalScroll(id="month-grid")

    def on_mount(self) -> None:
        if hasattr(self, "_pending_date"):
            self.current_date = self._pending_date
        if hasattr(self, "_pending_events"):
            self.events = self._pending_events
        if hasattr(self, "_pending_selected_event_id"):
            self.selected_event_id = self._pending_selected_event_id
        if hasattr(self, "_pending_loading"):
            self.loading = self._pending_loading
        self._composed = True
        self._refresh()

    def watch_current_date(self, date: datetime) -> None:
        if self._composed:
            self._refresh()

    def watch_events(self, events: list[CalendarEvent]) -> None:
        if self._composed:
            self._refresh()

    def watch_selected_event_id(self, event_id: str | None) -> None:
        if self._composed:
            self._refresh()

    def watch_loading(self, loading: bool) -> None:
        if self._composed:
            self._refresh()

    def on_resize(self, event) -> None:
        """Re-render when terminal size changes (page_size depends on height)."""
        if self._composed:
            self._refresh()

    def _refresh(self) -> None:
        try:
            header = self.query_one("#month-header", Static)
        except NoMatches:
            return
        header.update(f"[bold]{self.current_date.strftime('%B %Y')}[/bold]")

        grid = self.query_one("#month-grid", VerticalScroll)
        grid.remove_children()

        # Defer until we have a real layout size (on_resize will call us back)
        if self.size.height == 0:
            return

        year, month = self.current_date.year, self.current_date.month
        cal = calendar.Calendar(firstweekday=6)  # Sunday start
        month_days = list(cal.itermonthdays2(year, month))
        today = datetime.now().date()
        selected = self.current_date.date()

        # Group events by day
        events_by_day: dict[int, list[CalendarEvent]] = {}
        for event in self.events:
            if event.start:
                d = event.start.day
                events_by_day.setdefault(d, []).append(event)

        # Build calendar text with box drawing
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        col_width = 12
        weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]
        num_weeks = len(weeks)
        page_size = self._compute_page_size(num_weeks)

        lines: list[str] = []

        # Header row
        header_line = "┌" + "┬".join("─" * col_width for _ in range(7)) + "┐"
        lines.append(header_line)
        names_line = "│" + "│".join(f" {d:^{col_width - 1}}" for d in day_names) + "│"
        lines.append(f"[bold]{names_line}[/bold]")
        lines.append("├" + "┼".join("─" * col_width for _ in range(7)) + "┤")

        # Week rows
        for week_idx, week in enumerate(weeks):
            # Precompute which page each day shows (only selected day can be >0)
            day_pages: dict[int, int] = {}
            for day_num, _ in week:
                if day_num == 0:
                    continue
                is_sel_day = (
                    year == selected.year
                    and month == selected.month
                    and day_num == selected.day
                )
                if is_sel_day:
                    day_evts = events_by_day.get(day_num, [])
                    day_pages[day_num] = self._page_for_selected_day(
                        day_evts, page_size
                    )
                # Non-selected days default to page 0 via dict.get fallback

            # Day numbers row (with overflow arrows)
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
                    is_sel = (
                        year == selected.year
                        and month == selected.month
                        and day_num == selected.day
                    )

                    # Determine overflow arrow for this cell
                    day_evts = events_by_day.get(day_num, [])
                    page = day_pages.get(day_num, 0)
                    start_idx = page * page_size
                    has_above = start_idx > 0
                    has_below = start_idx + page_size < len(day_evts)

                    if has_above and has_below:
                        arrow = "↕"
                    elif has_above:
                        arrow = "↑"
                    elif has_below:
                        arrow = "↓"
                    else:
                        arrow = ""

                    if arrow:
                        padding = col_width - 3 - len(str(day_num))
                        cell_text = f" {day_num}{' ' * padding}{arrow} "
                    else:
                        cell_text = f" {day_num:<{col_width - 1}}"

                    if is_today and is_sel:
                        cell = f"[bold $accent on {SELECTED_BG}]{cell_text}[/bold $accent on {SELECTED_BG}]"
                    elif is_today:
                        cell = f"[bold $accent]{cell_text}[/bold $accent]"
                    elif is_sel:
                        cell = f"[bold on {SELECTED_BG}]{cell_text}[/bold on {SELECTED_BG}]"
                    else:
                        cell = cell_text
                    num_parts.append(cell)
            lines.append("│" + "│".join(num_parts) + "│")

            # Event rows (page_size rows per cell, showing the active page)
            for row in range(page_size):
                event_parts = []
                for day_num, _ in week:
                    if day_num == 0:
                        event_parts.append(" " * col_width)
                    else:
                        is_sel = (
                            year == selected.year
                            and month == selected.month
                            and day_num == selected.day
                        )
                        day_evts = events_by_day.get(day_num, [])
                        page = day_pages.get(day_num, 0)
                        start_idx = page * page_size
                        visible = day_evts[start_idx:start_idx + page_size]

                        if row < len(visible):
                            ev = visible[row]
                            summary = ev.summary[:col_width - 2]
                            is_sel_event = (
                                ev.id is not None
                                and ev.id == self.selected_event_id
                            )
                            style = self._event_style(ev)
                            if is_sel_event:
                                style += f" on {SELECTION_BG}"
                            elif is_sel:
                                style += f" on {SELECTED_BG}"
                            event_parts.append(
                                f" [{style}]{summary:<{col_width - 1}}[/{style}]"
                            )
                        else:
                            if is_sel:
                                event_parts.append(
                                    f"[on {SELECTED_BG}]{' ' * col_width}[/on {SELECTED_BG}]"
                                )
                            else:
                                event_parts.append(" " * col_width)
                lines.append("│" + "│".join(event_parts) + "│")

            # Row separator
            if week_idx < len(weeks) - 1:
                lines.append("├" + "┼".join("─" * col_width for _ in range(7)) + "┤")

        # Bottom border
        lines.append("└" + "┴".join("─" * col_width for _ in range(7)) + "┘")

        content = "\n".join(lines)
        grid.mount(Static(content))

    def _compute_page_size(self, num_weeks: int) -> int:
        """How many event rows fit per cell given the current widget height.

        Layout breakdown (in lines):
          month-header:  3  (1 top-pad + 1 text + 1 bottom-pad)
          grid header:   3  (top border + day-name row + separator)
          per week:      1  (day-number row)
                       + N  (event rows = page_size)
                       + 1  (separator or bottom border)
        Total = 6 + num_weeks * (page_size + 2)
        => page_size = (height - 6) // num_weeks - 2
        """
        height = self.size.height
        if height < 1 or num_weeks < 1:
            return 1
        return max(1, (height - 6) // num_weeks - 2)

    def _page_for_selected_day(
        self, day_evts: list[CalendarEvent], page_size: int
    ) -> int:
        """Which page of events contains the currently selected event."""
        if not day_evts or not self.selected_event_id:
            return 0
        for i, ev in enumerate(day_evts):
            if ev.id == self.selected_event_id:
                return i // page_size
        return 0

    @staticmethod
    def _event_style(event: CalendarEvent) -> str:
        if event.color_id and event.color_id in GOOGLE_COLORS:
            _, hex_color, _ = GOOGLE_COLORS[event.color_id]
            return f"bold {hex_color}"
        return "bold"
