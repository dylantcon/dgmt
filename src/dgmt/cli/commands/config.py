"""Configuration management commands."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from dgmt.cli.formatters import print_error, print_info, print_json, print_success


def cmd_config(args: argparse.Namespace) -> int:
    """Show current configuration."""
    from dgmt.core.config import Config
    from dgmt.utils.paths import get_config_file

    config_file = get_config_file()

    if not config_file.exists():
        print_error(f"Config file not found: {config_file}")
        print_info("Create one with: dgmt init")
        return 1

    if args.json:
        config = Config()
        print_json(config._to_dict())
    else:
        print(f"Config file: {config_file}")
        print()
        print(config_file.read_text())

    return 0


def cmd_config_edit(args: argparse.Namespace) -> int:
    """Open config file in editor."""
    from dgmt.utils.paths import get_config_file

    config_file = get_config_file()

    if not config_file.exists():
        print_error(f"Config file not found: {config_file}")
        print_info("Create one with: dgmt init")
        return 1

    # Determine editor
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        if sys.platform == "win32":
            editor = "notepad"
        else:
            editor = "nano"

    print_info(f"Opening {config_file} in {editor}...")

    try:
        subprocess.call([editor, str(config_file)])
        return 0
    except Exception as e:
        print_error(f"Failed to open editor: {e}")
        return 1


def cmd_config_set(args: argparse.Namespace) -> int:
    """Set a configuration value."""
    from dgmt.core.config import Config

    key = args.key
    value = args.value

    config = Config()

    # Handle known keys
    if key == "backend":
        config.with_backend(value)
    elif key == "debounce":
        config.debounce(int(value))
    elif key == "max_wait":
        config.max_wait(int(value))
    elif key == "health_check":
        config.health_check(int(value))
    elif key == "log_level":
        config.log_level(value)
    elif key == "rclone_enabled":
        config.data.backends.rclone_enabled = value.lower() in ("true", "1", "yes")
    elif key == "stop_syncthing_on_exit":
        config.stop_syncthing_on_exit(value.lower() in ("true", "1", "yes"))
    else:
        print_error(f"Unknown config key: {key}")
        print_info("Known keys: backend, debounce, max_wait, health_check, log_level, rclone_enabled, stop_syncthing_on_exit")
        return 1

    config.save()
    print_success(f"Set {key} = {value}")
    return 0


def cmd_config_add_watch(args: argparse.Namespace) -> int:
    """Add a path to watch."""
    from dgmt.core.config import Config
    from dgmt.utils.paths import expand_path

    path = args.path
    expanded = expand_path(path)

    if not expanded.exists():
        print_error(f"Path does not exist: {expanded}")
        return 1

    config = Config()

    if expanded in config.data.hub.watch_paths:
        print_info(f"Path already being watched: {expanded}")
        return 0

    config.watch(str(path))
    config.save()

    print_success(f"Now watching: {expanded}")
    return 0


def cmd_config_remove_watch(args: argparse.Namespace) -> int:
    """Remove a path from watch list."""
    from dgmt.core.config import Config
    from dgmt.utils.paths import expand_path

    path = args.path
    expanded = expand_path(path)

    config = Config()

    if expanded not in config.data.hub.watch_paths:
        print_error(f"Path is not being watched: {expanded}")
        return 1

    config.data.hub.watch_paths.remove(expanded)
    config.save()

    print_success(f"Removed from watch list: {expanded}")
    return 0


def cmd_config_backend(args: argparse.Namespace) -> int:
    """Set or show default backend."""
    from dgmt.core.config import Config
    from dgmt.backends import list_backends

    config = Config()

    if args.name:
        available = list_backends()
        if args.name not in available:
            print_error(f"Unknown backend: {args.name}")
            print_info(f"Available: {', '.join(available)}")
            return 1

        config.with_backend(args.name)
        config.save()
        print_success(f"Default backend set to: {args.name}")
    else:
        current = config.data.defaults.get("backend", "syncthing")
        print(f"Current default backend: {current}")
        print(f"Available: {', '.join(list_backends())}")

    return 0


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register configuration commands."""
    # config command group
    config_parser = subparsers.add_parser(
        "config",
        help="Show or manage configuration",
    )
    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    config_parser.set_defaults(func=cmd_config)

    config_subparsers = config_parser.add_subparsers(
        dest="config_command",
        metavar="<command>",
    )

    # config edit
    edit_parser = config_subparsers.add_parser(
        "edit",
        help="Open config in editor",
    )
    edit_parser.set_defaults(func=cmd_config_edit)

    # config set
    set_parser = config_subparsers.add_parser(
        "set",
        help="Set a config value",
    )
    set_parser.add_argument("key", help="Config key to set")
    set_parser.add_argument("value", help="Value to set")
    set_parser.set_defaults(func=cmd_config_set)

    # config add-watch
    add_watch_parser = config_subparsers.add_parser(
        "add-watch",
        help="Add a path to watch",
    )
    add_watch_parser.add_argument("path", help="Path to add")
    add_watch_parser.set_defaults(func=cmd_config_add_watch)

    # config remove-watch
    remove_watch_parser = config_subparsers.add_parser(
        "remove-watch",
        help="Remove a path from watch list",
    )
    remove_watch_parser.add_argument("path", help="Path to remove")
    remove_watch_parser.set_defaults(func=cmd_config_remove_watch)

    # config backend
    backend_parser = config_subparsers.add_parser(
        "backend",
        help="Set or show default backend",
    )
    backend_parser.add_argument("name", nargs="?", help="Backend name")
    backend_parser.set_defaults(func=cmd_config_backend)
