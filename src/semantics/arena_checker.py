"""Arena scope & memory lifetime validation module for Sapphire.

Decouples arena dependency tracking, nested scope lifetime validation, and
reference escape checks from the monolithic TypeChecker.
"""

from typing import Any, Callable, Optional
from src.parser.ast import ASTNode, IdentifierNode, StructInitializerNode, CloneNode, CallNode
from src.semantics.symbol_table import SymbolTable, VariableSymbol


class ArenaChecker:
  """Helper class for validating arena allocations and scope lifetimes."""

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
