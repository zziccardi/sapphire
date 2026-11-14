"""Type representations and built-in method tables for Sapphire.

This module defines the Type class hierarchy and built-in method
signatures used by the semantic analyzer and LSP.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union


# ==========================================
# Type Representations
# ==========================================

class Type:
  """Base class for all types in the Sapphire type system."""

  def is_compatible(self, other: "Type") -> bool:
    """Returns True if self is compatible with other (e.g. for assignment)."""
    if isinstance(self, NoneType) and isinstance(other, OptionalType):
      return True
    if isinstance(self, OptionalType) and isinstance(other, OptionalType):
      return self.base_type.is_compatible(other.base_type)
    if isinstance(other, OptionalType) and not isinstance(self, OptionalType):
      # Safe assignment of T to T?
      return self.is_compatible(other.base_type)
    if (
        isinstance(self, PrimitiveType)
        and self.name == "int"
        and isinstance(other, PrimitiveType)
        and other.name == "float"
    ):
      return True
    if isinstance(other, TraitType) and isinstance(self, StructType):
      return self.implements_trait(other)
    return self == other

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, Type):
      return False
    return type(self) is type(other)

  def is_move_only_type(
      self,
      symbol_table: Optional[Any] = None,
      _seen: Optional[Set[str]] = None,
  ) -> bool:
    """Returns True if values of this type have Move-Only ownership."""
    if isinstance(self, (RefType, ArenaType, CoroutineType)):
      return True
    if isinstance(self, OptionalType):
      return self.base_type.is_move_only_type(symbol_table, _seen)
    if isinstance(self, ArrayType):
      return self.element_type.is_move_only_type(symbol_table, _seen)
    if isinstance(self, MapType):
      return (
          self.key_type.is_move_only_type(symbol_table, _seen)
          or self.value_type.is_move_only_type(symbol_table, _seen)
      )
    if isinstance(self, StructType):
      if self.is_prototype:
        return False
      seen = set() if _seen is None else set(_seen)
      if self.name in seen:
        return False
      seen.add(self.name)
      if self.has_any_destructor(symbol_table):
        return True
      for field in self.fields.values():
        if field.field_type.is_move_only_type(symbol_table, seen):
          return True
    return False

  def is_shared_ref_lvalue_type(self) -> bool:
    """Returns True if this type is SharedRef<T> or Optional<SharedRef<T>>."""
    if isinstance(self, SharedRefType):
      return True
    if isinstance(self, OptionalType):
      return self.base_type.is_shared_ref_lvalue_type()
    return False


class StringType(Type):
  """Represents the built-in String reference type."""

  def __init__(self):
    self.name = "String"

  def __eq__(self, other: object) -> bool:
    return isinstance(other, StringType)

  def __repr__(self) -> str:
    return "String"


class PrimitiveType(Type):
  """Represents primitive scalar value types like 'int', 'float', 'bool'."""

  def __init__(self, name: str):
    self.name = name

  def __eq__(self, other: object) -> bool:
    if isinstance(other, NoneType) and self.name in ("none", "void"):
      return True
    if not isinstance(other, PrimitiveType):
      return False
    return self.name.lower() == other.name.lower()

  def __repr__(self) -> str:
    return self.name


class OptionalType(Type):
  """Represents an optional wrapper type (e.g., 'T?')."""

  def __init__(self, base_type: Type):
    self.base_type = base_type

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, OptionalType):
      return False
    return self.base_type == other.base_type

  def __repr__(self) -> str:
    return f"{self.base_type}?"


class MultiReturnType(Type):
  """Represents a multi-return type tuple (e.g. (float, float))."""

  def __init__(self, types: List[Type]):
    self.types = types

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, MultiReturnType):
      return False
    return self.types == other.types

  def __repr__(self) -> str:
    return f"({', '.join(str(t) for t in self.types)})"


class FunctionType(Type):
  """Represents a function type signature.

  Examples:
  * (int, int) -> float
  * (int, int) -> (float, float)
  """

  def __init__(
      self,
      param_types: List[Type],
      return_type: Any,
      param_mutabilities: Optional[List[bool]] = None,
      param_names: Optional[List[str]] = None,
      has_self: bool = False,
      extern_name: Optional[str] = None,
      num_defaults: int = 0,
      param_defaults: Optional[List[Any]] = None,
      ast_decl: Optional[Any] = None,
  ):
    self.param_types = param_types
    if isinstance(return_type, list):
      if len(return_type) == 0:
        self.return_type = PrimitiveType("none")
      elif len(return_type) == 1:
        self.return_type = return_type[0]
      else:
        self.return_type = MultiReturnType(return_type)
    else:
      self.return_type = return_type
    self.param_mutabilities = param_mutabilities or [False] * len(param_types)
    self.param_names = param_names or [f"p{i}" for i in range(len(param_types))]
    self.has_self = (
        has_self or (bool(self.param_names) and self.param_names[0] == "self"))
    self.extern_name = extern_name
    self.num_defaults = num_defaults
    self.param_defaults = param_defaults or [None] * len(param_types)
    self.ast_decl = ast_decl

  @property
  def return_types(self) -> List[Type]:
    if isinstance(self.return_type, MultiReturnType):
      return self.return_type.types
    elif (isinstance(self.return_type, PrimitiveType) and
          self.return_type.name == "none"):
      return []
    else:
      return [self.return_type]

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    if not isinstance(other, FunctionType):
      return False
    if len(self.param_types) != len(other.param_types):
      return False
    for p1, p2 in zip(self.param_types, other.param_types):
      if not p2.is_compatible(p1):
        return False
    ret1 = self.return_type
    ret2 = other.return_type
    is_void1 = isinstance(ret1, (NoneType, InferredType)) or (isinstance(ret1, PrimitiveType) and ret1.name in ("none", "void"))
    is_void2 = isinstance(ret2, (NoneType, InferredType)) or (isinstance(ret2, PrimitiveType) and ret2.name in ("none", "void"))
    if is_void1 and is_void2:
      return True
    return ret1.is_compatible(ret2)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, FunctionType):
      return False
    ret1 = self.return_type
    ret2 = other.return_type
    is_void1 = isinstance(ret1, (NoneType, InferredType)) or (isinstance(ret1, PrimitiveType) and ret1.name in ("none", "void"))
    is_void2 = isinstance(ret2, (NoneType, InferredType)) or (isinstance(ret2, PrimitiveType) and ret2.name in ("none", "void"))
    ret_eq = (is_void1 and is_void2) or (ret1 == ret2)
    return (
        self.param_types == other.param_types
        and ret_eq
        and self.param_mutabilities == other.param_mutabilities
    )

  def __repr__(self) -> str:
    params_reprs = []
    for idx, t in enumerate(self.param_types):
      if idx < len(self.param_mutabilities) and self.param_mutabilities[idx]:
        params_reprs.append(f"var {repr(t)}")
      else:
        params_reprs.append(repr(t))
    params_str = ", ".join(params_reprs)
    if isinstance(self.return_type, PrimitiveType) and self.return_type.name in ("none", "void"):
      ret_str = "()"
    elif isinstance(self.return_type, NoneType):
      ret_str = "()"
    else:
      ret_str = str(self.return_type)
    return f"({params_str}) -> {ret_str}"


class StructField:
  """Represents a field in a struct."""

  def __init__(self, name: str, field_type: Type, is_mutable: bool,
               has_default: bool = False, has_explicit_default: bool = False, comments: str = ""):
    self.name = name
    self.field_type = field_type
    self.is_mutable = is_mutable
    self.has_default = has_default
    self.has_explicit_default = has_explicit_default
    self.comments = comments


class StructMethod:
  """Represents a method in a struct impl block."""

  def __init__(self, name: str, method_type: FunctionType,
               modifier: Optional[str]):
    self.name = name
    self.method_type = method_type
    self.modifier = modifier  # 'static', 'var', or None


class GenericTypeParameter(Type):
  """Represents a generic type parameter (e.g., 'T', 'K', 'V')."""

  def __init__(self, name: str):
    self.name = name

  def is_compatible(self, other: "Type") -> bool:
    return self == other or isinstance(other, GenericTypeParameter)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, GenericTypeParameter):
      return False
    return self.name == other.name

  def __repr__(self) -> str:
    return self.name


class StructType(Type):
  """Represents a user-defined struct type."""

  def __init__(self, name: str,
               parent_names: Optional[Union[str, List[str]]] = None,
               is_prototype: bool = False, comments: Optional[str] = None,
               type_params: Optional[List[str]] = None,
               ast_decl: Optional[Any] = None,
               parent_name: Optional[str] = None,
               defining_module: Optional[str] = None,
               is_imported: bool = False):
    self.name = name
    if parent_names is None:
      self.parent_names = [parent_name] if parent_name else []
    elif isinstance(parent_names, str):
      self.parent_names = [parent_names]
    else:
      self.parent_names = list(parent_names)
    self.fields: Dict[str, StructField] = {}
    self.methods: Dict[str, StructMethod] = {}
    self.implemented_traits: Set[str] = set()
    self.is_cloned = False  # Set during clone-tracking analysis
    self.is_prototype = is_prototype
    self.comments = comments or ""
    self.type_params = type_params or []
    self.ast_decl = ast_decl
    self.defining_module = defining_module
    self.is_imported = is_imported

  @property
  def parent_name(self) -> Optional[str]:
    return self.parent_names[0] if self.parent_names else None

  @property
  def has_destructor(self) -> bool:
    return "__del__" in self.methods

  def has_any_destructor(
      self,
      symbol_table: Optional[Any] = None,
      _seen: Optional[Set[str]] = None,
  ) -> bool:
    """Returns True if this struct or any ancestor struct defines '__del__'."""
    if "__del__" in self.methods:
      return True
    if self.parent_names and symbol_table:
      seen = set() if _seen is None else set(_seen)
      if self.name in seen:
        return False
      seen.add(self.name)
      for p_name in self.parent_names:
        parent = symbol_table.lookup_type(p_name)
        if isinstance(parent, StructType) and parent.has_any_destructor(symbol_table, seen):
          return True
    return False

  @parent_name.setter
  def parent_name(self, value: Optional[str]) -> None:
    if value is None:
      self.parent_names = []
    else:
      self.parent_names = [value]

  def get_method(
      self, name: str,
      symbol_table: Optional[Any] = None) -> Optional["StructMethod"]:
    """Look up a method on this struct, falling back to parent structs if symbol_table is provided."""
    if name in self.methods:
      return self.methods[name]
    if self.parent_names and symbol_table:
      for p_name in self.parent_names:
        parent = symbol_table.lookup_type(p_name)
        if isinstance(parent, StructType):
          res = parent.get_method(name, symbol_table)
          if res:
            return res
    return None

  def implements_trait(self, trait: "TraitType",
                       symbol_table: Optional[Any] = None) -> bool:
    """Returns True if this struct nominally implements the given trait (directly or via parent structs)."""
    if trait.name in self.implemented_traits:
      return True
    if self.parent_names and symbol_table:
      for p_name in self.parent_names:
        parent = symbol_table.lookup_type(p_name)
        if isinstance(parent, StructType) and parent.implements_trait(trait, symbol_table):
          return True
    return False

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, StructType):
      return False
    # Struct types are compared by name (nominal typing)
    return self.name == other.name

  def __repr__(self) -> str:
    if self.type_params:
      return f"{self.name}<{', '.join(self.type_params)}>"
    return self.name


class TraitType(Type):
  """Represents a user-defined trait type."""

  def __init__(self, name: str, comments: Optional[str] = None,
               type_params: Optional[List[str]] = None,
               ast_decl: Optional[Any] = None):
    self.name = name
    self.methods: Dict[str, FunctionType] = {}
    self.comments = comments or ""
    self.type_params = type_params or []
    self.ast_decl = ast_decl

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, TraitType):
      return False
    return self.name == other.name

  def __repr__(self) -> str:
    if self.type_params:
      return f"trait {self.name}<{', '.join(self.type_params)}>"
    return f"trait {self.name}"


class EnumType(Type):
  """Represents a custom enum type definition."""

  def __init__(
      self,
      name: str,
      variants: Optional[Dict[str, Union[int, str]]] = None,
      comments: Optional[str] = None,
  ):
    self.name = name
    self.variants: Dict[str, Union[int, str]] = variants or {}
    self.comments = comments or ""

  @property
  def value_type(self) -> str:
    """Returns 'String' if any variant is a string, otherwise 'int'."""
    if any(isinstance(v, str) for v in self.variants.values()):
      return "String"
    return "int"

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, EnumType):
      return False
    return self.name == other.name

  def __repr__(self) -> str:
    return self.name


class ArenaType(Type):
  """Represents the built-in Arena type."""

  @property
  def has_destructor(self) -> bool:
    return True

  def __repr__(self) -> str:
    return "Arena"


class RangeType(Type):
  """Represents the built-in Range type returned by range()."""

  def __eq__(self, other: object) -> bool:
    return isinstance(other, RangeType)

  def __repr__(self) -> str:
    return "Range"


class NoneType(Type):
  """Represents the special type of the 'none' literal."""

  def __eq__(self, other: object) -> bool:
    if isinstance(other, NoneType):
      return True
    if isinstance(other, PrimitiveType) and other.name in ("none", "void"):
      return True
    return False

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, NoneType):
      return True
    if isinstance(other, PrimitiveType) and other.name in ("none", "void"):
      return True
    return super().is_compatible(other)

  def __repr__(self) -> str:
    return "none"


class InferredType(Type):
  """Placeholder type for a lambda parameter whose type is being inferred.

  Used during the speculative body scan in ``visit_LambdaNode`` when neither
  an explicit annotation nor an enclosing ``expected_type`` is available.
  ``is_compatible`` returns ``True`` for all types so that no false arithmetic
  or comparison errors are emitted while the real type is being discovered.
  Once inference completes the placeholder is replaced with the resolved
  ``PrimitiveType`` before the symbol table entry is finalised.
  """

  def is_compatible(self, other: "Type") -> bool:
    return True

  def __repr__(self) -> str:
    return "<inferred>"


class ArrayType(Type):
  """Represents an array type (e.g. '[int]' or '[int; 3]')."""

  def __init__(self, element_type: Type, size: Optional[int] = None, is_fixed_size: Optional[bool] = None):
    self.element_type = element_type
    self.size = size
    self.is_fixed_size = (size is not None) if is_fixed_size is None else is_fixed_size

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, ArrayType):
      if (isinstance(self.element_type, NoneType) or
          isinstance(other.element_type, NoneType)):
        return True
      if other.is_fixed_size:
        if not self.is_fixed_size or self.size != other.size:
          return False
      return self.element_type.is_compatible(other.element_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, ArrayType):
      return False
    return self.element_type == other.element_type and self.size == other.size and self.is_fixed_size == other.is_fixed_size

  def __repr__(self) -> str:
    if self.is_fixed_size and self.size is not None:
      return f"[{self.element_type}; {self.size}]"
    return f"[{self.element_type}]"


class MapType(Type):
  """Represents a map type (e.g. '[key_type: value_type]')."""

  def __init__(self, key_type: Type, value_type: Type):
    self.key_type = key_type
    self.value_type = value_type

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, MapType):
      key_ok = (
          isinstance(self.key_type, NoneType)
          or isinstance(other.key_type, NoneType)
          or self.key_type.is_compatible(other.key_type)
      )
      val_ok = (
          isinstance(self.value_type, NoneType)
          or isinstance(other.value_type, NoneType)
          or self.value_type.is_compatible(other.value_type)
      )
      return key_ok and val_ok
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, MapType):
      return False
    return (self.key_type == other.key_type and
            self.value_type == other.value_type)

  def __repr__(self) -> str:
    return f"[{self.key_type}: {self.value_type}]"


class CoroutineType(Type):
  """Represents a Coroutine type (e.g. 'Coroutine<T>' or 'Coroutine<void>')."""

  def __init__(self, yield_type: Optional[Type] = None):
    self.yield_type = yield_type if yield_type is not None else NoneType()

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, CoroutineType):
      if (isinstance(self.yield_type, NoneType) or
          isinstance(other.yield_type, NoneType)):
        return True
      return self.yield_type.is_compatible(other.yield_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, CoroutineType):
      return False
    return self.yield_type == other.yield_type

  def __repr__(self) -> str:
    if isinstance(self.yield_type, NoneType):
      return "Coroutine<void>"
    return f"Coroutine<{self.yield_type}>"


class RefType(Type):
  """Represents unique heap ownership 'Ref<T>'."""

  def __init__(self, inner_type: Type):
    self.inner_type = inner_type
    self.is_move_only = True

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, RefType):
      return self.inner_type.is_compatible(other.inner_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, RefType):
      return False
    return self.inner_type == other.inner_type

  def __repr__(self) -> str:
    return f"Ref<{self.inner_type}>"


class SharedRefType(Type):
  """Represents reference-counted heap ownership 'SharedRef<T>'."""

  def __init__(self, inner_type: Type):
    self.inner_type = inner_type

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, SharedRefType):
      return self.inner_type.is_compatible(other.inner_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, SharedRefType):
      return False
    return self.inner_type == other.inner_type

  def __repr__(self) -> str:
    return f"SharedRef<{self.inner_type}>"


class WeakRefType(Type):
  """Represents non-owning weak reference 'WeakRef<T>'."""

  def __init__(self, inner_type: Type):
    self.inner_type = inner_type

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, WeakRefType):
      return self.inner_type.is_compatible(other.inner_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, WeakRefType):
      return False
    return self.inner_type == other.inner_type

  def __repr__(self) -> str:
    return f"WeakRef<{self.inner_type}>"


COROUTINE_METHODS: Set[str] = {
    "step",
    "is_done",
    "reset",
}


STRING_METHODS: Dict[str, FunctionType] = {
    "size": FunctionType(
        [StringType()],
        PrimitiveType("int"),
        param_names=["self"],
        has_self=True,
    ),
    "empty": FunctionType(
        [StringType()],
        PrimitiveType("bool"),
        param_names=["self"],
        has_self=True,
    ),
    "lower": FunctionType(
        [StringType()],
        StringType(),
        param_names=["self"],
        has_self=True,
    ),
    "upper": FunctionType(
        [StringType()],
        StringType(),
        param_names=["self"],
        has_self=True,
    ),
    "strip": FunctionType(
        [StringType(), OptionalType(StringType())],
        StringType(),
        param_names=["self", "chars"],
        has_self=True,
        num_defaults=1,
    ),
    "split": FunctionType(
        [StringType(), OptionalType(StringType())],
        ArrayType(StringType()),
        param_names=["self", "sep"],
        has_self=True,
        num_defaults=1,
    ),
    "contains": FunctionType(
        [StringType(), StringType()],
        PrimitiveType("bool"),
        param_names=["self", "sub"],
        has_self=True,
    ),
    "find": FunctionType(
        [
            StringType(),
            StringType(),
            PrimitiveType("int"),
            PrimitiveType("bool"),
        ],
        OptionalType(PrimitiveType("int")),
        param_names=(["self", "start", "reverse"] if False
                     else ["self", "sub", "start", "reverse"]),
        has_self=True,
        num_defaults=2,
    ),
    "to_int": FunctionType(
        [StringType(), PrimitiveType("int")],
        OptionalType(PrimitiveType("int")),
        param_names=["self", "radix"],
        has_self=True,
        num_defaults=1,
    ),
    "to_float": FunctionType(
        [StringType()],
        OptionalType(PrimitiveType("float")),
        param_names=["self"],
        has_self=True,
    ),
    "to_bool": FunctionType(
        [StringType()],
        OptionalType(PrimitiveType("bool")),
        param_names=["self"],
        has_self=True,
    ),
}


ARRAY_METHODS: Dict[str, bool] = {
    "size": True,
    "empty": True,
    "contains": True,
    "get": True,
    "map": True,
    "filter": True,
    "reduce": True,
    "reverse": True,
    "sort": True,
    "join": True,
    "push": True,
    "pop": True,
    "insert": True,
    "remove": True,
    "clear": True,
    "swap": True,
}


MAP_METHODS: Dict[str, bool] = {
    "size": True,
    "empty": True,
    "contains": True,
    "get": True,
    "keys": True,
    "values": True,
    "insert": True,
    "remove": True,
    "clear": True,
}

