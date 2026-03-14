"""MCP server CLI commands (serve, install)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _get_claude_config_path() -> Path:
    """Get the platform-specific Claude Desktop config path."""
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming" / "Claude"
    elif sys.platform == "darwin":
        appdata = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        appdata = Path.home() / ".config" / "Claude"
    return appdata / "claude_desktop_config.json"


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    """Start the MCP stdio server."""
    try:
        from dgmt.mcp.server import run_server
    except ImportError:
        print(
            "MCP dependencies not installed.\n"
            "Install with: pip install dgmt[mcp]  (or: pip install mcp>=1.0.0)",
            file=sys.stderr,
        )
        return 1

    import asyncio
    asyncio.run(run_server())
    return 0


def cmd_mcp_install(args: argparse.Namespace) -> int:
    """Install dgmt as an MCP server in Claude Desktop config."""
    config_path = _get_claude_config_path()

    # Read existing config or start fresh
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    mcp_servers = config.setdefault("mcpServers", {})

    if "dgmt" in mcp_servers and not getattr(args, "force", False):
        print(f"dgmt is already configured in {config_path}")
        print("Use --force to overwrite.")
        return 0

    mcp_servers["dgmt"] = {
        "command": sys.executable,
        "args": ["-m", "dgmt", "mcp", "serve"],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Installed dgmt MCP server in {config_path}")
    print("Restart Claude Desktop to activate.")
    return 0


def register_mcp_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the mcp subcommand group."""
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="MCP server for AI agent integration",
        description="Expose dgmt calendar and color rules as MCP tools for Claude Desktop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  dgmt mcp serve           Start the MCP stdio server
  dgmt mcp install         Register dgmt in Claude Desktop config
  dgmt mcp install --force Overwrite existing Claude Desktop config entry
""",
    )

    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", metavar="<command>")

    # mcp serve
    serve_parser = mcp_sub.add_parser("serve", help="Start MCP stdio server")
    serve_parser.set_defaults(func=cmd_mcp_serve)

    # mcp install
    install_parser = mcp_sub.add_parser(
        "install",
        help="Register dgmt in Claude Desktop config",
    )
    install_parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing entry if present",
    )
    install_parser.set_defaults(func=cmd_mcp_install)
