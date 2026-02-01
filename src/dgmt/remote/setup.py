"""Remote dgmt installation and setup."""

from __future__ import annotations

from typing import Optional

from dgmt.remote.ssh import SSHConnection
from dgmt.utils.logging import get_logger


class RemoteSetup:
    """
    Handles installation and setup of dgmt on remote machines.
    """

    def __init__(self, host: str) -> None:
        """
        Initialize remote setup for a host.

        Args:
            host: SSH host alias or hostname.
        """
        self._host = host
        self._ssh = SSHConnection(host)
        self._logger = get_logger("dgmt.remote.setup")

    def check_python(self) -> Optional[str]:
        """
        Check if Python 3 is available on the remote.

        Returns:
            Python path if found, None otherwise.
        """
        for python in ["python3", "python"]:
            code, stdout, _ = self._ssh.run(f"which {python}")
            if code == 0:
                path = stdout.strip()
                # Verify it's Python 3
                code, stdout, _ = self._ssh.run(f"{path} --version")
                if code == 0 and "Python 3" in stdout:
                    return path
        return None

    def check_pip(self) -> Optional[str]:
        """
        Check if pip is available on the remote.

        Returns:
            pip path if found, None otherwise.
        """
        for pip in ["pip3", "pip"]:
            code, stdout, _ = self._ssh.run(f"which {pip}")
            if code == 0:
                return stdout.strip()
        return None

    def check_syncthing(self) -> Optional[str]:
        """
        Check if Syncthing is installed on the remote.

        Returns:
            Syncthing path if found, None otherwise.
        """
        code, stdout, _ = self._ssh.run("which syncthing")
        if code == 0:
            return stdout.strip()
        return None

    def check_rsync(self) -> Optional[str]:
        """
        Check if rsync is installed on the remote.

        Returns:
            rsync path if found, None otherwise.
        """
        code, stdout, _ = self._ssh.run("which rsync")
        if code == 0:
            return stdout.strip()
        return None

    def install_dgmt(self, pip_path: Optional[str] = None) -> bool:
        """
        Install dgmt on the remote machine.

        Args:
            pip_path: Path to pip (auto-detected if None).

        Returns:
            True if installation succeeded.
        """
        pip = pip_path or self.check_pip()
        if not pip:
            self._logger.error("pip not found on remote")
            return False

        self._logger.info(f"Installing dgmt on {self._host}...")
        code, stdout, stderr = self._ssh.run(f"{pip} install --user dgmt")

        if code != 0:
            self._logger.error(f"Installation failed: {stderr}")
            return False

        self._logger.info("dgmt installed successfully")
        return True

    def install_syncthing(self) -> bool:
        """
        Attempt to install Syncthing on the remote.

        Returns:
            True if installation succeeded.
        """
        # Try apt (Debian/Ubuntu)
        code, _, _ = self._ssh.run("which apt-get")
        if code == 0:
            self._logger.info("Installing Syncthing via apt...")
            code, _, stderr = self._ssh.run(
                "sudo apt-get update && sudo apt-get install -y syncthing"
            )
            if code == 0:
                return True
            self._logger.warning(f"apt install failed: {stderr}")

        # Try pacman (Arch)
        code, _, _ = self._ssh.run("which pacman")
        if code == 0:
            self._logger.info("Installing Syncthing via pacman...")
            code, _, stderr = self._ssh.run("sudo pacman -S --noconfirm syncthing")
            if code == 0:
                return True
            self._logger.warning(f"pacman install failed: {stderr}")

        # Try dnf (Fedora)
        code, _, _ = self._ssh.run("which dnf")
        if code == 0:
            self._logger.info("Installing Syncthing via dnf...")
            code, _, stderr = self._ssh.run("sudo dnf install -y syncthing")
            if code == 0:
                return True
            self._logger.warning(f"dnf install failed: {stderr}")

        self._logger.error(
            "Could not install Syncthing automatically. "
            "Please install it manually: https://syncthing.net/downloads/"
        )
        return False

    def get_syncthing_device_id(self) -> Optional[str]:
        """
        Get the Syncthing device ID from the remote.

        Returns:
            Device ID if available, None otherwise.
        """
        code, stdout, _ = self._ssh.run(
            "syncthing --device-id 2>/dev/null || syncthing -device-id 2>/dev/null"
        )
        if code == 0:
            return stdout.strip()
        return None

    def setup_sync_folder(self, path: str) -> bool:
        """
        Create and configure sync folder on remote.

        Args:
            path: Path for sync folder.

        Returns:
            True if setup succeeded.
        """
        # Expand ~ if needed
        if path.startswith("~"):
            home = self._ssh.get_home_dir()
            if home:
                path = home + path[1:]

        return self._ssh.mkdir(path)

    def check_prerequisites(self) -> dict[str, bool]:
        """
        Check all prerequisites on the remote machine.

        Returns:
            Dict of prerequisite name to availability.
        """
        return {
            "python3": self.check_python() is not None,
            "pip": self.check_pip() is not None,
            "syncthing": self.check_syncthing() is not None,
            "rsync": self.check_rsync() is not None,
        }

    def full_setup(
        self,
        sync_folder: str = "~/sync",
        backend: str = "syncthing",
    ) -> bool:
        """
        Perform full setup of a remote machine.

        Args:
            sync_folder: Path for sync folder.
            backend: Backend to use ('syncthing' or 'sftp').

        Returns:
            True if setup succeeded.
        """
        self._logger.info(f"Setting up {self._host} with {backend} backend...")

        # Test connection
        if not self._ssh.test_connection():
            self._logger.error(f"Cannot connect to {self._host}")
            return False

        # Check prerequisites
        prereqs = self.check_prerequisites()
        self._logger.info(f"Prerequisites: {prereqs}")

        # Create sync folder
        if not self.setup_sync_folder(sync_folder):
            self._logger.error("Failed to create sync folder")
            return False

        # Backend-specific setup
        if backend == "syncthing":
            if not prereqs["syncthing"]:
                self._logger.warning("Syncthing not installed, attempting to install...")
                if not self.install_syncthing():
                    return False

            device_id = self.get_syncthing_device_id()
            if device_id:
                self._logger.info(f"Syncthing device ID: {device_id}")

        elif backend == "sftp":
            if not prereqs["rsync"]:
                self._logger.warning("rsync not installed, sync may be slower")

        self._logger.info(f"Setup complete for {self._host}")
        return True
