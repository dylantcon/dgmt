"""Signal handlers and graceful shutdown management."""

from __future__ import annotations

import atexit
import signal
import subprocess
import sys
import threading
from typing import Callable, Optional

from dgmt.utils.logging import get_logger


class ShutdownHandler:
    """
    Manages graceful shutdown with signal handlers and cleanup callbacks.

    Example:
        handler = ShutdownHandler()
        handler.register_cleanup(lambda: print("Cleaning up..."))
        handler.on_shutdown(stop_daemon)
        handler.install()
    """

    def __init__(self) -> None:
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._shutdown_callback: Optional[Callable[[], None]] = None
        self._shutdown_event = threading.Event()
        self._installed = False
        self.logger = get_logger("dgmt.shutdown")

    def register_cleanup(self, callback: Callable[[], None]) -> ShutdownHandler:
        """
        Register a cleanup callback to run on shutdown.

        Args:
            callback: Function to call during cleanup.

        Returns:
            self for method chaining.
        """
        self._cleanup_callbacks.append(callback)
        return self

    def on_shutdown(self, callback: Callable[[], None]) -> ShutdownHandler:
        """
        Register the main shutdown callback.

        Args:
            callback: Function to call when shutdown is triggered.

        Returns:
            self for method chaining.
        """
        self._shutdown_callback = callback
        return self

    def install(self) -> ShutdownHandler:
        """
        Install signal handlers for graceful shutdown.

        Returns:
            self for method chaining.
        """
        if self._installed:
            return self

        # Register atexit handler
        atexit.register(self._run_cleanup)

        # Install signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Windows-specific: CTRL_BREAK_EVENT
        if sys.platform == "win32":
            try:
                signal.signal(signal.SIGBREAK, self._signal_handler)
            except (AttributeError, ValueError):
                pass

        self._installed = True
        self.logger.debug("Shutdown handlers installed")
        return self

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name}, initiating shutdown...")
        self.trigger_shutdown()

    def trigger_shutdown(self) -> None:
        """Trigger shutdown programmatically."""
        if self._shutdown_event.is_set():
            return  # Already shutting down

        self._shutdown_event.set()

        if self._shutdown_callback:
            try:
                self._shutdown_callback()
            except Exception as e:
                self.logger.error(f"Shutdown callback error: {e}")

        self._run_cleanup()

    def _run_cleanup(self) -> None:
        """Run all registered cleanup callbacks."""
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for shutdown to be triggered.

        Args:
            timeout: Maximum seconds to wait (None = forever).

        Returns:
            True if shutdown was triggered, False if timeout.
        """
        return self._shutdown_event.wait(timeout)

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been triggered."""
        return self._shutdown_event.is_set()


def kill_syncthing(config: dict) -> None:
    """Kill Syncthing process if configured to stop on exit."""
    logger = get_logger("dgmt.shutdown")

    if not config.get("stop_syncthing_on_exit", False):
        return

    logger.info("Stopping Syncthing...")

    if sys.platform == "win32":
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            subprocess.run(
                ["taskkill", "/f", "/im", "syncthing.exe"],
                capture_output=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            logger.error(f"Failed to kill Syncthing: {e}")
    else:
        try:
            subprocess.run(["pkill", "syncthing"], capture_output=True)
        except Exception as e:
            logger.error(f"Failed to kill Syncthing: {e}")
