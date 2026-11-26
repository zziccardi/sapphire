"""Member-access and module-path resolution visitors for TypeChecker."""

from typing import TYPE_CHECKING, Any

from sapphire.parser.ast import (
  ASTNode,
  IdentifierNode,
  MemberAccessNode,
  MoveNode,
)
from sapphire.semantics.collection_checker import CollectionChecker
from sapphire.semantics.symbol_table import (
  COROUTINE_METHODS,
  STRING_METHODS,
  ArrayType,
  CoroutineType,
  EnumType,
  FunctionType,
  MapType,
  ModuleSymbol,
  ModuleType,
  NoneType,
  OptionalType,
  PrimitiveType,
  RefType,
  SharedRefType,
  StringType,
  StructSymbol,
  StructType,
  TraitType,
  Type,
  VariableSymbol,
  WeakRefType,
)

_ASSERTION_NAMES = (
  "assert_true",
  "assert_false",
  "assert_eq",
  "assert_ne",
  "assert_almost_eq",
  "assert_none",
  "assert_not_none",
  "expect_true",
  "expect_false",
  "expect_eq",
  "expect_ne",
  "expect_almost_eq",
  "expect_none",
  "expect_not_none",
)


if TYPE_CHECKING:
  from sapphire.semantics.type_checker import TypeChecker as _TypeCheckerBase
else:
  _TypeCheckerBase = object


class MemberAccessVisitorMixin(_TypeCheckerBase):
  """Provides AST visitor and helper methods for member access resolution."""

  def _get_dotted_path(self, expr: Any) -> list[str] | None:
    """Returns the dotted identifier path components of an expression."""
    if isinstance(expr, IdentifierNode):
      return [expr.name]
    if isinstance(expr, MemberAccessNode) and not expr.is_optional:
      recv = self._get_dotted_path(expr.receiver)
      if recv is not None:
        return recv + [expr.member]
    return None

  def _find_imported_module_by_path(self, path: str) -> ModuleSymbol | None:
    """Finds an imported ModuleSymbol by its full import path."""
    root_scope = self.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    for sym in root_scope.symbols.values():
      if isinstance(sym, ModuleSymbol) and sym.module_path == path:
        return sym
    return None

  def _find_imported_modules_with_prefix(
    self, prefix: str
  ) -> list[ModuleSymbol]:
    """Returns all imported ModuleSymbols starting with prefix."""
    root_scope = self.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    res: list[ModuleSymbol] = []
    prefix_dot = prefix + "."
    for sym in root_scope.symbols.values():
      if isinstance(sym, ModuleSymbol) and sym.module_path.startswith(
        prefix_dot
      ):
        res.append(sym)
    return res

  def _diagnose_unaliased_module_access(
    self, node: MemberAccessNode
  ) -> Type | None:
    """Detects unaliased dotted module paths (e.g. `std.os.args`) and suggests
    alias.
    """
    # Check receiver first (e.g. `std.os.args` where `std.os` is the module).
    dotted_recv = self._get_dotted_path(node.receiver)
    if dotted_recv and len(dotted_recv) >= 2:
      root_ident = dotted_recv[0]
      if (
        self.symbol_table.lookup(root_ident) is None
        and self.symbol_table.lookup_type(root_ident) is None
      ):
        for i in range(len(dotted_recv), 1, -1):
          sub_path = ".".join(dotted_recv[:i])
          mod_sym = self._find_imported_module_by_path(sub_path)
          if mod_sym:
            remaining = dotted_recv[i:]
            call_suffix = "()" if getattr(node, "is_call", False) else ""
            if remaining:
              sug = (
                f"{mod_sym.name}.{'.'.join(remaining)}.{node.member}"
                f"{call_suffix}"
              )
            else:
              sug = f"{mod_sym.name}.{node.member}{call_suffix}"
            self.error(
              f"Undefined identifier '{root_ident}'. Module "
              f"'{mod_sym.module_path}' was imported as '{mod_sym.name}'. "
              f"Did you mean '{sug}'?",
              node=node.receiver,
            )
            node.receiver.has_diagnosed_module_import = True
            node.receiver.diagnosed_module_type = ModuleType(
              mod_sym.module_path
            )
            if not remaining:
              exp_sym = mod_sym.lookup_export(node.member)
              if exp_sym:
                return (
                  exp_sym.symbol_type
                  if hasattr(exp_sym, "symbol_type")
                  else exp_sym
                )
            return PrimitiveType("none")

    # Check the full node path (e.g. `std.os` used as a module prefix).
    dotted_self = self._get_dotted_path(node)
    if dotted_self and len(dotted_self) >= 2:
      root_ident = dotted_self[0]
      if (
        self.symbol_table.lookup(root_ident) is None
        and self.symbol_table.lookup_type(root_ident) is None
      ):
        for i in range(len(dotted_self), 1, -1):
          sub_path = ".".join(dotted_self[:i])
          mod_sym = self._find_imported_module_by_path(sub_path)
          if mod_sym:
            remaining = dotted_self[i:]
            sug = (
              f"{mod_sym.name}.{'.'.join(remaining)}"
              if remaining
              else mod_sym.name
            )
            self.error(
              f"Undefined identifier '{root_ident}'. Module "
              f"'{mod_sym.module_path}' was imported as '{mod_sym.name}'. "
              f"Did you mean '{sug}'?",
              node=node,
            )
            node.has_diagnosed_module_import = True
            node.diagnosed_module_type = ModuleType(mod_sym.module_path)
            return ModuleType(mod_sym.module_path)

    return None

  def _widen_array_size_on_mutation(
    self, node: MemberAccessNode, receiver_type: ArrayType
  ) -> None:
    """Clears inferred static size when a dynamic array is mutated."""
    if (
      node.member in ("push", "pop", "insert", "remove", "clear")
      and not receiver_type.is_fixed_size
      and receiver_type.size is not None
      and isinstance(node.receiver, IdentifierNode)
    ):
      sym = self.symbol_table.lookup(node.receiver.name)
      if isinstance(sym, VariableSymbol) and isinstance(
        sym.symbol_type, ArrayType
      ):
        sym.symbol_type = ArrayType(
          sym.symbol_type.element_type, size=None, is_fixed_size=False
        )

  def _resolve_builtin_receiver_member(
    self, node: MemberAccessNode, receiver_type: Type
  ) -> Type | None:
    """Resolves member access on builtin, module, enum, and trait types."""
    if isinstance(receiver_type, StringType):
      if node.member == "from":
        node.is_string_from = True
        return FunctionType([StringType()], StringType())
      method = STRING_METHODS.get(node.member)
      if method:
        node.is_string_method = True
        return method
      self.error(f"String has no method '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, ArrayType):
      self._widen_array_size_on_mutation(node, receiver_type)
      return CollectionChecker.resolve_array_member(self, node, receiver_type)

    if isinstance(receiver_type, MapType):
      return CollectionChecker.resolve_map_member(self, node, receiver_type)

    if isinstance(receiver_type, CoroutineType):
      if node.member in COROUTINE_METHODS:
        node.is_coroutine_method = True
        node.coroutine_method = node.member
        node.coroutine_receiver_type = receiver_type
        y_type = receiver_type.yield_type
        if node.member == "step":
          ret_t = (
            NoneType() if isinstance(y_type, NoneType) else OptionalType(y_type)
          )
          return FunctionType(
            [receiver_type], ret_t, param_names=["self"], has_self=True
          )
        if node.member == "is_done":
          return FunctionType(
            [receiver_type],
            PrimitiveType("bool"),
            param_names=["self"],
            has_self=True,
          )
        if node.member == "reset":
          return FunctionType(
            [receiver_type],
            PrimitiveType("none"),
            param_names=["self"],
            has_self=True,
          )
      self.error(f"Coroutine has no method '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, ModuleType):
      if isinstance(node.receiver, IdentifierNode):
        mod_sym = self.symbol_table.lookup(node.receiver.name)
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(node.member)
          if exp_sym:
            return (
              exp_sym.symbol_type
              if hasattr(exp_sym, "symbol_type")
              else exp_sym
            )
          mod_path = mod_sym.module_path or ""
          if node.member in _ASSERTION_NAMES and (
            mod_path == "std.testing"
            or mod_path == "testing"
            or mod_path.endswith(".testing")
          ):
            fn_t = FunctionType([], PrimitiveType("none"))
            fn_t.is_testing_assertion = True
            return fn_t
          if mod_sym.exports or getattr(mod_sym, "file_path", None):
            self.error(
              f"Module '{mod_sym.name}' has no exported member "
              f"'{node.member}'.",
              node=node,
            )
      return PrimitiveType("none")

    if isinstance(receiver_type, EnumType):
      if node.member == "from":
        node.is_enum_from = True
        node.enum_type = receiver_type
        return FunctionType([StringType()], OptionalType(receiver_type))
      if node.member in receiver_type.variants:
        return receiver_type
      self.error(f"Enum '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, TraitType):
      method = receiver_type.methods.get(node.member)
      if method:
        if getattr(method, "extern_name", None):
          node.target_name = method.extern_name
        is_static = getattr(method.ast_decl, "modifier", None) == "static"
        node.is_static_method = is_static
        node.is_instance_method = not is_static
        return method
      if node.member in _ASSERTION_NAMES and (
        receiver_type is self.symbol_table.testcase_trait
        or receiver_type.name == "TestCase"
      ):
        node.is_instance_method = True
        fn_t = FunctionType([], PrimitiveType("none"))
        fn_t.is_testing_assertion = True
        return fn_t
      self.error(f"Trait '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if (
      node.member in _ASSERTION_NAMES
      and isinstance(receiver_type, StructType)
      and (
        receiver_type.name == "TestContext"
        or receiver_type.implements_trait(
          self.symbol_table.testcase_trait, self.symbol_table
        )
      )
    ):
      node.is_instance_method = True
      fn_t = FunctionType([], PrimitiveType("none"))
      fn_t.is_testing_assertion = True
      return fn_t

    return None

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> Type:
    """Resolves field, method, enum variant, and module member accesses."""
    if isinstance(node.receiver, MoveNode):
      self.error(
        f"Cannot access member '{node.member}' on moved variable "
        f"'{node.receiver.name}'.",
        node=node,
      )
      return PrimitiveType("none")

    if getattr(node, "has_diagnosed_module_import", False):
      return getattr(node, "diagnosed_module_type", PrimitiveType("none"))

    diagnosed_type = self._diagnose_unaliased_module_access(node)
    if diagnosed_type is not None:
      return diagnosed_type

    receiver_type = self.visit(node.receiver)

    # Validate optional chaining against OptionalType receivers.
    if node.is_optional:
      if not isinstance(receiver_type, OptionalType):
        self.error("Optional chaining '?.' requires an optional receiver.")
        return PrimitiveType("none")
      receiver_type = receiver_type.base_type
    elif isinstance(receiver_type, OptionalType):
      self.error(
        "Must use optional chaining '?.' to access properties on an optional "
        "receiver."
      )
      return PrimitiveType("none")

    builtin_res = self._resolve_builtin_receiver_member(node, receiver_type)
    if builtin_res is not None:
      return builtin_res

    # Handle smart-pointer methods (.share, .downgrade, .upgrade) and
    # auto-deref.
    if isinstance(receiver_type, SharedRefType):
      if node.member == "share":
        node.is_shared_ref_share = True
        node.is_instance_method = True
        return FunctionType(
          [receiver_type], receiver_type, param_names=["self"], has_self=True
        )
      if node.member == "downgrade":
        node.is_shared_ref_downgrade = True
        node.is_instance_method = True
        return FunctionType(
          [receiver_type],
          WeakRefType(receiver_type.inner_type),
          param_names=["self"],
          has_self=True,
        )
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, RefType):
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, WeakRefType):
      if node.member == "upgrade":
        node.is_weak_ref_upgrade = True
        node.is_instance_method = True
        return FunctionType(
          [receiver_type],
          OptionalType(SharedRefType(receiver_type.inner_type)),
          param_names=["self"],
          has_self=True,
        )
      self.error(
        f"WeakRef has no member '{node.member}'; call '.upgrade()' to "
        "access the underlying value.",
        node=node,
      )
      return PrimitiveType("none")

    # Re-check builtin receivers (String, Array, Map, Coroutine, Enum, Trait)
    # after auto-deref from Ref<T>/SharedRef<T>.
    if getattr(node, "is_auto_deref", False):
      builtin_res = self._resolve_builtin_receiver_member(node, receiver_type)
      if builtin_res is not None:
        return builtin_res

    if not isinstance(receiver_type, StructType):
      self.error("Member access receiver is not a struct or trait.")
      return PrimitiveType("none")

    if node.member == "__proto__":
      if not receiver_type.is_prototype:
        self.error(
          f"Cannot access '__proto__' on standard struct "
          f"'{receiver_type.name}'; '__proto__' is only available on "
          "'proto' instances.",
          node=node,
        )
        return PrimitiveType("none")
      return OptionalType(receiver_type)

    if node.member == "__del__":
      self.error("Destructor '__del__' cannot be manually invoked.")
      return PrimitiveType("none")

    if self._is_struct_type_receiver(node.receiver):
      return self._resolve_struct_type_member_access(node, receiver_type)

    field = receiver_type.fields.get(node.member)
    if field:
      # Flatten T?? -> T? when optional chaining accesses an optional field.
      if node.is_optional:
        if isinstance(field.field_type, OptionalType):
          return field.field_type
        return OptionalType(field.field_type)
      return field.field_type

    static_field = receiver_type.get_static_field(
      node.member, self.symbol_table
    )
    if static_field is not None:
      self.error(
        f"Cannot access static field '{node.member}' on an instance of "
        f"'{receiver_type.name}'; access "
        f"'{receiver_type.name}.{node.member}' instead.",
        node=node,
      )
      return static_field.field_type

    method = receiver_type.get_method(node.member, self.symbol_table)
    if method:
      if method.modifier == "static":
        self.error(
          f"Cannot call static method '{node.member}' on an instance of "
          f"'{receiver_type.name}'; call "
          f"'{receiver_type.name}.{node.member}(...)' instead.",
          node=node,
        )
        return method.method_type
      node.is_static_method = False
      node.is_instance_method = True
      return method.method_type

    self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
    return PrimitiveType("none")

  def _is_struct_type_receiver(self, expr: ASTNode) -> bool:
    """Returns True if *expr* refers to a struct type rather than a value."""
    if isinstance(expr, IdentifierNode):
      sym = self.symbol_table.lookup(expr.name)
      if sym is not None:
        return isinstance(sym, StructSymbol)
      return isinstance(self.symbol_table.lookup_type(expr.name), StructType)
    if (
      isinstance(expr, MemberAccessNode)
      and isinstance(expr.receiver, IdentifierNode)
      and not expr.is_optional
    ):
      mod_sym = self.symbol_table.lookup(expr.receiver.name)
      if isinstance(mod_sym, ModuleSymbol):
        exp_sym = mod_sym.lookup_export(expr.member)
        return isinstance(exp_sym, (StructSymbol, StructType))
    return False

  def _resolve_struct_type_member_access(
    self, node: MemberAccessNode, receiver_type: StructType
  ) -> Type:
    """Resolves `StructType.member` for static fields, static methods, or
    ancestor dispatch.
    """
    if node.member == "__init__":
      self.error(
        f"Cannot call '__init__' directly on '{receiver_type.name}'; "
        f"use ': {receiver_type.name}(...)' in a subclass '__init__' or "
        f"'{receiver_type.name}(...)' to construct.",
        node=node,
      )
      return PrimitiveType("none")

    static_field = receiver_type.get_static_field(
      node.member, self.symbol_table
    )
    if static_field is not None:
      return static_field.field_type

    if node.member in receiver_type.fields:
      self.error(
        f"Cannot access instance field '{node.member}' on type "
        f"'{receiver_type.name}'.",
        node=node,
      )
      return PrimitiveType("none")

    method = receiver_type.get_method(node.member, self.symbol_table)
    if not method:
      self.error(
        f"Struct '{receiver_type.name}' has no member '{node.member}'."
      )
      return PrimitiveType("none")

    if method.modifier == "static":
      node.is_static_method = True
      node.is_instance_method = False
      return method.method_type

    if not getattr(node, "is_call", False):
      self.error(
        f"Cannot reference unbound instance method "
        f"'{receiver_type.name}.{node.member}' as a value; call it with "
        "'(self, ...)' inside a subclass method.",
        node=node,
      )
      return PrimitiveType("none")

    self_sym = self.symbol_table.lookup("self")
    if not self.current_struct or not isinstance(self_sym, VariableSymbol):
      self.error(
        f"Qualified method call '{receiver_type.name}.{node.member}(self, "
        "...)' "
        "is only allowed inside an instance method of a subclass.",
        node=node,
      )
      return PrimitiveType("none")

    if not self.current_struct.has_ancestor(receiver_type, self.symbol_table):
      if self.current_struct == receiver_type:
        self.error(
          f"Cannot use qualified ancestor dispatch "
          f"'{receiver_type.name}.{node.member}(self, ...)' on own struct "
          f"'{self.current_struct.name}'; use 'self.{node.member}(...)' "
          "instead.",
          node=node,
        )
      else:
        self.error(
          f"Struct '{receiver_type.name}' is not an ancestor of "
          f"'{self.current_struct.name}'.",
          node=node,
        )
      return PrimitiveType("none")

    if method.modifier == "var" and not self_sym.is_mutable:
      self.error(
        f"Cannot call mutating ancestor method "
        f"'{receiver_type.name}.{node.member}' from immutable method; "
        "declare the enclosing method as 'var func'.",
        node=node,
      )
      return PrimitiveType("none")

    node.is_qualified_ancestor_call = True
    node.qualified_ancestor_type = receiver_type
    node.qualified_ancestor_method = method
    node.is_static_method = True
    node.is_instance_method = False

    mt = method.method_type
    self_mut = method.modifier == "var"
    fn_t = FunctionType(
      param_types=[self.current_struct] + list(mt.param_types),
      return_type=mt.return_type,
      param_names=["self"] + list(mt.param_names),
      param_mutabilities=[self_mut] + list(mt.param_mutabilities),
      has_self=False,
      num_defaults=mt.num_defaults,
      param_defaults=[None] + list(getattr(mt, "param_defaults", [])),
      ast_decl=mt.ast_decl,
    )
    # Explicit `self` is passed as argument 0, so disable implicit-self slicing.
    fn_t.has_self = False
    return fn_t
