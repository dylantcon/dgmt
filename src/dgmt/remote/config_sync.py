"""Push portable dgmt config (color rules, calendar settings) to spokes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dgmt.remote.ssh import SSHConnection
from dgmt.utils.logging import get_logger

logger = get_logger("dgmt.config_sync")

# Config keys that are sensitive or hub-specific and should never be pushed
_STRIP_KEYS = {"backends", "hub"}

# Directories considered "dotfile" paths (config-only, no user data)
_DOTFILE_PREFIXES = (".config", ".local", ".dgmt")


def _sanitize_config(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive/hub-specific keys from config before pushing.

    Keeps: calendar (color_rules, default_view), logging.level, defaults.
    Removes: backends (API keys, exe paths), hub (watch_paths, debounce).
    """
    return {k: v for k, v in config_dict.items() if k not in _STRIP_KEYS}


def _spoke_has_non_dotfile_paths(hub_watch_paths: list[str | Path]) -> bool:
    """Return True if any hub watch_path is outside a dotfile directory.

    This is used as a heuristic: if the hub watches real data dirs like
    ~/Obsidian, the spoke likely has its own data dirs and only needs
    config sync.  If all paths are under dotfile dirs, the spoke is
    probably a config mirror and doesn't need a separate push.
    """
    for p in hub_watch_paths:
        parts = Path(p).expanduser().parts
        # Check if any component starts with "."
        if not any(part.startswith(".") for part in parts[1:]):  # skip root
            return True
    return False


def push_config_to_spoke(host: str, config_dict: dict[str, Any]) -> bool:
    """Push sanitized config to a single spoke via SSH.

    Creates ~/.dgmt/ on the spoke if it doesn't exist and writes
    config.json with the sanitized (no secrets) config data.
    """
    ssh = SSHConnection(host)

    if not ssh.test_connection(timeout=10):
        logger.warning(f"Cannot connect to {host}, skipping config push")
        return False

    sanitized = _sanitize_config(config_dict)
    config_json = json.dumps(sanitized, indent=2)

    if not ssh.mkdir("~/.dgmt"):
        logger.error(f"Failed to create ~/.dgmt on {host}")
        return False

    if not ssh.write_file("~/.dgmt/config.json", config_json):
        logger.error(f"Failed to write config to {host}")
        return False

    logger.info(f"Pushed config to {host}")
    return True


def push_config_to_all_spokes(config: Any) -> dict[str, bool]:
    """Push sanitized config to all enabled spokes.

    Args:
        config: A Config instance (from dgmt.core.config).

    Returns:
        Dict mapping spoke name -> success bool.
    """
    config_dict = config._to_dict()
    results: dict[str, bool] = {}

    for spoke in config.get_enabled_spokes():
        try:
            results[spoke.name] = push_config_to_spoke(spoke.name, config_dict)
        except Exception as e:
            logger.error(f"Config push failed for {spoke.name}: {e}")
            results[spoke.name] = False

    return results
