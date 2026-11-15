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
    StructSymbol,
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
        param_names = sym.symbol_type.param_names or []
        for idx, arg in enumerate(node.arguments):
          if arg.name:
            param_idx = (
                param_names.index(arg.name)
                if arg.name in param_names
                else None
            )
          else:
            param_idx = idx
          if param_idx is not None and param_idx < len(sym.symbol_type.param_types):
            param_t = sym.symbol_type.param_types[param_idx]
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
      node._is_struct_constructor = True
      # Look up constructor
      init_method = callee_type.methods.get("__init__")
      if not init_method:
        self.error(f"Struct '{callee_type.name}' has no '__init__' constructor defined.")
        return callee_type
      signature = init_method.method_type
      # Match arguments
      self._check_arguments(
          node.arguments, signature, is_constructor=True, call_node=node
      )
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
        self.error("Target is not callable.", node=node.callee)
        return PrimitiveType("none")
      if node.arena_expr:
        self.error("The 'in <arena>' clause can only be used on struct/proto instantiations and clone expressions.")
      signature = callee_type
      if (
          isinstance(node.callee, MemberAccessNode)
          and getattr(node.callee, "is_qualified_ancestor_call", False)
      ):
        if (
            not node.arguments
            or node.arguments[0].name is not None
            or not (
                isinstance(node.arguments[0].expr, IdentifierNode)
                and node.arguments[0].expr.name == "self"
            )
        ):
          anc_t = getattr(node.callee, "qualified_ancestor_type", None)
          anc_name = anc_t.name if anc_t else "Ancestor"
          self.error(
              f"Qualified ancestor call '{anc_name}.{node.callee.member}' "
              "must pass 'self' as the first positional argument.",
              node=node,
          )
          rets = callee_type.return_types
          if len(rets) > 1:
            return MultiReturnType(rets)
          return rets[0] if rets else PrimitiveType("none")
      self._check_arguments(
          node.arguments,
          signature,
          callee_node=node.callee,
          call_node=node,
      )

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

  def _is_expr_pure(self, expr: Any) -> bool:
    """Returns True when evaluating expr cannot cause or observe side effects."""
    if expr is None or isinstance(expr, (LiteralNode, IdentifierNode)):
      return True
    if isinstance(expr, (UnaryOpNode, CastExprNode)):
      return self._is_expr_pure(expr.expr)
    if isinstance(expr, BinaryOpNode):
      return self._is_expr_pure(expr.left) and self._is_expr_pure(expr.right)
    if isinstance(expr, TernaryExprNode):
      return (
          self._is_expr_pure(expr.condition)
          and self._is_expr_pure(expr.true_expr)
          and self._is_expr_pure(expr.false_expr)
      )
    if isinstance(expr, MemberAccessNode):
      return self._is_expr_pure(expr.receiver)
    if isinstance(expr, IndexExprNode):
      return self._is_expr_pure(expr.array) and self._is_expr_pure(expr.index)
    if isinstance(expr, InterpolatedStringNode):
      return all(self._is_expr_pure(p) for p in expr.parts)
    if isinstance(expr, ArrayLiteralNode):
      return all(self._is_expr_pure(e) for e in expr.elements)
    if isinstance(expr, MapLiteralNode):
      return all(
          self._is_expr_pure(e.key) and self._is_expr_pure(e.value)
          for e in expr.entries
      )
    return False

  def _visit_call_arg_expr(
      self, expr: ASTNode, expected: Optional[Type]
  ) -> Type:
    """Visits an argument expression with optional expected type context."""
    old_expected = self.expected_type
    self.expected_type = expected
    try:
      arg_type = self.visit(expr)
    finally:
      self.expected_type = old_expected
    if self.is_in_del and isinstance(expr, IdentifierNode) and expr.name == "self":
      self.error(
          "Cannot pass 'self' as an argument from destructor '__del__'; "
          "'self' cannot escape destruction.",
          node=expr,
      )
    return arg_type

  def _check_single_argument(
      self,
      idx: int,
      arg: ArgumentNode,
      arg_type: Type,
      param_idx: int,
      expected_param_types: List[Type],
      expected_mutabilities: List[bool],
  ) -> None:
    """Validates mode and type compatibility for a single resolved argument."""
    param_type = expected_param_types[param_idx]
    param_is_var = (
        expected_mutabilities[param_idx]
        if param_idx < len(expected_mutabilities)
        else False
    )

    effective_arg_type = arg_type
    # Auto-borrowing
    if isinstance(arg_type, RefType) and not isinstance(param_type, RefType):
      effective_arg_type = arg_type.inner_type
      arg.is_auto_borrow = True
    elif isinstance(arg_type, SharedRefType) and not isinstance(param_type, SharedRefType):
      if param_is_var:
        self.error(
            f"Cannot pass 'SharedRef<{arg_type.inner_type}>' as mutable "
            "'var' parameter; shared references are read-only borrows."
        )
      else:
        effective_arg_type = arg_type.inner_type
        arg.is_auto_borrow = True

    # Explicit move check when passing to RefType parameter
    if isinstance(param_type, RefType):
      if isinstance(arg.expr, IdentifierNode) and not isinstance(arg.expr, MoveNode):
        self.error(
            f"Cannot pass move-only type '{arg_type}' by value; use "
            f"explicit 'move {arg.expr.name}' to transfer ownership."
        )
      elif isinstance(arg.expr, (MemberAccessNode, IndexExprNode)):
        self.error(
            f"Cannot copy or partially move move-only type '{arg_type}' "
            "out of a field or collection index."
        )

    if not effective_arg_type.is_compatible(param_type):
      self.error(
          f"Argument type mismatch at position {idx+1}. "
          f"Expected '{param_type}', got '{arg_type}'.",
          node=arg,
      )

  def _check_range_arguments(
      self,
      arguments: List[ArgumentNode],
      call_node: Optional[CallNode] = None,
  ) -> None:
    """Validates positional and named arguments for built-in range()."""
    if len(arguments) < 1:
      for arg in arguments:
        self._visit_call_arg_expr(arg.expr, PrimitiveType("int"))
      self.error(
          "Not enough arguments passed to call. Expected at least 1, got 0.",
          node=call_node,
      )
      return

    seen_named = False
    pos_count = 0
    named_args: Dict[str, ArgumentNode] = {}
    int_t = PrimitiveType("int")

    for idx, arg in enumerate(arguments):
      if arg.name:
        seen_named = True
        if arg.name not in ("start", "stop", "step"):
          self.error(f"Unexpected named argument '{arg.name}'.", node=arg)
        elif arg.name in named_args:
          self.error(
              f"Multiple values provided for parameter '{arg.name}'.",
              node=arg,
          )
        else:
          named_args[arg.name] = arg
      else:
        if seen_named:
          self.error(
              "Positional argument cannot follow a named argument.",
              node=arg,
          )
        pos_count += 1

      arg_type = self._visit_call_arg_expr(arg.expr, int_t)
      if not arg_type.is_compatible(int_t):
        self.error(
            f"Argument type mismatch at position {idx+1}. "
            f"Expected 'int', got '{arg_type}'.",
            node=arg,
        )

    if len(arguments) > 3:
      self.error("Too many arguments passed to call.", node=call_node)
      return

    conflict_keys = {
        1: ("start",),
        2: ("start", "stop"),
        3: ("start", "stop", "step"),
    }.get(pos_count, ())
    for key in conflict_keys:
      if key in named_args:
        self.error(
            f"Multiple values provided for parameter '{key}'.",
            node=named_args[key],
        )
    if "stop" not in named_args and (
        pos_count == 0
        or (pos_count == 1 and "start" not in named_args and "step" in named_args)
    ):
      self.error(
          "Missing required argument for parameter 'stop'.",
          node=call_node,
      )

  def _check_arguments(
      self,
      arguments: List[ArgumentNode],
      signature: FunctionType,
      is_constructor: bool = False,
      callee_node: Optional[ASTNode] = None,
      call_node: Optional[CallNode] = None,
  ) -> None:
    """Matches argument lists against signatures and canonicalizes call metadata."""
    is_test_assert = getattr(signature, "is_testing_assertion", False)
    if is_test_assert:
      seen_named = False
      for arg in arguments:
        if arg.name:
          seen_named = True
        elif seen_named:
          self.error(
              "Positional argument cannot follow a named argument.",
              node=arg,
          )
        self._visit_call_arg_expr(arg.expr, None)
      return

    if (
        isinstance(callee_node, IdentifierNode)
        and callee_node.name == "range"
        and isinstance(signature.return_type, RangeType)
        and getattr(signature, "ast_decl", None) is None
    ):
      self._check_range_arguments(arguments, call_node=call_node)
      return

    expected_param_types = signature.param_types
    expected_param_names = signature.param_names or []
    expected_mutabilities = getattr(signature, "param_mutabilities", None) or []
    has_implicit_self = (
        getattr(signature, "has_self", False)
        and bool(expected_param_names)
        and expected_param_names[0] == "self"
        and len(expected_param_types) == len(expected_param_names)
        and (isinstance(callee_node, MemberAccessNode) or is_constructor)
    )
    if has_implicit_self:
      expected_param_types = expected_param_types[1:]
      expected_param_names = expected_param_names[1:]
      expected_mutabilities = expected_mutabilities[1:]

    has_named_params = getattr(signature, "has_named_params", True)
    num_params = len(expected_param_types)
    num_defaults = getattr(signature, "num_defaults", 0)
    min_required = max(0, num_params - num_defaults)
    if len(arguments) < min_required:
      self.error(
          f"Not enough arguments passed to call. "
          f"Expected at least {min_required}, got {len(arguments)}."
      )
      for idx, arg in enumerate(arguments):
        p_idx = None
        if arg.name and has_named_params and arg.name in expected_param_names:
          p_idx = expected_param_names.index(arg.name)
        elif not arg.name and idx < num_params:
          p_idx = idx
        exp_t = expected_param_types[p_idx] if p_idx is not None else None
        self._visit_call_arg_expr(arg.expr, exp_t)
      return

    seen_named = False
    bound_slots: Dict[int, ArgumentNode] = {}
    arg_param_indices: List[Optional[int]] = []
    has_binding_error = False

    for idx, arg in enumerate(arguments):
      param_idx: Optional[int] = None
      if arg.name:
        seen_named = True
        if not has_named_params:
          self.error(
              f"Named argument '{arg.name}' is not supported when calling "
              "an unnamed function type.",
              node=arg,
          )
          has_binding_error = True
        elif arg.name not in expected_param_names:
          self.error(
              f"Unexpected named argument '{arg.name}'.",
              node=arg,
          )
          has_binding_error = True
        else:
          cand_idx = expected_param_names.index(arg.name)
          if cand_idx in bound_slots:
            self.error(
                f"Multiple values provided for parameter '{arg.name}'.",
                node=arg,
            )
            has_binding_error = True
          else:
            param_idx = cand_idx
            bound_slots[param_idx] = arg
      else:
        if seen_named:
          self.error(
              "Positional argument cannot follow a named argument.",
              node=arg,
          )
          has_binding_error = True
        elif idx >= num_params:
          self.error("Too many arguments passed to call.", node=arg)
          has_binding_error = True
        else:
          param_idx = idx
          bound_slots[param_idx] = arg

      exp_t = (
          expected_param_types[param_idx]
          if param_idx is not None and param_idx < num_params
          else None
      )
      arg_type = self._visit_call_arg_expr(arg.expr, exp_t)
      if param_idx is not None and param_idx < num_params:
        self._check_single_argument(
            idx,
            arg,
            arg_type,
            param_idx,
            expected_param_types,
            expected_mutabilities,
        )
      arg_param_indices.append(param_idx)

    if not has_binding_error:
      for m_idx in range(min_required):
        if m_idx not in bound_slots:
          p_name = (
              expected_param_names[m_idx]
              if m_idx < len(expected_param_names)
              else f"p{m_idx}"
          )
          self.error(
              f"Missing required argument for parameter '{p_name}'.",
              node=call_node,
          )
          has_binding_error = True

    if call_node is not None and not has_binding_error:
      if not bound_slots:
        call_node._resolved_arguments = []
        call_node._requires_eval_order_temps = False
        call_node._eval_order_slots = []
      else:
        max_idx = max(bound_slots.keys())
        call_node._resolved_arguments = [
            bound_slots[i].expr if i in bound_slots else LiteralNode(None, "none")
            for i in range(max_idx + 1)
        ]
        valid_slots = [p for p in arg_param_indices if p is not None]
        is_reordered = any(
            valid_slots[k] > valid_slots[k + 1]
            for k in range(len(valid_slots) - 1)
        )
        eval_exprs = [a.expr for a in arguments]
        if isinstance(callee_node, MemberAccessNode):
          eval_exprs.append(callee_node.receiver)
        elif callee_node is not None and not isinstance(callee_node, IdentifierNode):
          eval_exprs.append(callee_node)
        has_side_effects = any(not self._is_expr_pure(e) for e in eval_exprs)
        call_node._requires_eval_order_temps = bool(
            is_reordered and has_side_effects
        )
        call_node._eval_order_slots = valid_slots

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

    if self._is_struct_type_receiver(node.receiver):
      return self._resolve_struct_type_member_access(node, receiver_type)

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
        if isinstance(exp_sym, StructSymbol):
          return True
        return (
            exp_sym is not None
            and not isinstance(exp_sym, VariableSymbol)
            and isinstance(getattr(exp_sym, "symbol_type", exp_sym), StructType)
        )
    return False

  def _resolve_struct_type_member_access(
      self, node: MemberAccessNode, receiver_type: StructType
  ) -> Type:
    """Resolves `StructType.member` for static methods or ancestor dispatch."""
    if node.member == "__init__":
      self.error(
          f"Cannot call '__init__' directly on '{receiver_type.name}'; "
          f"use ': {receiver_type.name}(...)' in a subclass '__init__' or "
          f"'{receiver_type.name}(...)' to construct.",
          node=node,
      )
      return PrimitiveType("none")

    if node.member in receiver_type.fields:
      self.error(
          f"Cannot access instance field '{node.member}' on type "
          f"'{receiver_type.name}'.",
          node=node,
      )
      return PrimitiveType("none")

    method = receiver_type.get_method(node.member, self.symbol_table)
    if not method:
      self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
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
          f"Qualified method call '{receiver_type.name}.{node.member}(self, ...)' "
          "is only allowed inside an instance method of a subclass.",
          node=node,
      )
      return PrimitiveType("none")

    if not self.current_struct.has_ancestor(receiver_type, self.symbol_table):
      if self.current_struct == receiver_type:
        self.error(
            f"Cannot use qualified ancestor dispatch "
            f"'{receiver_type.name}.{node.member}(self, ...)' on own struct "
            f"'{self.current_struct.name}'; use 'self.{node.member}(...)' instead.",
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

