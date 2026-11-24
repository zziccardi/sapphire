"""Call, argument, and aliasing visitors for TypeChecker."""

from typing import Any

from sapphire.parser.ast import (
  ArgumentNode,
  ArrayLiteralNode,
  ArrayTypeNode,
  ASTNode,
  BasicTypeNode,
  BinaryOpNode,
  CallNode,
  CastExprNode,
  FunctionTypeNode,
  IdentifierNode,
  IndexExprNode,
  InterpolatedStringNode,
  LiteralNode,
  MapLiteralNode,
  MapTypeNode,
  MemberAccessNode,
  MoveNode,
  OptionalTypeNode,
  TernaryExprNode,
  TypeNode,
  UnaryOpNode,
)
from sapphire.semantics.arena_checker import ArenaChecker
from sapphire.semantics.collection_checker import CollectionChecker
from sapphire.semantics.member_access_visitor import MemberAccessVisitorMixin
from sapphire.semantics.symbol_table import (
  ArenaType,
  ArrayType,
  CoroutineType,
  EnumType,
  FunctionSymbol,
  FunctionType,
  GenericTypeParameter,
  MapType,
  ModuleSymbol,
  MultiReturnType,
  NoneType,
  OptionalType,
  PrimitiveType,
  RangeType,
  RefType,
  SharedRefType,
  StringType,
  StructSymbol,
  StructType,
  Type,
  VariableSymbol,
  WeakRefType,
)


class CallVisitorMixin(MemberAccessVisitorMixin):
  """Provides AST visitor methods for calls, arguments, and member access."""

  def _get_lvalue_path(self, node: ASTNode) -> tuple[str, list[str]] | None:
    """Resolves an AST node to its root variable name and field path if it is an
    lvalue.
    """
    return ArenaChecker.get_lvalue_path(self.symbol_table, node)

  def _is_reference_type(self, type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    return ArenaChecker.is_reference_type(type_obj)

  def _check_aliasing(
    self, node: CallNode, signature: FunctionType, is_constructor: bool
  ) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability
    aliasing.
    """
    ArenaChecker.check_aliasing(self, node, signature, is_constructor)

  def _unify_generic_type(
    self, param_t: Type, arg_t: Type, inferred_map: dict[str, Type]
  ) -> None:
    """Recursively unifies generic type parameters in *param_t* against *arg_t*.
    """
    if isinstance(param_t, GenericTypeParameter):
      if param_t.name not in inferred_map:
        inferred_map[param_t.name] = arg_t
      else:
        widened = self._widen_types(inferred_map[param_t.name], arg_t)
        if widened is not None:
          inferred_map[param_t.name] = widened
      return
    if isinstance(arg_t, (RefType, SharedRefType)) and not isinstance(
      param_t, (RefType, SharedRefType)
    ):
      self._unify_generic_type(param_t, arg_t.inner_type, inferred_map)
      return
    if isinstance(param_t, OptionalType):
      if isinstance(arg_t, OptionalType):
        self._unify_generic_type(
          param_t.base_type, arg_t.base_type, inferred_map
        )
      elif not isinstance(arg_t, NoneType):
        self._unify_generic_type(param_t.base_type, arg_t, inferred_map)
      return
    if isinstance(param_t, ArrayType) and isinstance(arg_t, ArrayType):
      if not isinstance(arg_t.element_type, NoneType):
        self._unify_generic_type(
          param_t.element_type, arg_t.element_type, inferred_map
        )
      return
    if isinstance(param_t, MapType) and isinstance(arg_t, MapType):
      if not isinstance(arg_t.key_type, NoneType):
        self._unify_generic_type(param_t.key_type, arg_t.key_type, inferred_map)
      if not isinstance(arg_t.value_type, NoneType):
        self._unify_generic_type(
          param_t.value_type, arg_t.value_type, inferred_map
        )
      return
    if isinstance(param_t, RefType) and isinstance(arg_t, RefType):
      self._unify_generic_type(
        param_t.inner_type, arg_t.inner_type, inferred_map
      )
      return
    if isinstance(param_t, SharedRefType) and isinstance(arg_t, SharedRefType):
      self._unify_generic_type(
        param_t.inner_type, arg_t.inner_type, inferred_map
      )
      return
    if isinstance(param_t, WeakRefType) and isinstance(arg_t, WeakRefType):
      self._unify_generic_type(
        param_t.inner_type, arg_t.inner_type, inferred_map
      )
      return
    if isinstance(param_t, CoroutineType) and isinstance(arg_t, CoroutineType):
      if not isinstance(arg_t.yield_type, NoneType):
        self._unify_generic_type(
          param_t.yield_type, arg_t.yield_type, inferred_map
        )
      return
    if isinstance(param_t, FunctionType) and isinstance(arg_t, FunctionType):
      for p_sub, a_sub in zip(
        param_t.param_types, arg_t.param_types, strict=False
      ):
        self._unify_generic_type(p_sub, a_sub, inferred_map)
      self._unify_generic_type(
        param_t.return_type, arg_t.return_type, inferred_map
      )

  def _type_to_type_node(self, t: Type) -> TypeNode:
    """Converts a resolved semantic Type into a structured AST TypeNode."""
    if isinstance(t, OptionalType):
      return OptionalTypeNode(self._type_to_type_node(t.base_type))
    if isinstance(t, ArrayType):
      elem_node = self._type_to_type_node(t.element_type)
      size = t.size if t.is_fixed_size else None
      return ArrayTypeNode(elem_node, size=size)
    if isinstance(t, MapType):
      return MapTypeNode(
        self._type_to_type_node(t.key_type),
        self._type_to_type_node(t.value_type),
      )
    if isinstance(t, FunctionType):
      return FunctionTypeNode(
        [self._type_to_type_node(p) for p in t.param_types],
        [self._type_to_type_node(r) for r in t.return_types],
      )
    if isinstance(t, RefType):
      return BasicTypeNode(
        "Ref", type_args=[self._type_to_type_node(t.inner_type)]
      )
    if isinstance(t, SharedRefType):
      return BasicTypeNode(
        "SharedRef", type_args=[self._type_to_type_node(t.inner_type)]
      )
    if isinstance(t, WeakRefType):
      return BasicTypeNode(
        "WeakRef", type_args=[self._type_to_type_node(t.inner_type)]
      )
    if isinstance(t, CoroutineType):
      t_args = (
        []
        if isinstance(t.yield_type, NoneType)
        else [self._type_to_type_node(t.yield_type)]
      )
      return BasicTypeNode("Coroutine", type_args=t_args)
    if isinstance(t, NoneType):
      return BasicTypeNode("void")
    return BasicTypeNode(str(t))

  def _try_monomorphize_generic_call(self, node: CallNode) -> None:
    """Resolves and monomorphizes calls to generic functions when applicable."""
    sym = None
    mod_sym = None
    if isinstance(node.callee, IdentifierNode):
      sym = self.symbol_table.lookup(node.callee.name)
    elif isinstance(node.callee, MemberAccessNode) and isinstance(
      node.callee.receiver, IdentifierNode
    ):
      mod_sym = self.symbol_table.lookup(node.callee.receiver.name)
      if isinstance(mod_sym, ModuleSymbol):
        sym = mod_sym.lookup_export(node.callee.member)

    if not (sym and isinstance(sym, FunctionSymbol) and sym.type_params):
      return

    if node.type_args:
      resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
      type_arg_nodes = node.type_args
    else:
      # Infer generic type parameters from call arguments when omitted.
      # Snapshot move state so speculative inference does not double-move args.
      inferred_map: dict[str, Type] = {}
      param_names = sym.symbol_type.param_names or []
      saved_moved = set(self.moved_symbols)
      saved_errors_len = len(self.errors)
      saved_diags_len = len(self.diagnostics)
      try:
        for idx, arg in enumerate(node.arguments):
          if arg.name:
            param_idx = (
              param_names.index(arg.name) if arg.name in param_names else None
            )
          else:
            param_idx = idx
          if param_idx is not None and param_idx < len(
            sym.symbol_type.param_types
          ):
            param_t = sym.symbol_type.param_types[param_idx]
            arg_t = self.visit(arg.expr)
            self._unify_generic_type(param_t, arg_t, inferred_map)
      finally:
        self._restore_moved_symbols(saved_moved)
        del self.errors[saved_errors_len:]
        del self.diagnostics[saved_diags_len:]

      type_arg_nodes = []
      resolved_type_args = []
      for p_name in sym.type_params:
        if p_name not in inferred_map:
          self.error(
            f"Cannot infer generic type parameter '{p_name}' for '{sym.name}'; "
            "specify explicit type arguments.",
            node=node,
          )
          return
        inf_t = inferred_map[p_name]
        resolved_type_args.append(inf_t)
        type_arg_nodes.append(self._type_to_type_node(inf_t))

    mangled_name = self._monomorphize_function(
      sym, type_arg_nodes, resolved_type_args
    )
    if isinstance(node.callee, IdentifierNode):
      node.callee.name = mangled_name
    else:
      node.callee.member = mangled_name
    if mod_sym:
      mono_sym = self.symbol_table.lookup(mangled_name)
      if mono_sym:
        mod_sym.exports[mangled_name] = mono_sym

  def _try_check_builtin_call(self, node: CallNode) -> Type | None:
    """Handles special-cased builtin calls (String.from, Enum.from, Ref, etc.).
    """
    if getattr(node.callee, "is_string_from", False):
      if len(node.arguments) != 1:
        self.error("String.from() requires exactly 1 argument.")
        return StringType()
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = (
        isinstance(arg_t, StringType)
        or (
          isinstance(arg_t, PrimitiveType)
          and arg_t.name in ("int", "float", "bool")
        )
        or isinstance(arg_t, EnumType)
      )
      if not is_valid:
        self.error(
          f"Cannot convert type '{arg_t}' to String using String.from()."
        )
      return StringType()

    if getattr(node.callee, "is_enum_from", False):
      enum_t = getattr(node.callee, "enum_type", PrimitiveType("none"))
      if len(node.arguments) != 1:
        self.error(
          f"{getattr(enum_t, 'name', 'Enum')}.from() requires exactly 1 "
          "argument."
        )
        return OptionalType(enum_t)
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = isinstance(arg_t, StringType) or (
        isinstance(arg_t, PrimitiveType) and arg_t.name == "int"
      )
      if not is_valid:
        self.error(
          f"Cannot convert type '{arg_t}' to Enum "
          f"'{getattr(enum_t, 'name', 'Enum')}' using .from(). "
          "Requires int or String."
        )
      return OptionalType(enum_t)

    if isinstance(node.callee, MemberAccessNode) and getattr(
      node.callee, "is_array_method", False
    ):
      res = CollectionChecker.check_array_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, MemberAccessNode) and getattr(
      node.callee, "is_map_method", False
    ):
      res = CollectionChecker.check_map_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "Ref":
      return self._check_heap_box_constructor(node, is_shared=False)

    if (
      isinstance(node.callee, IdentifierNode)
      and node.callee.name == "SharedRef"
    ):
      return self._check_heap_box_constructor(node, is_shared=True)

    if (
      isinstance(node.callee, IdentifierNode) and node.callee.name == "WeakRef"
    ):
      self.error(
        "WeakRef cannot be constructed directly; use 'shared_ref.downgrade()'.",
        node=node,
      )
      return WeakRefType(PrimitiveType("none"))

    return None

  def _check_heap_box_constructor(
    self, node: CallNode, is_shared: bool
  ) -> Type:
    """Validates Ref() and SharedRef() heap-box constructors."""
    box_name = "SharedRef" if is_shared else "Ref"
    box_cls = SharedRefType if is_shared else RefType

    if node.arena_expr:
      self.error(
        f"{box_name}() allocations cannot specify an 'in <arena>' clause.",
        node=node,
      )
    if len(node.arguments) != 1:
      self.error(
        f"{box_name}() constructor expects 1 argument, got "
        f"{len(node.arguments)}.",
        node=node,
      )
      return box_cls(PrimitiveType("none"))

    arg_expr = node.arguments[0].expr
    arg_type = self.visit(arg_expr)
    self._check_value_ownership_transfer(arg_expr, arg_type, node=node)
    ArenaChecker.validate_heap_box_escape(
      self.symbol_table,
      box_name,
      arg_expr,
      lambda msg: self.error(msg, node=node),
      checker=self,
    )
    if is_shared:
      node.is_shared_ref_constructor = True
      inner_t = (
        arg_type.inner_type if isinstance(arg_type, RefType) else arg_type
      )
    else:
      node.is_ref_constructor = True
      inner_t = arg_type

    if node.type_args:
      expected_inner = self._resolve_type_node(node.type_args[0])
      if ArenaChecker.type_can_hold_arena_ref(
        expected_inner,
        is_box_check=True,
        symbol_table=self.symbol_table,
        checker=self,
      ):
        self.error(
          f"Cannot store arena-referencing type '{expected_inner}' inside "
          f"'{box_name}'.",
          node=node,
        )
      if not inner_t.is_compatible(expected_inner):
        self.error(
          f"{box_name}<{expected_inner}> expected argument of type "
          f"'{expected_inner}', got '{inner_t}'.",
          node=node,
        )
      return box_cls(expected_inner)
    return box_cls(inner_t)

  def _check_constructor_call(
    self, node: CallNode, callee_type: StructType
  ) -> tuple[StructType, FunctionType | None]:
    """Validates struct/proto constructor calls and `in <arena>` clauses."""
    if callee_type.type_params:
      if node.type_args:
        resolved_type_args = [
          self._resolve_type_node(t) for t in node.type_args
        ]
        callee_type = self._monomorphize_struct(
          callee_type, node.type_args, resolved_type_args
        )
        if isinstance(node.callee, IdentifierNode):
          node.callee.name = callee_type.name
        elif isinstance(node.callee, MemberAccessNode):
          node.callee.member = callee_type.name
          if isinstance(node.callee.receiver, IdentifierNode):
            mod_sym = self.symbol_table.lookup(node.callee.receiver.name)
            if isinstance(mod_sym, ModuleSymbol):
              mod_sym.exports[callee_type.name] = StructSymbol(
                callee_type.name, callee_type
              )
      else:
        self.error(
          f"Generic struct '{callee_type.name}' requires explicit type "
          "arguments."
        )
        return callee_type, None

    node._is_struct_constructor = True
    init_method = callee_type.methods.get("__init__")
    if not init_method:
      self.error(
        f"Struct '{callee_type.name}' has no '__init__' constructor defined."
      )
      return callee_type, None

    signature = init_method.method_type
    self._check_arguments(
      node.arguments, signature, is_constructor=True, call_node=node
    )
    if callee_type.is_prototype and not node.arena_expr:
      self.error(
        f"Proto constructor call for '{callee_type.name}' requires an "
        "explicit arena via 'in <arena>'."
      )
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
    return callee_type, signature

  def _check_module_var_reentrancy(self, node: CallNode) -> None:
    """Rejects passing mutable non-primitive globals that the callee also
    touches.
    """
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
    matching_keys = (
      [
        k
        for k in callee_transitive
        if k == callee_id or k.endswith(f".{callee_id}")
      ]
      if callee_id
      else []
    )

    for arg in node.arguments:
      arg_path = ArenaChecker.get_lvalue_path(self.symbol_table, arg.expr)
      if not arg_path:
        continue
      root, _ = arg_path
      if root not in getattr(self, "module_var_globals", set()):
        continue
      root_sym = self.symbol_table.lookup(root)
      if not (
        isinstance(root_sym, VariableSymbol)
        and ArenaChecker.is_reference_type(root_sym.symbol_type)
      ):
        continue
      if root in getattr(self, "exported_var_globals", set()):
        self.error(
          f"Cannot pass exported mutable global '{root}' by reference.",
          node=node,
        )
      elif not is_known_func or any(k in callee_dynamic for k in matching_keys):
        self.error(
          f"Cannot pass mutable global '{root}' by reference to "
          "dynamic or higher-order callee.",
          node=node,
        )
      elif any(root in callee_transitive.get(k, set()) for k in matching_keys):
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
          if isinstance(
            root_sym, VariableSymbol
          ) and ArenaChecker.is_reference_type(root_sym.symbol_type):
            if any(
              root in callee_transitive.get(k, set()) for k in matching_keys
            ):
              self.error(
                f"Cannot invoke method '{node.callee.member}' on mutable "
                f"global '{root}': method accesses '{root}' in its call "
                "graph (reentrant global aliasing hazard).",
                node=node,
              )

  def _collect_coroutine_call_borrows(self, node: CallNode) -> None:
    """Records local stack variables borrowed by a returned Coroutine<T>."""
    coro_borrows: set[str] = set()
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

  def visit_CallNode(self, node: CallNode) -> Type:
    """Type-checks function, method, constructor, and builtin calls."""
    self._try_monomorphize_generic_call(node)

    # Mark MemberAccessNode as a call target so qualified ancestor checks pass.
    if isinstance(node.callee, MemberAccessNode):
      node.callee.is_call = True
    callee_type = self.visit(node.callee)

    builtin_res = self._try_check_builtin_call(node)
    if builtin_res is not None:
      if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
        if not isinstance(builtin_res, OptionalType):
          builtin_res = OptionalType(builtin_res)
      return builtin_res

    signature: FunctionType | None = None
    is_constructor = False

    if isinstance(callee_type, StructType):
      is_constructor = True
      callee_type, signature = self._check_constructor_call(node, callee_type)
      if signature is None:
        return callee_type
    else:
      if not isinstance(callee_type, FunctionType):
        self.error("Target is not callable.", node=node.callee)
        return PrimitiveType("none")
      if node.arena_expr:
        self.error(
          "The 'in <arena>' clause can only be used on struct/proto "
          "instantiations and clone expressions."
        )
      signature = callee_type
      if isinstance(node.callee, MemberAccessNode) and getattr(
        node.callee, "is_qualified_ancestor_call", False
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

    if signature:
      self._check_aliasing(node, signature, is_constructor)
      ArenaChecker.check_call_var_sink_escape(
        self, node, signature, is_constructor
      )

    self._check_module_var_reentrancy(node)

    if is_constructor:
      return callee_type

    ret_type = signature.return_type
    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      if not isinstance(ret_type, OptionalType):
        ret_type = OptionalType(ret_type)

    if isinstance(ret_type, CoroutineType):
      self._collect_coroutine_call_borrows(node)

    return ret_type

  def _is_expr_pure(self, expr: Any) -> bool:
    """Returns True when evaluating expr cannot cause or observe side effects.
    """
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
    self, expr: ASTNode, expected: Type | None
  ) -> Type:
    """Visits an argument expression with optional expected type context."""
    old_expected = self.expected_type
    self.expected_type = expected
    try:
      arg_type = self.visit(expr)
    finally:
      self.expected_type = old_expected
    if (
      self.is_in_del
      and isinstance(expr, IdentifierNode)
      and expr.name == "self"
    ):
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
    expected_param_types: list[Type],
    expected_mutabilities: list[bool],
  ) -> None:
    """Validates mode and type compatibility for a single resolved argument."""
    param_type = expected_param_types[param_idx]
    param_is_var = (
      expected_mutabilities[param_idx]
      if param_idx < len(expected_mutabilities)
      else False
    )

    effective_arg_type = arg_type
    unwrapped_param = (
      param_type.base_type
      if isinstance(param_type, OptionalType)
      else param_type
    )
    # Auto-borrow Ref<T>/SharedRef<T> when passing to an unboxed parameter.
    if isinstance(arg_type, RefType) and not isinstance(
      unwrapped_param, RefType
    ):
      effective_arg_type = arg_type.inner_type
      arg.is_auto_borrow = True
    elif isinstance(arg_type, SharedRefType) and not isinstance(
      unwrapped_param, SharedRefType
    ):
      if param_is_var:
        self.error(
          f"Cannot pass 'SharedRef<{arg_type.inner_type}>' as mutable "
          "'var' parameter; shared references are read-only borrows."
        )
      else:
        effective_arg_type = arg_type.inner_type
        arg.is_auto_borrow = True

    if isinstance(unwrapped_param, RefType) and not getattr(
      arg, "is_auto_borrow", False
    ):

      def _check_ref_arg_move(expr: ASTNode) -> None:
        if isinstance(expr, TernaryExprNode):
          _check_ref_arg_move(expr.true_expr)
          _check_ref_arg_move(expr.false_expr)
          return
        if isinstance(expr, BinaryOpNode) and expr.op == "??":
          _check_ref_arg_move(expr.left)
          _check_ref_arg_move(expr.right)
          return
        if isinstance(expr, IdentifierNode) and not isinstance(expr, MoveNode):
          self.error(
            f"Cannot pass move-only type '{arg_type}' by value; use "
            f"explicit 'move {expr.name}' to transfer ownership.",
            node=arg,
          )
        elif isinstance(expr, (MemberAccessNode, IndexExprNode)):
          self.error(
            f"Cannot copy or partially move move-only type '{arg_type}' "
            "out of a field or collection index.",
            node=arg,
          )

      _check_ref_arg_move(arg.expr)

    if not effective_arg_type.is_compatible(param_type):
      self.error(
        f"Argument type mismatch at position {idx + 1}. "
        f"Expected '{param_type}', got '{arg_type}'.",
        node=arg,
      )
    elif param_is_var:
      if (
        isinstance(effective_arg_type, ArrayType)
        and isinstance(param_type, ArrayType)
        and not isinstance(effective_arg_type.element_type, NoneType)
        and not isinstance(param_type.element_type, NoneType)
        and not param_type.element_type.is_compatible(
          effective_arg_type.element_type
        )
      ):
        self.error(
          f"Argument type mismatch at position {idx + 1}. "
          f"Expected '{param_type}', got '{arg_type}' "
          "(mutable 'var' array parameters are invariant in their element "
          "type).",
          node=arg,
        )
      elif (
        isinstance(effective_arg_type, MapType)
        and isinstance(param_type, MapType)
        and not isinstance(effective_arg_type.value_type, NoneType)
        and not isinstance(param_type.value_type, NoneType)
        and (
          not param_type.key_type.is_compatible(effective_arg_type.key_type)
          or not param_type.value_type.is_compatible(
            effective_arg_type.value_type
          )
        )
      ):
        self.error(
          f"Argument type mismatch at position {idx + 1}. "
          f"Expected '{param_type}', got '{arg_type}' "
          "(mutable 'var' map parameters are invariant in their key/value "
          "types).",
          node=arg,
        )

    if param_is_var and isinstance(arg.expr, IdentifierNode):
      sym = self.symbol_table.lookup(arg.expr.name)
      if (
        isinstance(sym, VariableSymbol)
        and isinstance(sym.symbol_type, ArrayType)
        and not sym.symbol_type.is_fixed_size
        and sym.symbol_type.size is not None
      ):
        sym.symbol_type = ArrayType(
          sym.symbol_type.element_type, size=None, is_fixed_size=False
        )

  def _check_range_arguments(
    self,
    arguments: list[ArgumentNode],
    call_node: CallNode | None = None,
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
    named_args: dict[str, ArgumentNode] = {}
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
          f"Argument type mismatch at position {idx + 1}. "
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

  def _finalize_call_eval_order(
    self,
    call_node: CallNode,
    arguments: list[ArgumentNode],
    callee_node: ASTNode | None,
    bound_slots: dict[int, ArgumentNode],
    arg_param_indices: list[int | None],
  ) -> None:
    """Attaches canonicalized argument order and eval-temp flags for codegen."""
    if not bound_slots:
      call_node._resolved_arguments = []
      call_node._omitted_arg_slots = set()
      call_node._requires_eval_order_temps = False
      call_node._eval_order_slots = []
      return

    max_idx = max(bound_slots.keys())
    call_node._resolved_arguments = [
      bound_slots[i].expr if i in bound_slots else LiteralNode(None, "none")
      for i in range(max_idx + 1)
    ]
    call_node._omitted_arg_slots = {
      i for i in range(max_idx + 1) if i not in bound_slots
    }
    valid_slots = [p for p in arg_param_indices if p is not None]
    is_reordered = any(
      valid_slots[k] > valid_slots[k + 1] for k in range(len(valid_slots) - 1)
    )
    eval_exprs: list[Any] = [a.expr for a in arguments]
    if isinstance(callee_node, MemberAccessNode):
      eval_exprs.append(callee_node.receiver)
    elif callee_node is not None and not isinstance(
      callee_node, IdentifierNode
    ):
      eval_exprs.append(callee_node)
    has_side_effects = any(not self._is_expr_pure(e) for e in eval_exprs)
    # Only emit evaluation-order temporaries when named args reorder impure
    # exprs.
    call_node._requires_eval_order_temps = bool(
      is_reordered and has_side_effects
    )
    call_node._eval_order_slots = valid_slots

  def _check_arguments(
    self,
    arguments: list[ArgumentNode],
    signature: FunctionType,
    is_constructor: bool = False,
    callee_node: ASTNode | None = None,
    call_node: CallNode | None = None,
  ) -> None:
    """Matches argument lists against signatures and canonicalizes call
    metadata.
    """
    if getattr(signature, "is_testing_assertion", False):
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
    bound_slots: dict[int, ArgumentNode] = {}
    arg_param_indices: list[int | None] = []
    has_binding_error = False

    for idx, arg in enumerate(arguments):
      param_idx: int | None = None
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
      self._finalize_call_eval_order(
        call_node, arguments, callee_node, bound_slots, arg_param_indices
      )
