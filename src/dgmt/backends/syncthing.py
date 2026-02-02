"""Syncthing backend for peer-to-peer sync."""

from __future__ import annotations

import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import os

import requests

from dgmt.backends.base import Backend, BackendBuilder
from dgmt.utils.logging import get_logger
from dgmt.utils.paths import expand_path


class SyncthingBackend(Backend):
    """
    Syncthing backend for peer-to-peer synchronization.

    Syncthing handles the actual sync; this backend monitors health
    and can start/stop the Syncthing service.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8384",
        api_key: Optional[str] = None,
        exe_path: Optional[str] = None,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key or self._read_api_key()
        self._exe_path = exe_path
        self._logger = get_logger("dgmt.syncthing")

    @property
    def name(self) -> str:
        return "syncthing"

    def _read_api_key(self) -> Optional[str]:
        """Try to read API key from Syncthing's config."""
        if sys.platform == "win32":
            config_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Syncthing" / "config.xml"
        else:
            config_path = Path("~/.config/syncthing/config.xml").expanduser()

        if config_path.exists():
            try:
                tree = ET.parse(config_path)
                gui = tree.find(".//gui")
                if gui is not None:
                    apikey = gui.find("apikey")
                    if apikey is not None:
                        return apikey.text
            except Exception as e:
                self._logger.warning(f"Could not read Syncthing API key: {e}")

        return None

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def is_healthy(self) -> bool:
        """Check if Syncthing is responding."""
        try:
            resp = requests.get(
                f"{self._api_url}/rest/system/ping",
                headers=self._get_headers(),
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def sync(self, local_path: str, remote_path: Optional[str] = None) -> bool:
        """
        Syncthing handles sync automatically.
        This method triggers a rescan of the folder.
        """
        # Syncthing syncs automatically, but we can trigger a rescan
        return self._rescan_folder(local_path)

    def _rescan_folder(self, local_path: str) -> bool:
        """Trigger a rescan of a folder."""
        # First, get the folder ID for this path
        folder_id = self._get_folder_id(local_path)
        if not folder_id:
            self._logger.warning(f"No Syncthing folder found for {local_path}")
            return True  # Not an error, just not managed by Syncthing

        try:
            resp = requests.post(
                f"{self._api_url}/rest/db/scan",
                headers=self._get_headers(),
                params={"folder": folder_id},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException as e:
            self._logger.error(f"Failed to trigger rescan: {e}")
            return False

    def _get_folder_id(self, local_path: str) -> Optional[str]:
        """Get the Syncthing folder ID for a local path."""
        try:
            resp = requests.get(
                f"{self._api_url}/rest/config/folders",
                headers=self._get_headers(),
                timeout=5,
            )
            if resp.status_code != 200:
                return None

            folders = resp.json()
            local_path = str(expand_path(local_path))

            for folder in folders:
                folder_path = str(expand_path(folder.get("path", "")))
                if folder_path == local_path:
                    return folder.get("id")

            return None
        except requests.RequestException:
            return None

    def get_device_id(self) -> Optional[str]:
        """Get this device's Syncthing device ID."""
        try:
            resp = requests.get(
                f"{self._api_url}/rest/system/status",
                headers=self._get_headers(),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("myID")
            return None
        except requests.RequestException:
            return None

    def get_folder_statuses(self) -> dict[str, str]:
        """Get the sync state of all folders.

        Returns:
            Dict mapping folder ID to state (idle, scanning, syncing, etc.)
        """
        statuses = {}
        try:
            # Get list of folders
            resp = requests.get(
                f"{self._api_url}/rest/config/folders",
                headers=self._get_headers(),
                timeout=5,
            )
            if resp.status_code != 200:
                return statuses

            folders = resp.json()
            for folder in folders:
                folder_id = folder.get("id")
                if not folder_id:
                    continue

                # Get status for each folder
                status_resp = requests.get(
                    f"{self._api_url}/rest/db/status",
                    headers=self._get_headers(),
                    params={"folder": folder_id},
                    timeout=5,
                )
                if status_resp.status_code == 200:
                    state = status_resp.json().get("state", "unknown")
                    statuses[folder_id] = state

            return statuses
        except requests.RequestException as e:
            self._logger.warning(f"Failed to get folder statuses: {e}")
            return statuses

    def is_idle(self) -> bool:
        """Check if all Syncthing folders are idle (not syncing).

        Returns:
            True if all folders are idle or if Syncthing is not running.
        """
        if not self.is_healthy():
            return True  # Can't check, assume idle

        statuses = self.get_folder_statuses()
        if not statuses:
            return True  # No folders or couldn't get status

        for folder_id, state in statuses.items():
            if state not in ("idle", "error"):
                self._logger.debug(f"Folder {folder_id} is {state}")
                return False
        return True

    def wait_for_idle(self, timeout: float = 60, poll_interval: float = 2) -> bool:
        """Wait for all Syncthing folders to become idle.

        Args:
            timeout: Maximum seconds to wait.
            poll_interval: Seconds between status checks.

        Returns:
            True if idle within timeout, False if timed out.
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.is_idle():
                return True
            self._logger.debug(f"Waiting for Syncthing to idle...")
            time.sleep(poll_interval)

        self._logger.warning(f"Syncthing did not idle within {timeout}s")
        return False

    def start(self) -> bool:
        """Start Syncthing if not running."""
        if self.is_healthy():
            return True

        self._logger.info("Starting Syncthing...")

        exe_path = self._exe_path
        if not exe_path:
            # Try common locations
            exe_path = "syncthing"
        else:
            # Expand any ~ in the path (defensive, should already be expanded)
            exe_path = str(Path(exe_path).expanduser())

        # Check if executable exists (if it's an absolute path)
        if os.path.isabs(exe_path) and not os.path.exists(exe_path):
            self._logger.error(f"Syncthing executable not found: {exe_path}")
            return False

        if sys.platform == "win32":
            # Use pythonw.exe (no-console Python) as intermediary launcher
            # This prevents the child process from allocating a console window
            pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            if not Path(pythonw).exists():
                pythonw = sys.executable  # Fall back to regular python

            launcher_script = f'''import subprocess
subprocess.Popen(
    {[exe_path, "serve", "--no-browser"]!r},
    creationflags=0x08000000,
)'''
            subprocess.Popen(
                [pythonw, "-c", launcher_script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            # Try systemd first, fall back to direct start
            result = subprocess.run(
                ["systemctl", "--user", "start", "syncthing"],
                capture_output=True,
            )
            if result.returncode != 0:
                subprocess.Popen(
                    [exe_path, "serve", "--no-browser"],
                    start_new_session=True,
                )

        # Wait and verify
        time.sleep(5)
        return self.is_healthy()

    def stop(self) -> bool:
        """Stop Syncthing."""
        self._logger.info("Stopping Syncthing...")

        # Try API shutdown first
        try:
            requests.post(
                f"{self._api_url}/rest/system/shutdown",
                headers=self._get_headers(),
                timeout=5,
            )
            time.sleep(2)
            if not self.is_healthy():
                return True
        except requests.RequestException:
            pass

        # Fall back to killing process
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            subprocess.run(
                ["taskkill", "/f", "/im", "syncthing.exe"],
                capture_output=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.run(["pkill", "syncthing"], capture_output=True)

        time.sleep(2)
        return not self.is_healthy()

    def restart(self) -> bool:
        """Restart Syncthing."""
        self._logger.warning("Restarting Syncthing...")
        self.stop()
        time.sleep(2)
        return self.start()

    def __repr__(self) -> str:
        return f"SyncthingBackend(api_url={self._api_url!r})"


class SyncthingBuilder(BackendBuilder):
    """Fluent builder for SyncthingBackend."""

    def __init__(self) -> None:
        self._api_url = "http://localhost:8384"
        self._api_key: Optional[str] = None
        self._exe_path: Optional[str] = None

    def api(self, url: str) -> SyncthingBuilder:
        """Set the Syncthing API URL."""
        self._api_url = url
        return self

    def api_key(self, key: str) -> SyncthingBuilder:
        """Set the API key."""
        self._api_key = key
        return self

    def exe(self, path: str) -> SyncthingBuilder:
        """Set the Syncthing executable path."""
        self._exe_path = str(expand_path(path))
        return self

    def build(self) -> SyncthingBackend:
        """Build the SyncthingBackend instance."""
        return SyncthingBackend(
            api_url=self._api_url,
            api_key=self._api_key,
            exe_path=self._exe_path,
        )


def syncthing(**kwargs) -> SyncthingBackend:
    """Create a SyncthingBackend with the given options."""
    return SyncthingBackend(**kwargs)
