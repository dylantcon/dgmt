"""Completion state manager for Canvas assignments."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dgmt.canvas.models import Assignment
from dgmt.core.config import get_timezone
from dgmt.utils.paths import ensure_parent_exists, expand_path


class CompletionStore:
    """Manages assignment completion state.

    State is stored in a JSON file that can sync across devices.
    """

    def __init__(self, completion_file: str = "~/.dgmt/state/canvas_completed.json") -> None:
        self._path = expand_path(completion_file)
        self._data: dict[str, Any] = {"version": 1, "completed": {}}

    def load(self) -> None:
        """Load completion state from disk."""
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, KeyError):
                self._data = {"version": 1, "completed": {}}

    def save(self) -> None:
        """Save completion state to disk."""
        ensure_parent_exists(self._path)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    @property
    def completed(self) -> dict[str, Any]:
        """Get the completed assignments dict."""
        return self._data.get("completed", {})

    def mark_complete(self, uid: str, summary: str = "", course: str = "") -> None:
        """Mark an assignment as completed."""
        self._data.setdefault("completed", {})[uid] = {
            "completed_at": datetime.now(get_timezone()).isoformat(),
            "summary": summary,
            "course": course,
        }
        self.save()

    def mark_incomplete(self, uid: str) -> bool:
        """Unmark an assignment as completed. Returns True if it was completed."""
        removed = self._data.get("completed", {}).pop(uid, None)
        if removed is not None:
            self.save()
            return True
        return False

    def is_completed(self, uid: str) -> bool:
        """Check if an assignment is marked as completed."""
        return uid in self._data.get("completed", {})

    def merge_into(self, assignments: list[Assignment]) -> list[Assignment]:
        """Apply completion state to a list of assignments.

        Sets completed/completed_at on each assignment based on stored state.
        Returns the same list (mutated in place) for convenience.
        """
        for a in assignments:
            entry = self.completed.get(a.uid)
            if entry:
                a.completed = True
                if entry.get("completed_at"):
                    a.completed_at = datetime.fromisoformat(entry["completed_at"])
        return assignments

    def prune(self, max_age_days: int = 90) -> int:
        """Remove completion entries older than max_age_days. Returns count removed."""
        now = datetime.now(get_timezone())
        to_remove: list[str] = []

        for uid, entry in self.completed.items():
            if entry.get("completed_at"):
                completed_at = datetime.fromisoformat(entry["completed_at"])
                age_days = (now - completed_at).days
                if age_days > max_age_days:
                    to_remove.append(uid)

        for uid in to_remove:
            del self._data["completed"][uid]

        if to_remove:
            self.save()

        return len(to_remove)
