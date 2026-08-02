"""Symbol table and type representation for Sapphire's semantic analyzer.

This module defines classes for representing Sapphire types, symbols, scopes,
and the symbol table used to resolve and validate identifiers during type-checking.
"""

from typing import Dict, List, Optional, Any


# ==========================================
# Type Representations
# ==========================================

class Type:
  """Base class for all types in the Sapphire type system."""

  def is_compatible(self, other: "Type") -> bool:
    """Returns True if self is compatible with other (e.g. for assignment)."""
    if isinstance(self, NoneType) and isinstance(other, OptionalType):
      return True
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
    if isinstance(self, EnumType) and isinstance(other, PrimitiveType) and self.value_type.lower() == other.name.lower():
      return True
    return self == other

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, Type):
      return False
    return type(self) is type(other)


class PrimitiveType(Type):
  """Represents primitive types like 'int', 'float', 'bool', 'string'."""

  def __init__(self, name: str):
    self.name = name

  def __eq__(self, other: object) -> bool:
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
  """Represents a function type signature (e.g., '(int, int) -> float' or '(int, int) -> (float, float)')."""

  def __init__(
      self,
      param_types: List[Type],
      return_type: Any,
      param_mutabilities: Optional[List[bool]] = None,
      param_names: Optional[List[str]] = None,
      has_self: bool = False,
      extern_name: Optional[str] = None,
      num_defaults: int = 0,
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
    self.has_self = has_self or (bool(self.param_names) and self.param_names[0] == "self")
    self.extern_name = extern_name
    self.num_defaults = num_defaults

  @property
  def return_types(self) -> List[Type]:
    if isinstance(self.return_type, MultiReturnType):
      return self.return_type.types
    elif isinstance(self.return_type, PrimitiveType) and self.return_type.name == "none":
      return []
    else:
      return [self.return_type]

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, FunctionType):
      return False
    return (
        self.param_types == other.param_types
        and self.return_type == other.return_type
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
    return f"({params_str}) -> {self.return_type}"


class StructField:
  """Represents a field in a struct."""

  def __init__(self, name: str, field_type: Type, is_mutable: bool, has_default: bool = False, comments: str = ""):
    self.name = name
    self.field_type = field_type
    self.is_mutable = is_mutable
    self.has_default = has_default
    self.comments = comments


class StructMethod:
  """Represents a method in a struct impl block."""

  def __init__(self, name: str, method_type: FunctionType, modifier: Optional[str]):
    self.name = name
    self.method_type = method_type
    self.modifier = modifier  # 'static', 'const', or None


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

  def __init__(self, name: str, parent_name: Optional[str] = None, is_prototype: bool = False, comments: Optional[str] = None, type_params: Optional[List[str]] = None, ast_decl: Optional[Any] = None):
    self.name = name
    self.parent_name = parent_name
    self.fields: Dict[str, StructField] = {}
    self.methods: Dict[str, StructMethod] = {}
    self.is_cloned = False  # Set during clone-tracking analysis
    self.is_prototype = is_prototype
    self.comments = comments or ""
    self.type_params = type_params or []
    self.ast_decl = ast_decl

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

  def __init__(self, name: str, comments: Optional[str] = None, type_params: Optional[List[str]] = None, ast_decl: Optional[Any] = None):
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

  def __repr__(self) -> str:
    return "Arena"


class NoneType(Type):
  """Represents the special type of the 'none' literal."""

  def __repr__(self) -> str:
    return "none"


class ArrayType(Type):
  """Represents an array type (e.g. '[int]' or '[int; 3]')."""

  def __init__(self, element_type: Type, size: Optional[int] = None):
    self.element_type = element_type
    self.size = size

  def is_compatible(self, other: "Type") -> bool:
    if isinstance(other, ArrayType):
      if isinstance(self.element_type, NoneType) or isinstance(other.element_type, NoneType):
        return True
      return self.element_type.is_compatible(other.element_type)
    if isinstance(other, OptionalType):
      return self.is_compatible(other.base_type)
    return super().is_compatible(other)

  def __eq__(self, other: object) -> bool:
    if not isinstance(other, ArrayType):
      return False
    return self.element_type == other.element_type and self.size == other.size

  def __repr__(self) -> str:
    if self.size is not None:
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
    return self.key_type == other.key_type and self.value_type == other.value_type

  def __repr__(self) -> str:
    return f"[{self.key_type}: {self.value_type}]"


STRING_METHODS: Dict[str, FunctionType] = {
    "size": FunctionType(
        [PrimitiveType("String")],
        PrimitiveType("int"),
        param_names=["self"],
        has_self=True,
    ),
    "empty": FunctionType(
        [PrimitiveType("String")],
        PrimitiveType("bool"),
        param_names=["self"],
        has_self=True,
    ),
    "lower": FunctionType(
        [PrimitiveType("String")],
        PrimitiveType("String"),
        param_names=["self"],
        has_self=True,
    ),
    "upper": FunctionType(
        [PrimitiveType("String")],
        PrimitiveType("String"),
        param_names=["self"],
        has_self=True,
    ),
    "strip": FunctionType(
        [PrimitiveType("String"), OptionalType(PrimitiveType("String"))],
        PrimitiveType("String"),
        param_names=["self", "chars"],
        has_self=True,
        num_defaults=1,
    ),
    "split": FunctionType(
        [PrimitiveType("String"), OptionalType(PrimitiveType("String"))],
        ArrayType(PrimitiveType("String")),
        param_names=["self", "sep"],
        has_self=True,
        num_defaults=1,
    ),
    "contains": FunctionType(
        [PrimitiveType("String"), PrimitiveType("String")],
        PrimitiveType("bool"),
        param_names=["self", "sub"],
        has_self=True,
    ),
    "find": FunctionType(
        [
            PrimitiveType("String"),
            PrimitiveType("String"),
            PrimitiveType("int"),
            PrimitiveType("bool"),
        ],
        OptionalType(PrimitiveType("int")),
        param_names=["self", "start", "reverse"] if False else ["self", "sub", "start", "reverse"],
        has_self=True,
        num_defaults=2,
    ),
    "to_int": FunctionType(
        [PrimitiveType("String"), PrimitiveType("int")],
        OptionalType(PrimitiveType("int")),
        param_names=["self", "radix"],
        has_self=True,
        num_defaults=1,
    ),
    "to_float": FunctionType(
        [PrimitiveType("String")],
        OptionalType(PrimitiveType("float")),
        param_names=["self"],
        has_self=True,
    ),
    "to_bool": FunctionType(
        [PrimitiveType("String")],
        OptionalType(PrimitiveType("bool")),
        param_names=["self"],
        has_self=True,
    ),
}


# ==========================================
# Symbol Representations
# ==========================================

class Symbol:
  """Base class for all symbols in the symbol table."""

  def __init__(self, name: str, symbol_type: Type):
    self.name = name
    self.symbol_type = symbol_type
    self.scope_defined: Optional["Scope"] = None


class VariableSymbol(Symbol):
  """Represents variables and parameters."""

  def __init__(
      self, name: str, symbol_type: Type, is_mutable: bool, is_parameter: bool = False
  ):
    super().__init__(name, symbol_type)
    self.is_mutable = is_mutable
    self.is_parameter = is_parameter
    self.arena_dependency: Optional[str] = None


class FunctionSymbol(Symbol):
  """Represents functions and methods."""

  def __init__(self, name: str, signature: FunctionType, type_params: Optional[List[str]] = None, ast_decl: Optional[Any] = None):
    super().__init__(name, signature)
    self.type_params = type_params or []
    self.ast_decl = ast_decl


class StructSymbol(Symbol):
  """Represents a struct definition symbol."""

  def __init__(self, name: str, struct_type: StructType):
    super().__init__(name, struct_type)


class TraitSymbol(Symbol):
  """Represents a trait definition symbol."""

  def __init__(self, name: str, trait_type: TraitType):
    super().__init__(name, trait_type)


class EnumSymbol(Symbol):
  """Represents an enum definition symbol."""

  def __init__(self, name: str, enum_type: EnumType):
    super().__init__(name, enum_type)


class ModuleType(Type):
  """Represents a module type for imported modules."""

  def __init__(self, path: str):
    self.path = path

  def __repr__(self) -> str:
    return f"module({self.path})"


class ModuleSymbol(Symbol):
  """Represents an imported module symbol (e.g. 'graphics' or 'enums')."""

  def __init__(self, name: str, module_path: str, exports: Optional[Dict[str, Symbol]] = None):
    super().__init__(name, ModuleType(module_path))
    self.module_path = module_path
    self.exports: Dict[str, Symbol] = exports or {}

  def lookup_export(self, symbol_name: str) -> Optional[Symbol]:
    return self.exports.get(symbol_name)


# ==========================================
# Scope & Symbol Table
# ==========================================

class Scope:
  """Represents a single lexical scope in the program."""

  def __init__(self, parent: Optional["Scope"] = None):
    self.symbols: Dict[str, Symbol] = {}
    self.types: Dict[str, Type] = {}
    self.parent = parent

  def define(self, name: str, symbol: Symbol) -> None:
    """Defines a symbol in the current scope."""
    symbol.scope_defined = self
    self.symbols[name] = symbol

  def define_type(self, name: str, type_obj: Type) -> None:
    """Registers a type name in the current scope."""
    self.types[name] = type_obj

  def lookup(self, name: str) -> Optional[Symbol]:
    """Looks up a symbol recursively up the scope chain."""
    if name in self.symbols:
      return self.symbols[name]
    if self.parent:
      return self.parent.lookup(name)
    return None

  def lookup_type(self, name: str) -> Optional[Type]:
    """Looks up a type name recursively up the scope chain."""
    if name in self.types:
      return self.types[name]
    if self.parent:
      return self.parent.lookup_type(name)
    return None

  def lookup_current(self, name: str) -> Optional[Symbol]:
    """Looks up a symbol only in the current scope level."""
    return self.symbols.get(name)


class SymbolTable:
  """Manages the scope stack and provides symbol/type declarations and resolution."""

  def __init__(self):
    self.current_scope = Scope()
    # Initialize global types
    self.current_scope.define_type("int", PrimitiveType("int"))
    self.current_scope.define_type("float", PrimitiveType("float"))
    self.current_scope.define_type("bool", PrimitiveType("bool"))
    self.current_scope.define_type("String", PrimitiveType("String"))
    self.current_scope.define_type("none", NoneType())
    self.current_scope.define_type("void", NoneType())
    arena_t = ArenaType()
    self.current_scope.define_type("Arena", arena_t)
    self.current_scope.define("Arena", FunctionSymbol("Arena", FunctionType([], arena_t)))
    self.current_scope.define("print", FunctionSymbol("print", FunctionType([PrimitiveType("String")], NoneType())))

  def enter_scope(self) -> None:
    """Enters a new nested scope."""
    self.current_scope = Scope(parent=self.current_scope)

  def exit_scope(self) -> None:
    """Exits the current scope and returns to its parent scope."""
    if not self.current_scope.parent:
      raise RuntimeError("Cannot exit the root global scope.")
    self.current_scope = self.current_scope.parent

  def define(self, name: str, symbol: Symbol) -> None:
    """Defines a symbol in the current active scope."""
    self.current_scope.define(name, symbol)

  def define_type(self, name: str, type_obj: Type) -> None:
    """Registers a type in the current active scope."""
    self.current_scope.define_type(name, type_obj)

  def lookup(self, name: str) -> Optional[Symbol]:
    """Resolves an identifier to a Symbol across all active scopes."""
    return self.current_scope.lookup(name)

  def lookup_type(self, name: str) -> Optional[Type]:
    """Resolves a type name to a Type object across all active scopes."""
    return self.current_scope.lookup_type(name)

  def lookup_current_scope(self, name: str) -> Optional[Symbol]:
    """Looks up an identifier only in the current scope level."""
    return self.current_scope.lookup_current(name)
