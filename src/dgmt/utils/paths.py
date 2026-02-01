"""Path expansion and validation utilities."""

from pathlib import Path
from typing import Union


def expand_path(path: Union[str, Path]) -> Path:
    """Expand ~ and environment variables in a path."""
    return Path(path).expanduser().resolve()


def expand_paths(paths: list[Union[str, Path]]) -> list[Path]:
    """Expand ~ and environment variables in a list of paths."""
    return [expand_path(p) for p in paths]


def ensure_parent_exists(path: Union[str, Path]) -> Path:
    """Ensure the parent directory of a path exists, creating it if necessary."""
    path = expand_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_config_dir() -> Path:
    """Get the dgmt configuration directory (~/.dgmt)."""
    config_dir = Path("~/.dgmt").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """Get the path to the config file."""
    return get_config_dir() / "config.json"


def get_log_file() -> Path:
    """Get the default log file path."""
    return get_config_dir() / "dgmt.log"
