"""MCP tool handler implementations.

Each handler takes (args: dict, get_api: Callable) and returns a JSON string.
get_api() lazily initializes a CalendarAPI singleton.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import (
    GOOGLE_COLORS,
    ColorRule,
    ColorRuleEngine,
    color_id_from_name,
)
from dgmt.core.config import load_config

# Same presets as the CLI (Phase 1)
RECURRENCE_PRESETS: dict[str, str] = {
    "daily": "RRULE:FREQ=DAILY",
    "weekdays": "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "weekly": "RRULE:FREQ=WEEKLY",
    "biweekly": "RRULE:FREQ=WEEKLY;INTERVAL=2",
    "monthly": "RRULE:FREQ=MONTHLY",
    "yearly": "RRULE:FREQ=YEARLY",
}


def _parse_dt(s: str) -> datetime:
    """Parse datetime strings in common formats."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}. Use YYYY-MM-DD HH:MM")


def _event_to_dict(event: CalendarEvent, engine: ColorRuleEngine | None = None) -> dict[str, Any]:
    """Serialize a CalendarEvent to a JSON-safe dict."""
    d: dict[str, Any] = {
        "id": event.id,
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": event.start.isoformat() if event.start else None,
        "end": event.end.isoformat() if event.end else None,
        "all_day": event.all_day,
        "color_id": event.color_id,
        "color_name": ColorRuleEngine.get_color_name(event.color_id) if event.color_id else None,
        "calendar_id": event.calendar_id,
        "recurrence": event.recurrence,
    }
    return d


def _parse_recurrence(value: str) -> list[str]:
    """Parse recurrence preset or RRULE string."""
    if value.lower() == "none":
        return []
    preset = RECURRENCE_PRESETS.get(value.lower())
    if preset:
        return [preset]
    if not value.startswith("RRULE:"):
        raise ValueError(
            f"Invalid recurrence: {value!r}. "
            f"Use a preset ({', '.join(RECURRENCE_PRESETS)}) or RRULE string."
        )
    return [value]


# --- Tool handlers ---


def handle_list_events(args: dict, get_api: Callable) -> str:
    """List events in a date range."""
    api = get_api()
    start = _parse_dt(args["start"]) if "start" in args else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = _parse_dt(args["end"]) if "end" in args else start + timedelta(days=7)
    calendar_id = args.get("calendar_id", "primary")

    events = api.list_events(start=start, end=end, calendar_id=calendar_id)
    return json.dumps([_event_to_dict(e) for e in events], indent=2)


def handle_get_event(args: dict, get_api: Callable) -> str:
    """Get a single event by ID."""
    api = get_api()
    event = api.get_event(args["event_id"], calendar_id=args.get("calendar_id", "primary"))
    return json.dumps(_event_to_dict(event), indent=2)


def handle_create_event(args: dict, get_api: Callable) -> str:
    """Create an event with all fields."""
    api = get_api()
    start = _parse_dt(args["start"])
    all_day = args.get("all_day", False)

    if all_day:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = _parse_dt(args["end"]) if "end" in args else start + timedelta(days=1)
        end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        end = _parse_dt(args["end"]) if "end" in args else start + timedelta(hours=1)

    color_id = None
    if "color" in args:
        color_id = color_id_from_name(args["color"]) or args["color"]

    recurrence: list[str] = []
    if "recurrence" in args:
        recurrence = _parse_recurrence(args["recurrence"])

    event = CalendarEvent(
        summary=args["summary"],
        start=start,
        end=end,
        all_day=all_day,
        description=args.get("description", ""),
        location=args.get("location", ""),
        color_id=color_id,
        recurrence=recurrence,
        calendar_id=args.get("calendar_id", "primary"),
    )
    created = api.create_event(event)
    return json.dumps(_event_to_dict(created), indent=2)


def handle_update_event(args: dict, get_api: Callable) -> str:
    """Update any event field."""
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    event = api.get_event(args["event_id"], calendar_id=calendar_id)

    if "summary" in args:
        event.summary = args["summary"]
    if "start" in args:
        event.start = _parse_dt(args["start"])
    if "end" in args:
        event.end = _parse_dt(args["end"])
    if "description" in args:
        event.description = args["description"]
    if "location" in args:
        event.location = args["location"]
    if "all_day" in args:
        event.all_day = args["all_day"]
    if "color" in args:
        event.color_id = color_id_from_name(args["color"]) or args["color"]
    if "recurrence" in args:
        event.recurrence = _parse_recurrence(args["recurrence"])
    if "calendar_id" in args:
        event.calendar_id = args["calendar_id"]

    updated = api.update_event(event)
    return json.dumps(_event_to_dict(updated), indent=2)


def handle_delete_event(args: dict, get_api: Callable) -> str:
    """Delete an event by ID."""
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    api.delete_event(args["event_id"], calendar_id=calendar_id)
    return json.dumps({"deleted": True, "event_id": args["event_id"]})


def handle_list_calendars(args: dict, get_api: Callable) -> str:
    """List available calendars."""
    api = get_api()
    calendars = api.list_calendars()
    return json.dumps(calendars, indent=2)


def handle_list_color_rules(args: dict, get_api: Callable) -> str:
    """List configured color rules and available colors."""
    config = load_config()
    rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
    engine = ColorRuleEngine(rules)

    return json.dumps({
        "rules": [
            {
                "pattern": r.pattern,
                "color_id": r.color_id,
                "color_name": ColorRuleEngine.get_color_name(r.color_id),
                "case_sensitive": r.case_sensitive,
            }
            for r in engine.rules
        ],
    }, indent=2)


def handle_add_color_rule(args: dict, get_api: Callable) -> str:
    """Add a color rule."""
    config = load_config()
    rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
    engine = ColorRuleEngine(rules)

    color_id = color_id_from_name(args["color"])
    if not color_id:
        raise ValueError(
            f"Unknown color: {args['color']}. "
            f"Available: {', '.join(name for name, _, _ in GOOGLE_COLORS.values())}"
        )

    rule = ColorRule(
        pattern=args["pattern"],
        color_id=color_id,
        case_sensitive=args.get("case_sensitive", False),
    )
    engine.add_rule(rule)

    config._data.calendar.color_rules = [r.to_dict() for r in engine.rules]
    config.save()

    return json.dumps({
        "added": True,
        "pattern": rule.pattern,
        "color_name": ColorRuleEngine.get_color_name(color_id),
    })


def handle_remove_color_rule(args: dict, get_api: Callable) -> str:
    """Remove a color rule."""
    config = load_config()
    rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
    engine = ColorRuleEngine(rules)

    removed = engine.remove_rule(args["pattern"])

    if removed:
        config._data.calendar.color_rules = [r.to_dict() for r in engine.rules]
        config.save()

    return json.dumps({"removed": removed, "pattern": args["pattern"]})


def handle_list_available_colors(args: dict, get_api: Callable) -> str:
    """List all 11 Google Calendar colors."""
    colors = [
        {"id": cid, "name": name, "hex": hex_color}
        for cid, (name, hex_color, _) in GOOGLE_COLORS.items()
    ]
    return json.dumps(colors, indent=2)


# Dispatch table: tool_name -> handler function
TOOL_HANDLERS: dict[str, Callable[[dict, Callable], str]] = {
    "list_events": handle_list_events,
    "get_event": handle_get_event,
    "create_event": handle_create_event,
    "update_event": handle_update_event,
    "delete_event": handle_delete_event,
    "list_calendars": handle_list_calendars,
    "list_color_rules": handle_list_color_rules,
    "add_color_rule": handle_add_color_rule,
    "remove_color_rule": handle_remove_color_rule,
    "list_available_colors": handle_list_available_colors,
}
