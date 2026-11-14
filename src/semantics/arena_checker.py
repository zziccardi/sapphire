"""Arena lifetime and reference-aliasing validation helper for Sapphire.

Decouples arena escape checks, mutability/reassignment generation tracking,
transitivity, LIFO scope checking, and call-site mutable reference aliasing
checks from TypeChecker.
"""

from typing import Any, Callable, List, Optional, Set, Tuple
from src.parser.ast import (
    ArrayLiteralNode,
    ASTNode,
    BinaryOpNode,
    BlockNode,
    CallNode,
    CastExprNode,
    CloneNode,
    ExprStmtNode,
    IdentifierNode,
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
    NoneType,
    OptionalType,
    PrimitiveType,
    RangeType,
    RefType,
    SharedRefType,
    StringType,
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
    """Returns True if values of *type_obj* are copied scalars with no arena ptrs."""
    while isinstance(type_obj, OptionalType):
      type_obj = type_obj.base_type
    return isinstance(
        type_obj,
        (PrimitiveType, StringType, EnumType, RangeType, NoneType, ArenaType),
    )

  @staticmethod
  def type_can_hold_arena_ref(
      type_obj: Optional[Type],
      seen: Optional[Set[str]] = None,
      is_box_check: bool = False,
  ) -> bool:
    """Returns True if values of *type_obj* can contain an arena reference."""
    if type_obj is None or isinstance(type_obj, InferredType):
      return True
    if isinstance(type_obj, (TraitType, GenericTypeParameter)):
      return True
    if isinstance(type_obj, FunctionType):
      if is_box_check:
        return any(
            ArenaChecker.type_can_hold_arena_ref(
                rt, seen, is_box_check=True
            )
            for rt in type_obj.return_types
        )
      return True
    if isinstance(type_obj, OptionalType):
      return ArenaChecker.type_can_hold_arena_ref(
          type_obj.base_type, seen, is_box_check=is_box_check
      )
    if isinstance(type_obj, ArrayType):
      return ArenaChecker.type_can_hold_arena_ref(
          type_obj.element_type, seen, is_box_check=is_box_check
      )
    if isinstance(type_obj, MapType):
      return (
          ArenaChecker.type_can_hold_arena_ref(
              type_obj.key_type, seen, is_box_check=is_box_check
          )
          or ArenaChecker.type_can_hold_arena_ref(
              type_obj.value_type, seen, is_box_check=is_box_check
          )
      )
    if isinstance(type_obj, CoroutineType):
      return ArenaChecker.type_can_hold_arena_ref(
          type_obj.yield_type, seen, is_box_check=is_box_check
      )
    if isinstance(type_obj, (RefType, SharedRefType, WeakRefType)):
      return ArenaChecker.type_can_hold_arena_ref(
          type_obj.inner_type, seen, is_box_check=is_box_check
      )
    if isinstance(type_obj, StructType):
      if type_obj.is_prototype or not is_box_check:
        return True
      seen_set = set() if seen is None else seen
      if type_obj.name in seen_set:
        return False
      seen_set.add(type_obj.name)
      try:
        return any(
            ArenaChecker.type_can_hold_arena_ref(
                f.field_type, seen_set, is_box_check=is_box_check
            )
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
        recv_type = checker.node_types.get(arena_expr.receiver)
        if isinstance(recv_type, StructType):
          field = recv_type.fields.get(arena_expr.member)
          if field and not field.is_mutable:
            error_callback(
                f"Cannot allocate into immutable Arena field "
                f"'{arena_expr.member}'; declare it with 'var'."
            )
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
      if isinstance(node, VarDeclNode):
        walk(node.expr)
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
  def collect_arena_deps(
      symbol_table: SymbolTable, node: Any, checker: Any = None
  ) -> List[Tuple[str, int]]:
    """Collects all `(arena_name, generation)` dependencies of *node*."""
    if node is None:
      return []

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
      if isinstance(node.callee, IdentifierNode) and node.callee.name == "Arena":
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
      return _dedup_deps(deps)

    if isinstance(node, IdentifierNode):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        if sym.arena_dep_records:
          return list(sym.arena_dep_records)
        if sym.arena_dependency:
          return [(sym.arena_dependency, 0)]
      return []

    if isinstance(node, MoveNode):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        if sym.arena_dep_records:
          return list(sym.arena_dep_records)
        if sym.arena_dependency:
          return [(sym.arena_dependency, 0)]
      return []

    if isinstance(node, MemberAccessNode):
      return ArenaChecker.collect_arena_deps(
          symbol_table, node.receiver, checker
      )

    if isinstance(node, IndexExprNode):
      return ArenaChecker.collect_arena_deps(
          symbol_table, node.array, checker
      )

    if isinstance(node, ArrayLiteralNode):
      for elem in node.elements:
        deps.extend(ArenaChecker.collect_arena_deps(symbol_table, elem, checker))
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
          ArenaChecker.collect_arena_deps(
              symbol_table, node.true_expr, checker
          )
      )
      deps.extend(
          ArenaChecker.collect_arena_deps(
              symbol_table, node.false_expr, checker
          )
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
      for case in node.cases:
        if isinstance(case.body, BlockNode):
          for stmt in case.body.statements:
            if isinstance(stmt, ReturnNode):
              for rexpr in stmt.expressions:
                deps.extend(
                    ArenaChecker.collect_arena_deps(
                        symbol_table, rexpr, checker
                    )
                )
            elif isinstance(stmt, ExprStmtNode):
              deps.extend(
                  ArenaChecker.collect_arena_deps(
                      symbol_table, stmt.expr, checker
                  )
              )
        else:
          deps.extend(
              ArenaChecker.collect_arena_deps(symbol_table, case.body, checker)
          )
      return _dedup_deps(deps)

    if isinstance(node, LambdaNode):
      return ArenaChecker._collect_lambda_capture_deps(symbol_table, node)

    return []

  @staticmethod
  def get_arena_dependency(symbol_table: SymbolTable, node: ASTNode) -> Optional[str]:
    """Recursively finds the primary arena variable name an expression depends on."""
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
  def validate_arena_escape(
      symbol_table: SymbolTable,
      target_sym: VariableSymbol,
      expr_node: ASTNode,
      error_callback: Callable[[str], None],
      checker: Any = None,
      is_partial_mutation: bool = False,
  ) -> None:
    """Checks for arena escape when binding/assigning expr_node into target_sym."""
    if not ArenaChecker.type_can_hold_arena_ref(target_sym.symbol_type):
      in_branch = bool(checker and getattr(checker, "_branch_depth", 0) > 0)
      if not is_partial_mutation and not in_branch:
        ArenaChecker._merge_symbol_deps(target_sym, [], replace=True)
      return

    deps = ArenaChecker.collect_arena_deps(symbol_table, expr_node, checker)
    for arena_name, dep_gen in deps:
      arena_sym = symbol_table.lookup(arena_name)
      if isinstance(arena_sym, VariableSymbol):
        if arena_sym.is_moved or arena_sym.arena_generation != dep_gen:
          error_callback(
              f"Cannot assign reference from moved or reassigned Arena "
              f"'{arena_name}' to '{target_sym.name}'."
          )
        elif (
            target_sym is not arena_sym
            and ArenaChecker.symbol_outlives(target_sym, arena_sym)
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

    in_branch = bool(checker and getattr(checker, "_branch_depth", 0) > 0)
    ArenaChecker._merge_symbol_deps(
        target_sym, deps, replace=(not is_partial_mutation and not in_branch)
    )

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
    for arena_name, dep_gen in deps:
      arena_sym = symbol_table.lookup(arena_name)
      if isinstance(arena_sym, VariableSymbol):
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
    dst = ArenaChecker._resolve_arena_target(symbol_table, clone_node.arena_expr)
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
    return BorrowChecker.collect_stack_borrow_symbols(symbol_table, node, checker)

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
      checker: Any, node: CallNode, signature: FunctionType,
      is_constructor: bool = False,
  ) -> None:
    from src.semantics.borrow_checker import BorrowChecker
    BorrowChecker.check_aliasing(checker, node, signature, is_constructor)
