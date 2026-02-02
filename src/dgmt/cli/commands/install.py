"""Service installation commands."""

from __future__ import annotations

import argparse

from dgmt.cli.formatters import print_error, print_info, print_success, print_warning
from dgmt.service.factory import get_service_manager, get_platform_name, is_service_supported


def cmd_install(args: argparse.Namespace) -> int:
    """Install dgmt as a system service."""
    if not is_service_supported():
        print_error(f"Service management not supported on this platform")
        print_info("You can still run dgmt manually with: dgmt run")
        return 1

    print_info(f"Installing dgmt service ({get_platform_name()})...")

    try:
        manager = get_service_manager()

        if manager.is_installed():
            print_warning("Service is already installed")
            if not args.force:
                print_info("Use --force to reinstall")
                return 0

        if manager.install():
            print_success("Service installed successfully")
            print_info("Start the service with: dgmt start")
            return 0
        else:
            print_error("Failed to install service")
            return 1

    except Exception as e:
        print_error(f"Installation error: {e}")
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove dgmt system service."""
    if not is_service_supported():
        print_error("Service management not supported on this platform")
        return 1

    print_info("Uninstalling dgmt service...")

    try:
        manager = get_service_manager()

        if not manager.is_installed():
            print_info("Service is not installed")
            return 0

        if manager.uninstall():
            print_success("Service uninstalled successfully")
            return 0
        else:
            print_error("Failed to uninstall service")
            return 1

    except Exception as e:
        print_error(f"Uninstall error: {e}")
        return 1


def cmd_start(args: argparse.Namespace) -> int:
    """Start the dgmt service."""
    if not is_service_supported():
        print_error("Service management not supported on this platform")
        print_info("Run dgmt in foreground with: dgmt run")
        return 1

    try:
        manager = get_service_manager()

        if not manager.is_installed():
            print_error("Service is not installed")
            print_info("Install with: dgmt install")
            return 1

        status = manager.status()
        if status.status.value == "running":
            print_info("Service is already running")
            return 0

        if manager.start():
            print_success("Service started")
            return 0
        else:
            print_error("Failed to start service")
            return 1

    except Exception as e:
        print_error(f"Start error: {e}")
        return 1


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the dgmt service."""
    if not is_service_supported():
        print_error("Service management not supported on this platform")
        return 1

    try:
        manager = get_service_manager()

        if not manager.is_installed():
            print_error("Service is not installed")
            return 1

        status = manager.status()
        if status.status.value != "running":
            print_info("Service is not running")
            return 0

        if manager.stop():
            print_success("Service stopped")
            return 0
        else:
            print_error("Failed to stop service")
            return 1

    except Exception as e:
        print_error(f"Stop error: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show service and sync status."""
    from dgmt.cli.formatters import print_header, print_status
    from dgmt.core.config import Config

    # Service status
    print_header("Service Status")

    if is_service_supported():
        try:
            manager = get_service_manager()
            status = manager.status()
            print_status("dgmt", status.status.value)
            if status.pid:
                print(f"    PID: {status.pid}")
        except Exception as e:
            print_error(f"Could not get service status: {e}")
    else:
        print_info(f"Service management not available ({get_platform_name()})")

    # Configuration status
    print_header("Configuration")
    try:
        config = Config()
        data = config.data

        print(f"Config file: {config._config_path}")
        print(f"Watch paths: {len(data.hub.watch_paths)}")
        for path in data.hub.watch_paths:
            print(f"  - {path}")

        print(f"Default backend: {data.defaults.get('backend', 'syncthing')}")
        print(f"rclone enabled: {data.backends.rclone_enabled}")

    except Exception as e:
        print_error(f"Could not load config: {e}")

    # Spokes status
    print_header("Spokes")
    try:
        config = Config()
        spokes = config.data.spokes

        if not spokes:
            print_info("No spokes configured")
        else:
            for name, spoke in spokes.items():
                status = "enabled" if spoke.enabled else "disabled"
                print_status(name, status, f"backend={spoke.backend}")

    except Exception as e:
        print_error(f"Could not load spokes: {e}")

    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Tail and follow the dgmt log file."""
    import time
    from dgmt.core.config import Config
    from dgmt.utils.paths import get_log_file

    try:
        config = Config()
        log_file = config.data.logging.file
    except Exception:
        log_file = get_log_file()

    if not log_file.exists():
        print_error(f"Log file not found: {log_file}")
        return 1

    print_info(f"Following {log_file} (Ctrl+C to stop)\n")

    lines_to_show = args.lines

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # Show last N lines initially
            if lines_to_show > 0:
                # Read all lines and show last N
                all_lines = f.readlines()
                for line in all_lines[-lines_to_show:]:
                    print(line, end="")

            # Follow mode - seek to end and poll for new content
            f.seek(0, 2)  # Seek to end
            last_pos = f.tell()
            last_size = log_file.stat().st_size

            while True:
                # Check if file was truncated/rotated
                current_size = log_file.stat().st_size
                if current_size < last_size:
                    # File was truncated, start from beginning
                    f.seek(0)
                    print_info("--- Log file rotated ---")

                # Read new content
                line = f.readline()
                if line:
                    print(line, end="")
                    last_pos = f.tell()
                else:
                    # No new content, wait a bit
                    time.sleep(0.5)

                last_size = current_size

    except KeyboardInterrupt:
        print("\n")
        return 0
    except Exception as e:
        print_error(f"Error reading log: {e}")
        return 1


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register service management commands."""
    # install
    install_parser = subparsers.add_parser(
        "install",
        help="Install dgmt as a system service",
    )
    install_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force reinstall if already installed",
    )
    install_parser.set_defaults(func=cmd_install)

    # uninstall
    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Remove dgmt system service",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # start
    start_parser = subparsers.add_parser(
        "start",
        help="Start the dgmt service",
    )
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser(
        "stop",
        help="Stop the dgmt service",
    )
    stop_parser.set_defaults(func=cmd_stop)

    # status
    status_parser = subparsers.add_parser(
        "status",
        help="Show service and sync status",
    )
    status_parser.set_defaults(func=cmd_status)

    # logs
    logs_parser = subparsers.add_parser(
        "logs",
        help="Tail and follow the dgmt log file",
    )
    logs_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=20,
        help="Number of lines to show initially (default: 20)",
    )
    logs_parser.set_defaults(func=cmd_logs)
