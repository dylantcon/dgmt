"""Output formatters for CLI commands."""

from __future__ import annotations

import json
from typing import Any


class Formatter:
    """Base class for output formatters."""

    def format(self, data: Any) -> str:
        """Format data for output."""
        raise NotImplementedError


class TableFormatter(Formatter):
    """Format data as a text table."""

    def __init__(self, headers: list[str], min_widths: dict[str, int] | None = None) -> None:
        self.headers = headers
        self.min_widths = min_widths or {}

    def format(self, rows: list[dict[str, Any]]) -> str:
        """Format rows as a table."""
        if not rows:
            return "(no data)"

        # Calculate column widths
        widths = {}
        for header in self.headers:
            min_width = self.min_widths.get(header, 0)
            max_data_width = max(len(str(row.get(header, ""))) for row in rows)
            widths[header] = max(len(header), max_data_width, min_width)

        # Build format string
        fmt = "  ".join(f"{{:<{widths[h]}}}" for h in self.headers)

        # Build output
        lines = [fmt.format(*self.headers)]
        lines.append(fmt.format(*["-" * widths[h] for h in self.headers]))

        for row in rows:
            values = [str(row.get(h, "")) for h in self.headers]
            lines.append(fmt.format(*values))

        return "\n".join(lines)


class JsonFormatter(Formatter):
    """Format data as JSON."""

    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    def format(self, data: Any) -> str:
        """Format data as JSON."""
        return json.dumps(data, indent=self.indent, default=str)


class StatusFormatter:
    """Format service/spoke status for display."""

    STATUS_SYMBOLS = {
        "running": "[+]",
        "online": "[+]",
        "stopped": "[-]",
        "offline": "[-]",
        "error": "[!]",
        "not_installed": "[?]",
        "unknown": "[?]",
        "syncing": "[~]",
    }

    @classmethod
    def format_status(cls, status: str) -> str:
        """Format a status with symbol."""
        symbol = cls.STATUS_SYMBOLS.get(status.lower(), "[?]")
        return f"{symbol} {status}"


def print_table(headers: list[str], rows: list[dict[str, Any]]) -> None:
    """Print data as a table."""
    formatter = TableFormatter(headers)
    print(formatter.format(rows))


def print_json(data: Any) -> None:
    """Print data as JSON."""
    formatter = JsonFormatter()
    print(formatter.format(data))


def print_status(name: str, status: str, extra: str = "") -> None:
    """Print a status line."""
    formatted = StatusFormatter.format_status(status)
    if extra:
        print(f"{formatted} {name}: {extra}")
    else:
        print(f"{formatted} {name}")


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{text}")
    print("=" * len(text))


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"[+] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"[!] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"[*] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"[~] {message}")
