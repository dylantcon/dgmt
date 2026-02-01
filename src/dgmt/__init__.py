"""
dgmt - Dylan's General Management Tool

A hub-and-spoke sync orchestrator supporting multiple backends
(SFTP, Syncthing, rclone) with remote machine management via SSH.
"""

__version__ = "2.0.0"
__author__ = "Dylan"

from dgmt.core.config import Config
from dgmt.core.daemon import Daemon

__all__ = ["Config", "Daemon", "__version__"]
