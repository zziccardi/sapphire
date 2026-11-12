"""Abstract base class for all Sapphire transpiler backends.

Defines the visitor interface contract that every code-generation backend must
satisfy. Subclasses that omit any `@abstractmethod` will raise `TypeError` at
import time, making backend divergence impossible to miss.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Union

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
    GuardClauseNode,
    GuardStmtNode,
    IdentifierNode,
    IfNode,
    ImplBlockNode,
    ImplMemberNode,
    IndexExprNode,
    InterpolatedStringNode,
    LambdaNode,
    LiteralNode,
    MapLiteralNode,
    MatchExprNode,
    MemberAccessNode,
    MoveNode,
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


def is_coroutine_func(node: Optional[ASTNode]) -> bool:
  """Returns True if a FuncDeclNode, ImplMemberNode, or FunctionType returns Coroutine."""
  if node is None:
    return False
  func_node = getattr(node, "func_decl", node)
  if getattr(func_node, "return_types", None):
    for t in func_node.return_types:
      if isinstance(t, BasicTypeNode) and t.name == "Coroutine":
        return True
  if getattr(func_node, "return_type", None):
    if isinstance(func_node.return_type, BasicTypeNode) and func_node.return_type.name == "Coroutine":
      return True
  return False


def extract_type_name(t_node: Optional[ASTNode]) -> Optional[str]:
  """Extracts the base type name from a TypeNode."""
  if t_node is None:
    return None
  if hasattr(t_node, "base_type"):
    return extract_type_name(t_node.base_type)
  if hasattr(t_node, "name"):
    return t_node.name
  return None


def get_return_type_names(func_node: ASTNode) -> List[str]:
  """Extracts all return type names from a FuncDeclNode."""
  res: List[str] = []
  if hasattr(func_node, "return_types") and func_node.return_types:
    for t in func_node.return_types:
      name = extract_type_name(t)
      if name:
        res.append(name)
  elif hasattr(func_node, "return_type") and func_node.return_type:
    name = extract_type_name(func_node.return_type)
    if name:
      res.append(name)
  return res


class BaseTranspiler(ABC):
  """Abstract base for all Sapphire code-generation backends.

  Every concrete backend (e.g. `PythonTranspiler`, `LuaTranspiler`) must
  implement all visitor methods declared here. Python's `ABCMeta` machinery
  raises `TypeError` at *class definition time* if any `@abstractmethod` is
  left unimplemented, so a new AST node added to one backend but not the other
  will be caught immediately -- before any tests are even run.
  """

  # ------------------------------------------------------------------
  # Core interface & shared helpers
  # ------------------------------------------------------------------

  @abstractmethod
  def transpile(self, program: ProgramNode) -> str:
    """Transpile a fully-typed `ProgramNode` into target source code."""

  def visit(self, node: ASTNode) -> Any:
    """Dispatch *node* to the appropriate `visit_*` method."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    return visitor(node)

  @abstractmethod
  def generic_visit(self, node: ASTNode) -> None:
    """Called when no specific visitor exists; should raise `NotImplementedError`."""

  def emit(self, text: str) -> None:
    """Append *text* to the output buffer."""
    self.code.append(text)

  @abstractmethod
  def newline(self) -> None:
    """Emit a newline followed by the current indentation."""

  def indent(self) -> None:
    """Increase the indentation level by one."""
    self.indent_level += 1

  def dedent(self) -> None:
    """Decrease the indentation level by one."""
    if self.indent_level > 0:
      self.indent_level -= 1

  def get_output(self) -> str:
    """Return the accumulated output as a single string."""
    return "".join(self.code)

  def _expr_destructible_struct(self, expr: Any, return_index: int = 0) -> Optional[str]:
    """Determines if *expr* evaluates to a struct type with a `__del__` destructor."""
    if expr is None:
      return None
    if isinstance(expr, StructInitializerNode):
      if expr.struct_name in self.structs_with_destructor:
        return expr.struct_name
    elif isinstance(expr, CallNode):
      if isinstance(expr.callee, IdentifierNode):
        if expr.callee.name in self.structs_with_destructor:
          return expr.callee.name
        if expr.callee.name in self.func_return_types:
          rets = self.func_return_types[expr.callee.name]
          if return_index < len(rets) and rets[return_index] in self.structs_with_destructor:
            return rets[return_index]
      elif isinstance(expr.callee, MemberAccessNode):
        m_name = expr.callee.member
        if m_name in self.method_return_types:
          rets = self.method_return_types[m_name]
          if return_index < len(rets) and rets[return_index] in self.structs_with_destructor:
            return rets[return_index]
    elif isinstance(expr, (IdentifierNode, MoveNode)):
      m_name = (
          self._mangle_name(expr.name)
          if hasattr(self, "_mangle_name")
          else expr.name
      )
      if m_name in self.variable_types:
        st = self.variable_types[m_name]
        if st in self.structs_with_destructor:
          return st
      if expr.name in self.variable_types:
        st = self.variable_types[expr.name]
        if st in self.structs_with_destructor:
          return st
    elif isinstance(expr, TernaryExprNode):
      return (
          self._expr_destructible_struct(expr.true_expr, return_index=return_index)
          or self._expr_destructible_struct(expr.false_expr, return_index=return_index)
      )
    elif isinstance(expr, MatchExprNode):
      for case in expr.cases:
        if isinstance(case.body, BlockNode):
          for stmt in case.body.statements:
            if isinstance(stmt, YieldNode):
              y_exprs = getattr(stmt, "expressions", None) or ([stmt.expr] if getattr(stmt, "expr", None) else [])
              if return_index < len(y_exprs):
                st = self._expr_destructible_struct(y_exprs[return_index])
                if st:
                  return st
        else:
          st = self._expr_destructible_struct(case.body, return_index=return_index)
          if st:
            return st
    inferred = getattr(expr, "inferred_type", None)
    if hasattr(inferred, "base_type"):
      inferred = inferred.base_type
    if inferred and getattr(inferred, "name", None) in self.structs_with_destructor:
      return inferred.name
    return None

  @staticmethod
  def _is_owned_unwrap_expr(expr: Any) -> bool:
    """Returns True if an optional unwrap expression owns the unwrapped value."""
    if isinstance(expr, MoveNode):
      return True
    if isinstance(expr, (IdentifierNode, MemberAccessNode, IndexExprNode)):
      return False
    return True

  def _is_active_destructible_var(self, m_name: str) -> bool:
    """Returns True if *m_name* is tracked in an active destructor stack frame."""
    return any(m_name in frame for frame in self.destructor_stack)

  def _record_move(self, m_name: str) -> None:
    """Tracks unconditional vs conditional move of *m_name* for RAII drop flags."""
    branch_depth = getattr(self, "_branch_depth", 0)
    var_depths = getattr(self, "_var_branch_depth", None)
    decl_depth = var_depths.get(m_name, branch_depth) if var_depths is not None else branch_depth
    if decl_depth < branch_depth:
      pending = getattr(self, "_pending_null_vars", None)
      if pending is not None and m_name not in pending:
        pending.append(m_name)
    else:
      self.moved_vars.add(m_name)

  def _drain_pending_null_vars(
      self,
      null_literal: str,
      exclude: Optional[Set[str]] = None,
  ) -> None:
    """Emits post-statement drop-flag clearing (`v = None` / `v = nil`) for conditional moves."""
    pending = getattr(self, "_pending_null_vars", None)
    if not pending:
      return
    for var_name in list(pending):
      if not exclude or var_name not in exclude:
        self.newline()
        self.emit(f"{var_name} = {null_literal}")
    pending.clear()

  def _visit_in_branch(self, node: ASTNode) -> None:
    """Visits *node* inside a conditional branch depth for move drop-flag tracking."""
    self._branch_depth = getattr(self, "_branch_depth", 0) + 1
    try:
      self.visit(node)
    finally:
      self._branch_depth -= 1

  def _emit_destructor_call(self, var_name: str) -> None:
    """Emits the teardown statement for a single destructible variable."""
    self.emit(f"_sapphire_del({var_name})")

  def _emit_loop_destructors(self) -> None:
    """Emits destructors for variables in the active loop scopes."""
    if self.loop_destructor_depth:
      loop_depth = self.loop_destructor_depth[-1]
      for frame in reversed(self.destructor_stack[loop_depth:]):
        for var_name in reversed(frame):
          if not hasattr(self, "moved_vars") or var_name not in self.moved_vars:
            self.newline()
            self._emit_destructor_call(var_name)

  def _collect_struct_metadata(self, program: ProgramNode, track_known_structs: bool = False) -> None:
    """Collects struct methods, traits, return types, and destructors from program declarations."""
    for decl in program.declarations:
      if getattr(decl, "type_params", None):
        continue
      if track_known_structs and isinstance(decl, StructDeclNode):
        self.known_structs.add(decl.name)
      elif isinstance(decl, ImplBlockNode):
        if decl.struct_name not in self.struct_methods:
          self.struct_methods[decl.struct_name] = []
        self.struct_methods[decl.struct_name].extend(decl.members)
        if decl.trait_name and hasattr(self, "struct_traits"):
          if decl.struct_name not in self.struct_traits:
            self.struct_traits[decl.struct_name] = set()
          self.struct_traits[decl.struct_name].add(decl.trait_name)
        for m in decl.members:
          if getattr(m, "func_decl", None):
            ret_names = get_return_type_names(m.func_decl)
            if ret_names:
              self.method_return_types[m.func_decl.name] = ret_names
      elif isinstance(decl, FuncDeclNode):
        ret_names = get_return_type_names(decl)
        if ret_names:
          self.func_return_types[decl.name] = ret_names

    self.proto_structs: Set[str] = set()
    self.struct_destructible_fields: Dict[str, List[str]] = {}
    self.struct_parent_names: Dict[str, List[str]] = {}
    self.structs_with_destructor = {"Arena"}

    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if decl.is_prototype:
          self.proto_structs.add(decl.name)
        self.struct_parent_names[decl.name] = list(decl.parent_names or [])

    for s_name, members in self.struct_methods.items():
      if s_name in self.proto_structs:
        continue
      for m in members:
        if getattr(m, "func_decl", None) and m.func_decl.name == "__del__":
          self.structs_with_destructor.add(s_name)
          break

    changed = True
    while changed:
      changed = False
      for decl in program.declarations:
        if isinstance(decl, StructDeclNode) and not decl.is_prototype:
          destructible_fields = [
              f.name
              for f in decl.fields
              if extract_type_name(f.field_type) in self.structs_with_destructor
          ]
          self.struct_destructible_fields[decl.name] = destructible_fields
          if decl.name not in self.structs_with_destructor and (
              destructible_fields
              or any(
                  p in self.structs_with_destructor
                  for p in (decl.parent_names or [])
              )
          ):
            self.structs_with_destructor.add(decl.name)
            changed = True

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
  def visit_MoveNode(self, node: MoveNode) -> None: ...

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
