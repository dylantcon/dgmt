"""Output formatters for Canvas assignments."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from dgmt.canvas.models import Assignment


def format_table(assignments: list[Assignment]) -> None:
    """Print assignments as a Rich table with urgency color-coding."""
    console = Console()

    if not assignments:
        console.print("[dim]No assignments found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", width=4, justify="center")
    table.add_column("Course", min_width=8)
    table.add_column("Title", min_width=20)
    table.add_column("Due", min_width=18)
    table.add_column("Days", justify="right", width=6)

    for a in assignments:
        status = "[green]done[/green]" if a.completed else "[dim]--[/dim]"
        course = a.course or "[dim]???[/dim]"
        title = a.title or a.summary

        if a.due:
            due_str = a.due.strftime("%a %b %d %I:%M %p")
            days = a.days_until_due
            if days is None:
                days_str = ""
                style = ""
            elif days < 0:
                days_str = f"{days}d"
                style = "dim" if a.completed else "red"
            elif days == 0:
                days_str = "today"
                style = "bold red"
            elif days <= 2:
                days_str = f"{days}d"
                style = "yellow"
            else:
                days_str = f"{days}d"
                style = ""
        else:
            due_str = "[dim]no date[/dim]"
            days_str = ""
            style = ""

        if style and not a.completed:
            due_str = f"[{style}]{due_str}[/{style}]"
            days_str = f"[{style}]{days_str}[/{style}]"

        table.add_row(status, course, title, due_str, days_str)

    console.print(table)


def format_markdown(assignments: list[Assignment]) -> str:
    """Format assignments as markdown checklist for Templater.

    Includes <!-- canvas:uid --> comments for rollover identification.
    """
    lines: list[str] = []
    for a in assignments:
        check = "x" if a.completed else " "
        course = f"**{a.course}**" if a.course else "**???**"
        title = a.title or a.summary

        if a.due:
            due_str = a.due.strftime("%a %b %d")
            due_part = f" (due {due_str})"
        else:
            due_part = ""

        line = rf"- [{check}] {course} $\rightarrow$ {title}{due_part} <!-- canvas:{a.uid} -->"
        lines.append(line)

    return "\n".join(lines)


def format_json(assignments: list[Assignment]) -> str:
    """Format assignments as JSON."""
    return json.dumps([a.to_dict() for a in assignments], indent=2)
