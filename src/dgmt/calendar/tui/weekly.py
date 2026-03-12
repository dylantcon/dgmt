"""Weekly grid view widget."""

from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import GOOGLE_COLORS

# Background tint for the selected day — a subtle warm magenta wash
# that lets foreground colors (event colors, today accent) show through
SELECTED_BG = "#2d2030"


class WeeklyView(Widget):
    """7-column grid view for a week."""

    current_date: reactive[datetime] = reactive(datetime.now)
    events: reactive[list[CalendarEvent]] = reactive(list, always_update=True)

    DEFAULT_CSS = """
    WeeklyView {
        height: 1fr;
        width: 1fr;
    }

    .week-header {
        text-align: center;
        text-style: bold;
        padding: 1 0;
        width: 1fr;
    }

    .week-grid {
        height: 1fr;
        width: 1fr;
    }

    .day-column {
        width: 1fr;
        height: 1fr;
        border: round $primary-background;
        padding: 0 1;
    }

    .day-column-today {
        border: round $accent;
    }

    .day-column-selected {
        background: #2d2030;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._composed = False

    def compose(self) -> ComposeResult:
        yield Static("", id="week-header", classes="week-header")
        yield Horizontal(id="week-grid", classes="week-grid")

    def on_mount(self) -> None:
        self._composed = True
        if hasattr(self, "_pending_date"):
            self.current_date = self._pending_date
        if hasattr(self, "_pending_events"):
            self.events = self._pending_events
        self._refresh()

    def watch_current_date(self, date: datetime) -> None:
        if self._composed:
            self._refresh()

    def watch_events(self, events: list[CalendarEvent]) -> None:
        if self._composed:
            self._refresh()

    def _get_week_start(self) -> datetime:
        """Get Sunday of the current week."""
        weekday = self.current_date.weekday()  # Monday=0
        sunday = self.current_date - timedelta(days=(weekday + 1) % 7)
        return sunday.replace(hour=0, minute=0, second=0, microsecond=0)

    def _refresh(self) -> None:
        try:
            header = self.query_one("#week-header", Static)
        except NoMatches:
            return
        week_start = self._get_week_start()
        week_end = week_start + timedelta(days=6)
        header.update(
            f"[bold]Week of {week_start.strftime('%B %d')} - "
            f"{week_end.strftime('%B %d, %Y')}[/bold]"
        )

        grid = self.query_one("#week-grid", Horizontal)
        grid.remove_children()

        today = datetime.now().date()
        selected = self.current_date.date()
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        # Group events by day
        events_by_day: dict[int, list[CalendarEvent]] = {i: [] for i in range(7)}
        for event in self.events:
            if event.start:
                day_idx = (event.start.date() - week_start.date()).days
                if 0 <= day_idx < 7:
                    events_by_day[day_idx].append(event)

        for i in range(7):
            day_date = week_start + timedelta(days=i)
            is_today = day_date.date() == today
            is_selected = day_date.date() == selected

            # Build CSS classes for the column
            classes = "day-column"
            if is_today:
                classes += " day-column-today"
            if is_selected:
                classes += " day-column-selected"

            col = Vertical(classes=classes)

            lines: list[str] = []
            day_label = f"{day_names[i]} {day_date.day}"

            # Box char styling: today=accent fg, selected=tinted bg, both=both
            if is_today and is_selected:
                lines.append(
                    f"[bold $accent on {SELECTED_BG}]┌─ {day_label} ─┐[/bold $accent on {SELECTED_BG}]"
                )
            elif is_today:
                lines.append(f"[bold $accent]┌─ {day_label} ─┐[/bold $accent]")
            elif is_selected:
                lines.append(
                    f"[bold on {SELECTED_BG}]┌─ {day_label} ─┐[/bold on {SELECTED_BG}]"
                )
            else:
                lines.append(f"[bold]┌─ {day_label} ─┐[/bold]")

            day_events = events_by_day[i]
            if day_events:
                for ev in day_events:
                    style = self._event_style(ev)
                    if is_selected:
                        style += f" on {SELECTED_BG}"
                    if ev.all_day:
                        label = f"[{style}]- {ev.summary}[/{style}]"
                    else:
                        time_str = ev.start.strftime("%I:%M%p").lstrip("0").lower() if ev.start else ""
                        label = f"[{style}]- {time_str} {ev.summary}[/{style}]"
                    lines.append(label)
            else:
                if is_selected:
                    lines.append(f"[dim on {SELECTED_BG}]  No events[/dim on {SELECTED_BG}]")
                else:
                    lines.append("[dim]  No events[/dim]")

            bottom_border = f"└{'─' * (len(day_label) + 4)}┘"
            if is_today and is_selected:
                lines.append(f"[$accent on {SELECTED_BG}]{bottom_border}[/$accent on {SELECTED_BG}]")
            elif is_today:
                lines.append(f"[$accent]{bottom_border}[/$accent]")
            elif is_selected:
                lines.append(f"[on {SELECTED_BG}]{bottom_border}[/on {SELECTED_BG}]")
            else:
                lines.append(bottom_border)

            content = "\n".join(lines)
            grid.mount(col)
            col.mount(Static(content))

    @staticmethod
    def _event_style(event: CalendarEvent) -> str:
        if event.color_id and event.color_id in GOOGLE_COLORS:
            _, hex_color, _ = GOOGLE_COLORS[event.color_id]
            return f"bold {hex_color}"
        return "bold"
