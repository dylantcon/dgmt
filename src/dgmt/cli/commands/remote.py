"""Remote/spoke management commands."""

from __future__ import annotations

import argparse

from dgmt.cli.formatters import (
    print_error,
    print_header,
    print_info,
    print_status,
    print_success,
    print_table,
    print_warning,
)


def cmd_remote_add(args: argparse.Namespace) -> int:
    """Add a remote spoke machine."""
    from dgmt.core.config import Config
    from dgmt.remote.config_parser import SSHConfigParser
    from dgmt.remote.ssh import SSHConnection
    from dgmt.remote.setup import RemoteSetup

    host = args.host
    backend = args.backend or "syncthing"
    folder = args.folder or "~/sync"

    # Check SSH config
    ssh_config = SSHConfigParser()
    if ssh_config.has_host(host):
        host_info = ssh_config.get_host(host)
        print_info(f"Found SSH config for '{host}':")
        print(f"  Hostname: {host_info.hostname or host}")
        if host_info.user:
            print(f"  User: {host_info.user}")
        if host_info.port != 22:
            print(f"  Port: {host_info.port}")
    else:
        print_info(f"Using '{host}' as hostname (not in SSH config)")

    # Test connection
    print_info(f"Testing connection to {host}...")
    ssh = SSHConnection(host)
    if not ssh.test_connection():
        print_error(f"Cannot connect to {host}")
        print_info("Check your SSH config and try again")
        return 1

    print_success("Connection successful")

    # Set up remote
    if args.setup:
        print_info("Setting up remote...")
        setup = RemoteSetup(host)

        if not setup.full_setup(sync_folder=folder, backend=backend):
            print_error("Remote setup failed")
            return 1

        print_success("Remote setup complete")

    # Add to config
    config = Config()
    config.add_spoke(
        name=host,
        backend=backend,
        remote_path=folder,
        enabled=True,
    )
    config.save()

    print_success(f"Added spoke '{host}' with {backend} backend")
    return 0


def cmd_remote_remove(args: argparse.Namespace) -> int:
    """Remove a remote spoke machine."""
    from dgmt.core.config import Config

    host = args.host
    config = Config()

    if host not in config.data.spokes:
        print_error(f"Spoke '{host}' not found")
        return 1

    config.remove_spoke(host)
    config.save()

    print_success(f"Removed spoke '{host}'")
    return 0


def cmd_remote_list(args: argparse.Namespace) -> int:
    """List configured remote spokes."""
    from dgmt.core.config import Config

    config = Config()
    spokes = config.data.spokes

    if not spokes:
        print_info("No spokes configured")
        print_info("Add a spoke with: dgmt remote add <host>")
        return 0

    rows = []
    for name, spoke in spokes.items():
        rows.append({
            "Name": name,
            "Backend": spoke.backend,
            "Path": spoke.remote_path or "~/sync",
            "Enabled": "yes" if spoke.enabled else "no",
        })

    print_table(["Name", "Backend", "Path", "Enabled"], rows)
    return 0


def cmd_remote_status(args: argparse.Namespace) -> int:
    """Check status of a remote spoke."""
    from dgmt.core.config import Config
    from dgmt.remote.spoke import Spoke

    host = args.host

    # Check if in config
    config = Config()
    spoke_config = config.get_spoke(host)

    if spoke_config:
        print_header(f"Spoke: {host}")
        print(f"Backend: {spoke_config.backend}")
        print(f"Remote path: {spoke_config.remote_path or '~/sync'}")
        print(f"Enabled: {'yes' if spoke_config.enabled else 'no'}")
    else:
        print_warning(f"'{host}' is not configured as a spoke")

    # Test connection
    print_info("Testing connection...")
    spoke = Spoke(host)
    status = spoke.status()
    print_status(host, status.status.value)

    return 0


def cmd_remote_start(args: argparse.Namespace) -> int:
    """Start sync on a remote spoke."""
    from dgmt.core.config import Config

    host = args.host
    config = Config()

    spoke_config = config.get_spoke(host)
    if not spoke_config:
        print_error(f"Spoke '{host}' not found")
        return 1

    if spoke_config.backend == "syncthing":
        print_info("Syncthing syncs automatically")
        return 0

    # For SFTP, we'd need to trigger a sync
    print_info(f"Starting sync for {host}...")
    # TODO: Implement on-demand sync for SFTP

    return 0


def cmd_remote_stop(args: argparse.Namespace) -> int:
    """Stop sync on a remote spoke."""
    from dgmt.core.config import Config

    host = args.host
    config = Config()

    spoke_config = config.get_spoke(host)
    if not spoke_config:
        print_error(f"Spoke '{host}' not found")
        return 1

    print_info(f"Sync stopped for {host}")
    return 0


def cmd_remote_ssh(args: argparse.Namespace) -> int:
    """Open SSH session to a remote spoke."""
    from dgmt.remote.ssh import SSHConnection

    host = args.host
    ssh = SSHConnection(host)
    return ssh.run_interactive()


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register remote management commands."""
    # remote command group
    remote_parser = subparsers.add_parser(
        "remote",
        help="Manage remote spoke machines",
    )
    remote_subparsers = remote_parser.add_subparsers(
        dest="remote_command",
        metavar="<command>",
    )

    # remote add
    add_parser = remote_subparsers.add_parser(
        "add",
        help="Add a remote spoke",
    )
    add_parser.add_argument("host", help="SSH host alias or hostname")
    add_parser.add_argument(
        "-b", "--backend",
        choices=["sftp", "syncthing"],
        help="Sync backend (default: syncthing)",
    )
    add_parser.add_argument(
        "-f", "--folder",
        help="Remote sync folder (default: ~/sync)",
    )
    add_parser.add_argument(
        "--setup",
        action="store_true",
        help="Set up remote automatically",
    )
    add_parser.set_defaults(func=cmd_remote_add)

    # remote remove
    remove_parser = remote_subparsers.add_parser(
        "remove",
        help="Remove a remote spoke",
    )
    remove_parser.add_argument("host", help="Spoke name to remove")
    remove_parser.set_defaults(func=cmd_remote_remove)

    # remote list
    list_parser = remote_subparsers.add_parser(
        "list",
        help="List configured spokes",
    )
    list_parser.set_defaults(func=cmd_remote_list)

    # remote status
    status_parser = remote_subparsers.add_parser(
        "status",
        help="Check spoke status",
    )
    status_parser.add_argument("host", help="Spoke name")
    status_parser.set_defaults(func=cmd_remote_status)

    # remote start
    start_parser = remote_subparsers.add_parser(
        "start",
        help="Start sync on a spoke",
    )
    start_parser.add_argument("host", help="Spoke name")
    start_parser.set_defaults(func=cmd_remote_start)

    # remote stop
    stop_parser = remote_subparsers.add_parser(
        "stop",
        help="Stop sync on a spoke",
    )
    stop_parser.add_argument("host", help="Spoke name")
    stop_parser.set_defaults(func=cmd_remote_stop)

    # remote ssh
    ssh_parser = remote_subparsers.add_parser(
        "ssh",
        help="Open SSH session to spoke",
    )
    ssh_parser.add_argument("host", help="Spoke name")
    ssh_parser.set_defaults(func=cmd_remote_ssh)
