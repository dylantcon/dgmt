"""Parse Canvas .ics feed into Assignment objects."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

from icalendar import Calendar

from dgmt.canvas.models import Assignment
from dgmt.core.config import CanvasConfig, get_timezone

# Matches [CIS4930] or [CIS4930-001] or [CIS 4930] or [CIS3250L-0004.sp26]
_BRACKETED_COURSE = re.compile(r"\[([A-Z]{2,4}\s?\d{4}[A-Z]?)(?:-\d+)?(?:\.\w+)?\]")

# Matches bare CIS4930 or COT 4420 or CIS3250L at word boundary
_BARE_COURSE = re.compile(r"\b([A-Z]{2,4}\s?\d{4}[A-Z]?)\b")

# Matches trailing date patterns like "(Mon Mar 20 at 11:59pm)" or "(due Mar 20)"
_TRAILING_DATE = re.compile(r"\s*\((?:due\s+)?[A-Z][a-z]{2}.*?\)\s*$", re.IGNORECASE)

# Matches leading course bracket like "[CIS4930] " or "[CIS4930-001] "
_LEADING_BRACKET = re.compile(r"^\[[A-Z]{2,4}\s?\d{4}[A-Z]?(?:-\d+)?\]\s*")

# Matches trailing Canvas bracket like "[CAP5768-0001.sp26]" or "[CIS3250L-0004.sp26]"
_TRAILING_BRACKET = re.compile(
    r"\s*\[[A-Z]{2,5}\d{4}[A-Z]?(?:-\d+)?(?:\.\w+)?\]\s*$"
)


def extract_course_code(summary: str, categories: str = "") -> str:
    """Extract a normalized course code from a VEVENT summary or categories.

    Tries bracketed codes first, then bare codes, then CATEGORIES field.
    Returns normalized code (spaces stripped, uppercased) or "".
    """
    # 1. Bracketed: [CIS4930] or [CIS4930-001]
    m = _BRACKETED_COURSE.search(summary)
    if m:
        return _normalize_course(m.group(1))

    # 2. Bare: CIS4930 at word boundary
    m = _BARE_COURSE.search(summary)
    if m:
        return _normalize_course(m.group(1))

    # 3. Check CATEGORIES fallback
    if categories:
        m = _BARE_COURSE.search(categories)
        if m:
            return _normalize_course(m.group(1))

    return ""


def _normalize_course(code: str) -> str:
    """Normalize course code: strip spaces, uppercase."""
    return code.replace(" ", "").upper()


def extract_title(summary: str, course_code: str) -> str:
    """Clean up summary into a readable title.

    Removes [COURSE] prefix/suffix and trailing date patterns.
    """
    title = summary

    # Remove leading bracket course code
    title = _LEADING_BRACKET.sub("", title)

    # Remove trailing bracket course code (Canvas format: "Title [CIS4930-0001.sp26]")
    title = _TRAILING_BRACKET.sub("", title)

    # Remove bare course code at the start if it matches
    if course_code and title.upper().startswith(course_code):
        title = title[len(course_code):].lstrip(" :-")

    # Remove trailing date patterns
    title = _TRAILING_DATE.sub("", title)

    return title.strip()


def is_assignment(summary: str, keywords: list[str], has_rrule: bool) -> bool:
    """Determine if a VEVENT represents an assignment vs. a class meeting.

    - Recurring events (RRULE) are class meetings, not assignments
    - If keywords list is empty, include everything non-recurring
    - Otherwise check if any keyword appears in summary
    """
    if has_rrule:
        return False

    if not keywords:
        return True

    summary_lower = summary.lower()
    return any(kw.lower() in summary_lower for kw in keywords)


def _normalize_dt(dt_value, tz) -> Optional[datetime]:
    """Normalize an icalendar date/datetime to a tz-aware datetime.

    The icalendar library returns either date or datetime objects.
    Canvas uses DTSTART for due dates.
    """
    if dt_value is None:
        return None

    dt = dt_value.dt if hasattr(dt_value, "dt") else dt_value

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt

    if isinstance(dt, date):
        # Convert date to datetime at end of day (11:59 PM)
        return datetime(dt.year, dt.month, dt.day, 23, 59, 0, tzinfo=tz)

    return None


def parse_ics(ical_text: str, config: CanvasConfig) -> list[Assignment]:
    """Parse .ics text into a list of Assignment objects.

    Filters by assignment keywords and excludes recurring events.
    """
    tz = get_timezone()
    cal = Calendar.from_ical(ical_text)
    assignments: list[Assignment] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", ""))
        if not summary:
            continue

        uid = str(component.get("UID", ""))
        has_rrule = component.get("RRULE") is not None

        if not is_assignment(summary, config.assignment_keywords, has_rrule):
            continue

        categories = ""
        cat_prop = component.get("CATEGORIES")
        if cat_prop:
            if isinstance(cat_prop, list):
                categories = " ".join(str(c) for c in cat_prop)
            else:
                categories = str(cat_prop)

        course = extract_course_code(summary, categories)

        # Apply course aliases
        if course in config.course_aliases:
            course = config.course_aliases[course]

        title = extract_title(summary, course)

        # Canvas uses DTSTART for due dates
        due = _normalize_dt(component.get("DTSTART"), tz)

        description = str(component.get("DESCRIPTION", ""))

        # Extract URL from description or URL property
        url = None
        url_prop = component.get("URL")
        if url_prop:
            url = str(url_prop)

        assignments.append(Assignment(
            uid=uid,
            summary=summary,
            course=course,
            title=title,
            due=due,
            description=description,
            url=url,
        ))

    # Sort by due date (None last)
    far_future = datetime.max.replace(tzinfo=tz)
    assignments.sort(key=lambda a: (a.due is None, a.due or far_future))
    return assignments
