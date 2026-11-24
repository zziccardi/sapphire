"""Extensible target backend registry for Sapphire code generators (Open/Closed
Principle).
"""

import contextlib
from collections.abc import Callable, Iterator
from typing import Any

from sapphire.common.errors import SapphireTranspileError


class TranspilerTarget:
  """Metadata and factory for a registered target code generation backend."""

  def __init__(
    self,
    name: str,
    display_name: str,
    default_extension: str,
    transpiler_cls: type[Any],
    factory: Callable[..., Any] | None = None,
  ):
    self.name = name
    self.display_name = display_name
    self.default_extension = default_extension
    self.transpiler_cls = transpiler_cls
    self.factory = factory or (lambda **kwargs: transpiler_cls(**kwargs))


class ScopedTranspilerRegistry:
  """Instantiable, isolated transpiler target registry for DI and tests."""

  def __init__(
    self, targets: dict[str, TranspilerTarget] | None = None
  ) -> None:
    self._targets: dict[str, TranspilerTarget] = (
      dict(targets) if targets is not None else {}
    )

  def register(
    self,
    aliases: str | list[str],
    display_name: str,
    default_extension: str,
    factory: Callable[..., Any] | None = None,
  ) -> Callable[[type[Any]], type[Any]]:
    """Decorator to register a transpiler class on this registry instance."""

    def decorator(transpiler_cls: type[Any]) -> type[Any]:
      alias_list = [aliases] if isinstance(aliases, str) else aliases
      target_obj = TranspilerTarget(
        name=alias_list[0],
        display_name=display_name,
        default_extension=default_extension,
        transpiler_cls=transpiler_cls,
        factory=factory,
      )
      for alias in alias_list:
        self._targets[alias.lower()] = target_obj
      return transpiler_cls

    return decorator

  def get(self, target_name: str) -> TranspilerTarget:
    """Retrieves target backend metadata for target_name."""
    target_lower = target_name.lower()
    if target_lower not in self._targets:
      valid = ", ".join(sorted(set(self._targets.keys())))
      raise SapphireTranspileError(
        f"Unsupported compilation target '{target_name}'. Available targets: "
        f"{valid}"
      )
    return self._targets[target_lower]

  def list_targets(self) -> list[str]:
    """Returns a list of all registered target alias names."""
    return sorted(list(self._targets.keys()))


class TranspilerRegistry:
  """Default process-wide registry managing available transpiler backends."""

  _targets: dict[str, TranspilerTarget] = {}

  @classmethod
  def register(
    cls,
    aliases: str | list[str],
    display_name: str,
    default_extension: str,
    factory: Callable[..., Any] | None = None,
  ) -> Callable[[type[Any]], type[Any]]:
    """Decorator to register a transpiler class for target aliases."""

    def decorator(transpiler_cls: type[Any]) -> type[Any]:
      alias_list = [aliases] if isinstance(aliases, str) else aliases
      target_obj = TranspilerTarget(
        name=alias_list[0],
        display_name=display_name,
        default_extension=default_extension,
        transpiler_cls=transpiler_cls,
        factory=factory,
      )
      for alias in alias_list:
        cls._targets[alias.lower()] = target_obj
      return transpiler_cls

    return decorator

  @classmethod
  def get(cls, target_name: str) -> TranspilerTarget:
    """Retrieves target backend metadata for target_name."""
    target_lower = target_name.lower()
    if target_lower not in cls._targets:
      valid = ", ".join(sorted(set(cls._targets.keys())))
      raise SapphireTranspileError(
        f"Unsupported compilation target '{target_name}'. Available targets: "
        f"{valid}"
      )
    return cls._targets[target_lower]

  @classmethod
  def list_targets(cls) -> list[str]:
    """Returns a list of all registered target alias names."""
    return sorted(list(cls._targets.keys()))

  @classmethod
  def create_isolated(
    cls, *, copy_defaults: bool = False
  ) -> ScopedTranspilerRegistry:
    """Creates an isolated registry instance without mutating global state."""
    return ScopedTranspilerRegistry(
      cls._targets if copy_defaults else None
    )

  @classmethod
  @contextlib.contextmanager
  def scoped(
    cls, *, clear: bool = False
  ) -> Iterator[type["TranspilerRegistry"]]:
    """Temporarily isolates registrations on the global registry."""
    snapshot = dict(cls._targets)
    if clear:
      cls._targets = {}
    else:
      cls._targets = dict(cls._targets)
    try:
      yield cls
    finally:
      cls._targets = snapshot
