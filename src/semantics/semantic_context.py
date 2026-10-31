"""Semantic analysis context and typing annotations for Sapphire.

Provides a unified SemanticContext container for AST node types, symbol tables,
call resolutions, and compiler diagnostics across semantic analysis passes and LSP tooling.
"""

from typing import Any, Dict, List, Optional
from src.parser.ast import ASTNode, CallNode
from src.semantics.symbol_table import SymbolTable, Type


class SemanticContext:
  """Container for type checking state, resolved types, and symbol table."""

  def __init__(self, symbol_table: Optional[SymbolTable] = None):
    self.symbol_table: SymbolTable = symbol_table or SymbolTable()
    self.node_types: Dict[ASTNode, Type] = {}
    self.call_resolutions: Dict[CallNode, Any] = {}
    self.errors: List[str] = []

  def record_type(self, node: ASTNode, typ: Type) -> None:
    """Associates an AST node with its resolved semantic Type."""
    if node is not None and typ is not None:
      self.node_types[node] = typ

  def get_type(self, node: Optional[ASTNode]) -> Optional[Type]:
    """Retrieves the resolved Type for an AST node, or None if unrecorded."""
    if node is None:
      return None
    return self.node_types.get(node)
