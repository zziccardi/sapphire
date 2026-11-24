"""Semantic analysis context and typing annotations for Sapphire.

Provides a unified SemanticContext container for AST node types, symbol tables,
call resolutions, closure captures, and compiler diagnostics across semantic
analysis passes, code generators, and LSP tooling.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from sapphire.common.diagnostics import Diagnostic
from sapphire.parser.ast import ASTNode, CallNode, LambdaNode, MatchExprNode
from sapphire.semantics.symbol_table import SymbolTable, Type


@dataclass(frozen=True)
class CallResolution:
  """Resolved semantic dispatch metadata for a CallNode."""

  kind: str
  method_name: str | None = None
  receiver_type: Type | None = None
  is_auto_deref: bool = False


@dataclass
class ClosureCaptures:
  """Resolved variable captures for a LambdaNode."""

  read: set[str] = field(default_factory=set)
  mutated: set[str] = field(default_factory=set)


class TypeCheckerProtocol(Protocol):
  """Public structural interface implemented by TypeChecker for helpers."""

  symbol_table: SymbolTable
  node_types: dict[ASTNode, Type]
  expected_type: Type | None
  source_file_path: str | None
  errors: list[str]
  warnings: list[str]
  temporary_frozen_lvalues: list[tuple[str, list[str], str]]

  def error(
    self, message: str, node: ASTNode | None = None, **kwargs: Any
  ) -> None: ...
  def visit(self, node: ASTNode) -> Any: ...
  def has_shared_ref_base(self, node: ASTNode) -> bool: ...
  def get_frozen_lvalue_reason(
    self, root: str, path: list[str]
  ) -> str | None: ...
  def find_immutable_field_in_chain(self, expr: ASTNode) -> Any: ...
  def check_value_ownership_transfer(
    self, expr_node: ASTNode, expr_type: Type, node: ASTNode | None = None
  ) -> None: ...
  def resolve_type_node(self, type_node: Any) -> Type: ...
  def resolve_return_types(self, decl: Any) -> Type: ...
  def get_lvalue_path(self, node: ASTNode) -> tuple[str, list[str]] | None: ...
  def is_reference_type(self, type_obj: Type) -> bool: ...


class SemanticContext:
  """Container for type checking state, resolved side-tables, and symbols."""

  def __init__(self, symbol_table: SymbolTable | None = None) -> None:
    self.symbol_table: SymbolTable = symbol_table or SymbolTable()
    self.node_types: dict[ASTNode, Type] = {}
    self.call_resolutions: dict[CallNode, CallResolution] = {}
    self.closure_captures: dict[LambdaNode, ClosureCaptures] = {}
    self.exhaustive_matches: set[MatchExprNode] = set()
    self.diagnostics: list[Diagnostic] = []
    self.errors: list[str] = []

  def record_type(self, node: ASTNode | None, typ: Type | None) -> None:
    """Associates an AST node with its resolved semantic Type."""
    if node is not None and typ is not None:
      self.node_types[node] = typ

  def get_type(self, node: ASTNode | None) -> Type | None:
    """Retrieves the resolved Type for an AST node, or None if unrecorded."""
    if node is None:
      return None
    return self.node_types.get(node)

  def record_call(
    self, node: CallNode, resolution: CallResolution
  ) -> None:
    """Associates a CallNode with its resolved dispatch metadata."""
    self.call_resolutions[node] = resolution

  def get_call(self, node: CallNode | None) -> CallResolution | None:
    """Retrieves resolved dispatch metadata for a CallNode, if recorded."""
    if node is None:
      return None
    return self.call_resolutions.get(node)

  def record_closure_captures(
    self, node: LambdaNode, captures: ClosureCaptures
  ) -> None:
    """Associates a LambdaNode with its captured variable sets."""
    self.closure_captures[node] = captures

  def get_closure_captures(
    self, node: LambdaNode | None
  ) -> ClosureCaptures | None:
    """Retrieves recorded capture sets for a LambdaNode, if any."""
    if node is None:
      return None
    return self.closure_captures.get(node)

  def mark_exhaustive_match(self, node: MatchExprNode) -> None:
    """Marks a MatchExprNode as exhaustively covering all cases."""
    self.exhaustive_matches.add(node)

  def is_exhaustive_match(self, node: MatchExprNode | None) -> bool:
    """Returns True if *node* was proven exhaustive during type checking."""
    return node is not None and node in self.exhaustive_matches
