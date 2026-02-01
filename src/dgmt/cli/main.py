"""Main CLI entry point."""

from __future__ import annotations

import argparse
import sys

from dgmt import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="dgmt",
        description="Dylan's General Management Tool - Hub-and-spoke sync orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  dgmt run              Run daemon in foreground
  dgmt install          Install as system service
  dgmt status           Show service and sync status
  dgmt sync             Trigger manual sync
  dgmt remote add pc    Add a remote machine
  dgmt config           Show configuration

Config: ~/.dgmt/config.json
Logs:   ~/.dgmt/dgmt.log
""",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"dgmt {__version__}",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )

    # Create subcommand parsers
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        title="Commands",
    )

    # Register all command modules
    from dgmt.cli.commands import install, sync, remote, config

    install.register_commands(subparsers)
    sync.register_commands(subparsers)
    remote.register_commands(subparsers)
    config.register_commands(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # No command specified - show help
    if args.command is None:
        parser.print_help()
        return 0

    # Handle remote subcommand without sub-subcommand
    if args.command == "remote" and not hasattr(args, "func"):
        # Find remote parser and print its help
        for action in parser._subparsers._actions:
            if isinstance(action, argparse._SubParsersAction):
                remote_parser = action.choices.get("remote")
                if remote_parser:
                    remote_parser.print_help()
        return 0

    # Handle config without subcommand
    if args.command == "config" and args.config_command is None:
        # Show config by default
        from dgmt.cli.commands.config import cmd_config
        return cmd_config(args)

    # Execute command
    if hasattr(args, "func"):
        try:
            return args.func(args)
        except KeyboardInterrupt:
            print("\nInterrupted")
            return 130
        except Exception as e:
            if not args.quiet:
                print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
