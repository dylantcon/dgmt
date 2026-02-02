"""rclone backend for cloud storage sync."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from dgmt.backends.base import Backend, BackendBuilder
from dgmt.utils.logging import get_logger


class RcloneBackend(Backend):
    """
    rclone backend for syncing with cloud storage.

    Supports bidirectional sync (bisync) and pull operations.
    """

    def __init__(
        self,
        remote: str = "dgmt",
        dest: str = "Obsidian-Backup",
        flags: Optional[list[str]] = None,
    ) -> None:
        self._remote = remote
        self._dest = dest
        self._flags = flags or ["--verbose"]
        self._lock = threading.Lock()
        self._first_run = True
        self._logger = get_logger("dgmt.rclone")

    @property
    def name(self) -> str:
        return "rclone"

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

    def _get_remote_path(self, local_path: str) -> str:
        """Get the remote path for a local path."""
        folder_name = Path(local_path).name
        return f"{self._remote}:{self._dest}/{folder_name}"

    def is_healthy(self) -> bool:
        """Check if rclone is available and the remote is configured."""
        try:
            result = subprocess.run(
                ["rclone", "listremotes"],
                capture_output=True,
                text=True,
                timeout=10,
                **self._get_subprocess_args(),
            )
            if result.returncode != 0:
                return False

            remotes = result.stdout.strip().split("\n")
            return f"{self._remote}:" in remotes
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def ensure_remote_exists(self, local_path: str) -> bool:
        """Create the remote directory if it doesn't exist."""
        remote_path = self._get_remote_path(local_path)
        cmd = ["rclone", "mkdir", remote_path]

        self._logger.info(f"Ensuring remote exists: {remote_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                **self._get_subprocess_args(),
            )
            return result.returncode == 0
        except Exception as e:
            self._logger.error(f"Failed to create remote directory: {e}")
            return False

    def _run_bisync(
        self, local_path: str, remote: str, resync: bool = False
    ) -> subprocess.CompletedProcess:
        """Run rclone bisync command."""
        cmd = ["rclone", "bisync", local_path, remote]
        cmd.extend(self._flags)

        # Ignore checksum to handle files that change during transfer
        # (e.g., Obsidian's workspace.json)
        if "--ignore-checksum" not in cmd:
            cmd.append("--ignore-checksum")

        if resync:
            cmd.append("--resync")

        self._logger.info(f"Running: {' '.join(cmd)}")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            **self._get_subprocess_args(),
        )

    def sync(self, local_path: str, remote_path: Optional[str] = None) -> bool:
        """Run rclone bisync for the given path."""
        with self._lock:
            remote = remote_path or self._get_remote_path(local_path)

            # Ensure remote directory exists before bisync
            if self._first_run:
                self.ensure_remote_exists(local_path)

            try:
                # First run needs --resync
                resync = self._first_run
                if self._first_run:
                    self._first_run = False

                result = self._run_bisync(local_path, remote, resync=resync)

                if result.returncode == 0:
                    self._logger.info(f"Sync completed: {local_path}")
                    return True

                # Check if we need to recover with --resync
                output = result.stderr + result.stdout
                if "Must run --resync" in output or "cannot find prior" in output:
                    self._logger.warning(
                        "Bisync state corrupted, recovering with --resync"
                    )
                    result = self._run_bisync(local_path, remote, resync=True)

                    if result.returncode == 0:
                        self._logger.info(f"Sync recovered and completed: {local_path}")
                        return True

                self._logger.error(f"Sync failed: {result.stderr}")
                return False

            except subprocess.TimeoutExpired:
                self._logger.error("Sync timed out")
                return False
            except Exception as e:
                self._logger.error(f"Sync error: {e}")
                return False

    def pull(self, local_path: str, timeout: int = 120) -> bool:
        """Pull latest from remote to local (remote wins on conflicts)."""
        with self._lock:
            remote_path = self._get_remote_path(local_path)

            # Use copy with --update so newer remote files overwrite local
            cmd = [
                "rclone", "copy",
                remote_path, local_path,
                "--update",
                "--verbose",
            ]

            self._logger.info(f"Pulling from remote: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    **self._get_subprocess_args(),
                )

                if result.returncode == 0:
                    self._logger.info(f"Pull completed: {remote_path} -> {local_path}")
                    return True
                else:
                    self._logger.error(f"Pull failed: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                self._logger.error("Pull timed out")
                return False
            except Exception as e:
                self._logger.error(f"Pull error: {e}")
                return False

    def push(self, local_path: str, timeout: int = 120) -> bool:
        """Push changes from local to remote."""
        with self._lock:
            remote_path = self._get_remote_path(local_path)

            cmd = [
                "rclone", "copy",
                local_path, remote_path,
                "--update",
                "--verbose",
            ]

            self._logger.info(f"Pushing to remote: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    **self._get_subprocess_args(),
                )

                if result.returncode == 0:
                    self._logger.info(f"Push completed: {local_path} -> {remote_path}")
                    return True
                else:
                    self._logger.error(f"Push failed: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                self._logger.error("Push timed out")
                return False
            except Exception as e:
                self._logger.error(f"Push error: {e}")
                return False

    def __repr__(self) -> str:
        return f"RcloneBackend(remote={self._remote!r}, dest={self._dest!r})"


class RcloneBuilder(BackendBuilder):
    """Fluent builder for RcloneBackend."""

    def __init__(self, remote: str = "dgmt") -> None:
        self._remote = remote
        self._dest = "Obsidian-Backup"
        self._flags: list[str] = ["--verbose"]

    def dest(self, path: str) -> RcloneBuilder:
        """Set the remote destination path."""
        self._dest = path
        return self

    def flags(self, *flags: str) -> RcloneBuilder:
        """Set rclone flags."""
        self._flags = list(flags)
        return self

    def verbose(self) -> RcloneBuilder:
        """Enable verbose output."""
        if "--verbose" not in self._flags:
            self._flags.append("--verbose")
        return self

    def build(self) -> RcloneBackend:
        """Build the RcloneBackend instance."""
        return RcloneBackend(
            remote=self._remote,
            dest=self._dest,
            flags=self._flags,
        )


def rclone(remote: str = "dgmt", **kwargs) -> RcloneBackend:
    """Create an RcloneBackend with the given options."""
    return RcloneBackend(remote=remote, **kwargs)
