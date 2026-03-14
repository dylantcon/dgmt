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
        "description": "List Google Calendar events in a date range. Returns events with id, summary, start, end, location, description, color, and recurrence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM). Defaults to today."},
                "end": {"type": "string", "description": "End date/time. Defaults to start + 7 days."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
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
        "description": "Create a new Google Calendar event. Supports all-day events, recurrence, location, description, and color.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title."},
                "start": {"type": "string", "description": "Start date/time (YYYY-MM-DD HH:MM or YYYY-MM-DD for all-day)."},
                "end": {"type": "string", "description": "End date/time. Defaults to start + 1 hour (or +1 day for all-day)."},
                "all_day": {"type": "boolean", "description": "Whether this is an all-day event."},
                "description": {"type": "string", "description": "Event description."},
                "location": {"type": "string", "description": "Event location."},
                "color": {"type": "string", "description": "Color name (e.g., 'Peacock', 'Tomato'). See list_available_colors."},
                "recurrence": {"type": "string", "description": "Recurrence: preset (daily, weekly, monthly, yearly, weekdays, biweekly) or RRULE string."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["summary", "start"],
        },
    },
    {
        "name": "update_event",
        "description": "Update an existing Google Calendar event. Only provided fields are changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to update."},
                "summary": {"type": "string", "description": "New event title."},
                "start": {"type": "string", "description": "New start date/time."},
                "end": {"type": "string", "description": "New end date/time."},
                "all_day": {"type": "boolean", "description": "Toggle all-day status."},
                "description": {"type": "string", "description": "New description. Use empty string to clear."},
                "location": {"type": "string", "description": "New location. Use empty string to clear."},
                "color": {"type": "string", "description": "New color name."},
                "recurrence": {"type": "string", "description": "New recurrence (preset/RRULE, or 'none' to clear)."},
                "calendar_id": {"type": "string", "description": "Calendar ID."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_event",
        "description": "Delete a Google Calendar event by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to delete."},
                "calendar_id": {"type": "string", "description": "Calendar ID. Defaults to 'primary'."},
            },
            "required": ["event_id"],
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
        "description": "List all configured dgmt color rules that auto-assign colors to events based on summary patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_color_rule",
        "description": "Add a new color rule. When an event summary contains the pattern, it will be assigned the specified color.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text pattern to match in event summaries."},
                "color": {"type": "string", "description": "Color name (e.g., 'Peacock', 'Tomato'). See list_available_colors."},
                "case_sensitive": {"type": "boolean", "description": "Whether matching is case-sensitive. Default: false."},
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
