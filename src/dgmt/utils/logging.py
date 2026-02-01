"""Logging setup utilities."""

import logging
from pathlib import Path
from typing import Optional

from dgmt.utils.paths import ensure_parent_exists


def setup_logging(
    log_file: Optional[Path] = None,
    level: str = "INFO",
    name: str = "dgmt",
) -> logging.Logger:
    """
    Set up logging with both file and console handlers.

    Args:
        log_file: Path to log file. If None, only console logging is enabled.
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if log_file specified)
    if log_file:
        log_path = ensure_parent_exists(log_file)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "dgmt") -> logging.Logger:
    """Get an existing logger or create a basic one."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Set up basic console logging if not configured
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
    return logger
