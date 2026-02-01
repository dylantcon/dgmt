"""Linux systemd service manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dgmt.service.base import ServiceInfo, ServiceManager, ServiceStatus
from dgmt.utils.logging import get_logger


class SystemdServiceManager(ServiceManager):
    """
    Service manager for Linux using systemd user services.

    Creates a user-level systemd service (no root required).
    """

    UNIT_FILE_TEMPLATE = """\
[Unit]
Description={description}
After=network.target

[Service]
Type=simple
ExecStart={python} -m dgmt run
Restart=on-failure
RestartSec=5
Environment=HOME={home}
WorkingDirectory={home}

[Install]
WantedBy=default.target
"""

    def __init__(self) -> None:
        self._logger = get_logger("dgmt.service")
        self._unit_dir = Path("~/.config/systemd/user").expanduser()
        self._unit_file = self._unit_dir / f"{self.SERVICE_NAME}.service"

    @property
    def platform_name(self) -> str:
        return "systemd"

    def _run_systemctl(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        """Run a systemctl --user command."""
        cmd = ["systemctl", "--user", *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def install(self, python_path: Optional[str] = None) -> bool:
        """Install dgmt as a systemd user service."""
        python = python_path or sys.executable
        home = str(Path.home())

        # Create unit file content
        unit_content = self.UNIT_FILE_TEMPLATE.format(
            description=self.SERVICE_DESCRIPTION,
            python=python,
            home=home,
        )

        # Ensure directory exists
        self._unit_dir.mkdir(parents=True, exist_ok=True)

        # Write unit file
        try:
            self._unit_file.write_text(unit_content)
            self._logger.info(f"Created service file: {self._unit_file}")
        except Exception as e:
            self._logger.error(f"Failed to write unit file: {e}")
            return False

        # Reload systemd
        result = self._run_systemctl("daemon-reload")
        if result.returncode != 0:
            self._logger.error(f"Failed to reload systemd: {result.stderr}")
            return False

        # Enable the service
        result = self._run_systemctl("enable", self.SERVICE_NAME)
        if result.returncode != 0:
            self._logger.error(f"Failed to enable service: {result.stderr}")
            return False

        self._logger.info(f"Service '{self.SERVICE_NAME}' installed and enabled")
        return True

    def uninstall(self) -> bool:
        """Remove the systemd service."""
        # Stop the service first
        self.stop()

        # Disable the service
        self._run_systemctl("disable", self.SERVICE_NAME)

        # Remove unit file
        try:
            if self._unit_file.exists():
                self._unit_file.unlink()
                self._logger.info(f"Removed service file: {self._unit_file}")
        except Exception as e:
            self._logger.error(f"Failed to remove unit file: {e}")
            return False

        # Reload systemd
        self._run_systemctl("daemon-reload")

        self._logger.info(f"Service '{self.SERVICE_NAME}' uninstalled")
        return True

    def start(self) -> bool:
        """Start the dgmt service."""
        result = self._run_systemctl("start", self.SERVICE_NAME)
        if result.returncode != 0:
            self._logger.error(f"Failed to start service: {result.stderr}")
            return False

        self._logger.info(f"Service '{self.SERVICE_NAME}' started")
        return True

    def stop(self) -> bool:
        """Stop the dgmt service."""
        result = self._run_systemctl("stop", self.SERVICE_NAME)
        if result.returncode != 0:
            self._logger.error(f"Failed to stop service: {result.stderr}")
            return False

        self._logger.info(f"Service '{self.SERVICE_NAME}' stopped")
        return True

    def restart(self) -> bool:
        """Restart the dgmt service."""
        result = self._run_systemctl("restart", self.SERVICE_NAME)
        if result.returncode != 0:
            self._logger.error(f"Failed to restart service: {result.stderr}")
            return False

        self._logger.info(f"Service '{self.SERVICE_NAME}' restarted")
        return True

    def status(self) -> ServiceInfo:
        """Get current service status."""
        if not self.is_installed():
            return ServiceInfo(
                name=self.SERVICE_NAME,
                status=ServiceStatus.NOT_INSTALLED,
            )

        result = self._run_systemctl("is-active", self.SERVICE_NAME)
        status_text = result.stdout.strip()

        if status_text == "active":
            status = ServiceStatus.RUNNING
        elif status_text in ("inactive", "deactivating"):
            status = ServiceStatus.STOPPED
        elif status_text == "failed":
            status = ServiceStatus.ERROR
        else:
            status = ServiceStatus.UNKNOWN

        # Get PID if running
        pid = None
        if status == ServiceStatus.RUNNING:
            result = self._run_systemctl("show", "-p", "MainPID", self.SERVICE_NAME)
            try:
                pid_str = result.stdout.strip().split("=")[1]
                pid = int(pid_str) if pid_str != "0" else None
            except (IndexError, ValueError):
                pass

        return ServiceInfo(
            name=self.SERVICE_NAME,
            status=status,
            pid=pid,
            description=self.SERVICE_DESCRIPTION,
        )

    def is_installed(self) -> bool:
        """Check if the service is installed."""
        return self._unit_file.exists()

    def enable(self) -> bool:
        """Enable the service to start on boot."""
        result = self._run_systemctl("enable", self.SERVICE_NAME)
        return result.returncode == 0

    def disable(self) -> bool:
        """Disable the service from starting on boot."""
        result = self._run_systemctl("disable", self.SERVICE_NAME)
        return result.returncode == 0

    def logs(self, lines: int = 50) -> str:
        """Get recent service logs."""
        result = subprocess.run(
            ["journalctl", "--user", "-u", self.SERVICE_NAME, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
        )
        return result.stdout
