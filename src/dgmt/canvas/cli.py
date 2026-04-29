"""Canvas CLI subcommands."""

from __future__ import annotations

import argparse
import sys

from dgmt.cli.formatters import print_error, print_info, print_success, print_warning


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the canvas subcommand and its sub-subcommands."""
    canvas_parser = subparsers.add_parser(
        "canvas",
        help="Canvas LMS assignment tracking",
        description="Track Canvas assignments via .ics subscription feed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  dgmt canvas auth set          Set your Canvas .ics URL
  dgmt canvas fetch             Force-fetch assignments from Canvas
  dgmt canvas list              List upcoming assignments
  dgmt canvas list --format md  Markdown output for Templater
  dgmt canvas list --course CIS4930
  dgmt canvas complete "HW5" "Quiz 3"  Mark one or more done
  dgmt canvas uncomplete "HW5"         Unmark assignment(s)
  dgmt canvas courses                  List detected courses
""",
    )

    canvas_sub = canvas_parser.add_subparsers(dest="canvas_command", metavar="<command>")

    # --- auth ---
    auth_parser = canvas_sub.add_parser("auth", help="Manage Canvas .ics URL")
    auth_parser.set_defaults(func=cmd_auth)
    auth_sub = auth_parser.add_subparsers(dest="auth_command")

    auth_set = auth_sub.add_parser("set", help="Set .ics URL")
    auth_set.add_argument("--url", help="Canvas .ics URL (prompts if omitted)")
    auth_set.set_defaults(func=cmd_auth_set)

    auth_revoke = auth_sub.add_parser("revoke", help="Remove stored URL")
    auth_revoke.set_defaults(func=cmd_auth_revoke)

    # --- fetch ---
    fetch_parser = canvas_sub.add_parser("fetch", help="Force-fetch .ics feed")
    fetch_parser.set_defaults(func=cmd_fetch)

    # --- list ---
    list_parser = canvas_sub.add_parser("list", help="List assignments")
    list_parser.add_argument(
        "--format", "-f",
        choices=["table", "markdown", "md", "json"],
        default="table",
        help="Output format (default: table)",
    )
    list_parser.add_argument("--course", "-c", help="Filter by course code")
    list_parser.add_argument("--due-before", help="Show assignments due before date (YYYY-MM-DD)")
    list_parser.add_argument("--due-after", help="Show assignments due after date (YYYY-MM-DD)")
    list_parser.add_argument("--date", "-d", help="Show assignments due on this date (YYYY-MM-DD)")
    list_parser.add_argument(
        "--include-completed", action="store_true",
        help="Include completed assignments",
    )
    list_parser.add_argument(
        "--completed-only", action="store_true",
        help="Show only completed assignments",
    )
    list_parser.set_defaults(func=cmd_list)

    # --- complete ---
    complete_parser = canvas_sub.add_parser("complete", help="Mark assignment(s) complete")
    complete_parser.add_argument(
        "identifiers",
        nargs="+",
        metavar="IDENTIFIER",
        help="One or more assignment UIDs or fuzzy summary matches",
    )
    complete_parser.set_defaults(func=cmd_complete)

    # --- uncomplete ---
    uncomplete_parser = canvas_sub.add_parser("uncomplete", help="Unmark assignment(s) complete")
    uncomplete_parser.add_argument(
        "identifiers",
        nargs="+",
        metavar="IDENTIFIER",
        help="One or more assignment UIDs or fuzzy summary matches",
    )
    uncomplete_parser.set_defaults(func=cmd_uncomplete)

    # --- courses ---
    courses_parser = canvas_sub.add_parser("courses", help="List detected courses")
    courses_parser.set_defaults(func=cmd_courses)


def _get_fetcher():
    """Create a CanvasFetcher with current config."""
    from dgmt.canvas.fetcher import CanvasFetcher
    return CanvasFetcher()


def _fuzzy_match(assignments, identifier: str):
    """Find an assignment by UID or fuzzy summary/title match.

    Returns (assignment, None) on success, or (None, error_message) on failure.
    """
    # Exact UID match
    for a in assignments:
        if a.uid == identifier:
            return a, None

    # Fuzzy match on summary/title (case-insensitive)
    needle = identifier.lower()
    matches = [
        a for a in assignments
        if needle in a.summary.lower() or needle in a.title.lower()
    ]

    if len(matches) == 1:
        return matches[0], None
    if len(matches) == 0:
        return None, f"No assignment matching '{identifier}'"
    # Multiple matches — show them
    names = [f"  - {a.title} ({a.course})" for a in matches[:5]]
    return None, f"Multiple matches for '{identifier}':\n" + "\n".join(names)


def cmd_auth(args: argparse.Namespace) -> int:
    """Show auth status."""
    fetcher = _get_fetcher()
    url = fetcher.get_ics_url()
    if url:
        # Mask most of the URL for security
        masked = url[:40] + "..." if len(url) > 40 else url
        print_success(f"Canvas .ics URL configured: {masked}")
    else:
        print_info("No Canvas .ics URL configured. Run: dgmt canvas auth set")
    return 0


def cmd_auth_set(args: argparse.Namespace) -> int:
    """Set the .ics URL."""
    url = args.url
    if not url:
        try:
            url = input("Enter your Canvas .ics URL: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 1

    if not url:
        print_error("URL cannot be empty")
        return 1

    if not url.startswith("https://"):
        print_warning("URL doesn't start with https:// — are you sure?")

    fetcher = _get_fetcher()
    fetcher.set_ics_url(url)
    print_success("Canvas .ics URL saved")
    return 0


def cmd_auth_revoke(args: argparse.Namespace) -> int:
    """Remove the stored .ics URL."""
    fetcher = _get_fetcher()
    if fetcher.revoke_ics_url():
        print_success("Canvas .ics URL removed")
    else:
        print_info("No Canvas .ics URL was stored")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Force-fetch assignments from Canvas."""
    try:
        fetcher = _get_fetcher()
        assignments = fetcher.get_assignments(force_fetch=True)
        print_success(f"Fetched {len(assignments)} assignments")
    except Exception as e:
        print_error(f"Fetch failed: {e}")
        return 1
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List assignments with filtering and formatting."""
    from datetime import datetime

    from dgmt.core.config import get_timezone

    tz = get_timezone()

    try:
        fetcher = _get_fetcher()
        assignments = fetcher.get_assignments()
    except Exception as e:
        print_error(f"Failed to load assignments: {e}")
        return 1

    # Apply filters
    if args.course:
        code = args.course.replace(" ", "").upper()
        assignments = [a for a in assignments if a.course == code]

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        assignments = [
            a for a in assignments
            if a.due and a.due.date() == target
        ]

    if args.due_before:
        before = datetime.strptime(args.due_before, "%Y-%m-%d").replace(tzinfo=tz)
        assignments = [a for a in assignments if a.due and a.due < before]

    if args.due_after:
        after = datetime.strptime(args.due_after, "%Y-%m-%d").replace(tzinfo=tz)
        assignments = [a for a in assignments if a.due and a.due > after]

    if args.completed_only:
        assignments = [a for a in assignments if a.completed]
    elif not args.include_completed:
        assignments = [a for a in assignments if not a.completed]

    # Format output
    fmt = args.format
    if fmt == "table":
        from dgmt.canvas.formatter import format_table
        format_table(assignments)
    elif fmt in ("markdown", "md"):
        from dgmt.canvas.formatter import format_markdown
        print(format_markdown(assignments))
    elif fmt == "json":
        from dgmt.canvas.formatter import format_json
        print(format_json(assignments))

    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    """Mark one or more assignments as complete."""
    try:
        fetcher = _get_fetcher()
        assignments = fetcher.get_assignments()
    except Exception as e:
        print_error(f"Failed to load assignments: {e}")
        return 1

    failures = 0
    for identifier in args.identifiers:
        match, error = _fuzzy_match(assignments, identifier)
        if error:
            print_error(error)
            failures += 1
            continue

        fetcher.completion_store.mark_complete(match.uid, match.summary, match.course)
        print_success(f"Completed: {match.title} ({match.course})")

    return 1 if failures else 0


def cmd_uncomplete(args: argparse.Namespace) -> int:
    """Unmark one or more assignments as complete."""
    try:
        fetcher = _get_fetcher()
        assignments = fetcher.get_assignments()
    except Exception as e:
        print_error(f"Failed to load assignments: {e}")
        return 1

    failures = 0
    for identifier in args.identifiers:
        match, error = _fuzzy_match(assignments, identifier)
        if error:
            print_error(error)
            failures += 1
            continue

        if fetcher.completion_store.mark_incomplete(match.uid):
            print_success(f"Uncompleted: {match.title} ({match.course})")
        else:
            print_info(f"Was not marked complete: {match.title}")

    return 1 if failures else 0


def cmd_courses(args: argparse.Namespace) -> int:
    """List detected courses with assignment counts."""
    try:
        fetcher = _get_fetcher()
        assignments = fetcher.get_assignments()
    except Exception as e:
        print_error(f"Failed to load assignments: {e}")
        return 1

    # Count by course
    counts: dict[str, dict[str, int]] = {}
    for a in assignments:
        course = a.course or "(unknown)"
        if course not in counts:
            counts[course] = {"total": 0, "completed": 0, "upcoming": 0}
        counts[course]["total"] += 1
        if a.completed:
            counts[course]["completed"] += 1
        elif not a.is_past:
            counts[course]["upcoming"] += 1

    if not counts:
        print_info("No courses detected")
        return 0

    from dgmt.cli.formatters import print_header
    print_header("Canvas Courses")
    for course in sorted(counts):
        c = counts[course]
        print(f"  {course:12s}  {c['total']:3d} total  {c['upcoming']:3d} upcoming  {c['completed']:3d} completed")

    return 0
