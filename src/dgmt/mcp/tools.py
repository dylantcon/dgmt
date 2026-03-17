"""MCP tool handler implementations.

Each handler takes (args: dict, get_api: Callable) and returns a JSON string.
get_api() lazily initializes a CalendarAPI singleton.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from dgmt.calendar.models import CalendarEvent
from dgmt.calendar.colors import (
    GOOGLE_COLORS,
    ColorRule,
    ColorRuleEngine,
    color_id_from_name,
)
from dgmt.core.config import load_config

# Default timezone — matches CalendarEvent.to_google_body() convention
DEFAULT_TZ = ZoneInfo("America/New_York")

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
    """Parse datetime strings in common formats, returning tz-aware datetimes.

    If the input string has no timezone info, DEFAULT_TZ (America/New_York) is applied.
    If it already has a timezone (e.g. from isoformat()), it's preserved.
    """
    # Try fromisoformat first — handles offset-aware strings like "2026-03-18T09:00:00-04:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=DEFAULT_TZ)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=DEFAULT_TZ)
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
        "recurring_event_id": event.recurring_event_id,
        "is_recurring_instance": event.is_recurring_instance,
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


# --- Shared helpers ---


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware. Applies DEFAULT_TZ to naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=DEFAULT_TZ)
    return dt


def _filter_events(
    events: list[CalendarEvent],
    color: str | None = None,
    summary_contains: str | None = None,
) -> list[CalendarEvent]:
    """Filter events by color name (fuzzy) and/or summary substring."""
    if color:
        cid = color_id_from_name(color)
        events = [e for e in events if e.color_id == cid] if cid else []
    if summary_contains:
        needle = summary_contains.lower()
        events = [e for e in events if needle in (e.summary or "").lower()]
    return events


def _create_single_event(args: dict, api: Any) -> CalendarEvent:
    """Parse args and create a single event via the API. Returns the created event."""
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
    return api.create_event(event)


# --- Tool handlers ---


def handle_list_events(args: dict, get_api: Callable) -> str:
    """List events in a date range with optional filtering."""
    api = get_api()
    start = _parse_dt(args["start"]) if "start" in args else datetime.now(DEFAULT_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    end = _parse_dt(args["end"]) if "end" in args else start + timedelta(days=7)
    calendar_id = args.get("calendar_id", "primary")

    events = api.list_events(start=start, end=end, calendar_id=calendar_id)
    events = _filter_events(events, args.get("color"), args.get("summary_contains"))
    return json.dumps([_event_to_dict(e) for e in events], indent=2)


def handle_get_event(args: dict, get_api: Callable) -> str:
    """Get a single event by ID."""
    api = get_api()
    event = api.get_event(args["event_id"], calendar_id=args.get("calendar_id", "primary"))
    return json.dumps(_event_to_dict(event), indent=2)


def handle_create_event(args: dict, get_api: Callable) -> str:
    """Create one or many events.

    - Batch mode: ``events`` array present → create each, return batch response.
    - Single mode: top-level ``summary``/``start`` → create one, return flat event dict.
    """
    api = get_api()

    if "events" in args:
        # Batch mode
        succeeded: list[dict] = []
        failed: list[dict] = []
        for i, event_args in enumerate(args["events"]):
            try:
                created = _create_single_event(event_args, api)
                succeeded.append({"index": i, "event": _event_to_dict(created)})
            except Exception as e:
                failed.append({"index": i, "error": str(e), "summary": event_args.get("summary", "")})
        return json.dumps({
            "succeeded": succeeded,
            "failed": failed,
            "created_count": len(succeeded),
            "failed_count": len(failed),
        }, indent=2)

    # Single mode
    if "summary" not in args or "start" not in args:
        raise ValueError("Single mode requires 'summary' and 'start', or use 'events' for batch mode.")
    created = _create_single_event(args, api)
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
    """Delete one or many events.

    - Batch by IDs: ``event_ids`` array present.
    - Range mode: ``start`` + ``end`` present (with optional ``color``/``summary_contains`` filters).
    - Single mode: ``event_id`` present.
    All modes support ``dry_run``.
    """
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    dry_run = args.get("dry_run", False)

    if "event_ids" in args:
        # --- Batch by IDs ---
        targets: list[CalendarEvent] = []
        for eid in args["event_ids"]:
            try:
                ev = api.get_event(eid, calendar_id=calendar_id)
                targets.append(ev)
            except Exception:
                targets.append(CalendarEvent(id=eid, calendar_id=calendar_id))

        return _delete_targets(targets, api, calendar_id, dry_run)

    if "start" in args and "end" in args:
        # --- Range mode ---
        start = _parse_dt(args["start"])
        end = _parse_dt(args["end"])
        events = api.list_events(start=start, end=end, calendar_id=calendar_id)
        targets = _filter_events(events, args.get("color"), args.get("summary_contains"))

        return _delete_targets(targets, api, calendar_id, dry_run)

    # --- Single mode ---
    if "event_id" not in args:
        raise ValueError("Provide 'event_id', 'event_ids', or 'start'/'end' date range.")

    if dry_run:
        try:
            ev = api.get_event(args["event_id"], calendar_id=calendar_id)
            target_dict = _event_to_dict(ev)
        except Exception:
            target_dict = {"id": args["event_id"], "calendar_id": calendar_id}
        return json.dumps({
            "dry_run": True,
            "would_delete": [target_dict],
            "count": 1,
        }, indent=2)

    api.delete_event(args["event_id"], calendar_id=calendar_id)
    return json.dumps({"deleted": True, "event_id": args["event_id"]})


def _delete_targets(
    targets: list[CalendarEvent],
    api: Any,
    calendar_id: str,
    dry_run: bool,
) -> str:
    """Shared logic for batch/range delete modes."""
    target_dicts = [_event_to_dict(e) for e in targets]

    if dry_run:
        return json.dumps({
            "dry_run": True,
            "would_delete": target_dicts,
            "count": len(targets),
        }, indent=2)

    succeeded: list[dict] = []
    failed: list[dict] = []
    for event in targets:
        try:
            api.delete_event(event.id, calendar_id=event.calendar_id or calendar_id)
            succeeded.append(_event_to_dict(event))
        except Exception as e:
            failed.append({"event": _event_to_dict(event), "error": str(e)})

    return json.dumps({
        "succeeded": succeeded,
        "failed": failed,
        "deleted_count": len(succeeded),
        "failed_count": len(failed),
    }, indent=2)


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



def _merge_spans(
    events: list[CalendarEvent],
    all_day: bool,
) -> list[tuple[datetime, datetime]]:
    """Extract, tz-normalize, sort, and merge spans for the given all_day category."""
    spans = sorted(
        [
            (_ensure_aware(e.start), _ensure_aware(e.end))
            for e in events
            if e.all_day == all_day and e.start and e.end
        ],
        key=lambda s: s[0],
    )
    if not spans:
        return []
    merged: list[tuple[datetime, datetime]] = [spans[0]]
    for s, e in spans[1:]:
        prev_s, prev_e = merged[-1]
        if s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))
    return merged


def _subtract_spans(
    base: list[tuple[datetime, datetime]],
    blockers: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Subtract sorted merged blocker spans from sorted merged base spans.

    Returns the portions of base that don't overlap with any blocker.
    Both inputs must be sorted by start time and non-overlapping (merged).
    """
    result: list[tuple[datetime, datetime]] = []
    for b_start, b_end in base:
        cursor = b_start
        for s_start, s_end in blockers:
            if s_end <= cursor:
                continue
            if s_start >= b_end:
                break
            if cursor < s_start:
                result.append((cursor, s_start))
            cursor = max(cursor, s_end)
        if cursor < b_end:
            result.append((cursor, b_end))
    return result


def _compute_fill_gaps(
    deleted_events: list[CalendarEvent],
    surviving_events: list[CalendarEvent],
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime, bool]]:
    """Compute fillable time slots left by deleted events within a range.

    Only returns time that was occupied by a deleted event AND is not
    occupied by any surviving event. This prevents fill events from
    overlapping with events that remain on the calendar.

    Separates all-day and timed events, merges spans for each category,
    then subtracts surviving spans from deleted spans.

    All datetimes are normalized to tz-aware before comparison.
    """
    gaps: list[tuple[datetime, datetime, bool]] = []
    rs = _ensure_aware(range_start)
    re = _ensure_aware(range_end)

    for all_day in (True, False):
        # Merge deleted event spans — these are candidate fill zones
        deleted_spans = _merge_spans(deleted_events, all_day)
        if not deleted_spans:
            continue

        # Clip deleted spans to the requested range
        clipped: list[tuple[datetime, datetime]] = []
        for s, e in deleted_spans:
            cs = max(s, rs)
            ce = min(e, re)
            if cs < ce:
                clipped.append((cs, ce))

        if not clipped:
            continue

        # Merge surviving event spans — these are blockers
        surviving_spans = _merge_spans(surviving_events, all_day)

        # Subtract surviving from deleted → actual free slots
        free = _subtract_spans(clipped, surviving_spans)
        for fs, fe in free:
            gaps.append((fs, fe, all_day))

    return gaps


def handle_clear_range(args: dict, get_api: Callable) -> str:
    """Delete events in a range (with filters) and optionally fill gaps."""
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    dry_run = args.get("dry_run", False)

    start = _parse_dt(args["start"])
    end = _parse_dt(args["end"])

    all_events = api.list_events(start=start, end=end, calendar_id=calendar_id)
    targets = _filter_events(all_events, args.get("color"), args.get("summary_contains"))

    # Compute fill gaps before deleting — surviving events act as blockers
    # so fill events only go where deleted time was AND nothing else remains
    if args.get("fill_summary"):
        target_ids = {e.id for e in targets}
        surviving = [e for e in all_events if e.id not in target_ids]
        fill_gaps = _compute_fill_gaps(targets, surviving, start, end)
    else:
        fill_gaps = []

    if dry_run:
        fill_previews = [
            {"start": gs.isoformat(), "end": ge.isoformat(), "all_day": ad, "summary": args.get("fill_summary", "")}
            for gs, ge, ad in fill_gaps
        ]
        return json.dumps({
            "dry_run": True,
            "would_delete": [_event_to_dict(e) for e in targets],
            "would_create": fill_previews,
            "delete_count": len(targets),
            "create_count": len(fill_previews),
        }, indent=2)

    # Delete targets
    deleted: list[dict] = []
    delete_failed: list[dict] = []
    for event in targets:
        try:
            api.delete_event(event.id, calendar_id=event.calendar_id or calendar_id)
            deleted.append(_event_to_dict(event))
        except Exception as e:
            delete_failed.append({"event": _event_to_dict(event), "error": str(e)})

    # Fill gaps if requested
    created: list[dict] = []
    create_failed: list[dict] = []
    if args.get("fill_summary"):
        fill_color = args.get("fill_color")
        for gap_start, gap_end, all_day_gap in fill_gaps:
            try:
                fill_args = {
                    "summary": args["fill_summary"],
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "all_day": all_day_gap,
                    "calendar_id": calendar_id,
                }
                if fill_color:
                    fill_args["color"] = fill_color
                filled = _create_single_event(fill_args, api)
                created.append(_event_to_dict(filled))
            except Exception as e:
                create_failed.append({
                    "start": gap_start.isoformat(),
                    "end": gap_end.isoformat(),
                    "error": str(e),
                })

    return json.dumps({
        "deleted": deleted,
        "delete_failed": delete_failed,
        "created": created,
        "create_failed": create_failed,
        "deleted_count": len(deleted),
        "delete_failed_count": len(delete_failed),
        "created_count": len(created),
        "create_failed_count": len(create_failed),
    }, indent=2)


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
    "clear_range": handle_clear_range,
}
