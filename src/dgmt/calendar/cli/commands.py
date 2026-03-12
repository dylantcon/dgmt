"""Calendar CLI subcommands."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from dgmt.calendar.auth import TokenManager
from dgmt.calendar.api import CalendarAPI
from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import (
    GOOGLE_COLORS,
    ColorRule,
    ColorRuleEngine,
    color_id_from_name,
)
from dgmt.core.config import load_config


console = Console()


def _get_color_engine() -> ColorRuleEngine:
    """Load color rules from config."""
    config = load_config()
    rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
    return ColorRuleEngine(rules)


def _save_color_rules(engine: ColorRuleEngine) -> None:
    """Save color rules back to config."""
    config = load_config()
    config._data.calendar.color_rules = [r.to_dict() for r in engine.rules]
    config.save()


def _resolve_color_interactive(engine: ColorRuleEngine, summary: str) -> Optional[str]:
    """Resolve color for a summary, prompting on ambiguity."""
    matches = engine.match(summary)
    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0].color_id
    # Ambiguous: prompt user
    console.print("[yellow]Multiple color rules match this event:[/yellow]")
    for i, rule in enumerate(matches, 1):
        name = ColorRuleEngine.get_color_name(rule.color_id)
        console.print(f"  {i}. [bold]{rule.pattern}[/bold] -> {name}")
    console.print(f"  {len(matches) + 1}. Skip coloring")
    try:
        choice = input("Choose (number): ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            return matches[idx].color_id
    except (ValueError, EOFError):
        pass
    return None


def _parse_datetime(s: str) -> datetime:
    """Parse a datetime string in common formats."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}. Use format: YYYY-MM-DD HH:MM")


def cmd_auth(args: argparse.Namespace) -> int:
    """Run OAuth authorization flow."""
    tm = TokenManager()
    try:
        tm.authorize()
        console.print("[green]Authorization successful![/green]")
        console.print(f"Token saved to: {tm.token_path}")
        return 0
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return 1


def cmd_auth_revoke(args: argparse.Namespace) -> int:
    """Revoke stored token."""
    tm = TokenManager()
    if tm.revoke():
        console.print("[green]Token revoked.[/green]")
    else:
        console.print("[yellow]No token found.[/yellow]")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List events."""
    api = CalendarAPI()
    date = _parse_datetime(args.date) if args.date else datetime.now()
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=args.days)

    events = api.list_events(start=start, end=end)

    if not events:
        console.print("[dim]No events found.[/dim]")
        return 0

    table = Table(title=f"Events: {start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}", box=box.ROUNDED)
    table.add_column("Date", style="cyan")
    table.add_column("Time", style="green")
    table.add_column("Summary")
    table.add_column("ID", style="dim")

    for event in events:
        if event.all_day:
            date_str = event.start.strftime("%b %d") if event.start else ""
            time_str = "All day"
        else:
            date_str = event.start.strftime("%b %d") if event.start else ""
            time_str = (
                f"{event.start.strftime('%I:%M %p')} - {event.end.strftime('%I:%M %p')}"
                if event.start and event.end
                else ""
            )

        style = ""
        if event.color_id:
            style = ColorRuleEngine.get_rich_style(event.color_id)

        table.add_row(date_str, time_str, f"[{style}]{event.summary}[/{style}]" if style else event.summary, event.id or "")

    console.print(table)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Create a new event."""
    api = CalendarAPI()
    engine = _get_color_engine()

    start = _parse_datetime(args.start)
    end = _parse_datetime(args.end) if args.end else start + timedelta(hours=1)

    color_id = None
    if args.color:
        color_id = color_id_from_name(args.color)
        if not color_id:
            console.print(f"[red]Unknown color: {args.color}[/red]")
            return 1
    else:
        color_id = _resolve_color_interactive(engine, args.summary)

    event = CalendarEvent(
        summary=args.summary,
        start=start,
        end=end,
        color_id=color_id,
    )
    created = api.create_event(event)
    console.print(f"[green]Created:[/green] {created.summary} (ID: {created.id})")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    """Edit an existing event."""
    api = CalendarAPI()
    engine = _get_color_engine()

    event = api.get_event(args.event_id)

    if args.summary:
        event.summary = args.summary
    if args.start:
        event.start = _parse_datetime(args.start)
    if args.end:
        event.end = _parse_datetime(args.end)

    if args.color:
        color_id = color_id_from_name(args.color)
        if not color_id:
            console.print(f"[red]Unknown color: {args.color}[/red]")
            return 1
        event.color_id = color_id
    elif args.summary:
        resolved = _resolve_color_interactive(engine, event.summary)
        if resolved:
            event.color_id = resolved

    updated = api.update_event(event)
    console.print(f"[green]Updated:[/green] {updated.summary}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete an event."""
    api = CalendarAPI()
    api.delete_event(args.event_id)
    console.print(f"[green]Deleted event:[/green] {args.event_id}")
    return 0


def cmd_view(args: argparse.Namespace) -> int:
    """Show a rich-formatted calendar view."""
    api = CalendarAPI()
    date = _parse_datetime(args.date) if args.date else datetime.now()
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)

    view_type = "weekly"
    if args.daily:
        view_type = "daily"
    elif args.monthly:
        view_type = "monthly"
    elif args.weekly:
        view_type = "weekly"
    else:
        config = load_config()
        view_type = config.data.calendar.default_view

    if view_type == "daily":
        _render_daily(api, start)
    elif view_type == "weekly":
        _render_weekly(api, start)
    elif view_type == "monthly":
        _render_monthly(api, start)

    return 0


def _render_daily(api: CalendarAPI, date: datetime) -> None:
    """Render daily view using Rich."""
    end = date + timedelta(days=1)
    events = api.list_events(start=date, end=end)

    console.print(f"\n[bold]{date.strftime('%A, %B %d, %Y')}[/bold]\n")

    table = Table(box=box.ROUNDED, show_header=False, padding=(0, 1))
    table.add_column("Time", style="cyan", width=12)
    table.add_column("Event", ratio=1)

    # Build hour slots
    event_by_hour: dict[int, list[CalendarEvent]] = {h: [] for h in range(24)}
    for event in events:
        if event.all_day:
            event_by_hour[0].append(event)
        elif event.start:
            event_by_hour[event.start.hour].append(event)

    for hour in range(7, 23):  # 7 AM to 10 PM
        time_label = f"{hour:2d}:00" if hour < 13 else f" {hour - 12}:00 PM"
        if hour < 12:
            time_label = f"{hour:2d}:00 AM"
        elif hour == 12:
            time_label = "12:00 PM"
        else:
            time_label = f" {hour - 12}:00 PM"

        slot_events = event_by_hour[hour]
        if slot_events:
            parts = []
            for ev in slot_events:
                style = ColorRuleEngine.get_rich_style(ev.color_id) if ev.color_id else ""
                label = f"[{style}]│ {ev.summary} │[/{style}]" if style else f"│ {ev.summary} │"
                parts.append(label)
            table.add_row(time_label, "\n".join(parts))
        else:
            table.add_row(time_label, "[dim]─[/dim]")

    console.print(table)


def _render_weekly(api: CalendarAPI, date: datetime) -> None:
    """Render weekly view using Rich."""
    # Find start of week (Sunday)
    weekday = date.weekday()  # Monday=0
    sunday = date - timedelta(days=(weekday + 1) % 7)
    start = sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)

    events = api.list_events(start=start, end=end)

    console.print(f"\n[bold]Week of {start.strftime('%B %d, %Y')}[/bold]\n")

    table = Table(box=box.ROUNDED, padding=(0, 1))
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for i, day_name in enumerate(days):
        day_date = start + timedelta(days=i)
        header = f"{day_name} {day_date.day}"
        table.add_column(header, ratio=1)

    # Group events by day
    day_events: list[list[str]] = [[] for _ in range(7)]
    for event in events:
        if event.start:
            day_idx = (event.start.date() - start.date()).days
            if 0 <= day_idx < 7:
                style = ColorRuleEngine.get_rich_style(event.color_id) if event.color_id else ""
                if event.all_day:
                    label = event.summary
                else:
                    label = f"{event.start.strftime('%I:%M%p').lstrip('0').lower()} {event.summary}"
                if style:
                    label = f"[{style}]{label}[/{style}]"
                day_events[day_idx].append(label)

    # Find max events in any day
    max_events = max((len(d) for d in day_events), default=0)
    if max_events == 0:
        table.add_row(*["[dim]No events[/dim]"] * 7)
    else:
        for row_idx in range(max_events):
            row = []
            for day_idx in range(7):
                if row_idx < len(day_events[day_idx]):
                    row.append(day_events[day_idx][row_idx])
                else:
                    row.append("")
            table.add_row(*row)

    console.print(table)


def _render_monthly(api: CalendarAPI, date: datetime) -> None:
    """Render monthly view using Rich."""
    import calendar

    year, month = date.year, date.month
    cal = calendar.Calendar(firstweekday=6)  # Sunday start
    month_days = list(cal.itermonthdays2(year, month))

    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1)
    else:
        last_day = datetime(year, month + 1, 1)

    events = api.list_events(start=first_day, end=last_day)

    console.print(f"\n[bold]{date.strftime('%B %Y')}[/bold]\n")

    table = Table(box=box.ROUNDED, padding=(0, 1))
    for day_name in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        table.add_column(day_name, ratio=1, justify="left")

    # Group events by day number
    events_by_day: dict[int, list[str]] = {}
    for event in events:
        if event.start:
            d = event.start.day
            style = ColorRuleEngine.get_rich_style(event.color_id) if event.color_id else ""
            summary = event.summary[:15] + "..." if len(event.summary) > 18 else event.summary
            label = f"[{style}]{summary}[/{style}]" if style else summary
            events_by_day.setdefault(d, []).append(label)

    # Build rows (weeks)
    weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]
    for week in weeks:
        row = []
        for day_num, _ in week:
            if day_num == 0:
                row.append("")
            else:
                cell = f"[bold]{day_num}[/bold]"
                day_evts = events_by_day.get(day_num, [])
                for evt in day_evts[:3]:  # max 3 per cell
                    cell += f"\n {evt}"
                if len(day_evts) > 3:
                    cell += f"\n [dim]+{len(day_evts) - 3} more[/dim]"
                row.append(cell)
        table.add_row(*row)

    console.print(table)


def cmd_colors_list(args: argparse.Namespace) -> int:
    """List color rules with previews."""
    engine = _get_color_engine()

    # Show available colors
    console.print("\n[bold]Available Colors:[/bold]")
    table = Table(box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Preview")

    for cid, (name, hex_color, _) in GOOGLE_COLORS.items():
        table.add_row(cid, name, f"[bold {hex_color}]████ {name}[/bold {hex_color}]")
    console.print(table)

    # Show configured rules
    if engine.rules:
        console.print("\n[bold]Configured Rules:[/bold]")
        rules_table = Table(box=box.ROUNDED)
        rules_table.add_column("Pattern")
        rules_table.add_column("Color")
        rules_table.add_column("Case Sensitive")

        for rule in engine.rules:
            color_name = ColorRuleEngine.get_color_name(rule.color_id)
            style = ColorRuleEngine.get_rich_style(rule.color_id)
            rules_table.add_row(
                rule.pattern,
                f"[{style}]{color_name}[/{style}]",
                "Yes" if rule.case_sensitive else "No",
            )
        console.print(rules_table)
    else:
        console.print("\n[dim]No color rules configured.[/dim]")

    return 0


def cmd_colors_add(args: argparse.Namespace) -> int:
    """Add a color rule."""
    engine = _get_color_engine()

    color_id = color_id_from_name(args.color)
    if not color_id:
        console.print(f"[red]Unknown color: {args.color}[/red]")
        console.print("Available colors: " + ", ".join(
            name for name, _, _ in GOOGLE_COLORS.values()
        ))
        return 1

    rule = ColorRule(pattern=args.pattern, color_id=color_id)
    engine.add_rule(rule)
    _save_color_rules(engine)

    color_name = ColorRuleEngine.get_color_name(color_id)
    console.print(f"[green]Added rule:[/green] \"{args.pattern}\" -> {color_name}")
    return 0


def cmd_colors_remove(args: argparse.Namespace) -> int:
    """Remove a color rule."""
    engine = _get_color_engine()

    if engine.remove_rule(args.pattern):
        _save_color_rules(engine)
        console.print(f"[green]Removed rule:[/green] \"{args.pattern}\"")
    else:
        console.print(f"[yellow]No rule found for pattern:[/yellow] \"{args.pattern}\"")
    return 0


def cmd_calendars(args: argparse.Namespace) -> int:
    """List available calendars."""
    api = CalendarAPI()
    calendars = api.list_calendars()

    table = Table(title="Calendars", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Primary", style="green")

    for cal in calendars:
        table.add_row(
            cal["id"],
            cal["summary"],
            "*" if cal["primary"] else "",
        )

    console.print(table)
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the interactive TUI."""
    from dgmt.calendar.tui.app import CalendarApp

    app = CalendarApp()
    app.run()
    return 0


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the cal subcommand and its sub-subcommands."""
    cal_parser = subparsers.add_parser(
        "cal",
        help="Google Calendar management",
        description="Google Calendar CLI/TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  dgmt cal                  Launch interactive TUI
  dgmt cal auth             Run OAuth authorization
  dgmt cal list             List upcoming events
  dgmt cal add "Meeting" --start "2026-03-11 10:00"
  dgmt cal view --weekly    Show weekly calendar view
  dgmt cal colors           List color rules
""",
    )
    cal_parser.set_defaults(func=cmd_tui)

    cal_sub = cal_parser.add_subparsers(dest="cal_command", metavar="<command>")

    # auth
    auth_parser = cal_sub.add_parser("auth", help="Manage OAuth authorization")
    auth_parser.set_defaults(func=cmd_auth)
    auth_sub = auth_parser.add_subparsers(dest="auth_command")
    revoke_parser = auth_sub.add_parser("revoke", help="Revoke stored token")
    revoke_parser.set_defaults(func=cmd_auth_revoke)

    # list
    list_parser = cal_sub.add_parser("list", help="List events")
    list_parser.add_argument("--date", help="Start date (YYYY-MM-DD)")
    list_parser.add_argument("--days", type=int, default=7, help="Number of days (default: 7)")
    list_parser.set_defaults(func=cmd_list)

    # add
    add_parser = cal_sub.add_parser("add", help="Create a new event")
    add_parser.add_argument("summary", help="Event summary/title")
    add_parser.add_argument("--start", required=True, help="Start datetime")
    add_parser.add_argument("--end", help="End datetime (default: start + 1 hour)")
    add_parser.add_argument("--color", help="Color name (e.g., Peacock, Tomato)")
    add_parser.set_defaults(func=cmd_add)

    # edit
    edit_parser = cal_sub.add_parser("edit", help="Edit an event")
    edit_parser.add_argument("event_id", help="Event ID")
    edit_parser.add_argument("--summary", help="New summary")
    edit_parser.add_argument("--start", help="New start datetime")
    edit_parser.add_argument("--end", help="New end datetime")
    edit_parser.add_argument("--color", help="Color name")
    edit_parser.set_defaults(func=cmd_edit)

    # delete
    del_parser = cal_sub.add_parser("delete", help="Delete an event")
    del_parser.add_argument("event_id", help="Event ID")
    del_parser.set_defaults(func=cmd_delete)

    # view
    view_parser = cal_sub.add_parser("view", help="Show formatted calendar view")
    view_group = view_parser.add_mutually_exclusive_group()
    view_group.add_argument("--daily", action="store_true", help="Daily view")
    view_group.add_argument("--weekly", action="store_true", help="Weekly view")
    view_group.add_argument("--monthly", action="store_true", help="Monthly view")
    view_parser.add_argument("--date", help="Date to show (YYYY-MM-DD)")
    view_parser.set_defaults(func=cmd_view)

    # colors
    colors_parser = cal_sub.add_parser("colors", help="Manage color rules")
    colors_parser.set_defaults(func=cmd_colors_list)
    colors_sub = colors_parser.add_subparsers(dest="colors_command")

    colors_add = colors_sub.add_parser("add", help="Add a color rule")
    colors_add.add_argument("pattern", help="Pattern to match in event summary")
    colors_add.add_argument("--color", required=True, help="Color name")
    colors_add.set_defaults(func=cmd_colors_add)

    colors_rm = colors_sub.add_parser("remove", help="Remove a color rule")
    colors_rm.add_argument("pattern", help="Pattern to remove")
    colors_rm.set_defaults(func=cmd_colors_remove)

    # calendars
    calendars_parser = cal_sub.add_parser("calendars", help="List available calendars")
    calendars_parser.set_defaults(func=cmd_calendars)
