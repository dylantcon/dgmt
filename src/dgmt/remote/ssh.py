"""SSH connection and command execution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from dgmt.remote.config_parser import SSHConfigParser, SSHHost
from dgmt.utils.logging import get_logger


class SSHConnection:
    """
    SSH connection wrapper for executing commands on remote hosts.

    Supports reading connection details from ~/.ssh/config.
    """

    def __init__(
        self,
        host: str,
        user: Optional[str] = None,
        port: Optional[int] = None,
        identity_file: Optional[str] = None,
    ) -> None:
        """
        Initialize SSH connection.

        If host is an alias in ~/.ssh/config, connection details
        will be read from there. Explicit parameters override config.

        Args:
            host: Hostname or SSH config alias.
            user: SSH username (overrides config).
            port: SSH port (overrides config).
            identity_file: Path to private key (overrides config).
        """
        self._logger = get_logger("dgmt.ssh")

        # Resolve host from SSH config
        config = SSHConfigParser()
        self._host_config = config.resolve(host)

        # Override with explicit parameters
        if user:
            self._host_config.user = user
        if port:
            self._host_config.port = port
        if identity_file:
            self._host_config.identity_file = Path(identity_file).expanduser()

    @property
    def host(self) -> str:
        """Get the host alias."""
        return self._host_config.alias

    @property
    def hostname(self) -> str:
        """Get the effective hostname."""
        return self._host_config.effective_hostname

    @property
    def user(self) -> Optional[str]:
        """Get the SSH user."""
        return self._host_config.user

    @property
    def port(self) -> int:
        """Get the SSH port."""
        return self._host_config.port

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

    def _build_ssh_cmd(self, command: Optional[str] = None) -> list[str]:
        """Build the SSH command with all options."""
        cmd = ["ssh"]

        # Add options
        if self._host_config.port != 22:
            cmd.extend(["-p", str(self._host_config.port)])

        if self._host_config.identity_file:
            cmd.extend(["-i", str(self._host_config.identity_file)])

        # Add host (with user if specified)
        if self._host_config.user:
            cmd.append(f"{self._host_config.user}@{self.hostname}")
        else:
            cmd.append(self.hostname)

        # Add command if specified
        if command:
            cmd.append(command)

        return cmd

    def test_connection(self, timeout: int = 10) -> bool:
        """
        Test if the SSH connection works.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            True if connection succeeded.
        """
        cmd = self._build_ssh_cmd("echo ok")
        cmd.insert(1, "-o")
        cmd.insert(2, "BatchMode=yes")
        cmd.insert(3, "-o")
        cmd.insert(4, f"ConnectTimeout={timeout}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                **self._get_subprocess_args(),
            )
            return result.returncode == 0 and "ok" in result.stdout
        except Exception as e:
            self._logger.debug(f"Connection test failed: {e}")
            return False

    def run(
        self,
        command: str,
        timeout: Optional[int] = None,
        check: bool = False,
    ) -> Tuple[int, str, str]:
        """
        Execute a command on the remote host.

        Args:
            command: Command to execute.
            timeout: Command timeout in seconds.
            check: If True, raise exception on non-zero exit code.

        Returns:
            Tuple of (return_code, stdout, stderr).

        Raises:
            subprocess.CalledProcessError: If check=True and command fails.
            subprocess.TimeoutExpired: If command times out.
        """
        cmd = self._build_ssh_cmd(command)

        self._logger.debug(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **self._get_subprocess_args(),
        )

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                result.stdout,
                result.stderr,
            )

        return result.returncode, result.stdout, result.stderr

    def run_interactive(self) -> int:
        """
        Open an interactive SSH session.

        Returns:
            Exit code of the SSH session.
        """
        cmd = self._build_ssh_cmd()
        return subprocess.call(cmd)

    def file_exists(self, path: str) -> bool:
        """Check if a file exists on the remote host."""
        code, _, _ = self.run(f'test -e "{path}"')
        return code == 0

    def mkdir(self, path: str, parents: bool = True) -> bool:
        """Create a directory on the remote host."""
        flag = "-p" if parents else ""
        code, _, stderr = self.run(f'mkdir {flag} "{path}"')
        if code != 0:
            self._logger.error(f"Failed to create directory: {stderr}")
        return code == 0

    def read_file(self, path: str) -> Optional[str]:
        """Read a file from the remote host."""
        code, stdout, _ = self.run(f'cat "{path}"')
        return stdout if code == 0 else None

    def write_file(self, path: str, content: str) -> bool:
        """Write content to a file on the remote host."""
        # Escape content for shell
        escaped = content.replace("'", "'\"'\"'")
        code, _, stderr = self.run(f"cat > '{path}' << 'EOF'\n{content}\nEOF")
        if code != 0:
            self._logger.error(f"Failed to write file: {stderr}")
        return code == 0

    def get_home_dir(self) -> Optional[str]:
        """Get the home directory on the remote host."""
        code, stdout, _ = self.run("echo $HOME")
        return stdout.strip() if code == 0 else None

    def __repr__(self) -> str:
        return f"SSHConnection({self._host_config.alias!r})"


def ssh(host: str, **kwargs) -> SSHConnection:
    """Create an SSH connection."""
    return SSHConnection(host, **kwargs)
