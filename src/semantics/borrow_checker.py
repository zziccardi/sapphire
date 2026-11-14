"""Stack-borrow, heap-box, container-mutation, and aliasing checks.

Decouples stack-borrow escape analysis, use-after-move/reassignment
checks, container mutation freezes, and call-site mutable reference
aliasing checks from ArenaChecker.
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

from src.semantics.arena_checker import ArenaChecker


class BorrowChecker:
  """Validates stack borrows, container mutations, and call-site aliasing."""

  @staticmethod
  def collect_stack_borrow_symbols(
      symbol_table: SymbolTable, node: Any, checker: Any = None
  ) -> Set[str]:
    """Collects variable names of local stack borrows attached to *node*."""
    if node is None:
      return set()
    borrows = getattr(node, "stack_borrow_symbols", None)
    if borrows:
      return set(borrows)
    if isinstance(node, (IdentifierNode, MoveNode)):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol) and sym.stack_borrow_symbols:
        return set(sym.stack_borrow_symbols)
      return set()
    if isinstance(node, MemberAccessNode):
      return BorrowChecker.collect_stack_borrow_symbols(
          symbol_table, node.receiver, checker
      )
    if isinstance(node, IndexExprNode):
      return BorrowChecker.collect_stack_borrow_symbols(
          symbol_table, node.array, checker
      )
    if isinstance(node, (UnaryOpNode, CastExprNode)):
      return BorrowChecker.collect_stack_borrow_symbols(
          symbol_table, node.expr, checker
      )
    if isinstance(node, BinaryOpNode):
      out: Set[str] = set()
      out.update(
          BorrowChecker.collect_stack_borrow_symbols(
              symbol_table, node.left, checker
          )
      )
      out.update(
          BorrowChecker.collect_stack_borrow_symbols(
              symbol_table, node.right, checker
          )
      )
      return out
    if isinstance(node, TernaryExprNode):
      out = set()
      out.update(
          BorrowChecker.collect_stack_borrow_symbols(
              symbol_table, node.true_expr, checker
          )
      )
      out.update(
          BorrowChecker.collect_stack_borrow_symbols(
              symbol_table, node.false_expr, checker
          )
      )
      return out
    if isinstance(node, StructInitializerNode):
      out = set()
      for f in node.fields:
        out.update(
            BorrowChecker.collect_stack_borrow_symbols(
                symbol_table, f.expr, checker
            )
        )
      return out
    if isinstance(node, ArrayLiteralNode):
      out = set()
      for elem in node.elements:
        out.update(
            BorrowChecker.collect_stack_borrow_symbols(
                symbol_table, elem, checker
            )
        )
      return out
    if isinstance(node, MapLiteralNode):
      out = set()
      for entry in node.entries:
        out.update(
            BorrowChecker.collect_stack_borrow_symbols(
                symbol_table, entry.key, checker
            )
        )
        out.update(
            BorrowChecker.collect_stack_borrow_symbols(
                symbol_table, entry.value, checker
            )
        )
      return out
    return set()

  @staticmethod
  def validate_stack_borrow_escape(
      symbol_table: SymbolTable,
      target_sym: VariableSymbol,
      expr_node: ASTNode,
      error_callback: Callable[[str], None],
      checker: Any = None,
  ) -> None:
    """Rejects assigning a closure/coroutine stack borrow to target."""
    stack_borrows = BorrowChecker.collect_stack_borrow_symbols(
        symbol_table, expr_node, checker
    )
    is_closure = isinstance(expr_node, LambdaNode)
    if checker is not None:
      expr_type = checker.node_types.get(expr_node)
      if isinstance(expr_type, FunctionType):
        is_closure = True
    for name in sorted(stack_borrows):
      b_sym = symbol_table.lookup(name)
      if isinstance(b_sym, VariableSymbol):
        if target_sym is not b_sym and ArenaChecker.symbol_outlives(
            target_sym, b_sym
        ):
          kind = "Closure" if is_closure else "Coroutine"
          action = "capturing" if is_closure else "borrowing"
          error_callback(
              f"{kind} {action} local variable '{name}' cannot escape to outer "
              f"or earlier-declared variable '{target_sym.name}'."
          )
          return
    target_sym.stack_borrow_symbols.update(stack_borrows)

  @staticmethod
  def validate_stack_borrow_return_escape(
      symbol_table: SymbolTable,
      func_scope: Any,
      expr_node: ASTNode,
      error_callback: Callable[[str, ASTNode], None],
      checker: Any = None,
  ) -> None:
    """Rejects returning a closure/coroutine capturing local stack variables."""
    stack_borrows = BorrowChecker.collect_stack_borrow_symbols(
        symbol_table, expr_node, checker
    )
    is_closure = isinstance(expr_node, LambdaNode)
    if checker is not None:
      expr_type = checker.node_types.get(expr_node)
      if isinstance(expr_type, FunctionType):
        is_closure = True
    for name in sorted(stack_borrows):
      b_sym = symbol_table.lookup(name)
      if isinstance(b_sym, VariableSymbol):
        is_local = (
            b_sym.scope_defined is not None
            and ArenaChecker.is_descendant_scope(
                b_sym.scope_defined, func_scope
            )
        )
        if is_local:
          kind = "closure" if is_closure else "coroutine"
          action = "capturing" if is_closure else "borrowing"
          error_callback(
              f"Cannot return {kind} {action} local variable '{name}'.",
              expr_node,
          )
          return

  @staticmethod
  def validate_heap_box_escape(
      symbol_table: SymbolTable,
      box_name: str,
      arg_expr: ASTNode,
      error_callback: Callable[[str], None],
      checker: Any = None,
  ) -> None:
    """Rejects boxing arena-tied values into `Ref(...)` or `SharedRef(...)`."""
    stack_borrows = BorrowChecker.collect_stack_borrow_symbols(
        symbol_table, arg_expr, checker
    )
    if stack_borrows:
      name = sorted(stack_borrows)[0]
      error_callback(
          f"Cannot store closure or coroutine capturing local stack borrow "
          f"'{name}' inside '{box_name}'."
      )
      return
    deps = ArenaChecker.collect_arena_deps(symbol_table, arg_expr, checker)
    if deps:
      error_callback(
          f"Cannot box arena-dependent value from '{deps[0][0]}' "
          f"inside '{box_name}'."
      )
      return
    if checker is not None:
      arg_type = checker.node_types.get(arg_expr)
      if arg_type is not None and ArenaChecker.type_can_hold_arena_ref(
          arg_type, is_box_check=True
      ):
        error_callback(
            f"Cannot store arena-referencing type '{arg_type}' "
            f"inside '{box_name}'."
        )

  @staticmethod
  def check_use_validity(
      symbol_table: SymbolTable,
      sym: VariableSymbol,
      error_callback: Callable[[str], None],
  ) -> bool:
    """Verifies no arena backing *sym* has been moved or reassigned."""
    for arena_name, dep_gen in sym.arena_dep_records:
      arena_sym = symbol_table.lookup(arena_name)
      if isinstance(arena_sym, VariableSymbol):
        if arena_sym.is_moved:
          error_callback(
              f"Cannot use '{sym.name}' because its Arena '{arena_name}' "
              f"has been moved."
          )
          return False
        if arena_sym.arena_generation != dep_gen:
          error_callback(
              f"Cannot use '{sym.name}' because its Arena '{arena_name}' "
              f"was reassigned or reset."
          )
          return False
    return True

  @staticmethod
  def validate_container_mutation(
      checker: Any,
      receiver_expr: ASTNode,
      value_exprs: List[ASTNode],
      error_node: Optional[ASTNode] = None,
  ) -> None:
    """Propagates arena deps from *value_exprs* into *receiver_expr*'s root."""
    root = ArenaChecker.get_root_identifier(receiver_expr)
    if root is None:
      return
    recv_sym = checker.symbol_table.lookup(root.name)
    if not isinstance(recv_sym, VariableSymbol):
      return
    existing_arena_deps = list(recv_sym.arena_dep_records)
    for val_expr in value_exprs:
      ArenaChecker.validate_arena_escape(
          checker.symbol_table,
          recv_sym,
          val_expr,
          lambda msg: checker.error(msg, node=error_node or val_expr),
          checker=checker,
          is_partial_mutation=True,
      )
      BorrowChecker.validate_stack_borrow_escape(
          checker.symbol_table,
          recv_sym,
          val_expr,
          lambda msg: checker.error(msg, node=error_node or val_expr),
          checker=checker,
      )
      val_deps = ArenaChecker.collect_arena_deps(
          checker.symbol_table, val_expr, checker
      )
      for a_name, _ in existing_arena_deps:
        a_sym = checker.symbol_table.lookup(a_name)
        if not isinstance(a_sym, VariableSymbol):
          continue
        for b_name, _ in val_deps:
          if a_name == b_name:
            continue
          b_sym = checker.symbol_table.lookup(b_name)
          if isinstance(b_sym, VariableSymbol) and ArenaChecker.symbol_outlives(
              a_sym, b_sym
          ):
            checker.error(
                f"Cannot store reference from shorter-lived Arena '{b_name}' "
                f"inside object tied to Arena '{a_name}'.",
                node=error_node or val_expr,
            )

  @staticmethod
  def check_call_var_sink_escape(
      checker: Any,
      node: CallNode,
      signature: FunctionType,
      is_constructor: bool = False,
  ) -> None:
    """Validates arena transfers into `var` parameters or mutating receivers."""
    arg_exprs = [a.expr for a in node.arguments]
    if isinstance(node.callee, MemberAccessNode):
      recv_expr = node.callee.receiver
      # If mutating method on variable receiver (or receiver symbol is Arena-aware),
      # check whether any arg escapes into receiver's outer scope/lifetime.
      recv_type = checker.node_types.get(recv_expr)
      method_is_mutating = False
      if isinstance(recv_type, StructType):
        method = recv_type.methods.get(node.callee.member)
        if method and method.modifier == "var":
          method_is_mutating = True
      if method_is_mutating and arg_exprs:
        BorrowChecker.validate_container_mutation(
            checker, recv_expr, arg_exprs, error_node=node
        )

    param_muts = signature.param_mutabilities or []
    param_names = getattr(signature, "param_names", None) or []
    if (
        getattr(signature, "has_self", False)
        and isinstance(node.callee, MemberAccessNode)
        and not is_constructor
    ):
      param_muts = param_muts[1:]
      param_names = param_names[1:] if param_names else []

    var_indices: List[int] = []
    for idx, arg in enumerate(node.arguments):
      param_idx = idx
      if arg.name and param_names and arg.name in param_names:
        param_idx = param_names.index(arg.name)
      if param_idx < len(param_muts) and param_muts[param_idx]:
        var_indices.append(idx)

    if not var_indices:
      return

    other_exprs: List[ASTNode] = list(arg_exprs)
    if isinstance(node.callee, MemberAccessNode):
      other_exprs.append(node.callee.receiver)

    for v_idx in var_indices:
      sink_expr = node.arguments[v_idx].expr
      source_exprs = [
          expr for j, expr in enumerate(other_exprs) if j != v_idx
      ]
      if source_exprs:
        BorrowChecker.validate_container_mutation(
            checker, sink_expr, source_exprs, error_node=node
        )

  @staticmethod
  def get_lvalue_path(symbol_table: SymbolTable, node: ASTNode) -> Optional[Tuple[str, List[str]]]:
    """Resolves an AST node to its root variable name and field path if it is an lvalue."""
    if isinstance(node, IdentifierNode):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        return (node.name, [])
    elif isinstance(node, MemberAccessNode):
      res = BorrowChecker.get_lvalue_path(symbol_table, node.receiver)
      if res is not None:
        root, path = res
        return (root, path + [node.member])
    elif isinstance(node, IndexExprNode):
      res = BorrowChecker.get_lvalue_path(symbol_table, node.array)
      if res is not None:
        root, path = res
        return (root, path + ["[]"])
    return None

  @staticmethod
  def is_reference_type(type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    if isinstance(type_obj, OptionalType):
      return BorrowChecker.is_reference_type(type_obj.base_type)
    if isinstance(type_obj, PrimitiveType):
      return False
    if isinstance(type_obj, NoneType):
      return False
    return True

  @staticmethod
  def check_aliasing(checker: Any, node: CallNode, signature: FunctionType, is_constructor: bool = False) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    borrows: List[Tuple[str, List[str], bool]] = []

    # 1. Check implicit self receiver for non-static method calls
    if not is_constructor and isinstance(node.callee, MemberAccessNode):
      receiver_node = node.callee.receiver
      receiver_type = checker.visit(receiver_node)
      if isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type
      is_shared_ref = False
      if isinstance(receiver_type, SharedRefType):
        is_shared_ref = True
        receiver_type = receiver_type.inner_type
      elif isinstance(receiver_type, RefType):
        receiver_type = receiver_type.inner_type
      if checker.has_shared_ref_base(receiver_node):
        is_shared_ref = True

      if isinstance(receiver_type, StructType):
        method = receiver_type.get_method(node.callee.member, checker.symbol_table)
        if method and method.modifier != "static":
          is_mutable = (method.modifier == "var")
          if is_mutable and is_shared_ref:
            checker.error(
                f"Cannot invoke mutating method '{node.callee.member}' "
                "through deeply immutable 'SharedRef'.",
                node=node,
            )
          res = checker._get_lvalue_path(receiver_node)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))
            if is_mutable:
              reason = checker.get_frozen_lvalue_reason(root, path)
              if reason:
                checker.error(
                    f"Cannot invoke mutating method '{node.callee.member}' "
                    f"on '{root}' while it is frozen ({reason}).",
                    node=node,
                )
              root_sym = checker.symbol_table.lookup(root)
              if (
                  isinstance(root_sym, VariableSymbol)
                  and not root_sym.is_mutable
              ):
                checker.error(
                    f"Cannot invoke mutating method '{node.callee.member}' "
                    f"on constant variable '{root}'."
                )

    # 2. Check explicit arguments
    expected_param_types = signature.param_types
    expected_param_names = signature.param_names or []
    expected_mutabilities = signature.param_mutabilities
    if (
        not is_constructor
        and getattr(signature, "has_self", False)
        and isinstance(node.callee, MemberAccessNode)
    ):
      expected_param_types = signature.param_types[1:]
      expected_param_names = (
          signature.param_names[1:] if signature.param_names else []
      )
      muts = signature.param_mutabilities
      expected_mutabilities = muts[1:] if muts else []

    for idx, arg in enumerate(node.arguments):
      param_idx = idx
      if arg.name and expected_param_names and arg.name in expected_param_names:
        param_idx = expected_param_names.index(arg.name)
      if param_idx < len(expected_param_types):
        param_type = expected_param_types[param_idx]
        is_mutable = (
            expected_mutabilities[param_idx]
            if param_idx < len(expected_mutabilities)
            else False
        )
        if checker._is_reference_type(param_type):
          if is_mutable and checker.has_shared_ref_base(arg.expr):
            checker.error(
                "Cannot pass field of deeply immutable 'SharedRef' "
                "to mutable 'var' parameter.",
                node=node,
            )
          res = checker._get_lvalue_path(arg.expr)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))
            if is_mutable:
              reason = checker.get_frozen_lvalue_reason(root, path)
              if reason:
                checker.error(
                    f"Cannot pass '{root}' to 'var' parameter while it is "
                    f"frozen ({reason}).",
                    node=node,
                )
              root_sym = checker.symbol_table.lookup(root)
              if (
                  isinstance(root_sym, VariableSymbol)
                  and not root_sym.is_mutable
              ):
                checker.error(
                    f"Cannot pass constant variable '{root}' to mutable 'var' "
                    "parameter."
                )

    # 3. Check for conflicts among all borrows
    for i in range(len(borrows)):
      for j in range(i + 1, len(borrows)):
        r1, p1, m1 = borrows[i]
        r2, p2, m2 = borrows[j]
        if r1 == r2:
          overlap = p1[:len(p2)] == p2 or p2[:len(p1)] == p1
          if overlap and (m1 or m2):
            hint = ""
            if "[]" in p1 and "[]" in p2:
              hint = (
                  f" Hint: To swap two elements in a collection, use "
                  f"'{r1}.swap(i, j)'. To pass an element while modifying "
                  f"another, bind a local snapshot or process elements "
                  f"sequentially."
              )
            elif (not p1 and p2) or (not p2 and p1):
              field_path = ".".join(p2 if p2 else p1)
              hint = (
                  f" Hint: Invoking a mutating method on '{r1}' conflicts with "
                  f"borrowing its field '{r1}.{field_path}'. Bind the field to "
                  f"a local variable before the call, or pass individual fields "
                  f"directly."
              )
            checker.error(
                f"Aliasing conflict: variable '{r1}' (or a sub-field) "
                f"is mutably borrowed and cannot be borrowed again in the same "
                f"call.{hint}"
            )
        else:
          sym1 = checker.symbol_table.lookup(r1)
          sym2 = checker.symbol_table.lookup(r2)
          if (
              isinstance(sym1, VariableSymbol)
              and isinstance(sym2, VariableSymbol)
          ):
            if m1 and (r1 in getattr(sym2, "proto_ancestors", set())):
              checker.error(
                  f"Aliasing conflict: prototype '{r1}' is mutably borrowed "
                  f"while its cloned descendant '{r2}' is borrowed in the same "
                  "call.",
                  node=node,
              )
            elif m2 and (r2 in getattr(sym1, "proto_ancestors", set())):
              checker.error(
                  f"Aliasing conflict: prototype '{r2}' is mutably borrowed "
                  f"while its cloned descendant '{r1}' is borrowed in the same "
                  "call.",
                  node=node,
              )
