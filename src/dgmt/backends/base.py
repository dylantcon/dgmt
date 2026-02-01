"""Abstract base class for sync backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class Backend(ABC):
    """
    Abstract base class for sync backends.

    All backends (SFTP, Syncthing, rclone) implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name (e.g., 'sftp', 'syncthing', 'rclone')."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the backend is operational.

        Returns:
            True if the backend is healthy and ready to sync.
        """
        pass

    @abstractmethod
    def sync(self, local_path: str, remote_path: Optional[str] = None) -> bool:
        """
        Perform bidirectional sync.

        Args:
            local_path: Local directory path.
            remote_path: Remote path (optional, may use default from config).

        Returns:
            True if sync succeeded.
        """
        pass

    def pull(self, local_path: str, timeout: int = 120) -> bool:
        """
        Pull changes from remote to local.

        Args:
            local_path: Local directory path.
            timeout: Timeout in seconds.

        Returns:
            True if pull succeeded.
        """
        # Default implementation uses sync
        return self.sync(local_path)

    def push(self, local_path: str, timeout: int = 120) -> bool:
        """
        Push changes from local to remote.

        Args:
            local_path: Local directory path.
            timeout: Timeout in seconds.

        Returns:
            True if push succeeded.
        """
        # Default implementation uses sync
        return self.sync(local_path)

    def start(self) -> bool:
        """
        Start the backend service (if applicable).

        Returns:
            True if started successfully.
        """
        return True

    def stop(self) -> bool:
        """
        Stop the backend service (if applicable).

        Returns:
            True if stopped successfully.
        """
        return True

    def restart(self) -> bool:
        """
        Restart the backend service.

        Returns:
            True if restarted successfully.
        """
        return self.stop() and self.start()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class BackendBuilder(ABC):
    """
    Abstract builder for creating Backend instances with fluent interface.

    Example:
        backend = (
            SftpBackend.builder("webserver")
            .with_ssh_key("~/.ssh/id_rsa")
            .remote_path("/home/user/notes")
            .bidirectional()
            .build()
        )
    """

    @abstractmethod
    def build(self) -> Backend:
        """Build and return the configured backend instance."""
        pass
