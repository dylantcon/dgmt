"""System service management (systemd, Windows Task Scheduler)."""

from dgmt.service.factory import get_service_manager

__all__ = ["get_service_manager"]
