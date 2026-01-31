#!/usr/bin/env python3
"""
dgmt - Dylan's Google [Drive] Management Tool
Unified sync daemon: Syncthing health monitoring + rclone backup

Cross-platform (Windows/Linux)
"""

import subprocess
import threading
import logging
import time
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import requests

# Third-party (pip install watchdog)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_DEFAULT = {
    # Paths to sync
    "watch_paths": [
        "~/Obsidian"
    ],

    # rclone settings
    "rclone_remote": "dgmt",
    "rclone_dest": "Obsidian-Backup",
    "rclone_flags": ["--verbose"],

    # Timing
    "debounce_seconds": 30,       # Wait for quiet period before syncing
    "max_wait_seconds": 300,      # Force sync after this long even if changes continue
    "health_check_interval": 60,  # Check Syncthing health every N seconds

    # Startup behavior
    "pull_on_startup": True,      # Pull from Drive before watching (ensures latest version)
    "startup_pull_timeout": 120,  # Timeout for startup pull (seconds)

    # Syncthing REST API (default local)
    "syncthing_api": "http://localhost:8384",
    "syncthing_api_key": None,    # Set this or it'll try to read from config

    # Logging
    "log_file": "~/.dgmt/dgmt.log",
    "log_level": "INFO",

    # Behavior
    "restart_syncthing_on_failure": True,
    "syncthing_exe": "~/scoop/apps/syncthing/current/syncthing.exe",
}


def load_config() -> dict:
    """Load config from ~/.dgmt/config.json, falling back to defaults."""
    config_path = Path("~/.dgmt/config.json").expanduser()
    config = CONFIG_DEFAULT.copy()

    if config_path.exists():
        with open(config_path) as f:
            user_config = json.load(f)
            config.update(user_config)

    return config


def expand_paths(config: dict) -> dict:
    """Expand ~ in all path fields."""
    config["watch_paths"] = [
        str(Path(p).expanduser()) for p in config["watch_paths"]
    ]
    config["log_file"] = str(Path(config["log_file"]).expanduser())
    if config.get("syncthing_exe"):
        config["syncthing_exe"] = str(Path(config["syncthing_exe"]).expanduser())
    return config


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(config: dict) -> logging.Logger:
    log_path = Path(config["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("dgmt")
    logger.setLevel(getattr(logging, config["log_level"]))

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# ─────────────────────────────────────────────────────────────────────────────
# Syncthing Health Monitor
# ─────────────────────────────────────────────────────────────────────────────

class SyncthingMonitor:
    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.api_url = config["syncthing_api"]
        self.api_key = config["syncthing_api_key"] or self._read_api_key()

    def _read_api_key(self) -> Optional[str]:
        """Try to read API key from Syncthing's config."""
        # Common locations
        if sys.platform == "win32":
            config_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Syncthing" / "config.xml"
        else:
            config_path = Path("~/.config/syncthing/config.xml").expanduser()

        if config_path.exists():
            import xml.etree.ElementTree as ET
            try:
                tree = ET.parse(config_path)
                gui = tree.find(".//gui")
                if gui is not None:
                    apikey = gui.find("apikey")
                    if apikey is not None:
                        return apikey.text
            except Exception as e:
                self.logger.warning(f"Could not read Syncthing API key: {e}")

        return None

    def is_healthy(self) -> bool:
        """Check if Syncthing is responding."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            resp = requests.get(
                f"{self.api_url}/rest/system/ping",
                headers=headers,
                timeout=5
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def start(self) -> bool:
        """Start Syncthing if not running."""
        self.logger.info("Starting Syncthing...")

        if sys.platform == "win32":
            # Suppress console windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE = 0

            subprocess.Popen(
                [self.config["syncthing_exe"], "serve", "--no-browser"],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo
            )
        else:
            # Try systemd first, fall back to direct start
            result = subprocess.run(
                ["systemctl", "--user", "start", "syncthing"],
                capture_output=True
            )
            if result.returncode != 0:
                subprocess.Popen(
                    [self.config["syncthing_exe"], "serve", "--no-browser"],
                    start_new_session=True
                )

        # Wait and verify
        time.sleep(5)
        return self.is_healthy()

    def restart(self) -> bool:
        """Restart Syncthing (kill then start)."""
        self.logger.warning("Restarting Syncthing...")

        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE = 0
            creationflags = subprocess.CREATE_NO_WINDOW

            # Kill existing
            subprocess.run(["taskkill", "/f", "/im", "syncthing.exe"],
                           capture_output=True, startupinfo=startupinfo,
                           creationflags=creationflags)
            time.sleep(2)
        else:
            subprocess.run(["pkill", "syncthing"], capture_output=True)
            time.sleep(2)

        return self.start()


# ─────────────────────────────────────────────────────────────────────────────
# rclone Sync
# ─────────────────────────────────────────────────────────────────────────────

class RcloneSync:
    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.remote = config["rclone_remote"]
        self.dest = config["rclone_dest"]
        self.flags = config["rclone_flags"]
        self._lock = threading.Lock()
        self._first_run = True

    def _get_startupinfo(self):
        """Get subprocess startupinfo to hide console on Windows."""
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE = 0
            return startupinfo
        return None

    def _get_creationflags(self):
        """Get creation flags to prevent console window on Windows."""
        if sys.platform == "win32":
            return subprocess.CREATE_NO_WINDOW
        return 0

    def ensure_remote_exists(self, local_path: str) -> bool:
        """Create the remote directory if it doesn't exist."""
        folder_name = Path(local_path).name
        remote_path = f"{self.remote}:{self.dest}/{folder_name}"

        cmd = ["rclone", "mkdir", remote_path]
        self.logger.info(f"Ensuring remote exists: {remote_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                startupinfo=self._get_startupinfo(),
                creationflags=self._get_creationflags()
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Failed to create remote directory: {e}")
            return False

    def pull(self, local_path: str, timeout: int = 120) -> bool:
        """Pull latest from remote to local (remote wins on conflicts)."""
        with self._lock:
            folder_name = Path(local_path).name
            remote_path = f"{self.remote}:{self.dest}/{folder_name}"

            # Use copy with --update so newer remote files overwrite local
            # But don't delete local files that don't exist on remote
            cmd = [
                "rclone", "copy",
                remote_path, local_path,
                "--update",  # Skip files that are newer on destination
                "--verbose"
            ]

            self.logger.info(f"Pulling from remote: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    startupinfo=self._get_startupinfo(),
                    creationflags=self._get_creationflags()
                )

                if result.returncode == 0:
                    self.logger.info(f"Pull completed: {remote_path} -> {local_path}")
                    return True
                else:
                    self.logger.error(f"Pull failed: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                self.logger.error("Pull timed out")
                return False
            except Exception as e:
                self.logger.error(f"Pull error: {e}")
                return False

    def sync(self, local_path: str) -> bool:
        """Run rclone bisync for the given path."""
        with self._lock:
            folder_name = Path(local_path).name
            remote_path = f"{self.remote}:{self.dest}/{folder_name}"

            # Ensure remote directory exists before bisync
            if self._first_run:
                self.ensure_remote_exists(local_path)

            cmd = ["rclone", "bisync", local_path, remote_path]
            cmd.extend(self.flags)

            # First run needs --resync
            if self._first_run:
                cmd.append("--resync")
                self._first_run = False

            self.logger.info(f"Running: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minute timeout
                    startupinfo=self._get_startupinfo(),
                    creationflags=self._get_creationflags()
                )

                if result.returncode == 0:
                    self.logger.info(f"Sync completed: {local_path}")
                    return True
                else:
                    self.logger.error(f"Sync failed: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                self.logger.error("Sync timed out")
                return False
            except Exception as e:
                self.logger.error(f"Sync error: {e}")
                return False


# ─────────────────────────────────────────────────────────────────────────────
# Debounced File Watcher
# ─────────────────────────────────────────────────────────────────────────────

class DebouncedHandler(FileSystemEventHandler):
    """
    Watches for file changes and triggers sync after a quiet period.
    Prevents rapid-fire syncs when many files change at once.
    """

    def __init__(
        self,
        sync_callback,
        debounce_seconds: float,
        max_wait_seconds: float,
        logger: logging.Logger
    ):
        super().__init__()
        self.sync_callback = sync_callback
        self.debounce_seconds = debounce_seconds
        self.max_wait_seconds = max_wait_seconds
        self.logger = logger

        self._last_event: Optional[datetime] = None
        self._first_event: Optional[datetime] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # Ignore patterns
        self._ignore = {".git", ".obsidian", "__pycache__", ".sync", ".stfolder"}

    def _should_ignore(self, path: str) -> bool:
        parts = Path(path).parts
        return any(p in self._ignore or p.startswith(".") for p in parts)

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return

        with self._lock:
            now = datetime.now()
            self._last_event = now

            if self._first_event is None:
                self._first_event = now
                self.logger.debug(f"Change detected: {event.src_path}")

            # Cancel existing timer
            if self._timer:
                self._timer.cancel()

            # Check if we've exceeded max wait
            elapsed = (now - self._first_event).total_seconds()
            if elapsed >= self.max_wait_seconds:
                self.logger.info("Max wait exceeded, forcing sync")
                self._trigger_sync()
            else:
                # Schedule new debounced sync
                self._timer = threading.Timer(
                    self.debounce_seconds,
                    self._trigger_sync
                )
                self._timer.start()

    def _trigger_sync(self):
        with self._lock:
            self._first_event = None
            self._last_event = None
            self._timer = None

        self.logger.info("Quiet period reached, triggering sync")
        self.sync_callback()


# ─────────────────────────────────────────────────────────────────────────────
# Main Daemon
# ─────────────────────────────────────────────────────────────────────────────

class DGMT:
    def __init__(self):
        self.config = expand_paths(load_config())
        self.logger = setup_logging(self.config)
        self.syncthing = SyncthingMonitor(self.config, self.logger)
        self.rclone = RcloneSync(self.config, self.logger)
        self.observer = Observer()
        self._running = False

    def _sync_all(self):
        """Sync all watched paths."""
        for path in self.config["watch_paths"]:
            self.rclone.sync(path)

    def _pull_all(self):
        """Pull all watched paths from remote."""
        timeout = self.config.get("startup_pull_timeout", 120)
        for path in self.config["watch_paths"]:
            self.rclone.pull(path, timeout=timeout)

    def _health_check_loop(self):
        """Periodically check Syncthing health and ensure it's running."""
        # Initial check - start Syncthing if enabled and not running
        if self.config.get("restart_syncthing_on_failure", True):
            if not self.syncthing.is_healthy():
                self.logger.info("Syncthing not running, starting it...")
                if self.syncthing.start():
                    self.logger.info("Syncthing started successfully")
                else:
                    self.logger.error("Failed to start Syncthing")

        while self._running:
            time.sleep(self.config["health_check_interval"])

            if self.config.get("restart_syncthing_on_failure", True):
                if not self.syncthing.is_healthy():
                    self.logger.warning("Syncthing not responding!")

                    if self.syncthing.restart():
                        self.logger.info("Syncthing restarted successfully")
                    else:
                        self.logger.error("Failed to restart Syncthing")

    def start(self):
        """Start the daemon."""
        self.logger.info("=" * 60)
        self.logger.info("dgmt starting up")
        self.logger.info(f"Watching: {self.config['watch_paths']}")
        self.logger.info(f"Remote: {self.config['rclone_remote']}:{self.config['rclone_dest']}")
        self.logger.info("=" * 60)

        self._running = True

        # Set up file watchers
        handler = DebouncedHandler(
            sync_callback=self._sync_all,
            debounce_seconds=self.config["debounce_seconds"],
            max_wait_seconds=self.config["max_wait_seconds"],
            logger=self.logger
        )

        for path in self.config["watch_paths"]:
            if Path(path).exists():
                self.observer.schedule(handler, path, recursive=True)
                self.logger.info(f"Watching: {path}")
            else:
                self.logger.warning(f"Path does not exist: {path}")

        self.observer.start()

        # Start health check thread
        health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        health_thread.start()

        # Pull from remote first (get latest changes from other devices)
        if self.config.get("pull_on_startup", True):
            self.logger.info("Pulling latest from remote...")
            self._pull_all()

        # Small delay to let filesystem settle after pull
        time.sleep(2)

        # Initial bidirectional sync
        self.logger.info("Running initial sync...")
        self._sync_all()

        self.logger.info("dgmt running. Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the daemon."""
        self.logger.info("Shutting down...")
        self._running = False
        self.observer.stop()
        self.observer.join()
        self.logger.info("dgmt stopped")


def init_config():
    """Create default config file."""
    config_dir = Path("~/.dgmt").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.json"
    if not config_file.exists():
        with open(config_file, "w") as f:
            json.dump(CONFIG_DEFAULT, f, indent=2)
        print(f"Created config: {config_file}")
        print("Edit this file to configure your paths and settings.")
    else:
        print(f"Config already exists: {config_file}")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "init":
            init_config()
            return
        elif cmd == "config":
            config_file = Path("~/.dgmt/config.json").expanduser()
            print(f"Config file: {config_file}")
            if config_file.exists():
                print(config_file.read_text())
            return
        elif cmd in ("-h", "--help", "help"):
            print("dgmt - Dylan's Google [Drive] Management Tool")
            print()
            print("Usage:")
            print("  dgmt          Start the sync daemon")
            print("  dgmt init     Create default config file")
            print("  dgmt config   Show current config")
            print()
            print(f"Config: ~/.dgmt/config.json")
            print(f"Logs:   ~/.dgmt/dgmt.log")
            return

    daemon = DGMT()
    daemon.start()


if __name__ == "__main__":
    main()
