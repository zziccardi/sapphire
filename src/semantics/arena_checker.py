"""Arena scope, borrow checking, & memory lifetime validation module for Sapphire.

Decouples arena dependency tracking, nested scope lifetime validation, reference
escape checks, and call-site aliasing/borrow checking from TypeChecker.
"""

from typing import Any, Callable, List, Optional, Tuple
from src.parser.ast import (
    ASTNode,
    CallNode,
    CloneNode,
    IdentifierNode,
    IndexExprNode,
    MemberAccessNode,
    StructInitializerNode,
)
from src.semantics.symbol_table import (
    FunctionType,
    NoneType,
    OptionalType,
    PrimitiveType,
    StructType,
    SymbolTable,
    Type,
    VariableSymbol,
)


class ArenaChecker:
  """Helper class for validating arena allocations, scope lifetimes, and call-site borrows."""

  @staticmethod
  def get_arena_dependency(symbol_table: SymbolTable, node: ASTNode) -> Optional[str]:
    """Inspects an AST node to extract its underlying arena dependency string."""
    if isinstance(node, IdentifierNode):
      symbol = symbol_table.lookup(node.name)
      if isinstance(symbol, VariableSymbol):
        return symbol.arena_dependency
    elif isinstance(node, StructInitializerNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
    elif isinstance(node, CallNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
    elif isinstance(node, CloneNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
      else:
        return ArenaChecker.get_arena_dependency(symbol_table, node.expr)
    return None

  @staticmethod
  def is_descendant_scope(child: Optional[Any], parent: Optional[Any]) -> bool:
    """Returns True if child scope is nested within parent scope hierarchy."""
    curr = child
    while curr:
      if curr == parent:
        return True
      curr = getattr(curr, "parent", None)
    return False

  @staticmethod
  def validate_arena_escape(
      symbol_table: SymbolTable,
      target_sym: VariableSymbol,
      expr_node: ASTNode,
      error_fn: Callable[[str], None],
  ) -> None:
    """Validates that a reference allocated in an inner arena scope does not escape to outer variable."""
    arena_dep = ArenaChecker.get_arena_dependency(symbol_table, expr_node)
    if not arena_dep:
      return

    target_sym.arena_dependency = arena_dep
    arena_sym = symbol_table.lookup(arena_dep)
    if not arena_sym:
      return

    arena_scope = getattr(arena_sym, "scope_defined", getattr(arena_sym, "scope", None))
    target_scope = getattr(target_sym, "scope_defined", getattr(target_sym, "scope", None))

    if arena_scope and target_scope and arena_scope != target_scope:
      if ArenaChecker.is_descendant_scope(arena_scope, target_scope):
        error_fn(
            f"Variable '{target_sym.name}' in outer scope cannot hold a reference to an object "
            f"allocated in nested arena '{arena_dep}'."
        )

  @staticmethod
  def get_lvalue_path(symbol_table: SymbolTable, node: ASTNode) -> Optional[Tuple[str, List[str]]]:
    """Resolves an AST node to its root variable name and field path if it is an lvalue."""
    if isinstance(node, IdentifierNode):
      sym = symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        return (node.name, [])
    elif isinstance(node, MemberAccessNode):
      res = ArenaChecker.get_lvalue_path(symbol_table, node.receiver)
      if res is not None:
        root, path = res
        return (root, path + [node.member])
    elif isinstance(node, IndexExprNode):
      res = ArenaChecker.get_lvalue_path(symbol_table, node.array)
      if res is not None:
        root, path = res
        return (root, path + ["[]"])
    return None

  @staticmethod
  def is_reference_type(type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    if isinstance(type_obj, OptionalType):
      return ArenaChecker.is_reference_type(type_obj.base_type)
    if isinstance(type_obj, PrimitiveType):
      return False
    if isinstance(type_obj, NoneType):
      return False
    return True

  @staticmethod
  def check_aliasing(checker: Any, node: CallNode, signature: FunctionType, is_constructor: bool) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    borrows: List[Tuple[str, List[str], bool]] = []

    # 1. Check implicit self receiver for non-static method calls
    if not is_constructor and isinstance(node.callee, MemberAccessNode):
      receiver_node = node.callee.receiver
      receiver_type = checker.visit(receiver_node)
      if isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type
      if isinstance(receiver_type, StructType):
        method = receiver_type.get_method(node.callee.member, checker.symbol_table)
        if method and method.modifier != "static":
          is_mutable = (method.modifier == "var")
          res = checker._get_lvalue_path(receiver_node)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))
            if is_mutable:
              root_sym = checker.symbol_table.lookup(root)
              if isinstance(root_sym, VariableSymbol) and not root_sym.is_mutable:
                checker.error(f"Cannot invoke mutating method '{node.callee.member}' on constant variable '{root}'.")

    # 2. Check explicit arguments
    expected_param_types = signature.param_types
    expected_param_names = signature.param_names or []
    expected_mutabilities = signature.param_mutabilities
    if not is_constructor and getattr(signature, "has_self", False) and isinstance(node.callee, MemberAccessNode):
      expected_param_types = signature.param_types[1:]
      expected_param_names = signature.param_names[1:] if signature.param_names else []
      expected_mutabilities = signature.param_mutabilities[1:] if signature.param_mutabilities else []

    for idx, arg in enumerate(node.arguments):
      param_idx = idx
      if arg.name and expected_param_names and arg.name in expected_param_names:
        param_idx = expected_param_names.index(arg.name)
      if param_idx < len(expected_param_types):
        param_type = expected_param_types[param_idx]
        is_mutable = expected_mutabilities[param_idx] if param_idx < len(expected_mutabilities) else False
        if checker._is_reference_type(param_type):
          res = checker._get_lvalue_path(arg.expr)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))
            if is_mutable:
              root_sym = checker.symbol_table.lookup(root)
              if isinstance(root_sym, VariableSymbol) and not root_sym.is_mutable:
                checker.error(f"Cannot pass constant variable '{root}' to mutable 'var' parameter.")

    # 3. Check for conflicts among all borrows
    for i in range(len(borrows)):
      for j in range(i + 1, len(borrows)):
        r1, p1, m1 = borrows[i]
        r2, p2, m2 = borrows[j]
        if r1 == r2:
          overlap = p1[:len(p2)] == p2 or p2[:len(p1)] == p1
          if overlap and (m1 or m2):
            checker.error(
                f"Aliasing conflict: variable '{r1}' (or a sub-field) "
                f"is mutably borrowed and cannot be borrowed again in the same call."
            )
