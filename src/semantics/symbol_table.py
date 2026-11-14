"""Symbol table and scope representations for Sapphire's semantic analyzer.

This module defines Symbol subclasses, Scope, and SymbolTable, and
re-exports type definitions from src.semantics.types for compatibility.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.semantics.types import *  # noqa: F401, F403

# ==========================================
# Symbol Representations
# ==========================================

class Symbol:
  """Base class for all symbols in the symbol table."""

  def __init__(self, name: str, symbol_type: Type):
    self.name = name
    self.symbol_type = symbol_type
    self.scope_defined: Optional["Scope"] = None
    self.decl_order: int = 0


class VariableSymbol(Symbol):
  """Represents variables and parameters."""

  def __init__(
      self, name: str, symbol_type: Type, is_mutable: bool,
      is_parameter: bool = False):
    super().__init__(name, symbol_type)
    self.is_mutable = is_mutable
    self.is_parameter = is_parameter
    self.arena_dependency: Optional[str] = None
    self.arena_generation: int = 0
    self.arena_dep_records: List[Tuple[str, int]] = []
    self.is_moved: bool = False
    self.proto_ancestors: Set[str] = set()
    self.stack_borrow_symbols: Set[str] = set()


class FunctionSymbol(Symbol):
  """Represents functions and methods."""

  def __init__(self, name: str, signature: FunctionType,
               type_params: Optional[List[str]] = None,
               ast_decl: Optional[Any] = None):
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
    self._next_decl_order: int = 1
    self.frozen_lvalues: List[Tuple[str, List[str], str]] = []

  def define(self, name: str, symbol: Symbol) -> None:
    """Defines a symbol in the current scope."""
    existing = self.symbols.get(name)
    if existing is not None and getattr(existing, "decl_order", 0) > 0:
      symbol.decl_order = existing.decl_order
    else:
      symbol.decl_order = self._next_decl_order
      self._next_decl_order += 1
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
    if "." in name:
      parts = name.split(".")
      mod_sym = self.lookup(parts[0])
      if isinstance(mod_sym, ModuleSymbol):
        exp = mod_sym.lookup_export(parts[1])
        if isinstance(exp, Type):
          return exp
        elif hasattr(exp, "symbol_type") and isinstance(exp.symbol_type, Type):
          return exp.symbol_type
    if name in self.types:
      return self.types[name]
    if name in self.symbols:
      sym = self.symbols[name]
      if hasattr(sym, "symbol_type") and isinstance(sym.symbol_type, Type):
        return sym.symbol_type
    if self.parent:
      return self.parent.lookup_type(name)
    return None

  def lookup_current(self, name: str) -> Optional[Symbol]:
    """Looks up a symbol only in the current scope level."""
    return self.symbols.get(name)


class SymbolTable:
  """Manages scope stack; provides symbol/type declarations & resolution."""

  def __init__(self):
    self.current_scope = Scope()
    # Initialize global types
    self.current_scope.define_type("int", PrimitiveType("int"))
    self.current_scope.define_type("float", PrimitiveType("float"))
    self.current_scope.define_type("bool", PrimitiveType("bool"))
    self.current_scope.define_type("String", StringType())
    self.current_scope.define_type("none", NoneType())
    self.current_scope.define_type("void", NoneType())
    self.current_scope.define_type("Coroutine", CoroutineType(NoneType()))
    self.current_scope.define_type("Ref", RefType(NoneType()))
    self.current_scope.define_type("SharedRef", SharedRefType(NoneType()))
    self.current_scope.define_type("WeakRef", WeakRefType(NoneType()))
    self.current_scope.define(
        "Ref",
        FunctionSymbol("Ref", FunctionType([NoneType()], RefType(NoneType()))),
    )
    self.current_scope.define(
        "SharedRef",
        FunctionSymbol(
            "SharedRef",
            FunctionType([NoneType()], SharedRefType(NoneType())),
        ),
    )
    arena_t = ArenaType()
    self.current_scope.define_type("Arena", arena_t)
    self.current_scope.define(
        "Arena",
        FunctionSymbol("Arena", FunctionType([], arena_t)))
    self.current_scope.define(
        "print",
        FunctionSymbol("print", FunctionType([StringType()],
                                             NoneType())))
    range_t = RangeType()
    self.current_scope.define_type("Range", range_t)
    self.current_scope.define(
        "range",
        FunctionSymbol(
            "range",
            FunctionType(
                param_types=[PrimitiveType("int"), PrimitiveType("int"),
                             PrimitiveType("int")],
                return_type=range_t,
                param_names=["start", "stop", "step"],
                num_defaults=2,
            ),
        ),
    )
    # Register TestCase trait for std.testing framework
    testcase_trait = TraitType("TestCase")
    # Register default assertion and expectation method signatures
    assertion_names = [
        "assert_true", "assert_false", "assert_eq", "assert_ne",
        "assert_almost_eq", "assert_none", "assert_not_none",
        "expect_true", "expect_false", "expect_eq", "expect_ne",
        "expect_almost_eq", "expect_none", "expect_not_none"
    ]
    for name in assertion_names:
      fn_t = FunctionType([NoneType(), NoneType(), StringType(), StringType()], NoneType(), num_defaults=4)
      fn_t.is_testing_assertion = True
      testcase_trait.methods[name] = fn_t
    self.testcase_trait = testcase_trait

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
