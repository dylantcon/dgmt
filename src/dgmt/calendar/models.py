"""Calendar event data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Optional


@dataclass
class CalendarEvent:
    """Represents a Google Calendar event."""

    id: Optional[str] = None
    summary: str = ""
    description: str = ""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    all_day: bool = False
    location: str = ""
    color_id: Optional[str] = None
    calendar_id: str = "primary"
    recurrence: list[str] = field(default_factory=list)
    recurring_event_id: Optional[str] = None

    @property
    def is_recurring_instance(self) -> bool:
        """True if this event is an expanded instance of a recurring series."""
        return self.recurring_event_id is not None

    def to_google_body(self) -> dict[str, Any]:
        """Convert to Google Calendar API request body."""
        body: dict[str, Any] = {}

        if self.summary:
            body["summary"] = self.summary
        if self.description:
            body["description"] = self.description
        if self.location:
            body["location"] = self.location
        if self.color_id:
            body["colorId"] = self.color_id
        if self.recurrence:
            body["recurrence"] = self.recurrence

        if self.all_day:
            if self.start:
                body["start"] = {"date": self.start.strftime("%Y-%m-%d")}
            if self.end:
                body["end"] = {"date": self.end.strftime("%Y-%m-%d")}
        else:
            if self.start:
                body["start"] = {
                    "dateTime": self.start.isoformat(),
                    "timeZone": "America/New_York",
                }
            if self.end:
                body["end"] = {
                    "dateTime": self.end.isoformat(),
                    "timeZone": "America/New_York",
                }

        return body

    @classmethod
    def from_google_body(cls, data: dict[str, Any]) -> CalendarEvent:
        """Create a CalendarEvent from Google Calendar API response."""
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        all_day = "date" in start_data and "dateTime" not in start_data

        if all_day:
            start = datetime.strptime(start_data["date"], "%Y-%m-%d") if start_data.get("date") else None
            end = datetime.strptime(end_data["date"], "%Y-%m-%d") if end_data.get("date") else None
        else:
            start = (
                datetime.fromisoformat(start_data["dateTime"])
                if start_data.get("dateTime")
                else None
            )
            end = (
                datetime.fromisoformat(end_data["dateTime"])
                if end_data.get("dateTime")
                else None
            )

        return cls(
            id=data.get("id"),
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            start=start,
            end=end,
            all_day=all_day,
            location=data.get("location", ""),
            color_id=data.get("colorId"),
            calendar_id=data.get("organizer", {}).get("email", "primary"),
            recurrence=data.get("recurrence", []),
            recurring_event_id=data.get("recurringEventId"),
        )
