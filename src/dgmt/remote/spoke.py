"""Spoke (remote machine) management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from dgmt.backends import get_backend
from dgmt.backends.base import Backend
from dgmt.remote.ssh import SSHConnection
from dgmt.utils.fluent import FluentChain
from dgmt.utils.logging import get_logger


class SpokeStatus(Enum):
    """Status of a spoke machine."""

    ONLINE = "online"
    OFFLINE = "offline"
    SYNCING = "syncing"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class SpokeInfo:
    """Information about a spoke machine."""

    name: str
    status: SpokeStatus
    backend: str
    remote_path: Optional[str] = None
    last_sync: Optional[str] = None
    error_message: Optional[str] = None


class Spoke(FluentChain):
    """
    Represents a spoke (remote) machine in the hub-and-spoke model.

    Provides fluent interface for configuring and managing remote machines.

    Example:
        spoke = (
            Spoke("webserver")
            .use_backend("sftp")
            .sync_folder("~/notes")
            .connect()
            .setup()
            .start_sync()
        )
    """

    def __init__(self, host: str) -> None:
        """
        Initialize a spoke for a remote host.

        Args:
            host: SSH host alias or hostname.
        """
        self._host = host
        self._backend_name = "syncthing"
        self._sync_folder: Optional[str] = None
        self._ssh: Optional[SSHConnection] = None
        self._backend: Optional[Backend] = None
        self._logger = get_logger("dgmt.spoke")
        self._connected = False

    @property
    def host(self) -> str:
        """Get the host name."""
        return self._host

    @property
    def backend_name(self) -> str:
        """Get the backend name."""
        return self._backend_name

    @property
    def sync_folder(self) -> Optional[str]:
        """Get the sync folder path."""
        return self._sync_folder

    @property
    def is_connected(self) -> bool:
        """Check if connected to the spoke."""
        return self._connected

    def use_backend(self, backend: str) -> Spoke:
        """
        Set the sync backend for this spoke.

        Args:
            backend: Backend name ('sftp', 'syncthing', etc.).

        Returns:
            self for method chaining.
        """
        self._backend_name = backend
        return self

    def sync_folder(self, path: str) -> Spoke:
        """
        Set the folder to sync on the remote machine.

        Args:
            path: Path on the remote machine (supports ~).

        Returns:
            self for method chaining.
        """
        self._sync_folder = path
        return self

    def connect(self) -> Spoke:
        """
        Establish SSH connection to the spoke.

        Returns:
            self for method chaining.

        Raises:
            ConnectionError: If connection fails.
        """
        self._ssh = SSHConnection(self._host)

        if not self._ssh.test_connection():
            raise ConnectionError(f"Cannot connect to {self._host}")

        self._connected = True
        self._logger.info(f"Connected to {self._host}")
        return self

    def setup(self) -> Spoke:
        """
        Set up the spoke for syncing.

        Creates sync folder, configures backend, etc.

        Returns:
            self for method chaining.
        """
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")

        # Create sync folder
        if self._sync_folder:
            folder = self._expand_remote_path(self._sync_folder)
            if not self._ssh.file_exists(folder):
                self._logger.info(f"Creating sync folder: {folder}")
                self._ssh.mkdir(folder)

        # Backend-specific setup
        if self._backend_name == "syncthing":
            self._setup_syncthing()
        elif self._backend_name == "sftp":
            self._setup_sftp()

        return self

    def _expand_remote_path(self, path: str) -> str:
        """Expand ~ in remote path."""
        if path.startswith("~"):
            home = self._ssh.get_home_dir()
            if home:
                return home + path[1:]
        return path

    def _setup_syncthing(self) -> None:
        """Set up Syncthing on the spoke."""
        # Check if Syncthing is installed
        code, stdout, _ = self._ssh.run("which syncthing")
        if code != 0:
            self._logger.warning(
                "Syncthing not installed on remote. "
                "Please install it manually or use SFTP backend."
            )
            return

        # Get remote device ID
        code, stdout, _ = self._ssh.run("syncthing --device-id 2>/dev/null || syncthing -device-id 2>/dev/null")
        if code == 0:
            device_id = stdout.strip()
            self._logger.info(f"Remote Syncthing device ID: {device_id}")

    def _setup_sftp(self) -> None:
        """Set up SFTP backend (just verify connectivity)."""
        # SFTP just needs the folder to exist, which we already created
        self._logger.info("SFTP setup complete")

    def start_sync(self) -> Spoke:
        """
        Start synchronization with this spoke.

        Returns:
            self for method chaining.
        """
        if self._backend_name == "sftp":
            # Create SFTP backend
            remote_path = self._expand_remote_path(self._sync_folder or "~/sync")
            self._backend = get_backend(
                "sftp",
                host=self._host,
                remote_path=remote_path,
            )
        elif self._backend_name == "syncthing":
            # Syncthing handles sync automatically
            self._logger.info("Syncthing will handle sync automatically")

        return self

    def stop_sync(self) -> Spoke:
        """
        Stop synchronization with this spoke.

        Returns:
            self for method chaining.
        """
        if self._backend:
            self._backend.stop()
        return self

    def status(self) -> SpokeInfo:
        """
        Get the current status of this spoke.

        Returns:
            SpokeInfo with current status.
        """
        if not self._connected:
            # Try to connect
            try:
                ssh = SSHConnection(self._host)
                if ssh.test_connection(timeout=5):
                    status = SpokeStatus.ONLINE
                else:
                    status = SpokeStatus.OFFLINE
            except Exception:
                status = SpokeStatus.OFFLINE
        else:
            status = SpokeStatus.ONLINE

        return SpokeInfo(
            name=self._host,
            status=status,
            backend=self._backend_name,
            remote_path=self._sync_folder,
        )

    def disconnect(self) -> None:
        """Disconnect from the spoke."""
        self._ssh = None
        self._connected = False

    def ssh_session(self) -> int:
        """
        Open an interactive SSH session.

        Returns:
            Exit code of the SSH session.
        """
        ssh = SSHConnection(self._host)
        return ssh.run_interactive()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"Spoke({self._host!r}, backend={self._backend_name!r}, {status})"


def spoke(host: str) -> Spoke:
    """Create a Spoke for a remote host."""
    return Spoke(host)
