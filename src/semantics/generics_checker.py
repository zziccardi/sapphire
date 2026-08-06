"""Generics substitution and monomorphization helper module for Sapphire.

Decouples generic AST type parameter substitution and mangling from the
monolithic TypeChecker.
"""

import copy
from typing import Any, Dict, List
from src.parser.ast import ASTNode, BasicTypeNode, TypeNode
from src.semantics.symbol_table import (
    Type,
    OptionalType,
    ArrayType,
    MapType,
    FunctionType,
)


class GenericsChecker:
  """Helper class for generic AST substitutions and type mangling."""

  @staticmethod
  def substitute_ast(node: Any, param_map: Dict[str, TypeNode]) -> Any:
    """Recursively replaces generic parameter identifiers with concrete TypeNodes in an AST snippet."""
    if node is None:
      return None
    if isinstance(node, BasicTypeNode):
      if node.name in param_map:
        return copy.deepcopy(param_map[node.name])
      if node.type_args:
        new_args = [GenericsChecker.substitute_ast(t, param_map) for t in node.type_args]
        new_node = copy.deepcopy(node)
        new_node.type_args = new_args
        return new_node
      return copy.deepcopy(node)
    if isinstance(node, list):
      return [GenericsChecker.substitute_ast(item, param_map) for item in node]
    if isinstance(node, ASTNode):
      new_node = copy.copy(node)
      for k, v in node.__dict__.items():
        if isinstance(v, (ASTNode, list)):
          setattr(new_node, k, GenericsChecker.substitute_ast(v, param_map))
        else:
          setattr(new_node, k, v)
      return new_node
    return copy.deepcopy(node)

  @staticmethod
  def mangle_type_name(type_obj: Type) -> str:
    """Recursively converts a semantic Type into a clean, valid identifier string component."""
    if isinstance(type_obj, OptionalType):
      return f"Opt_{GenericsChecker.mangle_type_name(type_obj.base_type)}"
    elif isinstance(type_obj, ArrayType):
      return f"Arr_{GenericsChecker.mangle_type_name(type_obj.element_type)}"
    elif isinstance(type_obj, MapType):
      return f"Map_{GenericsChecker.mangle_type_name(type_obj.key_type)}_{GenericsChecker.mangle_type_name(type_obj.value_type)}"
    elif isinstance(type_obj, FunctionType):
      p_str = "_".join(GenericsChecker.mangle_type_name(t) for t in type_obj.param_types)
      r_str = "_".join(GenericsChecker.mangle_type_name(t) for t in type_obj.return_types)
      return f"Fn_{p_str}_to_{r_str}"
    else:
      raw = str(type_obj)
      clean = "".join(c if c.isalnum() else "_" for c in raw)
      clean = "_".join(filter(None, clean.split("_")))
      return clean or "type"
