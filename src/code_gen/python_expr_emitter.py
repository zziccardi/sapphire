"""Expression, literal, and initializer code generation mixin for
PythonTranspiler.
"""

from typing import TYPE_CHECKING

from src.code_gen.intrinsics import IntrinsicRegistry
from src.parser.ast import (
  ArrayLiteralNode,
  AssignmentNode,
  BinaryOpNode,
  BlockNode,
  CallNode,
  CastExprNode,
  CloneNode,
  IdentifierNode,
  IndexExprNode,
  InterpolatedStringNode,
  LambdaNode,
  LiteralNode,
  MapLiteralNode,
  MemberAccessNode,
  MoveNode,
  OptionalTypeNode,
  StructInitializerNode,
  TernaryExprNode,
  UnaryOpNode,
)

if TYPE_CHECKING:
  from src.code_gen.python_transpiler import (
    PythonTranspiler as _PythonTranspilerBase,
  )
else:
  _PythonTranspilerBase = object


class PythonExprMixin(_PythonTranspilerBase):
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
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
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
    self.emit(self._resolve_var_name(node.name))

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if id(node) in self._lifted_short_circuits:
      self.emit(self._lifted_short_circuits[id(node)])
      return

    if node.op == "+" and getattr(node, "is_string_concat", False):
      self.emit("(_sapphire_string_from(")
      self.visit(node.left)
      self.emit(") + _sapphire_string_from(")
      self.visit(node.right)
      self.emit("))")
      return

    if node.op == "/":
      from src.semantics.types import PrimitiveType

      lt = self.get_inferred_type(node.left)
      rt = self.get_inferred_type(node.right)
      it = self.get_inferred_type(node)
      if (
        isinstance(lt, PrimitiveType)
        and lt.name == "int"
        and isinstance(rt, PrimitiveType)
        and rt.name == "int"
      ) or (isinstance(it, PrimitiveType) and it.name == "int"):
        self.emit("_sapphire_div(")
        self.visit(node.left)
        self.emit(", ")
        self.visit(node.right)
        self.emit(")")
        return

    if node.op == "??":
      v_tmp = self._next_temp_name("_v")
      self.emit(f"((lambda {v_tmp}: {v_tmp} if {v_tmp} is not None else ")
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
    if id(node) in self._lifted_short_circuits:
      self.emit(self._lifted_short_circuits[id(node)])
      return
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
    is_opt = isinstance(node.target_type, OptionalTypeNode)
    inner_type = node.target_type.base_type if is_opt else node.target_type
    target = inner_type.name if hasattr(inner_type, "name") else str(inner_type)
    conv_map = {
      "float": "float",
      "int": "int",
      "bool": "bool",
      "String": "_sapphire_string_from",
    }
    conv = conv_map.get(target)
    if conv:
      if is_opt:
        c_tmp = self._next_temp_name("_c")
        self.emit(
          f"((lambda {c_tmp}: {conv}({c_tmp}) if {c_tmp} is not None else "
          "None)("
        )
        self.visit(node.expr)
        self.emit("))")
      else:
        self.emit(f"{conv}(")
        self.visit(node.expr)
        self.emit(")")
    else:
      self.visit(node.expr)

  def visit_CallNode(self, node: CallNode) -> None:
    if id(node) in self._lifted_short_circuits:
      self.emit(self._lifted_short_circuits[id(node)])
      return

    if IntrinsicRegistry.try_emit("python", self, node):
      return

    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      self._record_consumed_call_moves(node.arguments)
      member_name = getattr(
        node.callee, "target_name", None
      ) or self._mangle_name(node.callee.member)
      r_tmp = self._next_temp_name("_r")
      self.emit(f"((lambda {r_tmp}: {r_tmp}.")
      self.emit(member_name)
      self.emit("(")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)}=")
        self.visit(arg.expr)
      self.emit(f") if {r_tmp} is not None else None)(")
      self.visit(node.callee.receiver)
      self.emit("))")
      return

    if not self._is_struct_constructor_call(node):
      self._record_consumed_call_moves(node.arguments)

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
    member_name = getattr(node, "target_name", None) or self._mangle_name(
      node.member
    )
    if node.is_optional:
      r_tmp = self._next_temp_name("_r")
      self.emit(f"((lambda {r_tmp}: {r_tmp}.")
      self.emit(member_name)
      self.emit(f" if {r_tmp} is not None else None)(")
      self.visit(node.receiver)
      self.emit("))")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      if id(node) in self._lifted_clones:
        self.emit(f", {self._lifted_clones[id(node)]}")
      else:
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
          self.emit(
            f"setattr(self, '{self._mangle_name(assign.target.member)}', "
          )
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
    py_name = self._resolve_var_name(node.name)
    self._record_move(py_name)
    self.emit(py_name)

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    if id(node) in self._lifted_lambdas:
      self.emit(self._lifted_lambdas[id(node)])
      return
    if isinstance(node.body, BlockNode) or self._contains_liftable_expr(
      node.body
    ):
      fn_name = self._emit_lifted_lambda(node)
      self._lifted_lambdas[id(node)] = fn_name
      self.emit(fn_name)
      return

    params = [self._mangle_name(p.name) for p in node.parameters]
    param_raw_names = {p.name for p in node.parameters}
    caps = self._find_captured_loop_vars(node.body, param_raw_names)

    prev_id_map = self._identifier_map.copy()
    for p in node.parameters:
      self._identifier_map.pop(p.name, None)
    try:
      if caps:
        cap_str = ", ".join(caps)
        self.emit(f"((lambda {cap_str}: (lambda {', '.join(params)}: ")
        self.visit(node.body)
        self.emit(f"))({cap_str}))")
      else:
        self.emit(f"(lambda {', '.join(params)}: ")
        self.visit(node.body)
        self.emit(")")
    finally:
      self._identifier_map = prev_id_map

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
    self.emit(f"{self._mangle_dotted(node.struct_name)}(")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      self.emit(f"{self._mangle_name(arg.name)}=")
      self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")
