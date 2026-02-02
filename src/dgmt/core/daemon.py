"""Main daemon loop and orchestration."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from dgmt.backends import get_backend
from dgmt.backends.base import Backend
from dgmt.core.config import Config, ConfigData
from dgmt.core.shutdown import ShutdownHandler, kill_syncthing
from dgmt.core.watcher import DebouncedWatcher
from dgmt.utils.logging import setup_logging, get_logger
from dgmt.utils.paths import get_config_file


class ConfigFileHandler(FileSystemEventHandler):
    """Watches config file for changes and triggers reload."""

    def __init__(self, config_path: Path, reload_callback) -> None:
        self._config_path = config_path
        self._reload_callback = reload_callback
        self._debounce_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if Path(event.src_path).name != self._config_path.name:
            return

        # Debounce rapid saves (editors often write multiple times)
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(0.5, self._reload_callback)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()


class Daemon:
    """
    Main dgmt daemon that orchestrates file watching and syncing.

    Example:
        daemon = Daemon()
        daemon.start()  # Blocks until shutdown
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        """
        Initialize the daemon.

        Args:
            config: Configuration object. If None, loads from default location.
        """
        self._config_obj = config or Config()
        self._config: ConfigData = self._config_obj.data
        self._logger = setup_logging(
            log_file=self._config.logging.file,
            level=self._config.logging.level,
        )
        self._backends: dict[str, Backend] = {}
        self._watcher: Optional[DebouncedWatcher] = None
        self._config_observer: Optional[Observer] = None
        self._shutdown = ShutdownHandler()
        self._running = False
        self._health_thread: Optional[threading.Thread] = None
        self._reload_lock = threading.Lock()

    def _start_config_watcher(self) -> None:
        """Start watching the config file for changes."""
        config_path = get_config_file()
        if not config_path.exists():
            return

        handler = ConfigFileHandler(config_path, self._reload_config)
        self._config_observer = Observer()
        self._config_observer.schedule(handler, str(config_path.parent), recursive=False)
        self._config_observer.start()
        self._logger.debug(f"Watching config file: {config_path}")

    def _reload_config(self) -> None:
        """Reload configuration from disk and apply changes."""
        with self._reload_lock:
            self._logger.info("Config file changed, reloading...")

            try:
                new_config = Config()
                old_watch_paths = set(self._config.hub.watch_paths)
                new_watch_paths = set(new_config.data.hub.watch_paths)

                # Update config reference
                self._config = new_config.data

                # Handle watch path changes
                added = new_watch_paths - old_watch_paths
                removed = old_watch_paths - new_watch_paths

                if added or removed:
                    self._logger.info(f"Watch paths changed: +{len(added)} -{len(removed)}")
                    # Restart watcher with new paths
                    if self._watcher:
                        self._watcher.stop()
                    self._watcher = DebouncedWatcher(
                        callback=self._sync_all,
                        debounce_seconds=self._config.hub.debounce_seconds,
                        max_wait_seconds=self._config.hub.max_wait_seconds,
                    )
                    self._watcher.watch_all(self._config.hub.watch_paths)
                    self._watcher.start()

                # Reinitialize backends if settings changed
                self._init_backends()

                self._logger.info("Config reloaded successfully")

            except Exception as e:
                self._logger.error(f"Failed to reload config: {e}")

    def _init_backends(self) -> None:
        """Initialize sync backends based on configuration."""
        # Syncthing backend (for local device health monitoring)
        syncthing = get_backend(
            "syncthing",
            api_url=self._config.backends.syncthing_api,
            api_key=self._config.backends.syncthing_api_key,
            exe_path=self._config.backends.syncthing_exe,
        )
        self._backends["syncthing"] = syncthing

        # rclone backend (if enabled)
        if self._config.backends.rclone_enabled:
            rclone = get_backend(
                "rclone",
                remote=self._config.backends.rclone_remote,
                dest=self._config.backends.rclone_dest,
                flags=self._config.backends.rclone_flags,
            )
            self._backends["rclone"] = rclone

    def _sync_all(self) -> None:
        """Sync all watched paths using rclone (if enabled)."""
        rclone = self._backends.get("rclone")
        if not rclone:
            self._logger.debug("rclone not enabled, skipping sync")
            return

        # Wait for Syncthing to finish syncing before running rclone
        syncthing = self._backends.get("syncthing")
        if syncthing:
            if not syncthing.is_idle():
                self._logger.info("Waiting for Syncthing to idle before rclone sync...")
                if not syncthing.wait_for_idle(timeout=120):
                    self._logger.warning("Syncthing still busy, proceeding with rclone anyway")

        for path in self._config.hub.watch_paths:
            try:
                rclone.sync(str(path))
            except Exception as e:
                self._logger.error(f"Sync failed for {path}: {e}")

    def _pull_all(self) -> None:
        """Pull all watched paths from remote."""
        rclone = self._backends.get("rclone")
        if not rclone:
            self._logger.debug("rclone not enabled, skipping pull")
            return

        # Wait for Syncthing to finish syncing before pulling
        syncthing = self._backends.get("syncthing")
        if syncthing:
            if not syncthing.is_idle():
                self._logger.info("Waiting for Syncthing to idle before rclone pull...")
                if not syncthing.wait_for_idle(timeout=120):
                    self._logger.warning("Syncthing still busy, proceeding with rclone pull anyway")

        timeout = self._config.hub.startup_pull_timeout
        for path in self._config.hub.watch_paths:
            try:
                rclone.pull(str(path), timeout=timeout)
            except Exception as e:
                self._logger.error(f"Pull failed for {path}: {e}")

    def _health_check_loop(self) -> None:
        """Periodically check Syncthing health and restart if needed."""
        syncthing = self._backends.get("syncthing")
        if not syncthing:
            return

        # Initial check - start Syncthing if not running
        if self._config.backends.restart_syncthing_on_failure:
            if not syncthing.is_healthy():
                self._logger.info("Syncthing not running, starting it...")
                if syncthing.start():
                    self._logger.info("Syncthing started successfully")
                else:
                    self._logger.error("Failed to start Syncthing")

        while self._running:
            time.sleep(self._config.hub.health_check_interval)

            if not self._running:
                break

            if self._config.backends.restart_syncthing_on_failure:
                if not syncthing.is_healthy():
                    self._logger.warning("Syncthing not responding!")
                    if syncthing.restart():
                        self._logger.info("Syncthing restarted successfully")
                    else:
                        self._logger.error("Failed to restart Syncthing")

    def start(self) -> None:
        """Start the daemon (blocking)."""
        self._logger.info("=" * 60)
        self._logger.info("dgmt starting up")
        self._logger.info(f"Watching: {[str(p) for p in self._config.hub.watch_paths]}")
        if self._config.backends.rclone_enabled:
            self._logger.info(
                f"rclone: {self._config.backends.rclone_remote}:"
                f"{self._config.backends.rclone_dest}"
            )
        self._logger.info("=" * 60)

        self._running = True

        # Initialize backends
        self._init_backends()

        # Set up shutdown handler
        self._shutdown.on_shutdown(self._stop_internal)
        self._shutdown.register_cleanup(
            lambda: kill_syncthing({
                "stop_syncthing_on_exit": self._config.backends.stop_syncthing_on_exit
            })
        )
        self._shutdown.install()

        # Watch config file for hot reload
        self._start_config_watcher()

        # Set up file watcher
        self._watcher = DebouncedWatcher(
            callback=self._sync_all,
            debounce_seconds=self._config.hub.debounce_seconds,
            max_wait_seconds=self._config.hub.max_wait_seconds,
        )
        self._watcher.watch_all(self._config.hub.watch_paths)
        self._watcher.start()

        # Start health check thread
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="health-check",
        )
        self._health_thread.start()

        # Pull from remote first (get latest changes)
        if self._config.hub.pull_on_startup and self._config.backends.rclone_enabled:
            self._logger.info("Pulling latest from remote...")
            self._pull_all()
            time.sleep(2)  # Let filesystem settle

        # Initial sync
        if self._config.backends.rclone_enabled:
            self._logger.info("Running initial sync...")
            self._sync_all()

        self._logger.info("dgmt running. Press Ctrl+C to stop.")

        # Block until shutdown
        self._shutdown.wait_for_shutdown()

    def _stop_internal(self) -> None:
        """Internal stop method called by shutdown handler."""
        self._logger.info("Shutting down...")
        self._running = False

        if self._config_observer:
            self._config_observer.stop()
            self._config_observer.join(timeout=2)

        if self._watcher:
            self._watcher.stop()

        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=2)

        self._logger.info("dgmt stopped")

    def stop(self) -> None:
        """Stop the daemon programmatically."""
        self._shutdown.trigger_shutdown()

    @property
    def is_running(self) -> bool:
        """Check if the daemon is currently running."""
        return self._running
