"""Call, argument, aliasing, and member-access visitors for TypeChecker."""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import (
    SymbolTable,
    Type,
    PrimitiveType,
    StringType,
    OptionalType,
    FunctionType,
    MultiReturnType,
    StructMethod,
    StructType,
    TraitType,
    EnumType,
    NoneType,
    InferredType,
    ArrayType,
    MapType,
    ArenaType,
    RangeType,
    ModuleType,
    GenericTypeParameter,
    VariableSymbol,
    FunctionSymbol,
    EnumSymbol,
    ModuleSymbol,
    CoroutineType,
    RefType,
    SharedRefType,
    WeakRefType,
    COROUTINE_METHODS,
    STRING_METHODS,
)
from src.cli.diagnostics import format_diagnostic
from src.common.errors import SemanticError
from src.semantics.arena_checker import ArenaChecker
from src.semantics.collection_checker import CollectionChecker
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.generics_checker import GenericsChecker
from src.semantics.semantic_context import SemanticContext
from src.semantics.struct_layout_pass import StructLayoutPass


class CallVisitorMixin:
  """Provides AST visitor methods for calls, arguments, and member access."""

  def _get_lvalue_path(self, node: ASTNode) -> Optional[tuple[str, List[str]]]:
    """Resolves an AST node to its root variable name and field path if it is an lvalue."""
    return ArenaChecker.get_lvalue_path(self.symbol_table, node)

  def _is_reference_type(self, type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    return ArenaChecker.is_reference_type(type_obj)

  def _check_aliasing(self, node: CallNode, signature: FunctionType, is_constructor: bool) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    ArenaChecker.check_aliasing(self, node, signature, is_constructor)

  def _get_dotted_path(self, expr: Any) -> Optional[List[str]]:
    """Returns the dotted identifier path components of an expression."""
    if isinstance(expr, IdentifierNode):
      return [expr.name]
    if isinstance(expr, MemberAccessNode) and not expr.is_optional:
      recv = self._get_dotted_path(expr.receiver)
      if recv is not None:
        return recv + [expr.member]
    return None

  def _find_imported_module_by_path(self, path: str) -> Optional[ModuleSymbol]:
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
  ) -> List[ModuleSymbol]:
    """Returns all imported ModuleSymbols starting with prefix."""
    root_scope = self.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    res: List[ModuleSymbol] = []
    prefix_dot = prefix + "."
    for sym in root_scope.symbols.values():
      if (
          isinstance(sym, ModuleSymbol)
          and sym.module_path.startswith(prefix_dot)
      ):
        res.append(sym)
    return res

  def visit_CallNode(self, node: CallNode) -> Type:
    # Generic function resolution & monomorphization
    sym = None
    mod_sym = None
    if isinstance(node.callee, IdentifierNode):
      sym = self.symbol_table.lookup(node.callee.name)
    elif isinstance(node.callee, MemberAccessNode) and isinstance(node.callee.receiver, IdentifierNode):
      mod_sym = self.symbol_table.lookup(node.callee.receiver.name)
      if isinstance(mod_sym, ModuleSymbol):
        sym = mod_sym.lookup_export(node.callee.member)

    if sym and isinstance(sym, FunctionSymbol) and sym.type_params:
      if node.type_args:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        mangled_name = self._monomorphize_function(sym, node.type_args, resolved_type_args)
        if isinstance(node.callee, IdentifierNode):
          node.callee.name = mangled_name
        else:
          node.callee.member = mangled_name
        if mod_sym:
          mono_sym = self.symbol_table.lookup(mangled_name)
          if mono_sym:
            mod_sym.exports[mangled_name] = mono_sym
      else:
        inferred_map = {}
        for idx, arg in enumerate(node.arguments):
          if idx < len(sym.symbol_type.param_types):
            param_t = sym.symbol_type.param_types[idx]
            arg_t = self.visit(arg.expr)
            if isinstance(param_t, GenericTypeParameter):
              inferred_map[param_t.name] = arg_t

        type_arg_nodes = []
        resolved_type_args = []
        for p_name in sym.type_params:
          inf_t = inferred_map.get(p_name, PrimitiveType("int"))
          resolved_type_args.append(inf_t)
          type_arg_nodes.append(BasicTypeNode(str(inf_t)))
        mangled_name = self._monomorphize_function(sym, type_arg_nodes, resolved_type_args)
        if isinstance(node.callee, IdentifierNode):
          node.callee.name = mangled_name
        else:
          node.callee.member = mangled_name
        if mod_sym:
          mono_sym = self.symbol_table.lookup(mangled_name)
          if mono_sym:
            mod_sym.exports[mangled_name] = mono_sym

    # 1. Resolve callee
    if isinstance(node.callee, MemberAccessNode):
      node.callee.is_call = True
    callee_type = self.visit(node.callee)

    if getattr(node.callee, "is_string_from", False):
      if len(node.arguments) != 1:
        self.error("String.from() requires exactly 1 argument.")
        return StringType()
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = (
          isinstance(arg_t, StringType)
          or (isinstance(arg_t, PrimitiveType) and arg_t.name in ("int", "float", "bool"))
          or isinstance(arg_t, EnumType)
      )
      if not is_valid:
        self.error(f"Cannot convert type '{arg_t}' to String using String.from().")
      return StringType()

    if getattr(node.callee, "is_enum_from", False):
      enum_t = getattr(node.callee, "enum_type", PrimitiveType("none"))
      if len(node.arguments) != 1:
        self.error(f"{getattr(enum_t, 'name', 'Enum')}.from() requires exactly 1 argument.")
        return OptionalType(enum_t)
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = (
          isinstance(arg_t, StringType)
          or (isinstance(arg_t, PrimitiveType) and arg_t.name == "int")
      )
      if not is_valid:
        self.error(f"Cannot convert type '{arg_t}' to Enum '{getattr(enum_t, 'name', 'Enum')}' using .from(). Requires int or String.")
      return OptionalType(enum_t)

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_array_method", False):
      res = CollectionChecker.check_array_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_map_method", False):
      res = CollectionChecker.check_map_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "Ref":
      if node.arena_expr:
        self.error("Ref() allocations cannot specify an 'in <arena>' clause.", node=node)
      if len(node.arguments) != 1:
        self.error(f"Ref() constructor expects 1 argument, got {len(node.arguments)}.", node=node)
        return RefType(PrimitiveType("none"))
      arg_expr = node.arguments[0].expr
      arg_type = self.visit(arg_expr)
      self._check_value_ownership_transfer(arg_expr, arg_type, node=node)
      ArenaChecker.validate_heap_box_escape(
          self.symbol_table, "Ref", arg_expr,
          lambda msg: self.error(msg, node=node), checker=self
      )
      node.is_ref_constructor = True
      if node.type_args:
        expected_inner = self._resolve_type_node(node.type_args[0])
        if ArenaChecker.type_can_hold_arena_ref(expected_inner, is_box_check=True):
          self.error(
              f"Cannot store arena-referencing type '{expected_inner}' inside 'Ref'.",
              node=node,
          )
        if not arg_type.is_compatible(expected_inner):
          self.error(f"Ref<{expected_inner}> expected argument of type '{expected_inner}', got '{arg_type}'.", node=node)
        return RefType(expected_inner)
      return RefType(arg_type)

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "SharedRef":
      if node.arena_expr:
        self.error("SharedRef() allocations cannot specify an 'in <arena>' clause.", node=node)
      if len(node.arguments) != 1:
        self.error(f"SharedRef() constructor expects 1 argument, got {len(node.arguments)}.", node=node)
        return SharedRefType(PrimitiveType("none"))
      arg_expr = node.arguments[0].expr
      arg_type = self.visit(arg_expr)
      self._check_value_ownership_transfer(arg_expr, arg_type, node=node)
      ArenaChecker.validate_heap_box_escape(
          self.symbol_table, "SharedRef", arg_expr,
          lambda msg: self.error(msg, node=node), checker=self
      )
      node.is_shared_ref_constructor = True
      if isinstance(arg_type, RefType):
        inner_t = arg_type.inner_type
      else:
        inner_t = arg_type
      if node.type_args:
        expected_inner = self._resolve_type_node(node.type_args[0])
        if ArenaChecker.type_can_hold_arena_ref(expected_inner, is_box_check=True):
          self.error(
              f"Cannot store arena-referencing type '{expected_inner}' inside 'SharedRef'.",
              node=node,
          )
        if not inner_t.is_compatible(expected_inner):
          self.error(f"SharedRef<{expected_inner}> expected argument of type '{expected_inner}', got '{inner_t}'.", node=node)
        return SharedRefType(expected_inner)
      return SharedRefType(inner_t)

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "WeakRef":
      self.error("WeakRef cannot be constructed directly; use 'shared_ref.downgrade()'.", node=node)
      return WeakRefType(PrimitiveType("none"))

    signature = None
    is_constructor = False

    # Constructor resolution
    if isinstance(callee_type, StructType):
      if callee_type.type_params:
        if node.type_args:
          resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
          callee_type = self._monomorphize_struct(callee_type, node.type_args, resolved_type_args)
          if isinstance(node.callee, IdentifierNode):
            node.callee.name = callee_type.name
        else:
          self.error(f"Generic struct '{callee_type.name}' requires explicit type arguments.")
          return callee_type

      is_constructor = True
      # Look up constructor
      init_method = callee_type.methods.get("__init__")
      if not init_method:
        self.error(f"Struct '{callee_type.name}' has no '__init__' constructor defined.")
        return callee_type
      signature = init_method.method_type
      # Match arguments
      self._check_arguments(node.arguments, signature, is_constructor=True)
      if callee_type.is_prototype and not node.arena_expr:
        self.error(f"Proto constructor call for '{callee_type.name}' requires an explicit arena via 'in <arena>'.")
      if node.arena_expr:
        arena_type = self.visit(node.arena_expr)
        if not isinstance(arena_type, ArenaType):
          self.error("Explicit arena target must be an instance of Arena.")
        else:
          ArenaChecker.validate_arena_mutability(
              self.symbol_table,
              node.arena_expr,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )
          if (
              self.is_in_init
              and isinstance(node.arena_expr, MemberAccessNode)
              and isinstance(node.arena_expr.receiver, IdentifierNode)
              and node.arena_expr.receiver.name == "self"
          ):
            self._init_used_arena_fields.add(node.arena_expr.member)
    else:
      # Standard function/method resolution
      if not isinstance(callee_type, FunctionType):
        self.error("Target is not callable.")
        return PrimitiveType("none")
      if node.arena_expr:
        self.error("The 'in <arena>' clause can only be used on struct/proto instantiations and clone expressions.")
      signature = callee_type
      self._check_arguments(node.arguments, signature, callee_node=node.callee)

    # Perform borrow checking / aliasing rules
    if signature:
      self._check_aliasing(node, signature, is_constructor)
      ArenaChecker.check_call_var_sink_escape(self, node, signature, is_constructor)

    # Check module-level var global reentrancy
    callee_id = None
    is_known_func = False
    if isinstance(node.callee, IdentifierNode):
      callee_id = node.callee.name
      callee_sym = self.symbol_table.lookup(callee_id)
      if isinstance(callee_sym, FunctionSymbol):
        is_known_func = True
    elif isinstance(node.callee, MemberAccessNode):
      recv_t = self.node_types.get(node.callee.receiver)
      if isinstance(recv_t, StructType):
        callee_id = f"{recv_t.name}.{node.callee.member}"
      else:
        callee_id = node.callee.member
      is_known_func = True

    callee_transitive = getattr(self, "func_transitive_globals", {})
    callee_dynamic = getattr(self, "func_transitive_dynamic", set())
    matching_keys = [
        k for k in callee_transitive
        if k == callee_id or k.endswith(f".{callee_id}")
    ] if callee_id else []

    for arg in node.arguments:
      arg_path = ArenaChecker.get_lvalue_path(self.symbol_table, arg.expr)
      if arg_path:
        root, _ = arg_path
        if root in getattr(self, "module_var_globals", set()):
          root_sym = self.symbol_table.lookup(root)
          if (
              isinstance(root_sym, VariableSymbol)
              and ArenaChecker.is_reference_type(root_sym.symbol_type)
          ):
            if root in getattr(self, "exported_var_globals", set()):
              self.error(
                  f"Cannot pass exported mutable global '{root}' by reference.",
                  node=node,
              )
            elif (
                not is_known_func
                or any(k in callee_dynamic for k in matching_keys)
            ):
              self.error(
                  f"Cannot pass mutable global '{root}' by reference to "
                  "dynamic or higher-order callee.",
                  node=node,
              )
            elif any(
                root in callee_transitive.get(k, set()) for k in matching_keys
            ):
              self.error(
                  f"Cannot pass mutable global '{root}' by reference: callee "
                  f"accesses '{root}' in its call graph (reentrant global "
                  "aliasing hazard).",
                  node=node,
              )

    if isinstance(node.callee, MemberAccessNode):
      recv_path = ArenaChecker.get_lvalue_path(
          self.symbol_table, node.callee.receiver
      )
      if recv_path:
        root, _ = recv_path
        if root in getattr(self, "module_var_globals", set()):
          root_sym = self.symbol_table.lookup(root)
          if (
              isinstance(root_sym, VariableSymbol)
              and ArenaChecker.is_reference_type(root_sym.symbol_type)
          ):
            if any(
                root in callee_transitive.get(k, set()) for k in matching_keys
            ):
              self.error(
                  f"Cannot invoke method '{node.callee.member}' on mutable "
                  f"global '{root}': method accesses '{root}' in its call "
                  "graph (reentrant global aliasing hazard).",
                  node=node,
              )

    if is_constructor:
      return callee_type
    ret_type = signature.return_type
    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      if not isinstance(ret_type, OptionalType):
        ret_type = OptionalType(ret_type)

    if isinstance(ret_type, CoroutineType):
      coro_borrows: Set[str] = set()
      if isinstance(node.callee, MemberAccessNode):
        r_path = ArenaChecker.get_lvalue_path(
            self.symbol_table, node.callee.receiver
        )
        if r_path:
          root, _ = r_path
          r_sym = self.symbol_table.lookup(root)
          if (
              isinstance(r_sym, VariableSymbol)
              and r_sym.scope_defined is not None
              and r_sym.scope_defined.parent is not None
          ):
            coro_borrows.add(r_sym.name)
            coro_borrows.update(r_sym.stack_borrow_symbols)
        coro_borrows.update(
            ArenaChecker.collect_stack_borrow_symbols(
                self.symbol_table, node.callee.receiver, self
            )
        )
      for arg in node.arguments:
        a_path = ArenaChecker.get_lvalue_path(self.symbol_table, arg.expr)
        if a_path:
          root, _ = a_path
          a_sym = self.symbol_table.lookup(root)
          if (
              isinstance(a_sym, VariableSymbol)
              and a_sym.scope_defined is not None
              and a_sym.scope_defined.parent is not None
              and (
                  ArenaChecker.is_reference_type(a_sym.symbol_type)
                  or a_sym.is_mutable
              )
          ):
            coro_borrows.add(a_sym.name)
            coro_borrows.update(a_sym.stack_borrow_symbols)
        coro_borrows.update(
            ArenaChecker.collect_stack_borrow_symbols(
                self.symbol_table, arg.expr, self
            )
        )
      node.stack_borrow_symbols = coro_borrows

    return ret_type

  def _check_arguments(self, arguments: List[ArgumentNode], signature: FunctionType, is_constructor: bool = False, callee_node: Optional[ASTNode] = None) -> None:
    """Helper to match argument lists against signatures (including parameter modes)."""
    expected_param_types = signature.param_types
    expected_param_names = signature.param_names or []
    if getattr(signature, "has_self", False) and isinstance(callee_node, MemberAccessNode):
      expected_param_types = signature.param_types[1:]
      expected_param_names = signature.param_names[1:] if signature.param_names else []

    num_defaults = getattr(signature, "num_defaults", 0)
    min_required = max(0, len(expected_param_types) - num_defaults)
    if len(arguments) < min_required:
      self.error(f"Not enough arguments passed to call. Expected at least {min_required}, got {len(arguments)}.")
      return

    for idx, arg in enumerate(arguments):
      # Pass expected parameter type for lambda type inference
      old_expected = self.expected_type
      param_idx = idx
      if arg.name and expected_param_names and arg.name in expected_param_names:
        param_idx = expected_param_names.index(arg.name)

      if param_idx < len(expected_param_types):
        self.expected_type = expected_param_types[param_idx]
      else:
        self.expected_type = None

      arg_type = self.visit(arg.expr)
      self.expected_type = old_expected

      if self.is_in_del and isinstance(arg.expr, IdentifierNode) and arg.expr.name == "self":
        self.error(
            "Cannot pass 'self' as an argument from destructor '__del__'; 'self' cannot escape destruction.",
            node=arg.expr,
        )

      is_test_assert = getattr(signature, "is_testing_assertion", False)
      if param_idx < len(expected_param_types):
        param_type = expected_param_types[param_idx]
        param_is_var = False
        param_mutabilities = getattr(signature, "param_mutabilities", None)
        if param_mutabilities:
          mut_idx = param_idx
          if getattr(signature, "has_self", False) and isinstance(callee_node, MemberAccessNode):
            mut_idx = param_idx + 1
          if mut_idx < len(param_mutabilities):
            param_is_var = param_mutabilities[mut_idx]

        effective_arg_type = arg_type
        # Auto-borrowing
        if isinstance(arg_type, RefType) and not isinstance(param_type, RefType):
          effective_arg_type = arg_type.inner_type
          arg.is_auto_borrow = True
        elif isinstance(arg_type, SharedRefType) and not isinstance(param_type, SharedRefType):
          if param_is_var:
            self.error(f"Cannot pass 'SharedRef<{arg_type.inner_type}>' as mutable 'var' parameter; shared references are read-only borrows.")
          else:
            effective_arg_type = arg_type.inner_type
            arg.is_auto_borrow = True

        # Explicit move check when passing to RefType parameter
        if isinstance(param_type, RefType):
          if isinstance(arg.expr, IdentifierNode) and not isinstance(arg.expr, MoveNode):
            self.error(f"Cannot pass move-only type '{arg_type}' by value; use explicit 'move {arg.expr.name}' to transfer ownership.")
          elif isinstance(arg.expr, (MemberAccessNode, IndexExprNode)):
            self.error(f"Cannot copy or partially move move-only type '{arg_type}' out of a field or collection index.")

        if not is_test_assert and not effective_arg_type.is_compatible(param_type):
          self.error(f"Argument type mismatch at position {idx+1}. Expected '{param_type}', got '{arg_type}'.")
      else:
        # Extra parameter
        if not is_constructor and not is_test_assert:
          self.error("Too many arguments passed to call.")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> Type:
    if isinstance(node.receiver, MoveNode):
      self.error(f"Cannot access member '{node.member}' on moved variable '{node.receiver.name}'.", node=node)
      return PrimitiveType("none")

    if getattr(node, "has_diagnosed_module_import", False):
      return getattr(node, "diagnosed_module_type", PrimitiveType("none"))

    # Check if receiver is a dotted path to an imported module (e.g.
    # std.os.args)
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
            if remaining:
              sug = f"{mod_sym.name}.{'.'.join(remaining)}"
            else:
              sug = mod_sym.name
            self.error(
                f"Undefined identifier '{root_ident}'. Module "
                f"'{mod_sym.module_path}' was imported as '{mod_sym.name}'. "
                f"Did you mean '{sug}'?",
                node=node,
            )
            node.has_diagnosed_module_import = True
            node.diagnosed_module_type = ModuleType(mod_sym.module_path)
            return ModuleType(mod_sym.module_path)

    receiver_type = self.visit(node.receiver)

    # Optional chaining check
    if node.is_optional:
      if not isinstance(receiver_type, OptionalType):
        self.error("Optional chaining '?.' requires an optional receiver.")
        return PrimitiveType("none")
      receiver_type = receiver_type.base_type
    else:
      if isinstance(receiver_type, OptionalType):
        self.error("Must use optional chaining '?.' to access properties on an optional receiver.")
        return PrimitiveType("none")

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
          ret_t = NoneType() if isinstance(y_type, NoneType) else OptionalType(y_type)
          return FunctionType([receiver_type], ret_t, param_names=["self"], has_self=True)
        elif node.member == "is_done":
          return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
        elif node.member == "reset":
          return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
      self.error(f"Coroutine has no method '{node.member}'.")
      return PrimitiveType("none")

    assertion_names = (
        "assert_true", "assert_false", "assert_eq", "assert_ne",
        "assert_almost_eq", "assert_none", "assert_not_none",
        "expect_true", "expect_false", "expect_eq", "expect_ne",
        "expect_almost_eq", "expect_none", "expect_not_none"
    )
    if node.member in assertion_names:
      fn_t = FunctionType([], PrimitiveType("none"))
      fn_t.is_testing_assertion = True
      return fn_t

    if isinstance(receiver_type, ModuleType):
      if isinstance(node.receiver, IdentifierNode):
        mod_sym = self.symbol_table.lookup(node.receiver.name)
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(node.member)
          if exp_sym:
            return exp_sym.symbol_type if hasattr(exp_sym, "symbol_type") else exp_sym
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
      self.error(f"Trait '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, SharedRefType):
      if node.member == "share":
        node.is_shared_ref_share = True
        node.is_instance_method = True
        return FunctionType([receiver_type], receiver_type, param_names=["self"], has_self=True)
      elif node.member == "downgrade":
        node.is_shared_ref_downgrade = True
        node.is_instance_method = True
        return FunctionType([receiver_type], WeakRefType(receiver_type.inner_type), param_names=["self"], has_self=True)
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, RefType):
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, WeakRefType):
      if node.member == "upgrade":
        node.is_weak_ref_upgrade = True
        node.is_instance_method = True
        return FunctionType([receiver_type], OptionalType(SharedRefType(receiver_type.inner_type)), param_names=["self"], has_self=True)
      self.error(f"WeakRef has no member '{node.member}'; call '.upgrade()' to access the underlying value.", node=node)
      return PrimitiveType("none")

    if isinstance(receiver_type, ArrayType):
      return CollectionChecker.resolve_array_member(self, node, receiver_type)

    if isinstance(receiver_type, MapType):
      return CollectionChecker.resolve_map_member(self, node, receiver_type)

    if not isinstance(receiver_type, StructType):
      self.error("Member access receiver is not a struct or trait.")
      return PrimitiveType("none")

    # Special member __proto__
    if node.member == "__proto__":
      if not receiver_type.is_prototype:
        self.error(
            f"Cannot access '__proto__' on standard struct '{receiver_type.name}'; '__proto__' is only available on 'proto' instances.",
            node=node,
        )
        return PrimitiveType("none")
      return OptionalType(receiver_type)

    # Special member __del__
    if node.member == "__del__":
      self.error("Destructor '__del__' cannot be manually invoked.")
      return PrimitiveType("none")

    # Resolve field
    field = receiver_type.fields.get(node.member)
    if field:
      # If optional chained, result type is optional
      if node.is_optional:
        return OptionalType(field.field_type)
      return field.field_type

    # Resolve method
    method = receiver_type.get_method(node.member, self.symbol_table)
    if method:
      node.is_static_method = (method.modifier == "static")
      node.is_instance_method = (method.modifier != "static")
      return method.method_type

    self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
    return PrimitiveType("none")

