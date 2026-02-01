"""SFTP/rsync backend for direct server sync."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from dgmt.backends.base import Backend, BackendBuilder
from dgmt.utils.logging import get_logger
from dgmt.utils.paths import expand_path


class SftpBackend(Backend):
    """
    SFTP/rsync backend for syncing directly with remote servers.

    Uses rsync over SSH for efficient file transfer. Reads connection
    details from ~/.ssh/config when using host aliases.
    """

    def __init__(
        self,
        host: str,
        remote_path: str,
        ssh_key: Optional[str] = None,
        user: Optional[str] = None,
        port: int = 22,
        bidirectional: bool = True,
    ) -> None:
        """
        Initialize SFTP backend.

        Args:
            host: SSH host (can be alias from ~/.ssh/config).
            remote_path: Path on the remote server.
            ssh_key: Path to SSH private key (optional).
            user: SSH username (optional, uses config default).
            port: SSH port (default 22).
            bidirectional: If True, sync both directions.
        """
        self._host = host
        self._remote_path = remote_path
        self._ssh_key = expand_path(ssh_key) if ssh_key else None
        self._user = user
        self._port = port
        self._bidirectional = bidirectional
        self._logger = get_logger("dgmt.sftp")

    @property
    def name(self) -> str:
        return "sftp"

    def _get_rsync_ssh_cmd(self) -> str:
        """Build the SSH command string for rsync."""
        cmd_parts = ["ssh"]

        if self._port != 22:
            cmd_parts.extend(["-p", str(self._port)])

        if self._ssh_key:
            cmd_parts.extend(["-i", str(self._ssh_key)])

        return " ".join(cmd_parts)

    def _get_remote_uri(self) -> str:
        """Build the rsync remote URI."""
        if self._user:
            return f"{self._user}@{self._host}:{self._remote_path}"
        return f"{self._host}:{self._remote_path}"

    def _get_subprocess_args(self) -> dict:
        """Get platform-specific subprocess arguments."""
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            return {
                "startupinfo": startupinfo,
                "creationflags": subprocess.CREATE_NO_WINDOW,
            }
        return {}

    def is_healthy(self) -> bool:
        """Check if we can connect to the remote host."""
        ssh_cmd = ["ssh"]
        if self._port != 22:
            ssh_cmd.extend(["-p", str(self._port)])
        if self._ssh_key:
            ssh_cmd.extend(["-i", str(self._ssh_key)])

        # Build host string
        host = f"{self._user}@{self._host}" if self._user else self._host
        ssh_cmd.extend(["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "echo ok"])

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=10,
                **self._get_subprocess_args(),
            )
            return result.returncode == 0 and "ok" in result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def sync(self, local_path: str, remote_path: Optional[str] = None) -> bool:
        """
        Bidirectional sync using rsync.

        Performs push then pull to achieve bidirectional sync.
        """
        if self._bidirectional:
            # Push local changes, then pull remote changes
            push_ok = self.push(local_path)
            pull_ok = self.pull(local_path)
            return push_ok and pull_ok
        else:
            return self.push(local_path)

    def pull(self, local_path: str, timeout: int = 120) -> bool:
        """Pull changes from remote to local."""
        local_path = str(expand_path(local_path))
        remote_uri = self._get_remote_uri()

        # Ensure local path ends with / for rsync
        if not local_path.endswith("/"):
            local_path += "/"

        # Ensure remote path ends with / for rsync
        remote_uri_dir = remote_uri if remote_uri.endswith("/") else remote_uri + "/"

        cmd = [
            "rsync",
            "-avz",              # archive, verbose, compress
            "--update",          # skip files newer on destination
            "-e", self._get_rsync_ssh_cmd(),
            remote_uri_dir,
            local_path,
        ]

        self._logger.info(f"Pulling: {remote_uri} -> {local_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                **self._get_subprocess_args(),
            )

            if result.returncode == 0:
                self._logger.info("Pull completed successfully")
                return True
            else:
                self._logger.error(f"Pull failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self._logger.error("Pull timed out")
            return False
        except FileNotFoundError:
            self._logger.error("rsync not found. Please install rsync.")
            return False
        except Exception as e:
            self._logger.error(f"Pull error: {e}")
            return False

    def push(self, local_path: str, timeout: int = 120) -> bool:
        """Push changes from local to remote."""
        local_path = str(expand_path(local_path))
        remote_uri = self._get_remote_uri()

        # Ensure local path ends with / for rsync
        if not local_path.endswith("/"):
            local_path += "/"

        # Ensure remote path ends with / for rsync
        remote_uri_dir = remote_uri if remote_uri.endswith("/") else remote_uri + "/"

        cmd = [
            "rsync",
            "-avz",              # archive, verbose, compress
            "--update",          # skip files newer on destination
            "-e", self._get_rsync_ssh_cmd(),
            local_path,
            remote_uri_dir,
        ]

        self._logger.info(f"Pushing: {local_path} -> {remote_uri}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                **self._get_subprocess_args(),
            )

            if result.returncode == 0:
                self._logger.info("Push completed successfully")
                return True
            else:
                self._logger.error(f"Push failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self._logger.error("Push timed out")
            return False
        except FileNotFoundError:
            self._logger.error("rsync not found. Please install rsync.")
            return False
        except Exception as e:
            self._logger.error(f"Push error: {e}")
            return False

    def ensure_remote_path(self) -> bool:
        """Create the remote directory if it doesn't exist."""
        host = f"{self._user}@{self._host}" if self._user else self._host

        ssh_cmd = ["ssh"]
        if self._port != 22:
            ssh_cmd.extend(["-p", str(self._port)])
        if self._ssh_key:
            ssh_cmd.extend(["-i", str(self._ssh_key)])

        ssh_cmd.extend([host, f"mkdir -p {self._remote_path}"])

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                **self._get_subprocess_args(),
            )
            return result.returncode == 0
        except Exception as e:
            self._logger.error(f"Failed to create remote directory: {e}")
            return False

    def __repr__(self) -> str:
        return f"SftpBackend(host={self._host!r}, remote_path={self._remote_path!r})"


class SftpBuilder(BackendBuilder):
    """
    Fluent builder for SftpBackend.

    Example:
        backend = (
            SftpBackend.builder("webserver")
            .with_ssh_key("~/.ssh/id_rsa")
            .remote_path("/home/user/notes")
            .bidirectional()
            .build()
        )
    """

    def __init__(self, host: str) -> None:
        self._host = host
        self._remote_path = "~/sync"
        self._ssh_key: Optional[str] = None
        self._user: Optional[str] = None
        self._port = 22
        self._bidirectional = True

    def remote_path(self, path: str) -> SftpBuilder:
        """Set the remote sync path."""
        self._remote_path = path
        return self

    def with_ssh_key(self, key_path: str) -> SftpBuilder:
        """Set the SSH key to use."""
        self._ssh_key = key_path
        return self

    def user(self, username: str) -> SftpBuilder:
        """Set the SSH username."""
        self._user = username
        return self

    def port(self, port: int) -> SftpBuilder:
        """Set the SSH port."""
        self._port = port
        return self

    def bidirectional(self, enabled: bool = True) -> SftpBuilder:
        """Enable/disable bidirectional sync."""
        self._bidirectional = enabled
        return self

    def push_only(self) -> SftpBuilder:
        """Only push local changes to remote."""
        self._bidirectional = False
        return self

    def build(self) -> SftpBackend:
        """Build the SftpBackend instance."""
        return SftpBackend(
            host=self._host,
            remote_path=self._remote_path,
            ssh_key=self._ssh_key,
            user=self._user,
            port=self._port,
            bidirectional=self._bidirectional,
        )


def sftp(host: str, **kwargs) -> SftpBackend:
    """Create an SftpBackend with the given options."""
    return SftpBackend(host=host, **kwargs)
