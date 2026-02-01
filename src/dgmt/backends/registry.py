"""Backend registry and factory functions."""

from __future__ import annotations

from typing import Any, Callable, Optional, Type

from dgmt.backends.base import Backend


class BackendRegistry:
    """
    Registry for sync backends.

    Allows registering and retrieving backend implementations by name.
    """

    _backends: dict[str, Type[Backend]] = {}
    _factories: dict[str, Callable[..., Backend]] = {}

    @classmethod
    def register(cls, name: str, backend_class: Type[Backend]) -> None:
        """Register a backend class by name."""
        cls._backends[name.lower()] = backend_class

    @classmethod
    def register_factory(cls, name: str, factory: Callable[..., Backend]) -> None:
        """Register a factory function for creating backends."""
        cls._factories[name.lower()] = factory

    @classmethod
    def get(cls, name: str, **kwargs: Any) -> Backend:
        """
        Get a backend instance by name.

        Args:
            name: Backend name (e.g., 'sftp', 'syncthing', 'rclone').
            **kwargs: Arguments passed to the backend constructor.

        Returns:
            Backend instance.

        Raises:
            ValueError: If backend name is not registered.
        """
        name = name.lower()

        if name in cls._factories:
            return cls._factories[name](**kwargs)

        if name in cls._backends:
            return cls._backends[name](**kwargs)

        raise ValueError(
            f"Unknown backend: {name}. "
            f"Available: {', '.join(cls.list_backends())}"
        )

    @classmethod
    def list_backends(cls) -> list[str]:
        """List all registered backend names."""
        names = set(cls._backends.keys()) | set(cls._factories.keys())
        return sorted(names)

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if a backend is registered."""
        name = name.lower()
        return name in cls._backends or name in cls._factories


def _register_default_backends() -> None:
    """Register the built-in backends."""
    from dgmt.backends.sftp import SftpBackend, sftp
    from dgmt.backends.syncthing import SyncthingBackend, syncthing
    from dgmt.backends.rclone import RcloneBackend, rclone

    BackendRegistry.register("sftp", SftpBackend)
    BackendRegistry.register("syncthing", SyncthingBackend)
    BackendRegistry.register("rclone", RcloneBackend)

    # Register convenience factories
    BackendRegistry.register_factory("sftp", sftp)
    BackendRegistry.register_factory("syncthing", syncthing)
    BackendRegistry.register_factory("rclone", rclone)


# Auto-register defaults on import
_register_default_backends()


def get_backend(name: str, **kwargs: Any) -> Backend:
    """
    Get a backend instance by name.

    Convenience function wrapping BackendRegistry.get().

    Args:
        name: Backend name (e.g., 'sftp', 'syncthing', 'rclone').
        **kwargs: Arguments passed to the backend constructor.

    Returns:
        Backend instance.
    """
    return BackendRegistry.get(name, **kwargs)


def list_backends() -> list[str]:
    """List all available backend names."""
    return BackendRegistry.list_backends()
