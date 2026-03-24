"""Canvas .ics feed fetcher with caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import requests

from dgmt.canvas.completion import CompletionStore
from dgmt.canvas.models import Assignment
from dgmt.canvas.parser import parse_ics
from dgmt.core.config import CanvasConfig
from dgmt.utils.paths import ensure_parent_exists, expand_path


class CanvasFetcher:
    """Downloads and caches Canvas assignment data from an .ics feed."""

    def __init__(self, config: Optional[CanvasConfig] = None) -> None:
        if config is None:
            from dgmt.core.config import load_config
            config = load_config().data.canvas
        self._config = config
        self._cache_path = expand_path(config.cache_file)
        self._completion = CompletionStore(config.completion_file)
        self._completion.load()

    def get_ics_url(self) -> Optional[str]:
        """Read the .ics URL from the secrets file."""
        url_path = expand_path(self._config.ics_url_file)
        if not url_path.exists():
            return None
        return url_path.read_text().strip()

    def set_ics_url(self, url: str) -> None:
        """Store the .ics URL in the secrets file."""
        url_path = ensure_parent_exists(self._config.ics_url_file)
        url_path.write_text(url.strip() + "\n")

    def revoke_ics_url(self) -> bool:
        """Remove the stored .ics URL. Returns True if file existed."""
        url_path = expand_path(self._config.ics_url_file)
        if url_path.exists():
            url_path.unlink()
            return True
        return False

    def is_cache_fresh(self) -> bool:
        """Check if the cache file exists and is within the fetch interval."""
        if not self._cache_path.exists():
            return False
        age = time.time() - self._cache_path.stat().st_mtime
        return age < self._config.fetch_interval_seconds

    def get_assignments(self, force_fetch: bool = False) -> list[Assignment]:
        """Get assignments, using cache if fresh.

        1. If cache is fresh and not force_fetch, load from cache
        2. Otherwise fetch from .ics URL, parse, and cache
        3. Merge completion state
        """
        if not force_fetch and self.is_cache_fresh():
            assignments = self._load_cache()
            if assignments is not None:
                self._completion.merge_into(assignments)
                return assignments

        # Fetch fresh data
        url = self.get_ics_url()
        if not url:
            raise RuntimeError(
                "No Canvas .ics URL configured. Run: dgmt canvas auth set"
            )

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        assignments = parse_ics(response.text, self._config)
        self._save_cache(assignments)
        self._completion.merge_into(assignments)
        return assignments

    def _load_cache(self) -> Optional[list[Assignment]]:
        """Load assignments from the cache file."""
        try:
            with open(self._cache_path) as f:
                data = json.load(f)
            return [Assignment.from_dict(d) for d in data]
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    def _save_cache(self, assignments: list[Assignment]) -> None:
        """Save assignments to the cache file."""
        ensure_parent_exists(self._cache_path)
        with open(self._cache_path, "w") as f:
            json.dump([a.to_dict() for a in assignments], f, indent=2)

    @property
    def completion_store(self) -> CompletionStore:
        """Access the completion store for marking assignments."""
        return self._completion
