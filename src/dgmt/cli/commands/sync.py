"""Sync and daemon commands."""

from __future__ import annotations

import argparse

from dgmt.cli.formatters import print_error, print_info, print_success


def cmd_run(args: argparse.Namespace) -> int:
    """Run dgmt daemon in foreground."""
    from dgmt.core.daemon import Daemon
    from dgmt.core.config import Config

    print_info("Starting dgmt daemon...")

    try:
        config = Config()
        daemon = Daemon(config)
        daemon.start()
        return 0

    except KeyboardInterrupt:
        print_info("Shutting down...")
        return 0

    except Exception as e:
        print_error(f"Daemon error: {e}")
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    """Trigger manual sync."""
    from dgmt.core.config import Config
    from dgmt.backends import get_backend

    config = Config()
    data = config.data

    if not data.backends.rclone_enabled:
        print_info("rclone backend is not enabled")
        print_info("Syncthing handles sync automatically")
        return 0

    rclone = get_backend(
        "rclone",
        remote=data.backends.rclone_remote,
        dest=data.backends.rclone_dest,
        flags=data.backends.rclone_flags,
    )

    success = True

    for path in data.hub.watch_paths:
        print_info(f"Syncing {path}...")

        if args.pull:
            if rclone.pull(str(path)):
                print_success(f"Pull completed: {path}")
            else:
                print_error(f"Pull failed: {path}")
                success = False

        elif args.push:
            if rclone.push(str(path)):
                print_success(f"Push completed: {path}")
            else:
                print_error(f"Push failed: {path}")
                success = False

        else:
            # Bidirectional sync
            if rclone.sync(str(path)):
                print_success(f"Sync completed: {path}")
            else:
                print_error(f"Sync failed: {path}")
                success = False

    return 0 if success else 1


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize dgmt configuration."""
    from dgmt.core.config import Config, init_config
    from dgmt.utils.paths import get_config_file

    config_file = get_config_file()

    if config_file.exists() and not args.force:
        print_info(f"Config already exists: {config_file}")
        print_info("Use --force to overwrite")
        return 0

    try:
        config = Config()
        config.watch("~/Obsidian").save()
        print_success(f"Created config: {config_file}")
        print_info("Edit this file to configure your paths and settings.")
        return 0

    except Exception as e:
        print_error(f"Failed to create config: {e}")
        return 1


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register sync commands."""
    # run
    run_parser = subparsers.add_parser(
        "run",
        help="Run dgmt daemon in foreground",
    )
    run_parser.set_defaults(func=cmd_run)

    # sync
    sync_parser = subparsers.add_parser(
        "sync",
        help="Trigger manual sync",
    )
    sync_parser.add_argument(
        "--pull",
        action="store_true",
        help="Only pull from remote",
    )
    sync_parser.add_argument(
        "--push",
        action="store_true",
        help="Only push to remote",
    )
    sync_parser.set_defaults(func=cmd_sync)

    # init
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize dgmt configuration",
    )
    init_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing config",
    )
    init_parser.set_defaults(func=cmd_init)
