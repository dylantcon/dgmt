"""Google Calendar API wrapper."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from googleapiclient.discovery import build

from dgmt.calendar.auth import TokenManager
from dgmt.calendar.models import CalendarEvent
from dgmt.utils.logging import get_logger


class CalendarAPI:
    """Wrapper around the Google Calendar API."""

    def __init__(self, token_manager: Optional[TokenManager] = None) -> None:
        self._token_manager = token_manager or TokenManager()
        self._service = None
        self._logger = get_logger("dgmt.calendar.api")

    def _get_service(self):
        """Get or create the Calendar API service."""
        if self._service is None:
            creds = self._token_manager.get_or_authorize()
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def list_events(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        calendar_id: str = "primary",
        max_results: int = 250,
    ) -> list[CalendarEvent]:
        """List events in a time range."""
        service = self._get_service()

        if start is None:
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if end is None:
            end = start + timedelta(days=7)

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start.isoformat() + "Z" if start.tzinfo is None else start.isoformat(),
                timeMax=end.isoformat() + "Z" if end.tzinfo is None else end.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return [CalendarEvent.from_google_body(e) for e in events_result.get("items", [])]

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent:
        """Get a single event by ID."""
        service = self._get_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return CalendarEvent.from_google_body(event)

    def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Create a new event."""
        service = self._get_service()
        calendar_id = event.calendar_id or "primary"
        body = event.to_google_body()

        self._logger.info(f"Creating event: {event.summary}")
        result = service.events().insert(calendarId=calendar_id, body=body).execute()
        return CalendarEvent.from_google_body(result)

    def update_event(self, event: CalendarEvent) -> CalendarEvent:
        """Update an existing event."""
        service = self._get_service()
        calendar_id = event.calendar_id or "primary"
        body = event.to_google_body()

        if not event.id:
            raise ValueError("Event ID is required for update")

        self._logger.info(f"Updating event: {event.id}")
        result = (
            service.events()
            .update(calendarId=calendar_id, eventId=event.id, body=body)
            .execute()
        )
        return CalendarEvent.from_google_body(result)

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete an event."""
        service = self._get_service()

        self._logger.info(f"Deleting event: {event_id}")
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True

    def list_calendars(self) -> list[dict]:
        """List available calendars."""
        service = self._get_service()
        result = service.calendarList().list().execute()
        return [
            {
                "id": cal["id"],
                "summary": cal.get("summary", ""),
                "primary": cal.get("primary", False),
                "color_id": cal.get("colorId", ""),
            }
            for cal in result.get("items", [])
        ]
