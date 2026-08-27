"""Abstract base class for all Sapphire transpiler backends.

Defines the visitor interface contract that every code-generation backend must
satisfy. Subclasses that omit any `@abstractmethod` will raise `TypeError` at
import time, making backend divergence impossible to miss.
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.parser.ast import (
    ASTNode,
    ArrayLiteralNode,
    AssignmentNode,
    BinaryOpNode,
    BlockNode,
    BreakNode,
    CastExprNode,
    CallNode,
    CloneNode,
    ContinueNode,
    EllipsisPatternNode,
    EnumDeclNode,
    ExportStmtNode,
    ExprStmtNode,
    ForNode,
    FuncDeclNode,
    IdentifierNode,
    IfNode,
    ImplMemberNode,
    IndexExprNode,
    InterpolatedStringNode,
    LambdaNode,
    LiteralNode,
    MapLiteralNode,
    MatchExprNode,
    MemberAccessNode,
    ProgramNode,
    ReturnNode,
    StructDeclNode,
    StructFieldNode,
    StructInitializerNode,
    TernaryExprNode,
    TraitDeclNode,
    UnaryOpNode,
    VarDeclNode,
    WhileNode,
    WithClauseNode,
    WithStmtNode,
    YieldNode,
    ImportStmtNode,
    BasicTypeNode,
    OptionalTypeNode,
    TypeNode,
)



def get_default_value_for_type_node(type_node: Optional[TypeNode]) -> Optional[ASTNode]:
  """Returns a reasonable default literal ASTNode for uninitialized variables and struct fields."""
  if type_node is None:
    return None
  if isinstance(type_node, OptionalTypeNode):
    return LiteralNode(value="none", lit_type="none")
  if isinstance(type_node, BasicTypeNode):
    if type_node.name == "int":
      return LiteralNode(value=0, lit_type="int")
    elif type_node.name == "float":
      return LiteralNode(value=0.0, lit_type="float")
    elif type_node.name == "bool":
      return LiteralNode(value=False, lit_type="bool")
  return None


class BaseTranspiler(ABC):
  """Abstract base for all Sapphire code-generation backends.

  Every concrete backend (e.g. `PythonTranspiler`, `LuaTranspiler`) must
  implement all visitor methods declared here. Python's `ABCMeta` machinery
  raises `TypeError` at *class definition time* if any `@abstractmethod` is
  left unimplemented, so a new AST node added to one backend but not the other
  will be caught immediately -- before any tests are even run.
  """

  # ------------------------------------------------------------------
  # Core interface
  # ------------------------------------------------------------------

  @abstractmethod
  def transpile(self, program: ProgramNode) -> str:
    """Transpile a fully-typed `ProgramNode` into target source code."""

  @abstractmethod
  def visit(self, node: ASTNode) -> None:
    """Dispatch *node* to the appropriate `visit_*` method."""

  @abstractmethod
  def generic_visit(self, node: ASTNode) -> None:
    """Called when no specific visitor exists; should raise `NotImplementedError`."""

  @abstractmethod
  def emit(self, text: str) -> None:
    """Append *text* to the output buffer."""

  @abstractmethod
  def newline(self) -> None:
    """Emit a newline followed by the current indentation."""

  @abstractmethod
  def indent(self) -> None:
    """Increase the indentation level by one."""

  @abstractmethod
  def dedent(self) -> None:
    """Decrease the indentation level by one."""

  @abstractmethod
  def get_output(self) -> str:
    """Return the accumulated output as a single string."""

  # ------------------------------------------------------------------
  # Declaration visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None: ...

  @abstractmethod
  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None: ...

  @abstractmethod
  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None: ...

  @abstractmethod
  def visit_StructDeclNode(self, node: StructDeclNode) -> None: ...

  @abstractmethod
  def visit_StructFieldNode(self, node: StructFieldNode) -> None: ...

  @abstractmethod
  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None: ...

  @abstractmethod
  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None: ...

  @abstractmethod
  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None: ...

  # ------------------------------------------------------------------
  # Statement visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_BlockNode(self, node: BlockNode) -> None: ...

  @abstractmethod
  def visit_VarDeclNode(self, node: VarDeclNode) -> None: ...

  @abstractmethod
  def visit_AssignmentNode(self, node: AssignmentNode) -> None: ...

  @abstractmethod
  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None: ...

  @abstractmethod
  def visit_ReturnNode(self, node: ReturnNode) -> None: ...

  @abstractmethod
  def visit_YieldNode(self, node: YieldNode) -> None: ...

  @abstractmethod
  def visit_MatchExprNode(self, node: MatchExprNode) -> None: ...

  @abstractmethod
  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None: ...

  @abstractmethod
  def visit_IfNode(self, node: IfNode) -> None: ...

  @abstractmethod
  def visit_WhileNode(self, node: WhileNode) -> None: ...

  @abstractmethod
  def visit_ForNode(self, node: ForNode) -> None: ...

  @abstractmethod
  def visit_BreakNode(self, node: BreakNode) -> None: ...

  @abstractmethod
  def visit_ContinueNode(self, node: ContinueNode) -> None: ...

  # ------------------------------------------------------------------
  # Expression visitors
  # ------------------------------------------------------------------

  @abstractmethod
  def visit_LiteralNode(self, node: LiteralNode) -> None: ...

  @abstractmethod
  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None: ...

  @abstractmethod
  def visit_IdentifierNode(self, node: IdentifierNode) -> None: ...

  @abstractmethod
  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None: ...

  @abstractmethod
  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None: ...

  @abstractmethod
  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None: ...

  @abstractmethod
  def visit_CastExprNode(self, node: CastExprNode) -> None: ...

  @abstractmethod
  def visit_CallNode(self, node: CallNode) -> None: ...

  @abstractmethod
  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None: ...

  @abstractmethod
  def visit_CloneNode(self, node: CloneNode) -> None: ...

  @abstractmethod
  def visit_LambdaNode(self, node: LambdaNode) -> None: ...

  @abstractmethod
  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None: ...

  @abstractmethod
  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None: ...

  @abstractmethod
  def visit_IndexExprNode(self, node: IndexExprNode) -> None: ...

  @abstractmethod
  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None: ...

  @abstractmethod
  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None: ...

  @abstractmethod
  def visit_GuardStmtNode(self, node: GuardStmtNode) -> None: ...

  @abstractmethod
  def visit_WithClauseNode(self, node: WithClauseNode) -> None: ...

  @abstractmethod
  def visit_WithStmtNode(self, node: WithStmtNode) -> None: ...
