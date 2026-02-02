"""Debounced file system watcher."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)
from watchdog.observers import Observer

from dgmt.utils.logging import get_logger


@dataclass
class ChangeSet:
    """Accumulated file changes during debounce period."""

    created: set[str] = field(default_factory=set)
    modified: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)
    renamed: dict[str, str] = field(default_factory=dict)  # old_path -> new_path

    def clear(self) -> None:
        """Clear all tracked changes."""
        self.created.clear()
        self.modified.clear()
        self.deleted.clear()
        self.renamed.clear()

    def is_empty(self) -> bool:
        """Check if there are any tracked changes."""
        return not (self.created or self.modified or self.deleted or self.renamed)


class DebouncedHandler(FileSystemEventHandler):
    """
    Watches for file changes and triggers callback after a quiet period.
    Prevents rapid-fire syncs when many files change at once.
    """

    # Default patterns to ignore
    DEFAULT_IGNORE = {".git", ".obsidian", "__pycache__", ".sync", ".stfolder", ".stversions"}

    def __init__(
        self,
        callback: Callable[[ChangeSet], None],
        debounce_seconds: float = 30.0,
        max_wait_seconds: float = 300.0,
        ignore_patterns: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize the debounced handler.

        Args:
            callback: Function to call when sync should be triggered.
                      Receives a ChangeSet with accumulated changes.
            debounce_seconds: Wait this long after last change before syncing.
            max_wait_seconds: Force sync after this long even if changes continue.
            ignore_patterns: Set of directory/file name patterns to ignore.
        """
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.max_wait_seconds = max_wait_seconds
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE
        self.logger = get_logger("dgmt.watcher")

        self._last_event: Optional[datetime] = None
        self._first_event: Optional[datetime] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()  # RLock allows reentrant acquisition (needed for max_wait path)
        self._changes = ChangeSet()

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored."""
        parts = Path(path).parts
        for part in parts:
            if part in self.ignore_patterns:
                return True
            if part.startswith(".") and part not in {".", ".."}:
                # Ignore hidden files/directories
                return True
        return False

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event."""
        try:
            if event.is_directory:
                return
            if self._should_ignore(event.src_path):
                return

            with self._lock:
                now = datetime.now()
                self._last_event = now

                if self._first_event is None:
                    self._first_event = now

                # Track the specific change type
                self._track_event(event)

                # Cancel existing timer
                if self._timer:
                    self._timer.cancel()

                # Check if we've exceeded max wait
                elapsed = (now - self._first_event).total_seconds()
                if elapsed >= self.max_wait_seconds:
                    self.logger.info("Max wait exceeded, forcing sync")
                    self._trigger_callback()
                else:
                    # Schedule new debounced callback
                    self._timer = threading.Timer(
                        self.debounce_seconds,
                        self._trigger_callback
                    )
                    self._timer.daemon = True
                    self._timer.start()
        except Exception as e:
            self.logger.error(f"Error handling file event: {e}", exc_info=True)

    def _track_event(self, event: FileSystemEvent) -> None:
        """Track the specific type of file system event."""
        src = event.src_path

        if isinstance(event, FileMovedEvent):
            dest = event.dest_path
            self.logger.debug(f"Rename detected: {src} -> {dest}")
            # Track as rename
            self._changes.renamed[src] = dest
            # If the source was previously created in this batch, update it
            if src in self._changes.created:
                self._changes.created.discard(src)
                self._changes.created.add(dest)
            # Remove from deleted if dest was there
            self._changes.deleted.discard(dest)

        elif isinstance(event, FileCreatedEvent):
            self.logger.debug(f"Create detected: {src}")
            self._changes.created.add(src)
            # If it was deleted earlier in this batch, it's now modified
            if src in self._changes.deleted:
                self._changes.deleted.discard(src)
                self._changes.modified.add(src)

        elif isinstance(event, FileDeletedEvent):
            self.logger.debug(f"Delete detected: {src}")
            # If it was created in this batch, just remove the create
            if src in self._changes.created:
                self._changes.created.discard(src)
            else:
                self._changes.deleted.add(src)
            self._changes.modified.discard(src)

        elif isinstance(event, FileModifiedEvent):
            self.logger.debug(f"Modify detected: {src}")
            # Only track if not already tracked as created
            if src not in self._changes.created:
                self._changes.modified.add(src)

    def _trigger_callback(self) -> None:
        """Trigger the sync callback with accumulated changes."""
        with self._lock:
            self._first_event = None
            self._last_event = None
            self._timer = None
            # Take a snapshot of changes and clear
            changes = ChangeSet(
                created=self._changes.created.copy(),
                modified=self._changes.modified.copy(),
                deleted=self._changes.deleted.copy(),
                renamed=self._changes.renamed.copy(),
            )
            self._changes.clear()

        self.logger.info(
            f"Quiet period reached, triggering sync "
            f"(+{len(changes.created)} ~{len(changes.modified)} "
            f"-{len(changes.deleted)} >{len(changes.renamed)})"
        )
        try:
            self.callback(changes)
        except Exception as e:
            self.logger.error(f"Callback error: {e}")

    def cancel(self) -> None:
        """Cancel any pending timer."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None


class DebouncedWatcher:
    """
    High-level file watcher with debouncing support.

    Example:
        def on_change(changes: ChangeSet):
            print(f"Files changed: {changes}")

        watcher = DebouncedWatcher(on_change, debounce_seconds=30)
        watcher.watch("~/Documents")
        watcher.watch("~/Notes")
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(
        self,
        callback: Callable[[ChangeSet], None],
        debounce_seconds: float = 30.0,
        max_wait_seconds: float = 300.0,
        ignore_patterns: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize the watcher.

        Args:
            callback: Function to call when changes are detected.
                      Receives a ChangeSet with accumulated changes.
            debounce_seconds: Wait this long after last change.
            max_wait_seconds: Force callback after this long.
            ignore_patterns: Patterns to ignore.
        """
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.max_wait_seconds = max_wait_seconds
        self.ignore_patterns = ignore_patterns

        self._observer = Observer()
        self._handler = DebouncedHandler(
            callback=callback,
            debounce_seconds=debounce_seconds,
            max_wait_seconds=max_wait_seconds,
            ignore_patterns=ignore_patterns,
        )
        self._watch_paths: list[Path] = []
        self._running = False
        self.logger = get_logger("dgmt.watcher")

    def watch(self, path: str | Path) -> DebouncedWatcher:
        """
        Add a path to watch (fluent interface).

        Args:
            path: Path to watch for changes.

        Returns:
            self for method chaining.
        """
        path = Path(path).expanduser().resolve()
        if path.exists():
            self._watch_paths.append(path)
            if self._running:
                self._observer.schedule(self._handler, str(path), recursive=True)
                self.logger.info(f"Now watching: {path}")
        else:
            self.logger.warning(f"Path does not exist: {path}")
        return self

    def watch_all(self, paths: list[str | Path]) -> DebouncedWatcher:
        """
        Add multiple paths to watch.

        Args:
            paths: List of paths to watch.

        Returns:
            self for method chaining.
        """
        for path in paths:
            self.watch(path)
        return self

    def start(self) -> DebouncedWatcher:
        """
        Start watching for file changes.

        Returns:
            self for method chaining.
        """
        if self._running:
            return self

        for path in self._watch_paths:
            self._observer.schedule(self._handler, str(path), recursive=True)
            self.logger.info(f"Watching: {path}")

        self._observer.start()
        self._running = True
        self.logger.info("File watcher started")
        return self

    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running:
            return

        self._handler.cancel()
        self._observer.stop()
        self._observer.join(timeout=5)
        self._running = False
        self.logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running

    @property
    def watched_paths(self) -> list[Path]:
        """Get list of paths being watched."""
        return self._watch_paths.copy()

    def __enter__(self) -> DebouncedWatcher:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
