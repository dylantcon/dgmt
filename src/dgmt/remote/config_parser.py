"""SSH config parser for reading ~/.ssh/config."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SSHHost:
    """Parsed SSH host configuration."""

    alias: str
    hostname: Optional[str] = None
    user: Optional[str] = None
    port: int = 22
    identity_file: Optional[Path] = None
    proxy_command: Optional[str] = None
    forward_agent: bool = False
    other_options: dict[str, str] = field(default_factory=dict)

    @property
    def effective_hostname(self) -> str:
        """Get the effective hostname (alias if no explicit hostname)."""
        return self.hostname or self.alias

    def to_ssh_args(self) -> list[str]:
        """Convert to SSH command line arguments."""
        args = []
        if self.port != 22:
            args.extend(["-p", str(self.port)])
        if self.identity_file:
            args.extend(["-i", str(self.identity_file)])
        if self.user:
            args.append(f"{self.user}@{self.effective_hostname}")
        else:
            args.append(self.effective_hostname)
        return args


class SSHConfigParser:
    """
    Parser for ~/.ssh/config files.

    Reads SSH configuration and resolves host aliases to their
    full connection details.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Initialize the parser.

        Args:
            config_path: Path to SSH config file. Defaults to ~/.ssh/config.
        """
        self._config_path = config_path or Path("~/.ssh/config").expanduser()
        self._hosts: dict[str, SSHHost] = {}
        self._parse()

    def _parse(self) -> None:
        """Parse the SSH config file."""
        if not self._config_path.exists():
            return

        try:
            content = self._config_path.read_text()
        except Exception:
            return

        current_host: Optional[SSHHost] = None

        for line in content.split("\n"):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse key-value pairs
            match = re.match(r"^\s*(\w+)\s+(.+)$", line, re.IGNORECASE)
            if not match:
                continue

            key = match.group(1).lower()
            value = match.group(2).strip()

            # Handle Host directive (starts a new host block)
            if key == "host":
                # Support multiple hosts on one line
                aliases = value.split()
                for alias in aliases:
                    # Skip wildcard patterns for now
                    if "*" in alias or "?" in alias:
                        continue
                    current_host = SSHHost(alias=alias)
                    self._hosts[alias] = current_host
                continue

            # Skip if no current host
            if current_host is None:
                continue

            # Parse known options
            if key == "hostname":
                current_host.hostname = value
            elif key == "user":
                current_host.user = value
            elif key == "port":
                try:
                    current_host.port = int(value)
                except ValueError:
                    pass
            elif key == "identityfile":
                current_host.identity_file = Path(value).expanduser()
            elif key == "proxycommand":
                current_host.proxy_command = value
            elif key == "forwardagent":
                current_host.forward_agent = value.lower() in ("yes", "true", "1")
            else:
                current_host.other_options[key] = value

    def get_host(self, alias: str) -> Optional[SSHHost]:
        """
        Get SSH host configuration by alias.

        Args:
            alias: Host alias from SSH config.

        Returns:
            SSHHost if found, None otherwise.
        """
        return self._hosts.get(alias)

    def has_host(self, alias: str) -> bool:
        """Check if a host alias exists."""
        return alias in self._hosts

    def list_hosts(self) -> list[str]:
        """Get list of all configured host aliases."""
        return list(self._hosts.keys())

    def resolve(self, host: str) -> SSHHost:
        """
        Resolve a host string to SSH configuration.

        If the host is found in SSH config, returns that configuration.
        Otherwise, returns a basic SSHHost with the host as both alias
        and hostname.

        Args:
            host: Host string (can be alias or hostname).

        Returns:
            SSHHost configuration.
        """
        if host in self._hosts:
            return self._hosts[host]

        # Not in config, return basic host
        return SSHHost(alias=host, hostname=host)

    def __contains__(self, alias: str) -> bool:
        return alias in self._hosts

    def __len__(self) -> int:
        return len(self._hosts)


def get_ssh_config() -> SSHConfigParser:
    """Get the default SSH config parser."""
    return SSHConfigParser()


def resolve_host(host: str) -> SSHHost:
    """
    Convenience function to resolve a host alias.

    Args:
        host: Host alias or hostname.

    Returns:
        SSHHost configuration.
    """
    return SSHConfigParser().resolve(host)
