"""Abstract base class for system service managers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ServiceStatus(Enum):
    """Status of a system service."""

    RUNNING = "running"
    STOPPED = "stopped"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Information about a system service."""

    name: str
    status: ServiceStatus
    pid: Optional[int] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    error_message: Optional[str] = None


class ServiceManager(ABC):
    """
    Abstract base class for system service managers.

    Implementations handle platform-specific service registration
    (systemd on Linux, Task Scheduler on Windows).
    """

    SERVICE_NAME = "dgmt"
    SERVICE_DESCRIPTION = "Dylan's General Management Tool - Sync Daemon"

    @abstractmethod
    def install(self, python_path: Optional[str] = None) -> bool:
        """
        Install dgmt as a system service.

        Args:
            python_path: Path to Python interpreter (uses sys.executable if None).

        Returns:
            True if installation succeeded.
        """
        pass

    @abstractmethod
    def uninstall(self) -> bool:
        """
        Remove dgmt system service.

        Returns:
            True if uninstallation succeeded.
        """
        pass

    @abstractmethod
    def start(self) -> bool:
        """
        Start the dgmt service.

        Returns:
            True if service started successfully.
        """
        pass

    @abstractmethod
    def stop(self) -> bool:
        """
        Stop the dgmt service.

        Returns:
            True if service stopped successfully.
        """
        pass

    @abstractmethod
    def restart(self) -> bool:
        """
        Restart the dgmt service.

        Returns:
            True if service restarted successfully.
        """
        pass

    @abstractmethod
    def status(self) -> ServiceInfo:
        """
        Get the current service status.

        Returns:
            ServiceInfo with current status details.
        """
        pass

    @abstractmethod
    def is_installed(self) -> bool:
        """
        Check if the service is installed.

        Returns:
            True if service is installed.
        """
        pass

    def enable(self) -> bool:
        """
        Enable the service to start on boot.

        Returns:
            True if enabled successfully.
        """
        return True  # Default implementation (some platforms enable on install)

    def disable(self) -> bool:
        """
        Disable the service from starting on boot.

        Returns:
            True if disabled successfully.
        """
        return True  # Default implementation

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'systemd', 'windows')."""
        pass
