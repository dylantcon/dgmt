"""MCP server setup and tool registration.

Uses the `mcp` Python SDK to expose dgmt calendar and color rule
operations as tools for AI agents (e.g., Claude Desktop).
"""

from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from dgmt.mcp.tools import TOOL_HANDLERS

# Tool schemas — each describes one MCP tool with its JSON Schema input
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_events",
        "description": "List Google Calendar events in a date range with optional filtering. Returns events with id, summary, start, end, location, description, color, recurrence, recurring_event_id, and is_recurring_instance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM). Defaults to today."},
                "end": {"type": "string", "description": "End date/time. Defaults to start + 7 days."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
                "color": {"type": "string", "description": "Filter by color name (fuzzy matching supported)."},
                "summary_contains": {"type": "string", "description": "Filter to events whose summary contains this text (case-insensitive)."},
            },
        },
    },
    {
        "name": "get_event",
        "description": "Get a single Google Calendar event by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "create_event",
        "description": (
            "Create Google Calendar events. Two modes:\n"
            "- Single: provide summary + start (and optional fields) at the top level.\n"
            "- Batch: provide an 'events' array of event objects.\n"
            "Do not mix both modes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title (single mode)."},
                "start": {"type": "string", "description": "Start date/time (single mode). YYYY-MM-DD HH:MM or YYYY-MM-DD for all-day."},
                "end": {"type": "string", "description": "End date/time. Defaults to start + 1 hour (or +1 day for all-day)."},
                "all_day": {"type": "boolean", "description": "Whether this is an all-day event."},
                "description": {"type": "string", "description": "Event description."},
                "location": {"type": "string", "description": "Event location."},
                "color": {"type": "string", "description": "Color name (e.g., 'Peacock', 'Tomato'). See list_available_colors."},
                "recurrence": {"type": "string", "description": "Recurrence: preset (daily, weekly, monthly, yearly, weekdays, biweekly) or RRULE string."},
                "reminders": {
                    "description": "Reminders/notifications. Omit for calendar default. \"none\" to disable. Or array of {\"method\": \"popup\"|\"email\", \"minutes\": N}.",
                    "oneOf": [
                        {"type": "string", "enum": ["none"]},
                        {"type": "array", "items": {"type": "object", "properties": {"method": {"type": "string", "enum": ["popup", "email"]}, "minutes": {"type": "integer"}}, "required": ["method", "minutes"]}},
                    ],
                },
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
                "events": {
                    "type": "array",
                    "description": "Batch mode: array of event objects to create.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string", "description": "Event title."},
                            "start": {"type": "string", "description": "Start date/time."},
                            "end": {"type": "string", "description": "End date/time."},
                            "all_day": {"type": "boolean", "description": "Whether this is an all-day event."},
                            "description": {"type": "string", "description": "Event description."},
                            "location": {"type": "string", "description": "Event location."},
                            "color": {"type": "string", "description": "Color name (fuzzy matching supported)."},
                            "recurrence": {"type": "string", "description": "Recurrence preset or RRULE string."},
                            "reminders": {
                                "description": "Reminders. Omit for calendar default. \"none\" to disable. Or array of {\"method\": \"popup\"|\"email\", \"minutes\": N}.",
                                "oneOf": [
                                    {"type": "string", "enum": ["none"]},
                                    {"type": "array", "items": {"type": "object", "properties": {"method": {"type": "string", "enum": ["popup", "email"]}, "minutes": {"type": "integer"}}, "required": ["method", "minutes"]}},
                                ],
                            },
                            "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
                        },
                        "required": ["summary", "start"],
                    },
                },
            },
        },
    },
    {
        "name": "update_event",
        "description": (
            "Update Google Calendar events. Two modes:\n"
            "- Single: provide event_id + fields to change at the top level.\n"
            "- Batch: provide an 'updates' array of update objects (each must include event_id).\n"
            "Only provided fields are changed. Do not mix both modes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to update (single mode)."},
                "summary": {"type": "string", "description": "New event title."},
                "start": {"type": "string", "description": "New start date/time."},
                "end": {"type": "string", "description": "New end date/time."},
                "all_day": {"type": "boolean", "description": "Toggle all-day status."},
                "description": {"type": "string", "description": "New description. Use empty string to clear."},
                "location": {"type": "string", "description": "New location. Use empty string to clear."},
                "color": {"type": "string", "description": "New color name."},
                "recurrence": {"type": "string", "description": "New recurrence (preset/RRULE, or 'none' to clear)."},
                "reminders": {
                    "description": "Reminders. Omit to keep current. \"none\" to disable. \"default\" to revert to calendar defaults. Or array of {\"method\": \"popup\"|\"email\", \"minutes\": N}.",
                    "oneOf": [
                        {"type": "string", "enum": ["none", "default"]},
                        {"type": "array", "items": {"type": "object", "properties": {"method": {"type": "string", "enum": ["popup", "email"]}, "minutes": {"type": "integer"}}, "required": ["method", "minutes"]}},
                    ],
                },
                "calendar_id": {"type": "string", "description": "Calendar ID."},
                "updates": {
                    "type": "array",
                    "description": "Batch mode: array of update objects. Each must include event_id plus fields to change.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "The event ID to update."},
                            "summary": {"type": "string", "description": "New event title."},
                            "start": {"type": "string", "description": "New start date/time."},
                            "end": {"type": "string", "description": "New end date/time."},
                            "all_day": {"type": "boolean", "description": "Toggle all-day status."},
                            "description": {"type": "string", "description": "New description."},
                            "location": {"type": "string", "description": "New location."},
                            "color": {"type": "string", "description": "New color name."},
                            "recurrence": {"type": "string", "description": "Recurrence preset or RRULE string."},
                            "reminders": {
                                "description": "Reminders. Omit to keep current. \"none\" to disable. \"default\" for calendar defaults. Or array.",
                                "oneOf": [
                                    {"type": "string", "enum": ["none", "default"]},
                                    {"type": "array", "items": {"type": "object", "properties": {"method": {"type": "string", "enum": ["popup", "email"]}, "minutes": {"type": "integer"}}, "required": ["method", "minutes"]}},
                                ],
                            },
                            "calendar_id": {"type": "string", "description": "Calendar ID."},
                        },
                        "required": ["event_id"],
                    },
                },
            },
        },
    },
    {
        "name": "delete_event",
        "description": (
            "Delete Google Calendar events. Three modes:\n"
            "- Single: provide event_id.\n"
            "- Batch by IDs: provide event_ids array.\n"
            "- Range: provide start + end (with optional color/summary_contains filters).\n"
            "All modes support dry_run to preview without deleting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Single event ID to delete."},
                "event_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Batch mode: list of event IDs to delete.",
                },
                "start": {"type": "string", "description": "Start of date range (range mode)."},
                "end": {"type": "string", "description": "End of date range (range mode)."},
                "color": {"type": "string", "description": "Filter by color name (range mode, fuzzy matching supported)."},
                "summary_contains": {"type": "string", "description": "Filter by summary text (range mode, case-insensitive)."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
                "dry_run": {"type": "boolean", "description": "If true, preview what would be deleted without actually deleting."},
            },
        },
    },
    {
        "name": "list_calendars",
        "description": "List all available Google Calendars with their IDs, names, and primary status.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_color_rules",
        "description": "List all configured dgmt color rules that auto-assign colors and reminders to events based on summary patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_color_rule",
        "description": "Add a new color rule. When an event summary contains the pattern, it will be assigned the specified color and optional reminder defaults. These defaults are auto-applied on event creation when the caller doesn't explicitly set color/reminders.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text pattern to match in event summaries."},
                "color": {"type": "string", "description": "Color name (e.g., 'Peacock', 'Tomato'). See list_available_colors."},
                "case_sensitive": {"type": "boolean", "description": "Whether matching is case-sensitive. Default: false."},
                "reminders": {
                    "description": "Default reminders for matching events. Omit for no reminder override. \"none\" to disable reminders. Or array of {\"method\": \"popup\"|\"email\", \"minutes\": N}.",
                    "oneOf": [
                        {"type": "string", "enum": ["none"]},
                        {"type": "array", "items": {"type": "object", "properties": {"method": {"type": "string", "enum": ["popup", "email"]}, "minutes": {"type": "integer"}}, "required": ["method", "minutes"]}},
                    ],
                },
            },
            "required": ["pattern", "color"],
        },
    },
    {
        "name": "remove_color_rule",
        "description": "Remove a color rule by its pattern string.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "The exact pattern string of the rule to remove."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_available_colors",
        "description": "List all 11 Google Calendar colors with their IDs, names, and hex values.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clear_range",
        "description": "Delete events in a date range (with optional filters) and optionally fill the gaps with new events. Useful for clearing a time period and replacing with placeholder events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start of date range."},
                "end": {"type": "string", "description": "End of date range."},
                "color": {"type": "string", "description": "Filter: only delete events with this color (fuzzy matching supported)."},
                "summary_contains": {"type": "string", "description": "Filter: only delete events whose summary contains this text (case-insensitive)."},
                "fill_summary": {"type": "string", "description": "If provided, create fill events in the gaps left by deleted events with this summary."},
                "fill_color": {"type": "string", "description": "Color for fill events (fuzzy matching supported)."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
                "dry_run": {"type": "boolean", "description": "If true, preview deletions and fill events without executing."},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "find_free_time",
        "description": "Find unallocated time blocks in a date range. Only considers timed events (all-day events do not block free slots).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start of date range (YYYY-MM-DD or YYYY-MM-DD HH:MM)."},
                "end": {"type": "string", "description": "End of date range."},
                "min_duration": {"type": "integer", "description": "Minimum free block duration in minutes. Blocks shorter than this are excluded."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "move_event",
        "description": "Reschedule an event to a new start time, automatically computing the new end time from the original duration. Preserves the event ID and all metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to move."},
                "new_start": {"type": "string", "description": "New start date/time (YYYY-MM-DD HH:MM or YYYY-MM-DD for all-day)."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["event_id", "new_start"],
        },
    },
    {
        "name": "subdivide_event",
        "description": (
            "Split one event into N contiguous sub-events. Two modes:\n"
            "- count: divide into N equal parts (min 2).\n"
            "- split_points: provide explicit datetime boundaries within the event.\n"
            "Sub-events inherit summary (with '(1/N)' suffix), description, location, color, and reminders. "
            "Original event is only deleted after all sub-events are successfully created."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to subdivide."},
                "count": {"type": "integer", "description": "Number of equal parts to split into (min 2)."},
                "split_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit split points as datetime strings. Must be within the event's time range.",
                },
                "new_summary": {"type": "string", "description": "Override summary for sub-events (default: original summary)."},
                "new_color": {"type": "string", "description": "Override color for sub-events (default: original color)."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "time_summary",
        "description": "Get a time usage breakdown for a date range. Groups events by color (default) or summary text. Timed events are reported in hours; all-day events are reported in days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start of date range (YYYY-MM-DD or YYYY-MM-DD HH:MM)."},
                "end": {"type": "string", "description": "End of date range."},
                "group_by": {"type": "string", "enum": ["color", "summary"], "description": "How to group events. Default: 'color'."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "list_canvas_assignments",
        "description": "List Canvas LMS assignments from the .ics subscription feed. Returns assignments with uid, summary, course, title, due date, completion status, and URL. By default only shows upcoming incomplete assignments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course": {"type": "string", "description": "Filter by course code (e.g., 'CIS4930')."},
                "due_before": {"type": "string", "description": "Show assignments due before this date (YYYY-MM-DD or YYYY-MM-DD HH:MM)."},
                "due_after": {"type": "string", "description": "Show assignments due after this date."},
                "include_completed": {"type": "boolean", "description": "Include completed assignments. Default: false."},
            },
        },
    },
    {
        "name": "complete_canvas_assignment",
        "description": "Mark one or many Canvas assignments as complete. Single mode: provide 'identifier'. Batch mode: provide 'identifiers' array to complete multiple in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Single assignment UID or fuzzy summary/title match."},
                "identifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of assignment UIDs or fuzzy matches to complete in batch.",
                },
            },
        },
    },
    {
        "name": "uncomplete_canvas_assignment",
        "description": "Unmark one or many Canvas assignments as complete. Single mode: provide 'identifier'. Batch mode: provide 'identifiers' array.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Single assignment UID or fuzzy summary/title match."},
                "identifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of assignment UIDs or fuzzy matches to uncomplete in batch.",
                },
            },
        },
    },
    {
        "name": "fetch_canvas_assignments",
        "description": "Force-fetch assignments from the Canvas .ics feed, bypassing the cache. Returns all fetched assignments.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def create_server() -> Server:
    """Create and configure the MCP server with all dgmt tools.

    The CalendarAPI is lazily initialized on the first tool call that
    needs it, so the server starts quickly even without valid OAuth tokens.
    """
    server = Server("dgmt")

    # Lazy CalendarAPI singleton
    _api_instance = None

    def get_api():
        nonlocal _api_instance
        if _api_instance is None:
            from dgmt.calendar.api import CalendarAPI
            _api_instance = CalendarAPI()
        return _api_instance

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=schema["name"],
                description=schema["description"],
                inputSchema=schema["inputSchema"],
            )
            for schema in TOOL_SCHEMAS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        try:
            result = handler(arguments or {}, get_api)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]

    return server


async def run_server() -> None:
    """Run the MCP server with stdio transport."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
