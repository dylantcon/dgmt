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
    RuleDefaults,
)
from dgmt.core.config import get_timezone, load_config


def _tz() -> ZoneInfo:
    """Get the configured timezone."""
    return get_timezone()

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

    If the input string has no timezone info, the configured timezone is applied.
    If it already has a timezone (e.g. from isoformat()), it's preserved.
    """
    # Try fromisoformat first — handles offset-aware strings like "2026-03-18T09:00:00-04:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=_tz())
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=_tz())
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
        "reminders": event.reminders,
    }
    return d


def _parse_reminders(value: Any) -> list[dict[str, Any]] | None:
    """Parse reminders arg into the CalendarEvent format.

    - absent/None → None (use calendar defaults)
    - "none" → [] (disable all reminders)
    - "default" → None (revert to calendar defaults, useful for update)
    - list of dicts → use directly as overrides
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value.lower() == "none":
            return []
        if value.lower() == "default":
            return None
        raise ValueError(f"Invalid reminders value: {value!r}. Use 'none', 'default', or an array.")
    if isinstance(value, list):
        return value
    raise ValueError(f"Invalid reminders type: {type(value).__name__}. Use 'none', 'default', or an array.")


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
    """Ensure a datetime is timezone-aware. Applies _tz() to naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz())
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


def _resolve_rule_defaults(summary: str) -> RuleDefaults:
    """Load color rules from config and resolve defaults for a summary."""
    config = load_config()
    rules = [ColorRule.from_dict(r) for r in config.data.calendar.color_rules]
    engine = ColorRuleEngine(rules)
    return engine.resolve(summary)


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

    reminders = _parse_reminders(args.get("reminders"))

    # Apply color rule defaults for fields the caller didn't explicitly set
    summary = args["summary"]
    if summary and (color_id is None or reminders is None):
        defaults = _resolve_rule_defaults(summary)
        if color_id is None and defaults.color_id is not None:
            color_id = defaults.color_id
        if reminders is None and defaults.reminders is not None:
            reminders = defaults.reminders

    event = CalendarEvent(
        summary=summary,
        start=start,
        end=end,
        all_day=all_day,
        description=args.get("description", ""),
        location=args.get("location", ""),
        color_id=color_id,
        recurrence=recurrence,
        calendar_id=args.get("calendar_id", "primary"),
        reminders=reminders,
    )
    return api.create_event(event)


# --- Tool handlers ---


def handle_list_events(args: dict, get_api: Callable) -> str:
    """List events in a date range with optional filtering."""
    api = get_api()
    start = _parse_dt(args["start"]) if "start" in args else datetime.now(_tz()).replace(hour=0, minute=0, second=0, microsecond=0)
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


def _update_single_event(args: dict, api: Any) -> CalendarEvent:
    """Apply update fields to a single event and save via the API. Returns the updated event."""
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
    if "reminders" in args:
        event.reminders = _parse_reminders(args["reminders"])
    if "calendar_id" in args:
        event.calendar_id = args["calendar_id"]

    return api.update_event(event)


def handle_update_event(args: dict, get_api: Callable) -> str:
    """Update one or many events.

    - Batch mode: ``updates`` array present → update each, return batch response.
    - Single mode: top-level ``event_id`` → update one, return flat event dict.
    """
    api = get_api()

    if "updates" in args:
        succeeded: list[dict] = []
        failed: list[dict] = []
        for i, update_args in enumerate(args["updates"]):
            try:
                updated = _update_single_event(update_args, api)
                succeeded.append({"index": i, "event": _event_to_dict(updated)})
            except Exception as e:
                failed.append({"index": i, "error": str(e), "event_id": update_args.get("event_id", "")})
        return json.dumps({
            "succeeded": succeeded,
            "failed": failed,
            "updated_count": len(succeeded),
            "failed_count": len(failed),
        }, indent=2)

    if "event_id" not in args:
        raise ValueError("Single mode requires 'event_id', or use 'updates' for batch mode.")

    updated = _update_single_event(args, api)
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
                "reminders": r.reminders,
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

    reminders = _parse_reminders(args.get("reminders"))

    rule = ColorRule(
        pattern=args["pattern"],
        color_id=color_id,
        case_sensitive=args.get("case_sensitive", False),
        reminders=reminders,
    )
    engine.add_rule(rule)

    config._data.calendar.color_rules = [r.to_dict() for r in engine.rules]
    config.save()

    return json.dumps({
        "added": True,
        "pattern": rule.pattern,
        "color_name": ColorRuleEngine.get_color_name(color_id),
        "reminders": rule.reminders,
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


def handle_find_free_time(args: dict, get_api: Callable) -> str:
    """Find unallocated time blocks in a date range."""
    api = get_api()
    start = _parse_dt(args["start"])
    end = _parse_dt(args["end"])
    calendar_id = args.get("calendar_id", "primary")
    min_duration = args.get("min_duration", 0)

    events = api.list_events(start=start, end=end, calendar_id=calendar_id)

    # Build spans from timed events only (all-day events don't block timed slots)
    timed_spans = sorted(
        [
            (max(_ensure_aware(e.start), _ensure_aware(start)),
             min(_ensure_aware(e.end), _ensure_aware(end)))
            for e in events
            if not e.all_day and e.start and e.end
        ],
        key=lambda s: s[0],
    )

    # Merge overlapping spans
    merged: list[tuple[datetime, datetime]] = []
    for s, e in timed_spans:
        if s >= e:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Subtract occupied from full range
    range_start = _ensure_aware(start)
    range_end = _ensure_aware(end)
    free = _subtract_spans([(range_start, range_end)], merged)

    # Filter by min_duration
    blocks = []
    total_free = 0
    for fs, fe in free:
        dur_minutes = (fe - fs).total_seconds() / 60
        if dur_minutes >= min_duration:
            blocks.append({
                "start": fs.isoformat(),
                "end": fe.isoformat(),
                "duration_minutes": round(dur_minutes, 1),
            })
            total_free += dur_minutes

    return json.dumps({
        "free_blocks": blocks,
        "total_free_minutes": round(total_free, 1),
    }, indent=2)


def handle_move_event(args: dict, get_api: Callable) -> str:
    """Reschedule an event to a new start time, preserving duration."""
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    event = api.get_event(args["event_id"], calendar_id=calendar_id)

    if not event.start or not event.end:
        raise ValueError("Event has no start/end times.")

    duration = event.end - event.start
    new_start = _parse_dt(args["new_start"])
    event.start = new_start
    event.end = new_start + duration

    updated = api.update_event(event)
    return json.dumps(_event_to_dict(updated), indent=2)


def handle_subdivide_event(args: dict, get_api: Callable) -> str:
    """Split one event into N contiguous sub-events."""
    api = get_api()
    calendar_id = args.get("calendar_id", "primary")
    event = api.get_event(args["event_id"], calendar_id=calendar_id)

    if event.all_day:
        raise ValueError("Cannot subdivide all-day events.")
    if not event.start or not event.end:
        raise ValueError("Event has no start/end times.")

    ev_start = _ensure_aware(event.start)
    ev_end = _ensure_aware(event.end)
    total_seconds = (ev_end - ev_start).total_seconds()

    # Determine split boundaries
    if "split_points" in args:
        points = sorted(_parse_dt(p) for p in args["split_points"])
        for p in points:
            if p <= ev_start or p >= ev_end:
                raise ValueError(
                    f"Split point {p.isoformat()} is outside event range "
                    f"({ev_start.isoformat()} - {ev_end.isoformat()})."
                )
        boundaries = [ev_start] + points + [ev_end]
    elif "count" in args:
        count = args["count"]
        if count < 2:
            raise ValueError("count must be at least 2.")
        chunk = total_seconds / count
        boundaries = [ev_start + timedelta(seconds=chunk * i) for i in range(count + 1)]
    else:
        raise ValueError("Provide 'count' or 'split_points'.")

    n = len(boundaries) - 1
    base_summary = args.get("new_summary", event.summary)

    # Create-first strategy: create all sub-events before deleting original
    created: list[CalendarEvent] = []
    failed: list[dict] = []
    for i in range(n):
        sub_args: dict[str, Any] = {
            "summary": f"{base_summary} ({i + 1}/{n})",
            "start": boundaries[i].isoformat(),
            "end": boundaries[i + 1].isoformat(),
            "description": event.description,
            "location": event.location,
            "calendar_id": calendar_id,
        }
        if args.get("new_color"):
            sub_args["color"] = args["new_color"]
        elif event.color_id:
            sub_args["color"] = event.color_id
        if event.reminders is not None:
            sub_args["reminders"] = event.reminders
        try:
            created_event = _create_single_event(sub_args, api)
            created.append(created_event)
        except Exception as e:
            failed.append({"index": i, "error": str(e)})

    # Only delete original if ALL sub-events succeeded
    if not failed:
        api.delete_event(event.id, calendar_id=calendar_id)

    result: dict[str, Any] = {
        "original": _event_to_dict(event),
        "sub_events": [_event_to_dict(e) for e in created],
        "created_count": len(created),
    }
    if failed:
        result["failed"] = failed
        result["warning"] = "Some sub-events failed to create. Original event was NOT deleted."

    return json.dumps(result, indent=2)


def handle_time_summary(args: dict, get_api: Callable) -> str:
    """Hours breakdown by color/category for a date range."""
    api = get_api()
    start = _parse_dt(args["start"])
    end = _parse_dt(args["end"])
    calendar_id = args.get("calendar_id", "primary")
    group_by = args.get("group_by", "color")

    events = api.list_events(start=start, end=end, calendar_id=calendar_id)

    range_start = _ensure_aware(start)
    range_end = _ensure_aware(end)

    # Timed events → hours
    by_group: dict[str, dict[str, Any]] = {}
    total_hours = 0.0
    total_events = 0

    # All-day events → days
    ad_by_group: dict[str, dict[str, Any]] = {}
    total_days = 0

    for event in events:
        if not event.start or not event.end:
            continue

        if event.all_day:
            # Count days (clipped to range)
            es = _ensure_aware(event.start)
            ee = _ensure_aware(event.end)
            clipped_start = max(es, range_start)
            clipped_end = min(ee, range_end)
            days = (clipped_end - clipped_start).days
            if days <= 0:
                continue

            key = _get_group_key(event, group_by)
            if key not in ad_by_group:
                ad_by_group[key] = {"days": 0, "event_count": 0}
            ad_by_group[key]["days"] += days
            ad_by_group[key]["event_count"] += 1
            total_days += days
        else:
            # Timed event → hours (clipped to range)
            es = _ensure_aware(event.start)
            ee = _ensure_aware(event.end)
            clipped_start = max(es, range_start)
            clipped_end = min(ee, range_end)
            hours = (clipped_end - clipped_start).total_seconds() / 3600
            if hours <= 0:
                continue

            key = _get_group_key(event, group_by)
            if key not in by_group:
                by_group[key] = {"hours": 0.0, "event_count": 0}
            by_group[key]["hours"] = round(by_group[key]["hours"] + hours, 2)
            by_group[key]["event_count"] += 1
            total_hours += hours
            total_events += 1

    result: dict[str, Any] = {
        "by_color" if group_by == "color" else "by_summary": by_group,
        "total_hours": round(total_hours, 2),
        "total_events": total_events,
    }
    if ad_by_group or total_days:
        result["all_day"] = {
            "by_color" if group_by == "color" else "by_summary": ad_by_group,
            "total_days": total_days,
        }

    return json.dumps(result, indent=2)


def _get_group_key(event: CalendarEvent, group_by: str) -> str:
    """Get the grouping key for an event based on group_by mode."""
    if group_by == "summary":
        return event.summary or "(no title)"
    # Default: group by color
    if event.color_id:
        return ColorRuleEngine.get_color_name(event.color_id)
    return "No color"


# --- Canvas tool handlers ---


def handle_list_canvas_assignments(args: dict, get_api: Callable) -> str:
    """List Canvas assignments with optional filtering."""
    from dgmt.canvas.fetcher import CanvasFetcher

    fetcher = CanvasFetcher()
    assignments = fetcher.get_assignments()

    # Filter by course
    if "course" in args:
        code = args["course"].replace(" ", "").upper()
        assignments = [a for a in assignments if a.course == code]

    # Filter by due dates
    if "due_before" in args:
        before = _parse_dt(args["due_before"])
        assignments = [a for a in assignments if a.due and a.due < before]
    if "due_after" in args:
        after = _parse_dt(args["due_after"])
        assignments = [a for a in assignments if a.due and a.due > after]

    # Filter by completion status
    include_completed = args.get("include_completed", False)
    if not include_completed:
        assignments = [a for a in assignments if not a.completed]

    return json.dumps([a.to_dict() for a in assignments], indent=2)


def handle_complete_canvas_assignment(args: dict, get_api: Callable) -> str:
    """Mark one or many Canvas assignments as complete.

    - Batch mode: ``identifiers`` array present → complete each, return batch response.
    - Single mode: top-level ``identifier`` → complete one, return flat dict.
    """
    from dgmt.canvas.fetcher import CanvasFetcher

    fetcher = CanvasFetcher()
    assignments = fetcher.get_assignments()

    if "identifiers" in args:
        succeeded: list[dict] = []
        failed: list[dict] = []
        for i, identifier in enumerate(args["identifiers"]):
            try:
                match = _find_canvas_assignment(assignments, identifier)
                fetcher.completion_store.mark_complete(match.uid, match.summary, match.course)
                succeeded.append({"index": i, "uid": match.uid, "title": match.title, "course": match.course})
            except Exception as e:
                failed.append({"index": i, "identifier": identifier, "error": str(e)})
        return json.dumps({
            "succeeded": succeeded,
            "failed": failed,
            "completed_count": len(succeeded),
            "failed_count": len(failed),
        }, indent=2)

    if "identifier" not in args:
        raise ValueError("Provide 'identifier' or 'identifiers' array.")

    match = _find_canvas_assignment(assignments, args["identifier"])
    fetcher.completion_store.mark_complete(match.uid, match.summary, match.course)
    return json.dumps({
        "completed": True,
        "uid": match.uid,
        "title": match.title,
        "course": match.course,
    })


def handle_uncomplete_canvas_assignment(args: dict, get_api: Callable) -> str:
    """Unmark one or many Canvas assignments as complete.

    - Batch mode: ``identifiers`` array present → uncomplete each, return batch response.
    - Single mode: top-level ``identifier`` → uncomplete one, return flat dict.
    """
    from dgmt.canvas.fetcher import CanvasFetcher

    fetcher = CanvasFetcher()
    assignments = fetcher.get_assignments()

    if "identifiers" in args:
        succeeded: list[dict] = []
        failed: list[dict] = []
        for i, identifier in enumerate(args["identifiers"]):
            try:
                match = _find_canvas_assignment(assignments, identifier)
                removed = fetcher.completion_store.mark_incomplete(match.uid)
                succeeded.append({"index": i, "uid": match.uid, "title": match.title, "course": match.course, "was_completed": removed})
            except Exception as e:
                failed.append({"index": i, "identifier": identifier, "error": str(e)})
        return json.dumps({
            "succeeded": succeeded,
            "failed": failed,
            "uncompleted_count": len(succeeded),
            "failed_count": len(failed),
        }, indent=2)

    if "identifier" not in args:
        raise ValueError("Provide 'identifier' or 'identifiers' array.")

    match = _find_canvas_assignment(assignments, args["identifier"])
    removed = fetcher.completion_store.mark_incomplete(match.uid)
    return json.dumps({
        "uncompleted": removed,
        "uid": match.uid,
        "title": match.title,
        "course": match.course,
    })


def handle_fetch_canvas_assignments(args: dict, get_api: Callable) -> str:
    """Force-fetch assignments from the Canvas .ics feed."""
    from dgmt.canvas.fetcher import CanvasFetcher

    fetcher = CanvasFetcher()
    assignments = fetcher.get_assignments(force_fetch=True)
    return json.dumps({
        "fetched": True,
        "count": len(assignments),
        "assignments": [a.to_dict() for a in assignments],
    }, indent=2)


def _find_canvas_assignment(assignments, identifier: str):
    """Find a canvas assignment by UID or fuzzy match. Raises ValueError on failure."""
    # Exact UID match
    for a in assignments:
        if a.uid == identifier:
            return a

    # Fuzzy match
    needle = identifier.lower()
    matches = [
        a for a in assignments
        if needle in a.summary.lower() or needle in a.title.lower()
    ]

    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise ValueError(f"No assignment matching '{identifier}'")
    names = [f"{a.title} ({a.course})" for a in matches[:5]]
    raise ValueError(
        f"Multiple matches for '{identifier}': {', '.join(names)}. "
        "Use a more specific search or the full UID."
    )


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
    "find_free_time": handle_find_free_time,
    "move_event": handle_move_event,
    "subdivide_event": handle_subdivide_event,
    "time_summary": handle_time_summary,
    "list_canvas_assignments": handle_list_canvas_assignments,
    "complete_canvas_assignment": handle_complete_canvas_assignment,
    "uncomplete_canvas_assignment": handle_uncomplete_canvas_assignment,
    "fetch_canvas_assignments": handle_fetch_canvas_assignments,
}
