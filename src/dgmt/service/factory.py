"""Factory for creating platform-specific service managers."""

from __future__ import annotations

import sys
from typing import Optional

from dgmt.service.base import ServiceManager


def get_service_manager() -> ServiceManager:
    """
    Get the appropriate service manager for the current platform.

    Returns:
        ServiceManager implementation for the current OS.

    Raises:
        NotImplementedError: If the platform is not supported.
    """
    if sys.platform == "win32":
        from dgmt.service.windows import WindowsServiceManager
        return WindowsServiceManager()

    elif sys.platform in ("linux", "linux2"):
        from dgmt.service.linux import SystemdServiceManager
        return SystemdServiceManager()

    elif sys.platform == "darwin":
        # macOS could use launchd, but not implemented yet
        raise NotImplementedError(
            "macOS service management not yet implemented. "
            "Consider using launchd manually or running dgmt in a terminal."
        )

    else:
        raise NotImplementedError(
            f"Service management not supported on platform: {sys.platform}"
        )


def is_service_supported() -> bool:
    """Check if service management is supported on this platform."""
    return sys.platform in ("win32", "linux", "linux2")


def get_platform_name() -> str:
    """Get a human-readable platform name."""
    if sys.platform == "win32":
        return "Windows (Task Scheduler)"
    elif sys.platform in ("linux", "linux2"):
        return "Linux (systemd)"
    elif sys.platform == "darwin":
        return "macOS (launchd - not implemented)"
    else:
        return f"Unknown ({sys.platform})"
