"""Expression, literal, and initializer code generation mixin for PythonTranspiler."""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.code_gen.base_transpiler import extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.intrinsics import IntrinsicRegistry


class PythonExprMixin:
  """Provides expression, call, and literal AST emission for Python."""

  def visit_LiteralNode(self, node: LiteralNode) -> None:
    if node.lit_type == "bool":
      self.emit("True" if node.value else "False")
    elif node.lit_type == "none":
      self.emit("None")
    elif node.lit_type == "string":
      val = str(node.value).replace("\r", "\\r").replace("\n", "\\n")
      self.emit(f'"{val}"')
    else:
      self.emit(str(node.value))

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None:
    if not node.parts:
      self.emit('""')
      return

    def _emit_part_str(part):
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("_sapphire_string_from(")
        self.visit(part)
        self.emit(")")

    if len(node.parts) == 1:
      _emit_part_str(node.parts[0])
      return

    self.emit("(")
    for idx, part in enumerate(node.parts):
      if idx > 0:
        self.emit(" + ")
      _emit_part_str(part)
    self.emit(")")

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    name = self._identifier_map.get(node.name, self._mangle_name(node.name))
    self.emit(name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if node.op == "+" and getattr(node, "is_string_concat", False):
      self.emit("(str(")
      self.visit(node.left)
      self.emit(") + str(")
      self.visit(node.right)
      self.emit("))")
      return

    if node.op == "??":
      self.emit("((lambda _v: _v if _v is not None else ")
      self.visit(node.right)
      self.emit(")(")
      self.visit(node.left)
      self.emit("))")
      return

    op_map = {"&&": "and", "||": "or"}
    op = op_map.get(node.op, node.op)
    self.emit("(")
    self.visit(node.left)
    self.emit(f" {op} ")
    self.visit(node.right)
    self.emit(")")

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None:
    self.emit("(")
    self.visit(node.true_expr)
    self.emit(" if ")
    self.visit(node.condition)
    self.emit(" else ")
    self.visit(node.false_expr)
    self.emit(")")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CastExprNode(self, node: CastExprNode) -> None:
    target = node.target_type.name if hasattr(node.target_type, "name") else str(node.target_type)
    if target == "float":
      self.emit("float(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "int":
      self.emit("int(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "bool":
      self.emit("bool(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "String":
      self.emit("_sapphire_string_from(")
      self.visit(node.expr)
      self.emit(")")
    else:
      self.visit(node.expr)

  def visit_CallNode(self, node: CallNode) -> None:
    if IntrinsicRegistry.try_emit("python", self, node):
      return

    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      member_name = getattr(node.callee, "target_name", None) or self._mangle_name(node.callee.member)
      self.emit("((lambda _r: _r.")
      self.emit(member_name)
      self.emit("(")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)}=")
        self.visit(arg.expr)
      self.emit(") if _r is not None else None)(")
      self.visit(node.callee.receiver)
      self.emit("))")
      return

    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(".register(")
    self.visit(node.callee)
    self.emit("(")
    args = []
    for arg in node.arguments:
      if arg.name:
        args.append(f"{self._mangle_name(arg.name)}=")
      else:
        args.append("")

    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      if args[idx]:
        self.emit(args[idx])
      self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    member_name = getattr(node, "target_name", None) or self._mangle_name(node.member)
    if node.is_optional:
      self.emit("((lambda _r: _r.")
      self.emit(member_name)
      self.emit(" if _r is not None else None)(")
      self.visit(node.receiver)
      self.emit("))")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", lambda self: [")
      assignments = []
      for stmt in node.initializer_block:
        if isinstance(stmt, AssignmentNode) and isinstance(
            stmt.target, MemberAccessNode
        ):
          if (
              isinstance(stmt.target.receiver, IdentifierNode)
              and stmt.target.receiver.name == "self"
          ):
            assignments.append(stmt)

      for idx, assign in enumerate(assignments):
        if idx > 0:
          self.emit(", ")
        self.emit(f"setattr(self, '{assign.target.member}', ")
        self.visit(assign.expr)
        self.emit(")")
      self.emit("]")
    else:
      if node.arena_expr:
        self.emit(", None")

    if node.arena_expr:
      self.emit(", arena=")
      self.visit(node.arena_expr)

    self.emit(")")

  def visit_MoveNode(self, node: MoveNode) -> None:
    m_name = self._mangle_name(node.name)
    name = self._identifier_map.get(m_name, m_name)
    self._record_move(m_name)
    self.emit(name)

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    if isinstance(node.body, BlockNode):
      if not getattr(node, "_is_lifted", False):
        node._is_lifted = True
        node._lifted_name = self._emit_lifted_lambda(node)
      self.emit(node._lifted_name)
    else:
      params = [self._mangle_name(p.name) for p in node.parameters]
      self.emit(f"(lambda {', '.join(params)}: ")
      self.visit(node.body)
      self.emit(")")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    self.emit("[")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self.visit(elem)
    self.emit("]")

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.visit(entry.key)
      self.emit(": ")
      self.visit(entry.value)
    self.emit("}")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    self.visit(node.array)
    self.emit("[")
    self.visit(node.index)
    self.emit("]")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(".register(")
    self.emit(f"{node.struct_name}(")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      self.emit(f"{self._mangle_name(arg.name)}=")
      self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")

