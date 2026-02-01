"""Fluent interface base classes for method chaining."""

from typing import TypeVar, Generic

T = TypeVar("T")


class FluentBuilder(Generic[T]):
    """
    Base class for fluent builders that return self for method chaining.

    Example usage:
        class MyBuilder(FluentBuilder["MyBuilder"]):
            def __init__(self):
                super().__init__()
                self._name = ""

            def name(self, value: str) -> "MyBuilder":
                self._name = value
                return self

            def build(self) -> MyObject:
                return MyObject(self._name)
    """

    def __init__(self) -> None:
        self._built = False

    def _check_not_built(self) -> None:
        """Raise an error if build() has already been called."""
        if self._built:
            raise RuntimeError("Builder has already been used to build an object")

    def _mark_built(self) -> None:
        """Mark this builder as having been used."""
        self._built = True


class FluentChain:
    """
    Mixin for classes that support method chaining (returning self).

    Example:
        class MyClass(FluentChain):
            def set_value(self, v: int) -> "MyClass":
                self._value = v
                return self
    """
    pass
