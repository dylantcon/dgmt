"""Configuration management with fluent builder interface."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dgmt.utils.fluent import FluentBuilder
from dgmt.utils.paths import expand_path, get_config_file, get_log_file


@dataclass
class HubConfig:
    """Configuration for the hub (local) machine."""

    watch_paths: list[Path] = field(default_factory=list)
    debounce_seconds: int = 30
    max_wait_seconds: int = 300
    health_check_interval: int = 60
    pull_on_startup: bool = True
    startup_pull_timeout: int = 120


@dataclass
class SpokeConfig:
    """Configuration for a spoke (remote) machine."""

    name: str
    backend: str = "syncthing"
    remote_path: Optional[str] = None
    device_id: Optional[str] = None
    enabled: bool = True


@dataclass
class BackendSettings:
    """Settings for sync backends."""

    # rclone settings
    rclone_remote: str = "dgmt"
    rclone_dest: str = "Obsidian-Backup"
    rclone_flags: list[str] = field(default_factory=lambda: ["--verbose"])
    rclone_enabled: bool = False

    # Syncthing settings
    syncthing_api: str = "http://localhost:8384"
    syncthing_api_key: Optional[str] = None
    syncthing_exe: Optional[str] = None
    stop_syncthing_on_exit: bool = True
    restart_syncthing_on_failure: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration."""

    file: Path = field(default_factory=get_log_file)
    level: str = "INFO"


@dataclass
class ConfigData:
    """Complete configuration data structure."""

    hub: HubConfig = field(default_factory=HubConfig)
    defaults: dict[str, Any] = field(default_factory=lambda: {"backend": "syncthing"})
    spokes: dict[str, SpokeConfig] = field(default_factory=dict)
    backends: BackendSettings = field(default_factory=BackendSettings)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config(FluentBuilder["Config"]):
    """
    Fluent configuration builder for dgmt.

    Example:
        config = (
            Config()
            .watch("~/Obsidian", "~/Documents/notes")
            .with_backend("syncthing")
            .stop_syncthing_on_exit(True)
            .debounce(seconds=30)
            .health_check(interval=60)
            .save()
        )
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        super().__init__()
        self._config_path = config_path or get_config_file()
        self._data = ConfigData()
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing config if present."""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                self._from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass

    def _from_dict(self, data: dict[str, Any]) -> None:
        """Populate config from dictionary (for loading from JSON)."""
        # Hub config
        if "hub" in data:
            hub = data["hub"]
            self._data.hub.watch_paths = [
                expand_path(p) for p in hub.get("watch_paths", [])
            ]
            self._data.hub.debounce_seconds = hub.get("debounce_seconds", 30)
            self._data.hub.max_wait_seconds = hub.get("max_wait_seconds", 300)
            self._data.hub.health_check_interval = hub.get("health_check_interval", 60)
            self._data.hub.pull_on_startup = hub.get("pull_on_startup", True)
            self._data.hub.startup_pull_timeout = hub.get("startup_pull_timeout", 120)
        elif "watch_paths" in data:
            # Legacy flat config format
            self._data.hub.watch_paths = [
                expand_path(p) for p in data.get("watch_paths", [])
            ]
            self._data.hub.debounce_seconds = data.get("debounce_seconds", 30)
            self._data.hub.max_wait_seconds = data.get("max_wait_seconds", 300)
            self._data.hub.health_check_interval = data.get("health_check_interval", 60)
            self._data.hub.pull_on_startup = data.get("pull_on_startup", True)
            self._data.hub.startup_pull_timeout = data.get("startup_pull_timeout", 120)

        # Defaults
        if "defaults" in data:
            self._data.defaults = data["defaults"]

        # Spokes
        if "spokes" in data:
            for name, spoke_data in data["spokes"].items():
                self._data.spokes[name] = SpokeConfig(
                    name=name,
                    backend=spoke_data.get("backend", "syncthing"),
                    remote_path=spoke_data.get("remote_path"),
                    device_id=spoke_data.get("device_id"),
                    enabled=spoke_data.get("enabled", True),
                )

        # Backend settings
        if "backends" in data:
            backends = data["backends"]
            if "rclone" in backends:
                rc = backends["rclone"]
                self._data.backends.rclone_remote = rc.get("remote", "dgmt")
                self._data.backends.rclone_dest = rc.get("dest", "Obsidian-Backup")
                self._data.backends.rclone_flags = rc.get("flags", ["--verbose"])
                self._data.backends.rclone_enabled = rc.get("enabled", False)
            if "syncthing" in backends:
                st = backends["syncthing"]
                self._data.backends.syncthing_api = st.get("api", "http://localhost:8384")
                self._data.backends.syncthing_api_key = st.get("api_key")
                exe = st.get("exe")
                self._data.backends.syncthing_exe = str(expand_path(exe)) if exe else None
                self._data.backends.stop_syncthing_on_exit = st.get(
                    "stop_on_exit", True
                )
                self._data.backends.restart_syncthing_on_failure = st.get(
                    "restart_on_failure", True
                )
        elif "rclone_remote" in data:
            # Legacy flat config format
            self._data.backends.rclone_remote = data.get("rclone_remote", "dgmt")
            self._data.backends.rclone_dest = data.get("rclone_dest", "Obsidian-Backup")
            self._data.backends.rclone_flags = data.get("rclone_flags", ["--verbose"])
            self._data.backends.syncthing_api = data.get(
                "syncthing_api", "http://localhost:8384"
            )
            self._data.backends.syncthing_api_key = data.get("syncthing_api_key")
            self._data.backends.syncthing_exe = data.get("syncthing_exe")
            self._data.backends.restart_syncthing_on_failure = data.get(
                "restart_syncthing_on_failure", True
            )

        # Logging
        if "logging" in data:
            log = data["logging"]
            self._data.logging.file = expand_path(log.get("file", "~/.dgmt/dgmt.log"))
            self._data.logging.level = log.get("level", "INFO")
        elif "log_file" in data:
            # Legacy flat config format
            self._data.logging.file = expand_path(data.get("log_file", "~/.dgmt/dgmt.log"))
            self._data.logging.level = data.get("log_level", "INFO")

    def _to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        return {
            "hub": {
                "watch_paths": [str(p) for p in self._data.hub.watch_paths],
                "debounce_seconds": self._data.hub.debounce_seconds,
                "max_wait_seconds": self._data.hub.max_wait_seconds,
                "health_check_interval": self._data.hub.health_check_interval,
                "pull_on_startup": self._data.hub.pull_on_startup,
                "startup_pull_timeout": self._data.hub.startup_pull_timeout,
            },
            "defaults": self._data.defaults,
            "spokes": {
                name: {
                    "backend": spoke.backend,
                    "remote_path": spoke.remote_path,
                    "device_id": spoke.device_id,
                    "enabled": spoke.enabled,
                }
                for name, spoke in self._data.spokes.items()
            },
            "backends": {
                "rclone": {
                    "remote": self._data.backends.rclone_remote,
                    "dest": self._data.backends.rclone_dest,
                    "flags": self._data.backends.rclone_flags,
                    "enabled": self._data.backends.rclone_enabled,
                },
                "syncthing": {
                    "api": self._data.backends.syncthing_api,
                    "api_key": self._data.backends.syncthing_api_key,
                    "exe": self._data.backends.syncthing_exe,
                    "stop_on_exit": self._data.backends.stop_syncthing_on_exit,
                    "restart_on_failure": self._data.backends.restart_syncthing_on_failure,
                },
            },
            "logging": {
                "file": str(self._data.logging.file),
                "level": self._data.logging.level,
            },
        }

    # Fluent builder methods

    def watch(self, *paths: str) -> Config:
        """Add paths to watch for changes."""
        self._check_not_built()
        for path in paths:
            expanded = expand_path(path)
            if expanded not in self._data.hub.watch_paths:
                self._data.hub.watch_paths.append(expanded)
        return self

    def with_backend(self, backend: str) -> Config:
        """Set the default sync backend."""
        self._check_not_built()
        self._data.defaults["backend"] = backend
        return self

    def stop_syncthing_on_exit(self, value: bool) -> Config:
        """Configure whether to stop Syncthing when dgmt exits."""
        self._check_not_built()
        self._data.backends.stop_syncthing_on_exit = value
        return self

    def debounce(self, seconds: int) -> Config:
        """Set the debounce period before triggering sync."""
        self._check_not_built()
        self._data.hub.debounce_seconds = seconds
        return self

    def max_wait(self, seconds: int) -> Config:
        """Set the maximum wait time before forcing sync."""
        self._check_not_built()
        self._data.hub.max_wait_seconds = seconds
        return self

    def health_check(self, interval: int) -> Config:
        """Set the health check interval in seconds."""
        self._check_not_built()
        self._data.hub.health_check_interval = interval
        return self

    def pull_on_startup(self, value: bool) -> Config:
        """Configure whether to pull from remote on startup."""
        self._check_not_built()
        self._data.hub.pull_on_startup = value
        return self

    def log_file(self, path: str) -> Config:
        """Set the log file path."""
        self._check_not_built()
        self._data.logging.file = expand_path(path)
        return self

    def log_level(self, level: str) -> Config:
        """Set the log level."""
        self._check_not_built()
        self._data.logging.level = level.upper()
        return self

    def syncthing_api(self, url: str, api_key: Optional[str] = None) -> Config:
        """Configure Syncthing API settings."""
        self._check_not_built()
        self._data.backends.syncthing_api = url
        if api_key:
            self._data.backends.syncthing_api_key = api_key
        return self

    def syncthing_exe(self, path: str) -> Config:
        """Set the path to the Syncthing executable."""
        self._check_not_built()
        self._data.backends.syncthing_exe = str(expand_path(path))
        return self

    def rclone(self, remote: str, dest: str, enabled: bool = True) -> Config:
        """Configure rclone backend."""
        self._check_not_built()
        self._data.backends.rclone_remote = remote
        self._data.backends.rclone_dest = dest
        self._data.backends.rclone_enabled = enabled
        return self

    def add_spoke(
        self,
        name: str,
        backend: Optional[str] = None,
        remote_path: Optional[str] = None,
        device_id: Optional[str] = None,
        enabled: bool = True,
    ) -> Config:
        """Add a spoke machine configuration."""
        self._check_not_built()
        self._data.spokes[name] = SpokeConfig(
            name=name,
            backend=backend or self._data.defaults.get("backend", "syncthing"),
            remote_path=remote_path,
            device_id=device_id,
            enabled=enabled,
        )
        return self

    def remove_spoke(self, name: str) -> Config:
        """Remove a spoke machine configuration."""
        self._check_not_built()
        self._data.spokes.pop(name, None)
        return self

    def save(self) -> Config:
        """Save configuration to file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump(self._to_dict(), f, indent=2)
        return self

    def build(self) -> ConfigData:
        """Build and return the configuration data."""
        self._mark_built()
        return self._data

    @property
    def data(self) -> ConfigData:
        """Get the configuration data without marking as built."""
        return self._data

    # Convenience methods

    def get_spoke(self, name: str) -> Optional[SpokeConfig]:
        """Get a spoke configuration by name."""
        return self._data.spokes.get(name)

    def get_enabled_spokes(self) -> list[SpokeConfig]:
        """Get all enabled spoke configurations."""
        return [s for s in self._data.spokes.values() if s.enabled]

    def __repr__(self) -> str:
        return f"Config(path={self._config_path}, spokes={len(self._data.spokes)})"


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from file."""
    return Config(config_path)


def init_config(config_path: Optional[Path] = None) -> Config:
    """Create a new configuration with defaults."""
    config = Config(config_path)
    if not config._config_path.exists():
        config.watch("~/Obsidian").save()
    return config
