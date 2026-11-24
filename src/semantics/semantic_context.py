"""Semantic analysis context and typing annotations for Sapphire.

Provides a unified SemanticContext container for AST node types, symbol tables,
call resolutions, and compiler diagnostics across semantic analysis passes and
LSP tooling.
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple

from src.parser.ast import ASTNode, CallNode
from src.semantics.symbol_table import SymbolTable, Type


class TypeCheckerProtocol(Protocol):
  """Structural interface implemented by TypeChecker for helper passes."""

  symbol_table: SymbolTable
  node_types: Dict[ASTNode, Type]
  expected_type: Optional[Type]
  source_file_path: Optional[str]
  errors: List[str]
  warnings: List[str]
  _temporary_frozen_lvalues: List[Tuple[str, List[str], str]]

  def error(
    self, message: str, node: Optional[ASTNode] = None, **kwargs: Any
  ) -> None: ...
  def visit(self, node: ASTNode) -> Any: ...
  def has_shared_ref_base(self, node: ASTNode) -> bool: ...
  def get_frozen_lvalue_reason(
    self, root: str, path: List[str]
  ) -> Optional[str]: ...
  def _check_value_ownership_transfer(
    self, expr_node: ASTNode, expr_type: Type, node: Optional[ASTNode] = None
  ) -> None: ...
  def _resolve_type_node(self, type_node: Any) -> Type: ...
  def _resolve_return_types(self, decl: Any) -> Type: ...
  def _get_lvalue_path(
    self, node: ASTNode
  ) -> Optional[Tuple[str, List[str]]]: ...
  def _is_reference_type(self, type_obj: Type) -> bool: ...


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
