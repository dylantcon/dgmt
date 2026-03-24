"""Canvas assignment data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Assignment:
    """Represents a Canvas LMS assignment parsed from an .ics feed."""

    uid: str
    summary: str  # raw VEVENT SUMMARY
    course: str  # extracted course code (e.g. "CIS4930"), "" if unknown
    title: str  # cleaned title after removing course prefix/date suffix
    due: Optional[datetime] = None
    description: str = ""
    url: Optional[str] = None
    completed: bool = False
    completed_at: Optional[datetime] = None

    @property
    def is_past(self) -> bool:
        """True if the assignment due date is in the past."""
        if self.due is None:
            return False
        return self.due < datetime.now(self.due.tzinfo)

    @property
    def days_until_due(self) -> Optional[int]:
        """Days until due date. Negative if past due. None if no due date."""
        if self.due is None:
            return None
        delta = self.due - datetime.now(self.due.tzinfo)
        return delta.days

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "uid": self.uid,
            "summary": self.summary,
            "course": self.course,
            "title": self.title,
            "due": self.due.isoformat() if self.due else None,
            "description": self.description,
            "url": self.url,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assignment:
        """Deserialize from a dictionary."""
        due = None
        if data.get("due"):
            due = datetime.fromisoformat(data["due"])

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        return cls(
            uid=data["uid"],
            summary=data.get("summary", ""),
            course=data.get("course", ""),
            title=data.get("title", ""),
            due=due,
            description=data.get("description", ""),
            url=data.get("url"),
            completed=data.get("completed", False),
            completed_at=completed_at,
        )
