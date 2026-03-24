"""Google Calendar color mapping and rule engine."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Optional


# Google Calendar color IDs mapped to (name, hex, ansi_256_code)
GOOGLE_COLORS: dict[str, tuple[str, str, int]] = {
    "1": ("Lavender", "#7986cb", 104),
    "2": ("Sage", "#33b679", 72),
    "3": ("Grape", "#8e24aa", 133),
    "4": ("Flamingo", "#e67c73", 174),
    "5": ("Banana", "#f6bf26", 220),
    "6": ("Tangerine", "#f4511e", 202),
    "7": ("Peacock", "#039be5", 39),
    "8": ("Graphite", "#616161", 241),
    "9": ("Blueberry", "#3f51b5", 62),
    "10": ("Basil", "#0b8043", 28),
    "11": ("Tomato", "#d50000", 160),
}

# Reverse lookup: lowercase name -> color_id
COLOR_NAME_TO_ID: dict[str, str] = {
    name.lower(): cid for cid, (name, _, _) in GOOGLE_COLORS.items()
}


@dataclass
class ColorMatch:
    """Result of a fuzzy color match attempt."""

    color_id: str
    color_name: str
    match_type: str  # "exact", "prefix", "fuzzy"


def fuzzy_color_match(name: str) -> Optional[ColorMatch]:
    """Match a color name using exact, prefix, or fuzzy matching.

    Match strategy (in priority order):
    1. Exact: case-insensitive exact match
    2. Prefix: unique color name starting with the input
    3. Fuzzy: difflib close match (only for inputs >= 3 chars, cutoff 0.6)
    """
    if not name:
        return None

    lower = name.lower()

    # 1. Exact match
    if lower in COLOR_NAME_TO_ID:
        cid = COLOR_NAME_TO_ID[lower]
        cname = GOOGLE_COLORS[cid][0]
        return ColorMatch(color_id=cid, color_name=cname, match_type="exact")

    # 2. Prefix match — must be unambiguous (exactly one match)
    prefix_matches = [
        (cname_lower, cid)
        for cname_lower, cid in COLOR_NAME_TO_ID.items()
        if cname_lower.startswith(lower)
    ]
    if len(prefix_matches) == 1:
        cid = prefix_matches[0][1]
        cname = GOOGLE_COLORS[cid][0]
        return ColorMatch(color_id=cid, color_name=cname, match_type="prefix")

    # 3. Fuzzy match — only for inputs with 3+ chars to avoid nonsense
    if len(lower) >= 3:
        all_names = list(COLOR_NAME_TO_ID.keys())
        close = difflib.get_close_matches(lower, all_names, n=1, cutoff=0.6)
        if close:
            cid = COLOR_NAME_TO_ID[close[0]]
            cname = GOOGLE_COLORS[cid][0]
            return ColorMatch(color_id=cid, color_name=cname, match_type="fuzzy")

    return None


def color_id_from_name(name: str) -> Optional[str]:
    """Get color ID from color name (fuzzy matching supported)."""
    match = fuzzy_color_match(name)
    return match.color_id if match else None


@dataclass
class ColorRule:
    """A rule that maps an event summary pattern to a color and optional reminders.

    The reminders field follows CalendarEvent three-state semantics:
    - None  → no override (caller/calendar default applies)
    - []    → disable all reminders
    - [...]  → custom overrides (e.g. [{"method": "popup", "minutes": 10}])
    """

    pattern: str
    color_id: str
    case_sensitive: bool = False
    reminders: Optional[list[dict[str, Any]]] = field(default=None)

    def matches(self, summary: str) -> bool:
        """Check if this rule matches the given summary."""
        if self.case_sensitive:
            return self.pattern in summary
        return self.pattern.lower() in summary.lower()

    def to_dict(self) -> dict:
        """Serialize to dict for config storage."""
        d: dict[str, Any] = {
            "pattern": self.pattern,
            "color_id": self.color_id,
            "case_sensitive": self.case_sensitive,
        }
        if self.reminders is not None:
            d["reminders"] = self.reminders
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ColorRule:
        """Deserialize from config dict."""
        return cls(
            pattern=data["pattern"],
            color_id=data["color_id"],
            case_sensitive=data.get("case_sensitive", False),
            reminders=data.get("reminders"),
        )


@dataclass
class RuleDefaults:
    """Resolved defaults from a color rule match."""

    color_id: Optional[str] = None
    reminders: Optional[list[dict[str, Any]]] = None


class ColorRuleEngine:
    """Engine for matching event summaries to colors and reminders via rules."""

    def __init__(self, rules: Optional[list[ColorRule]] = None) -> None:
        self._rules = rules or []

    @property
    def rules(self) -> list[ColorRule]:
        return self._rules

    def add_rule(self, rule: ColorRule) -> None:
        """Add a color rule."""
        self._rules.append(rule)

    def remove_rule(self, pattern: str) -> bool:
        """Remove a rule by pattern. Returns True if found and removed."""
        for i, rule in enumerate(self._rules):
            if rule.pattern == pattern:
                self._rules.pop(i)
                return True
        return False

    def match(self, summary: str) -> list[ColorRule]:
        """Return all rules that match the given summary."""
        return [rule for rule in self._rules if rule.matches(summary)]

    def resolve(self, summary: str) -> RuleDefaults:
        """Resolve defaults for a summary from matching rules.

        Returns color_id and reminders if exactly one rule matches.
        If zero or multiple rules match, returns empty defaults.
        """
        matches = self.match(summary)
        if len(matches) == 1:
            rule = matches[0]
            return RuleDefaults(color_id=rule.color_id, reminders=rule.reminders)
        return RuleDefaults()

    def resolve_color(self, summary: str) -> Optional[str]:
        """Resolve color for a summary. Returns color_id if exactly one match, None otherwise."""
        return self.resolve(summary).color_id

    @staticmethod
    def get_rich_style(color_id: str) -> str:
        """Get a Rich markup style string for a color ID."""
        if color_id in GOOGLE_COLORS:
            _, hex_color, _ = GOOGLE_COLORS[color_id]
            return f"bold {hex_color}"
        return "bold"

    @staticmethod
    def get_ansi_code(color_id: str) -> int:
        """Get ANSI 256-color code for a color ID."""
        if color_id in GOOGLE_COLORS:
            _, _, ansi = GOOGLE_COLORS[color_id]
            return ansi
        return 7  # default white

    @staticmethod
    def get_color_name(color_id: str) -> str:
        """Get human-readable color name."""
        if color_id in GOOGLE_COLORS:
            name, _, _ = GOOGLE_COLORS[color_id]
            return name
        return "Unknown"
