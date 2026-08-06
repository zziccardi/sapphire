"""Extensible target backend registry for Sapphire code generators (Open/Closed Principle)."""

from typing import Any, Callable, Dict, List, Optional, Type, Union
from src.common.errors import SapphireTranspileError


class TranspilerTarget:
  """Metadata and factory for a registered target code generation backend."""

  def __init__(
      self,
      name: str,
      display_name: str,
      default_extension: str,
      transpiler_cls: Type[Any],
      factory: Optional[Callable[..., Any]] = None,
  ):
    self.name = name
    self.display_name = display_name
    self.default_extension = default_extension
    self.transpiler_cls = transpiler_cls
    self.factory = factory or (lambda **kwargs: transpiler_cls(**kwargs))


class TranspilerRegistry:
  """Registry managing available transpiler backends."""

  _targets: Dict[str, TranspilerTarget] = {}

  @classmethod
  def register(
      cls,
      aliases: Union[str, List[str]],
      display_name: str,
      default_extension: str,
      factory: Optional[Callable[..., Any]] = None,
  ) -> Callable[[Type[Any]], Type[Any]]:
    """Decorator to register a transpiler class for target aliases."""

    def decorator(transpiler_cls: Type[Any]) -> Type[Any]:
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
          f"Unsupported compilation target '{target_name}'. Available targets: {valid}"
      )
    return cls._targets[target_lower]

  @classmethod
  def list_targets(cls) -> List[str]:
    """Returns a list of all registered target alias names."""
    return sorted(list(cls._targets.keys()))
