"""Arena lifetime and reference-aliasing validation helper for Sapphire.

Decouples arena escape checks, mutability/reassignment generation tracking,
transitivity, LIFO scope checking, and call-site mutable reference aliasing
checks from TypeChecker.
"""

from typing import Any, Callable, List, Optional, Set, Tuple

from src.parser.ast import (
  ArrayLiteralNode,
  AssignmentNode,
  ASTNode,
  BinaryOpNode,
  BlockNode,
  CallNode,
  CastExprNode,
  CloneNode,
  ExprStmtNode,
  ForNode,
  IdentifierNode,
  IfNode,
  IndexExprNode,
  LambdaNode,
  MapLiteralNode,
  MatchExprNode,
  MemberAccessNode,
  MoveNode,
  ReturnNode,
  StructInitializerNode,
  TernaryExprNode,
  UnaryOpNode,
  VarDeclNode,
  YieldNode,
)
from src.semantics.symbol_table import (
  ArenaType,
  ArrayType,
  CoroutineType,
  EnumType,
  FunctionType,
  GenericTypeParameter,
  InferredType,
  MapType,
  ModuleSymbol,
  NoneType,
  OptionalType,
  PrimitiveType,
  RangeType,
  RefType,
  SharedRefType,
  StringType,
  StructSymbol,
  StructType,
  SymbolTable,
  TraitType,
  Type,
  VariableSymbol,
  WeakRefType,
)


def _dedup_deps(deps: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
  """Deduplicates `(arena_name, generation)` pairs while preserving order."""
  seen: Set[Tuple[str, int]] = set()
  out: List[Tuple[str, int]] = []
  for item in deps:
    if item not in seen:
      seen.add(item)
      out.append(item)
  return out


class ArenaChecker:
  """Helper class for arena safety and aliasing checks."""

  @staticmethod
  def get_root_identifier(node: ASTNode) -> Optional[IdentifierNode]:
    """Extracts the base IdentifierNode from an lvalue or projection chain."""
    cur = node
    while True:
      if isinstance(cur, IdentifierNode):
        return cur
      if isinstance(cur, MemberAccessNode):
        cur = cur.receiver
      elif isinstance(cur, IndexExprNode):
        cur = cur.array
      else:
        return None

  @staticmethod
  def _is_scalar_non_arena_type(type_obj: Optional[Type]) -> bool:
    """Returns True if values of *type_obj* are copied scalars with no arena
    ptrs.
    """
    while isinstance(type_obj, OptionalType):
      type_obj = type_obj.base_type
    return isinstance(
      type_obj,
      (PrimitiveType, StringType, EnumType, RangeType, NoneType, ArenaType),
    )

  @staticmethod
  def _struct_implements_trait(
    struct_type: StructType,
    trait_type: TraitType,
    symbol_table: Optional[SymbolTable] = None,
  ) -> bool:
    """Returns True if *struct_type* implements *trait_type* (module-aware)."""
    impl_types = getattr(struct_type, "implemented_trait_types", None)
    if impl_types and trait_type.name in impl_types:
      return impl_types[trait_type.name] == trait_type
    return struct_type.implements_trait(trait_type, symbol_table)

  @staticmethod
  def _collect_trait_implementors(
    trait_type: TraitType,
    symbol_table: Optional[SymbolTable] = None,
    checker: Optional[Any] = None,
  ) -> List[StructType]:
    """Collects all known closed-world struct/proto implementors of a trait."""
    implementors: List[StructType] = []
    seen_ids: Set[int] = set()

    def _add(st: Any) -> None:
      if not isinstance(st, StructType):
        return
      obj_id = id(st)
      if obj_id in seen_ids:
        return
      if ArenaChecker._struct_implements_trait(st, trait_type, symbol_table):
        seen_ids.add(obj_id)
        implementors.append(st)

    for st in getattr(trait_type, "implementors", ()):
      _add(st)

    if symbol_table is not None:
      scope = getattr(symbol_table, "current_scope", None)
      visited_scopes: Set[int] = set()
      while scope is not None and id(scope) not in visited_scopes:
        visited_scopes.add(id(scope))
        for t in scope.types.values():
          _add(t)
        for sym in scope.symbols.values():
          if isinstance(sym, StructSymbol):
            _add(sym.symbol_type)
          elif isinstance(sym, ModuleSymbol):
            for exp in sym.exports.values():
              if isinstance(exp, StructSymbol):
                _add(exp.symbol_type)
        scope = scope.parent

    if checker is not None:
      checked_imports = getattr(checker, "_checked_import_results", None)
      if isinstance(checked_imports, dict):
        for entry in checked_imports.values():
          if isinstance(entry, tuple) and entry and isinstance(entry[0], dict):
            for exp in entry[0].values():
              if isinstance(exp, StructSymbol):
                _add(exp.symbol_type)

    return implementors

  @staticmethod
  def type_can_hold_arena_ref(
    type_obj: Optional[Type],
    seen: Optional[Set[str]] = None,
    is_box_check: bool = False,
    symbol_table: Optional[SymbolTable] = None,
    checker: Optional[Any] = None,
  ) -> bool:
    """Returns True if values of *type_obj* can contain an arena reference."""
    if type_obj is None or isinstance(type_obj, InferredType):
      return True
    if isinstance(type_obj, GenericTypeParameter):
      return True
    if isinstance(type_obj, TraitType):
      if not is_box_check or (symbol_table is None and checker is None):
        return True
      seen_set = set() if seen is None else seen
      trait_key = f"trait:{type_obj.defining_module or ''}:{type_obj.name}"
      if trait_key in seen_set:
        return False
      seen_set.add(trait_key)
      try:
        implementors = ArenaChecker._collect_trait_implementors(
          type_obj, symbol_table=symbol_table, checker=checker
        )
        return any(
          ArenaChecker.type_can_hold_arena_ref(
            impl_st,
            seen_set,
            is_box_check=True,
            symbol_table=symbol_table,
            checker=checker,
          )
          for impl_st in implementors
        )
      finally:
        seen_set.remove(trait_key)
    if isinstance(type_obj, FunctionType):
      if is_box_check:
        return any(
          ArenaChecker.type_can_hold_arena_ref(
            rt,
            seen,
            is_box_check=True,
            symbol_table=symbol_table,
            checker=checker,
          )
          for rt in type_obj.return_types
        )
      return True
    if isinstance(type_obj, OptionalType):
      return ArenaChecker.type_can_hold_arena_ref(
        type_obj.base_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      )
    if isinstance(type_obj, ArrayType):
      return ArenaChecker.type_can_hold_arena_ref(
        type_obj.element_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      )
    if isinstance(type_obj, MapType):
      return ArenaChecker.type_can_hold_arena_ref(
        type_obj.key_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      ) or ArenaChecker.type_can_hold_arena_ref(
        type_obj.value_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      )
    if isinstance(type_obj, CoroutineType):
      return ArenaChecker.type_can_hold_arena_ref(
        type_obj.yield_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      )
    if isinstance(type_obj, (RefType, SharedRefType, WeakRefType)):
      return ArenaChecker.type_can_hold_arena_ref(
        type_obj.inner_type,
        seen,
        is_box_check=is_box_check,
        symbol_table=symbol_table,
        checker=checker,
      )
    if isinstance(type_obj, StructType):
      if type_obj.is_prototype or not is_box_check:
        return True
      seen_set = set() if seen is None else seen
      struct_key = f"struct:{type_obj.defining_module or ''}:{type_obj.name}"
      if struct_key in seen_set:
        return False
      seen_set.add(struct_key)
      try:
        if any(
          ArenaChecker.type_can_hold_arena_ref(
            f.field_type,
            seen_set,
            is_box_check=is_box_check,
            symbol_table=symbol_table,
            checker=checker,
          )
          for f in type_obj.fields.values()
        ):
          return True
        for p_type in getattr(type_obj, "parent_types", ()):
          if ArenaChecker.type_can_hold_arena_ref(
            p_type,
            seen_set,
            is_box_check=is_box_check,
            symbol_table=symbol_table,
            checker=checker,
          ):
            return True
        if symbol_table is not None and not getattr(
          type_obj, "parent_types", ()
        ):
          for p_name in getattr(type_obj, "parent_names", ()):
            p_type = symbol_table.lookup_type(p_name)
            if isinstance(
              p_type, StructType
            ) and ArenaChecker.type_can_hold_arena_ref(
              p_type,
              seen_set,
              is_box_check=is_box_check,
              symbol_table=symbol_table,
              checker=checker,
            ):
              return True
        return False
      finally:
        seen_set.remove(struct_key)
    return False

  @staticmethod
  def type_contains_proto(
    type_obj: Optional[Type],
    seen: Optional[Set[str]] = None,
  ) -> bool:
    """Returns True if *type_obj* directly or transitively contains a proto."""
    if type_obj is None or isinstance(type_obj, InferredType):
      return False
    if isinstance(type_obj, FunctionType):
      return any(
        ArenaChecker.type_contains_proto(rt, seen)
        for rt in type_obj.return_types
      )
    if isinstance(type_obj, OptionalType):
      return ArenaChecker.type_contains_proto(type_obj.base_type, seen)
    if isinstance(type_obj, ArrayType):
      return ArenaChecker.type_contains_proto(type_obj.element_type, seen)
    if isinstance(type_obj, MapType):
      return ArenaChecker.type_contains_proto(
        type_obj.key_type, seen
      ) or ArenaChecker.type_contains_proto(type_obj.value_type, seen)
    if isinstance(type_obj, CoroutineType):
      return ArenaChecker.type_contains_proto(type_obj.yield_type, seen)
    if isinstance(type_obj, (RefType, SharedRefType, WeakRefType)):
      return ArenaChecker.type_contains_proto(type_obj.inner_type, seen)
    if isinstance(type_obj, StructType):
      if type_obj.is_prototype:
        return True
      seen_set = set() if seen is None else seen
      if type_obj.name in seen_set:
        return False
      seen_set.add(type_obj.name)
      try:
        return any(
          ArenaChecker.type_contains_proto(f.field_type, seen_set)
          for f in type_obj.fields.values()
        )
      finally:
        seen_set.remove(type_obj.name)
    return False

  @staticmethod
  def _resolve_arena_target(
    symbol_table: SymbolTable, arena_expr: ASTNode
  ) -> Optional[Tuple[str, Optional[VariableSymbol], int]]:
    """Resolves `(owner_name, symbol, generation)` for an `in <arena>` expr."""
    if isinstance(arena_expr, IdentifierNode):
      sym = symbol_table.lookup(arena_expr.name)
      if isinstance(sym, VariableSymbol):
        return (sym.name, sym, sym.arena_generation)
      return (arena_expr.name, None, 0)
    if isinstance(arena_expr, MemberAccessNode):
      root = ArenaChecker.get_root_identifier(arena_expr)
      if root is not None:
        sym = symbol_table.lookup(root.name)
        if isinstance(sym, VariableSymbol):
          return (sym.name, sym, sym.arena_generation)
        return (root.name, None, 0)
    return None

  @staticmethod
  def validate_arena_mutability(
    symbol_table: SymbolTable,
    arena_expr: ASTNode,
    error_callback: Callable[[str], None],
    checker: Any = None,
  ) -> None:
    """Enforces that `in <arena>` targets a mutable, non-moved Arena."""
    if isinstance(arena_expr, MoveNode):
      error_callback(f"Cannot allocate into moved Arena '{arena_expr.name}'.")
      return
    if (
      checker is not None
      and hasattr(checker, "has_shared_ref_base")
      and checker.has_shared_ref_base(arena_expr)
    ):
      error_callback(
        "Cannot allocate into Arena through deeply immutable 'SharedRef'."
      )
      return
    if isinstance(arena_expr, IdentifierNode):
      sym = symbol_table.lookup(arena_expr.name)
      if isinstance(sym, VariableSymbol):
        if sym.is_moved:
          error_callback(f"Cannot allocate into moved Arena '{sym.name}'.")
        elif not sym.is_mutable:
          error_callback(
            f"Cannot allocate into immutable Arena '{sym.name}'; "
            f"declare it with 'var'."
          )
      return
    if isinstance(arena_expr, MemberAccessNode):
      root = ArenaChecker.get_root_identifier(arena_expr)
      if root is None:
        error_callback(
          "Arena allocation target must be a mutable 'var' Arena variable, "
          "not a temporary expression."
        )
        return
      root_sym = symbol_table.lookup(root.name)
      if isinstance(root_sym, VariableSymbol):
        if root_sym.is_moved:
          error_callback(
            f"Cannot allocate into moved Arena owner '{root_sym.name}'."
          )
          return
        if not root_sym.is_mutable:
          error_callback(
            f"Cannot allocate into Arena through immutable binding "
            f"'{root_sym.name}'; declare it or its method with 'var'."
          )
          return
      if checker is not None:
        curr: Any = arena_expr
        while curr is not None:
          if isinstance(curr, MemberAccessNode):
            recv_type = checker.node_types.get(curr.receiver)
            if isinstance(recv_type, OptionalType):
              recv_type = recv_type.base_type
            if isinstance(recv_type, RefType):
              recv_type = recv_type.inner_type
            if isinstance(recv_type, StructType):
              field = recv_type.fields.get(curr.member)
              if field and not field.is_mutable:
                error_callback(
                  f"Cannot allocate into immutable Arena field "
                  f"'{curr.member}'; declare it with 'var'."
                )
                return
            curr = curr.receiver
          elif isinstance(curr, IndexExprNode):
            curr = curr.array
          else:
            break
      return
    error_callback(
      "Arena allocation target must be a mutable 'var' Arena variable, "
      "not a temporary expression."
    )

  @staticmethod
  def _collect_lambda_capture_deps(
    symbol_table: SymbolTable, lambda_node: LambdaNode
  ) -> List[Tuple[str, int]]:
    """Collects arena deps for outer variables captured inside a LambdaNode."""
    local_names: Set[str] = {p.name for p in lambda_node.parameters}
    deps: List[Tuple[str, int]] = []

    def walk(node: Any) -> None:
      if node is None:
        return
      if isinstance(node, list):
        for item in node:
          walk(item)
        return
      if isinstance(node, BlockNode):
        saved = set(local_names)
        walk(node.statements)
        local_names.clear()
        local_names.update(saved)
        return
      if isinstance(node, IfNode):
        saved = set(local_names)
        for b in getattr(node, "bindings", None) or []:
          walk(b.expr)
          for n in getattr(b, "let_names", None) or [b.let_name]:
            local_names.add(n)
        walk(node.condition)
        walk(node.then_block)
        local_names.clear()
        local_names.update(saved)
        walk(node.else_block)
        return
      if isinstance(node, ForNode):
        walk(node.iterable)
        saved = set(local_names)
        if node.key_var:
          local_names.add(node.key_var)
        if node.val_var:
          local_names.add(node.val_var)
        walk(node.block)
        local_names.clear()
        local_names.update(saved)
        return
      if isinstance(node, VarDeclNode):
        expr_list = getattr(node, "exprs", None) or (
          [node.expr] if getattr(node, "expr", None) else []
        )
        for e in expr_list:
          walk(e)
        for name in node.names:
          local_names.add(name)
        return
      if isinstance(node, IdentifierNode):
        if node.name not in local_names:
          sym = symbol_table.lookup(node.name)
          if isinstance(sym, VariableSymbol):
            if sym.arena_dep_records:
              deps.extend(sym.arena_dep_records)
            elif sym.arena_dependency:
              deps.append((sym.arena_dependency, 0))
        return
      if isinstance(node, MoveNode):
        if node.name not in local_names:
          sym = symbol_table.lookup(node.name)
          if isinstance(sym, VariableSymbol):
            if sym.arena_dep_records:
              deps.extend(sym.arena_dep_records)
            elif sym.arena_dependency:
              deps.append((sym.arena_dependency, 0))
        return
      if isinstance(node, LambdaNode):
        # Nested lambda: check its captures avoiding its own params
        saved = set(local_names)
        for p in node.parameters:
          local_names.add(p.name)
        walk(node.body)
        local_names.clear()
        local_names.update(saved)
        return
      if isinstance(node, ASTNode):
        for v in node.__dict__.values():
          if isinstance(v, (ASTNode, list)):
            walk(v)

    walk(lambda_node.body)
    return _dedup_deps(deps)

  @staticmethod
  def _collect_symbol_arena_deps(
    symbol_table: SymbolTable, name: str
  ) -> List[Tuple[str, int]]:
    """Returns `(arena_name, generation)` dependency records for variable
    *name*.
    """
    sym = symbol_table.lookup(name)
    if isinstance(sym, VariableSymbol):
      if sym.arena_dep_records:
        return list(sym.arena_dep_records)
      if sym.arena_dependency:
        return [(sym.arena_dependency, 0)]
    return []

  @staticmethod
  def _collect_match_arena_deps(
    symbol_table: SymbolTable, node: MatchExprNode, checker: Any
  ) -> List[Tuple[str, int]]:
    """Collects arena dependencies across all branches of a `match` expression.
    """
    deps: List[Tuple[str, int]] = []

    def walk_stmt(stmt: Any) -> None:
      if stmt is None:
        return
      if isinstance(stmt, BlockNode):
        for s in stmt.statements:
          walk_stmt(s)
      elif isinstance(stmt, IfNode):
        walk_stmt(stmt.then_block)
        walk_stmt(stmt.else_block)
      elif isinstance(stmt, YieldNode):
        exprs = getattr(stmt, "expressions", None) or (
          [stmt.expr] if getattr(stmt, "expr", None) else []
        )
        for yexpr in exprs:
          deps.extend(
            ArenaChecker.collect_arena_deps(symbol_table, yexpr, checker)
          )
      elif isinstance(stmt, ReturnNode):
        for rexpr in stmt.expressions:
          deps.extend(
            ArenaChecker.collect_arena_deps(symbol_table, rexpr, checker)
          )
      elif isinstance(stmt, ExprStmtNode):
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, stmt.expr, checker)
        )

    for case in node.cases:
      if isinstance(case.body, BlockNode):
        walk_stmt(case.body)
      else:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, case.body, checker)
        )
    return _dedup_deps(deps)

  @staticmethod
  def _collect_clone_init_deps(
    symbol_table: SymbolTable, stmts: List[ASTNode], checker: Any
  ) -> List[Tuple[str, int]]:
    """Collects arena deps stored via statements inside a `clone { ... }` block.
    """
    deps: List[Tuple[str, int]] = []

    def walk(stmt: Any) -> None:
      if stmt is None:
        return
      if isinstance(stmt, list):
        for item in stmt:
          walk(item)
        return
      if isinstance(stmt, BlockNode):
        walk(stmt.statements)
      elif isinstance(stmt, IfNode):
        walk(stmt.then_block)
        walk(stmt.else_block)
      elif isinstance(stmt, ForNode):
        walk(stmt.block)
      elif isinstance(stmt, AssignmentNode):
        for e in stmt.exprs:
          if not (isinstance(e, IdentifierNode) and e.name == "self"):
            deps.extend(
              ArenaChecker.collect_arena_deps(symbol_table, e, checker)
            )
      elif isinstance(stmt, ExprStmtNode):
        if isinstance(stmt.expr, CallNode):
          for arg in stmt.expr.arguments:
            if not (
              isinstance(arg.expr, IdentifierNode) and arg.expr.name == "self"
            ):
              deps.extend(
                ArenaChecker.collect_arena_deps(symbol_table, arg.expr, checker)
              )

    walk(stmts)
    return _dedup_deps(deps)

  @staticmethod
  def collect_arena_deps(
    symbol_table: SymbolTable, node: Any, checker: Any = None
  ) -> List[Tuple[str, int]]:
    """Collects all `(arena_name, generation)` dependencies of *node*."""
    if node is None:
      return []

    # Value types that cannot transitively hold arena-allocated `proto` refs
    # can never carry an arena dependency out of scope.
    if checker is not None and not isinstance(
      node, (StructInitializerNode, CloneNode, LambdaNode)
    ):
      expr_type = checker.node_types.get(node)
      if expr_type is not None and not ArenaChecker.type_can_hold_arena_ref(
        expr_type
      ):
        return []

    deps: List[Tuple[str, int]] = []

    if isinstance(node, StructInitializerNode):
      if node.arena_expr:
        resolved = ArenaChecker._resolve_arena_target(
          symbol_table, node.arena_expr
        )
        if resolved:
          deps.append((resolved[0], resolved[2]))
      for arg in node.fields:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, arg.expr, checker)
        )
      return _dedup_deps(deps)

    if isinstance(node, CallNode):
      # Constructing a new Arena() does not depend on an enclosing arena.
      if (
        isinstance(node.callee, IdentifierNode) and node.callee.name == "Arena"
      ):
        return []
      if node.arena_expr:
        resolved = ArenaChecker._resolve_arena_target(
          symbol_table, node.arena_expr
        )
        if resolved:
          deps.append((resolved[0], resolved[2]))
      if isinstance(node.callee, MemberAccessNode):
        deps.extend(
          ArenaChecker.collect_arena_deps(
            symbol_table, node.callee.receiver, checker
          )
        )
      else:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, node.callee, checker)
        )
      for arg in node.arguments:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, arg.expr, checker)
        )
      return _dedup_deps(deps)

    if isinstance(node, CloneNode):
      deps.extend(
        ArenaChecker.collect_arena_deps(symbol_table, node.expr, checker)
      )
      if node.arena_expr:
        resolved = ArenaChecker._resolve_arena_target(
          symbol_table, node.arena_expr
        )
        if resolved:
          deps.append((resolved[0], resolved[2]))
      if node.initializer_block:
        deps.extend(
          ArenaChecker._collect_clone_init_deps(
            symbol_table, node.initializer_block, checker
          )
        )
      return _dedup_deps(deps)

    if isinstance(node, (IdentifierNode, MoveNode)):
      return ArenaChecker._collect_symbol_arena_deps(symbol_table, node.name)

    if isinstance(node, MemberAccessNode):
      return ArenaChecker.collect_arena_deps(
        symbol_table, node.receiver, checker
      )

    if isinstance(node, IndexExprNode):
      return ArenaChecker.collect_arena_deps(symbol_table, node.array, checker)

    if isinstance(node, ArrayLiteralNode):
      for elem in node.elements:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, elem, checker)
        )
      return _dedup_deps(deps)

    if isinstance(node, MapLiteralNode):
      for entry in node.entries:
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, entry.key, checker)
        )
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, entry.value, checker)
        )
      return _dedup_deps(deps)

    if isinstance(node, TernaryExprNode):
      deps.extend(
        ArenaChecker.collect_arena_deps(symbol_table, node.true_expr, checker)
      )
      deps.extend(
        ArenaChecker.collect_arena_deps(symbol_table, node.false_expr, checker)
      )
      return _dedup_deps(deps)

    if isinstance(node, BinaryOpNode):
      if node.op == "??":
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, node.left, checker)
        )
        deps.extend(
          ArenaChecker.collect_arena_deps(symbol_table, node.right, checker)
        )
      return _dedup_deps(deps)

    if isinstance(node, (UnaryOpNode, CastExprNode)):
      return ArenaChecker.collect_arena_deps(symbol_table, node.expr, checker)

    if isinstance(node, MatchExprNode):
      return ArenaChecker._collect_match_arena_deps(symbol_table, node, checker)

    if isinstance(node, LambdaNode):
      return ArenaChecker._collect_lambda_capture_deps(symbol_table, node)

    return []

  @staticmethod
  def get_arena_dependency(
    symbol_table: SymbolTable, node: ASTNode
  ) -> Optional[str]:
    """Recursively finds the primary arena variable name an expression depends
    on.
    """
    deps = ArenaChecker.collect_arena_deps(symbol_table, node)
    return deps[0][0] if deps else None

  @staticmethod
  def is_descendant_scope(child: Any, parent: Any) -> bool:
    """Returns True if child scope is nested strictly inside parent scope."""
    curr = child
    while curr:
      if curr == parent:
        return True
      curr = curr.parent
    return False

  @staticmethod
  def symbol_outlives(
    target_sym: VariableSymbol, arena_sym: VariableSymbol
  ) -> bool:
    """Returns True if *target_sym* will be destroyed AFTER *arena_sym*."""
    if not target_sym.scope_defined or not arena_sym.scope_defined:
      return False
    if arena_sym.scope_defined == target_sym.scope_defined:
      return 0 < target_sym.decl_order < arena_sym.decl_order
    return ArenaChecker.is_descendant_scope(
      arena_sym.scope_defined, target_sym.scope_defined
    )

  @staticmethod
  def _merge_symbol_deps(
    target_sym: VariableSymbol,
    deps: List[Tuple[str, int]],
    replace: bool,
  ) -> None:
    """Updates `target_sym.arena_dep_records` and legacy `arena_dependency`."""
    if replace:
      target_sym.arena_dep_records = list(deps)
    else:
      target_sym.arena_dep_records = _dedup_deps(
        list(target_sym.arena_dep_records) + list(deps)
      )
    target_sym.arena_dependency = (
      target_sym.arena_dep_records[0][0]
      if target_sym.arena_dep_records
      else None
    )

  @staticmethod
  def _expr_may_carry_param_arena_ref(
    symbol_table: SymbolTable, node: Any, checker: Any = None
  ) -> bool:
    """Returns True if *node* may carry a caller-stack arena ref from a param.
    """
    if node is None:
      return False

    if checker is not None and not isinstance(
      node, (StructInitializerNode, CloneNode, LambdaNode)
    ):
      expr_type = checker.node_types.get(node)
      if expr_type is not None and not ArenaChecker.type_can_hold_arena_ref(
        expr_type, is_box_check=True
      ):
        return False

    if isinstance(node, (IdentifierNode, MoveNode)):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        if sym.has_param_arena_ref:
          return True
        if sym.is_parameter and ArenaChecker.type_can_hold_arena_ref(
          sym.symbol_type, is_box_check=True
        ):
          return True
      return False

    if isinstance(node, StructInitializerNode):
      return any(
        ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, arg.expr, checker
        )
        for arg in node.fields
      )

    if isinstance(node, CallNode):
      if (
        isinstance(node.callee, IdentifierNode) and node.callee.name == "Arena"
      ):
        return False
      if isinstance(node.callee, MemberAccessNode):
        if ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, node.callee.receiver, checker
        ):
          return True
      elif ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.callee, checker
      ):
        return True
      return any(
        ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, arg.expr, checker
        )
        for arg in node.arguments
      )

    if isinstance(node, CloneNode):
      return ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.expr, checker
      )

    if isinstance(node, MemberAccessNode):
      return ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.receiver, checker
      )

    if isinstance(node, IndexExprNode):
      return ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.array, checker
      )

    if isinstance(node, ArrayLiteralNode):
      return any(
        ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, elem, checker
        )
        for elem in node.elements
      )

    if isinstance(node, MapLiteralNode):
      return any(
        ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, entry.key, checker
        )
        or ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, entry.value, checker
        )
        for entry in node.entries
      )

    if isinstance(node, TernaryExprNode):
      return ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.true_expr, checker
      ) or ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.false_expr, checker
      )

    if isinstance(node, BinaryOpNode):
      if node.op == "??":
        return ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, node.left, checker
        ) or ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, node.right, checker
        )
      return False

    if isinstance(node, (UnaryOpNode, CastExprNode)):
      return ArenaChecker._expr_may_carry_param_arena_ref(
        symbol_table, node.expr, checker
      )

    if isinstance(node, MatchExprNode):
      for case in node.cases:
        if isinstance(case.body, BlockNode):
          for stmt in case.body.statements:
            if isinstance(stmt, YieldNode):
              exprs = getattr(stmt, "expressions", None) or (
                [stmt.expr] if getattr(stmt, "expr", None) else []
              )
              if any(
                ArenaChecker._expr_may_carry_param_arena_ref(
                  symbol_table, ye, checker
                )
                for ye in exprs
              ):
                return True
            elif isinstance(stmt, ReturnNode):
              if any(
                ArenaChecker._expr_may_carry_param_arena_ref(
                  symbol_table, re, checker
                )
                for re in stmt.expressions
              ):
                return True
            elif isinstance(stmt, ExprStmtNode):
              if ArenaChecker._expr_may_carry_param_arena_ref(
                symbol_table, stmt.expr, checker
              ):
                return True
        elif ArenaChecker._expr_may_carry_param_arena_ref(
          symbol_table, case.body, checker
        ):
          return True
      return False

    return False

  @staticmethod
  def validate_arena_escape(
    symbol_table: SymbolTable,
    target_sym: VariableSymbol,
    expr_node: ASTNode,
    error_callback: Callable[[str], None],
    checker: Any = None,
    is_partial_mutation: bool = False,
  ) -> None:
    """Checks for arena escape when binding/assigning expr_node into target_sym.
    """
    if not ArenaChecker.type_can_hold_arena_ref(target_sym.symbol_type):
      in_branch = bool(checker and getattr(checker, "_branch_depth", 0) > 0)
      if not is_partial_mutation and not in_branch:
        ArenaChecker._merge_symbol_deps(target_sym, [], replace=True)
        target_sym.has_param_arena_ref = False
      return

    has_param_ref = ArenaChecker._expr_may_carry_param_arena_ref(
      symbol_table, expr_node, checker
    )

    # Module-level globals outlive all local/caller stack arenas; reject storing
    # any explicit proto value or value carrying a borrowed parameter that may
    # hold a caller-stack arena reference (including behind a trait).
    is_module_global = (
      target_sym.scope_defined is not None
      and target_sym.scope_defined.parent is None
    )
    if (
      is_module_global
      and checker is not None
      and getattr(checker, "current_function", None) is not None
    ):
      expr_type = checker.node_types.get(expr_node)
      if has_param_ref or (
        expr_type is not None and ArenaChecker.type_contains_proto(expr_type)
      ):
        error_callback(
          f"Cannot store arena-referencing value of type '{expr_type}' "
          f"into module-level global '{target_sym.name}'."
        )
        return

    deps = ArenaChecker.collect_arena_deps(symbol_table, expr_node, checker)
    moved_self_name = (
      expr_node.name if isinstance(expr_node, MoveNode) else None
    )
    propagated_deps: List[Tuple[str, int]] = []
    for arena_name, dep_gen in deps:
      arena_sym = symbol_table.lookup(arena_name)
      if isinstance(arena_sym, VariableSymbol):
        if (
          moved_self_name is not None
          and arena_name == moved_self_name
          and arena_sym.arena_generation == dep_gen
        ):
          # Moving a self-contained Arena-owning struct transfers its arena
          # together with its self-allocated fields to target_sym.
          propagated_deps.append((target_sym.name, target_sym.arena_generation))
          continue
        if arena_sym.is_moved or arena_sym.arena_generation != dep_gen:
          error_callback(
            f"Cannot assign reference from moved or reassigned Arena "
            f"'{arena_name}' to '{target_sym.name}'."
          )
        elif target_sym is not arena_sym and ArenaChecker.symbol_outlives(
          target_sym, arena_sym
        ):
          if arena_sym.scope_defined == target_sym.scope_defined:
            error_callback(
              f"Variable '{target_sym.name}' cannot hold a reference to an "
              f"object allocated in later-declared arena '{arena_name}'."
            )
          else:
            error_callback(
              f"Variable '{target_sym.name}' in outer scope cannot hold a "
              f"reference to an object allocated in nested arena "
              f"'{arena_name}'."
            )
      propagated_deps.append((arena_name, dep_gen))

    in_branch = bool(checker and getattr(checker, "_branch_depth", 0) > 0)
    replace = not is_partial_mutation and not in_branch
    ArenaChecker._merge_symbol_deps(
      target_sym, _dedup_deps(propagated_deps), replace=replace
    )
    if replace:
      target_sym.has_param_arena_ref = has_param_ref
    elif has_param_ref:
      target_sym.has_param_arena_ref = True

  @staticmethod
  def validate_return_escape(
    symbol_table: SymbolTable,
    func_scope: Any,
    expr_node: ASTNode,
    error_callback: Callable[[str, ASTNode], None],
    is_local_scope_fn: Optional[Callable[[Any], bool]] = None,
    checker: Any = None,
  ) -> None:
    """Checks for arena escape when returning expr_node from a function."""
    if checker is not None:
      expr_type = checker.node_types.get(expr_node)
      if expr_type is not None and not ArenaChecker.type_can_hold_arena_ref(
        expr_type
      ):
        return

    deps = ArenaChecker.collect_arena_deps(symbol_table, expr_node, checker)
    moved_self_name = (
      expr_node.name if isinstance(expr_node, MoveNode) else None
    )
    for arena_name, dep_gen in deps:
      arena_sym = symbol_table.lookup(arena_name)
      if isinstance(arena_sym, VariableSymbol):
        if (
          moved_self_name is not None
          and arena_name == moved_self_name
          and arena_sym.arena_generation == dep_gen
        ):
          # Returning `move st` transfers st's own Arena and self-allocated
          # fields together to the caller.
          continue
        if arena_sym.is_moved or arena_sym.arena_generation != dep_gen:
          error_callback(
            f"Cannot return reference from moved or reassigned Arena "
            f"'{arena_name}'.",
            expr_node,
          )
          continue
        if is_local_scope_fn is not None:
          is_local = is_local_scope_fn(arena_sym.scope_defined)
        else:
          is_local = (
            arena_sym.scope_defined is not None
            and ArenaChecker.is_descendant_scope(
              arena_sym.scope_defined, func_scope
            )
          )
        if not arena_sym.is_parameter and is_local:
          error_callback(
            f"Cannot return a reference to an object allocated in local "
            f"arena '{arena_name}'.",
            expr_node,
          )

  @staticmethod
  def validate_cross_arena_clone(
    symbol_table: SymbolTable,
    clone_node: CloneNode,
    error_callback: Callable[[str], None],
    checker: Any = None,
  ) -> None:
    """Validates `clone` arena placement against source prototype arena."""
    if not clone_node.arena_expr:
      return
    ArenaChecker.validate_arena_mutability(
      symbol_table, clone_node.arena_expr, error_callback, checker=checker
    )
    dst = ArenaChecker._resolve_arena_target(
      symbol_table, clone_node.arena_expr
    )
    if not dst:
      return
    dst_name, dst_sym, dst_gen = dst
    src_deps = ArenaChecker.collect_arena_deps(
      symbol_table, clone_node.expr, checker
    )
    for src_name, src_gen in src_deps:
      if src_name == dst_name and src_gen == dst_gen:
        continue
      src_sym = symbol_table.lookup(src_name)
      if isinstance(src_sym, VariableSymbol) and (
        src_sym.is_moved or src_sym.arena_generation != src_gen
      ):
        error_callback(
          f"Cannot clone prototype from moved or reassigned Arena "
          f"'{src_name}' into Arena '{dst_name}'."
        )
        return
      if (
        isinstance(dst_sym, VariableSymbol)
        and isinstance(src_sym, VariableSymbol)
        and ArenaChecker.symbol_outlives(dst_sym, src_sym)
      ):
        error_callback(
          f"Cannot clone prototype from shorter-lived Arena '{src_name}' "
          f"into longer-lived Arena '{dst_name}'."
        )
        return

  @staticmethod
  def collect_stack_borrow_symbols(
    symbol_table: SymbolTable, node: Any, checker: Any = None
  ) -> Set[str]:
    from src.semantics.borrow_checker import BorrowChecker

    return BorrowChecker.collect_stack_borrow_symbols(
      symbol_table, node, checker
    )

  @staticmethod
  def validate_stack_borrow_escape(
    symbol_table: SymbolTable,
    target_sym: VariableSymbol,
    expr_node: ASTNode,
    error_callback: Callable[[str], None],
    checker: Any = None,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.validate_stack_borrow_escape(
      symbol_table, target_sym, expr_node, error_callback, checker
    )

  @staticmethod
  def validate_stack_borrow_return_escape(
    symbol_table: SymbolTable,
    func_scope: Any,
    expr_node: ASTNode,
    error_callback: Callable[[str, ASTNode], None],
    checker: Any = None,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.validate_stack_borrow_return_escape(
      symbol_table, func_scope, expr_node, error_callback, checker
    )

  @staticmethod
  def validate_heap_box_escape(
    symbol_table: SymbolTable,
    box_name: str,
    arg_expr: ASTNode,
    error_callback: Callable[[str], None],
    checker: Any = None,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.validate_heap_box_escape(
      symbol_table, box_name, arg_expr, error_callback, checker
    )

  @staticmethod
  def check_use_validity(
    symbol_table: SymbolTable,
    sym: VariableSymbol,
    error_callback: Callable[[str], None],
  ) -> bool:
    from src.semantics.borrow_checker import BorrowChecker

    return BorrowChecker.check_use_validity(symbol_table, sym, error_callback)

  @staticmethod
  def validate_container_mutation(
    checker: Any,
    receiver_expr: ASTNode,
    value_exprs: List[ASTNode],
    error_node: Optional[ASTNode] = None,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.validate_container_mutation(
      checker, receiver_expr, value_exprs, error_node
    )

  @staticmethod
  def check_call_var_sink_escape(
    checker: Any,
    node: CallNode,
    signature: FunctionType,
    is_constructor: bool = False,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.check_call_var_sink_escape(
      checker, node, signature, is_constructor
    )

  @staticmethod
  def get_lvalue_path(
    symbol_table: SymbolTable, node: ASTNode
  ) -> Optional[Tuple[str, List[str]]]:
    from src.semantics.borrow_checker import BorrowChecker

    return BorrowChecker.get_lvalue_path(symbol_table, node)

  @staticmethod
  def is_reference_type(type_obj: Type) -> bool:
    from src.semantics.borrow_checker import BorrowChecker

    return BorrowChecker.is_reference_type(type_obj)

  @staticmethod
  def check_aliasing(
    checker: Any,
    node: CallNode,
    signature: FunctionType,
    is_constructor: bool = False,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker

    BorrowChecker.check_aliasing(checker, node, signature, is_constructor)
