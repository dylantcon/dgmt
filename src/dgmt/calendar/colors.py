"""Google Calendar color mapping and rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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


def color_id_from_name(name: str) -> Optional[str]:
    """Get color ID from color name (case-insensitive)."""
    return COLOR_NAME_TO_ID.get(name.lower())


@dataclass
class ColorRule:
    """A rule that maps an event summary pattern to a color."""

    pattern: str
    color_id: str
    case_sensitive: bool = False

    def matches(self, summary: str) -> bool:
        """Check if this rule matches the given summary."""
        if self.case_sensitive:
            return self.pattern in summary
        return self.pattern.lower() in summary.lower()

    def to_dict(self) -> dict:
        """Serialize to dict for config storage."""
        return {
            "pattern": self.pattern,
            "color_id": self.color_id,
            "case_sensitive": self.case_sensitive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ColorRule:
        """Deserialize from config dict."""
        return cls(
            pattern=data["pattern"],
            color_id=data["color_id"],
            case_sensitive=data.get("case_sensitive", False),
        )


class ColorRuleEngine:
    """Engine for matching event summaries to colors via rules."""

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

    def resolve_color(self, summary: str) -> Optional[str]:
        """Resolve color for a summary. Returns color_id if exactly one match, None otherwise."""
        matches = self.match(summary)
        if len(matches) == 1:
            return matches[0].color_id
        return None

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
