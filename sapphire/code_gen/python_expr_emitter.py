"""Expression, literal, and initializer code generation mixin for
PythonTranspiler.
"""

from typing import TYPE_CHECKING

from sapphire.code_gen.intrinsics import IntrinsicRegistry
from sapphire.parser.ast import (
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
  from sapphire.code_gen.python_transpiler import (
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

  def _needs_string_from(self, expr: object) -> bool:
    """Returns True if *expr* needs `_sapphire_string_from` inside f-strings."""
    from sapphire.semantics.types import PrimitiveType

    if isinstance(expr, LiteralNode) and expr.lit_type in (
      "string",
      "int",
      "float",
    ):
      return False
    if isinstance(expr, InterpolatedStringNode):
      return False
    t = self.get_inferred_type(expr)
    return not (
      isinstance(t, PrimitiveType) and t.name in ("String", "int", "float")
    )

  def _is_non_opt_string_expr(self, expr: object) -> bool:
    """Returns True if *expr* is statically a non-optional String."""
    from sapphire.semantics.types import PrimitiveType

    if isinstance(expr, InterpolatedStringNode):
      return True
    if isinstance(expr, LiteralNode) and expr.lit_type == "string":
      return True
    t = self.get_inferred_type(expr)
    return isinstance(t, PrimitiveType) and t.name == "String"

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None:
    if not node.parts:
      self.emit('""')
      return

    if len(node.parts) == 1:
      part = node.parts[0]
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
        self.emit(f'"{escaped_val}"')
      elif self._is_non_opt_string_expr(part):
        self.visit(part)
      elif not self._needs_string_from(part):
        self.emit("str(")
        self.visit(part)
        self.emit(")")
      else:
        self.emit("_sapphire_string_from(")
        self.visit(part)
        self.emit(")")
      return

    # Emit native Python 3.12+ f-string (PEP 701 supports nested quotes).
    f_chunks: list[str] = []
    can_use_fstring = True
    for part in node.parts:
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("{", "{{")
          .replace("}", "}}")
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
        f_chunks.append(escaped_val)
      else:
        expr_code = self.capture_expr(part)
        if "\n" in expr_code or "\r" in expr_code:
          can_use_fstring = False
          break
        if self._needs_string_from(part):
          f_chunks.append(f"{{_sapphire_string_from({expr_code})}}")
        else:
          f_chunks.append(f"{{{expr_code}}}")

    if can_use_fstring:
      self.emit(f'f"{"".join(f_chunks)}"')
      return

    self.emit('"".join([')
    for idx, part in enumerate(node.parts):
      if idx > 0:
        self.emit(", ")
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
        self.emit(f'"{escaped_val}"')
      elif self._is_non_opt_string_expr(part):
        self.visit(part)
      elif not self._needs_string_from(part):
        self.emit("str(")
        self.visit(part)
        self.emit(")")
      else:
        self.emit("_sapphire_string_from(")
        self.visit(part)
        self.emit(")")
    self.emit("])")

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    self.emit(self._resolve_var_name(node.name))

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if id(node) in self._lifted_short_circuits:
      self.emit(self._lifted_short_circuits[id(node)])
      return

    if node.op == "+" and getattr(node, "is_string_concat", False):
      self.emit("(")
      if self._is_non_opt_string_expr(node.left):
        self.visit(node.left)
      else:
        self.emit("_sapphire_string_from(")
        self.visit(node.left)
        self.emit(")")
      self.emit(" + ")
      if self._is_non_opt_string_expr(node.right):
        self.visit(node.right)
      else:
        self.emit("_sapphire_string_from(")
        self.visit(node.right)
        self.emit(")")
      self.emit(")")
      return

    if node.op == "/":
      from sapphire.semantics.types import PrimitiveType

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
      if isinstance(node.left, IdentifierNode):
        lhs_name = self._resolve_var_name(node.left.name)
        self.emit(f"({lhs_name} if {lhs_name} is not None else ")
        self.visit(node.right)
        self.emit(")")
      else:
        v_tmp = self._next_temp_name("_v")
        self.emit(f"({v_tmp} if ({v_tmp} := ")
        self.visit(node.left)
        self.emit(") is not None else ")
        self.visit(node.right)
        self.emit(")")
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
    from sapphire.semantics.types import OptionalType, PrimitiveType

    if isinstance(node.target_type, OptionalTypeNode):
      is_opt = True
      inner_type = node.target_type.base_type
    else:
      is_opt = False
      inner_type = node.target_type
    target = getattr(inner_type, "name", str(inner_type))
    src_t = self.get_inferred_type(node.expr)
    if (
      not is_opt
      and isinstance(src_t, PrimitiveType)
      and src_t.name == target
    ):
      self.visit(node.expr)
      return
    if (
      is_opt
      and isinstance(src_t, OptionalType)
      and isinstance(src_t.base_type, PrimitiveType)
      and src_t.base_type.name == target
    ):
      self.visit(node.expr)
      return

    conv_map = {
      "float": "float",
      "int": "int",
      "bool": "bool",
      "String": "_sapphire_string_from",
    }
    conv = conv_map.get(target)
    if conv:
      if is_opt:
        if isinstance(node.expr, IdentifierNode):
          var_name = self._resolve_var_name(node.expr.name)
          self.emit(
            f"({conv}({var_name}) if {var_name} is not None else None)"
          )
        else:
          c_tmp = self._next_temp_name("_c")
          self.emit(f"({conv}({c_tmp}) if ({c_tmp} := ")
          self.visit(node.expr)
          self.emit(") is not None else None)")
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
      if isinstance(node.callee.receiver, IdentifierNode):
        r_name = self._resolve_var_name(node.callee.receiver.name)
        self.emit(f"({r_name}.{member_name}(")
        for idx, arg in enumerate(node.arguments):
          if idx > 0:
            self.emit(", ")
          if arg.name:
            self.emit(f"{self._mangle_name(arg.name)}=")
          self.visit(arg.expr)
        self.emit(f") if {r_name} is not None else None)")
      else:
        r_tmp = self._next_temp_name("_r")
        self.emit(f"({r_tmp}.{member_name}(")
        for idx, arg in enumerate(node.arguments):
          if idx > 0:
            self.emit(", ")
          if arg.name:
            self.emit(f"{self._mangle_name(arg.name)}=")
          self.visit(arg.expr)
        self.emit(f") if ({r_tmp} := ")
        self.visit(node.callee.receiver)
        self.emit(") is not None else None)")
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
      if isinstance(node.receiver, IdentifierNode):
        r_name = self._resolve_var_name(node.receiver.name)
        self.emit(f"({r_name}.{member_name} if {r_name} is not None else None)")
      else:
        r_tmp = self._next_temp_name("_r")
        self.emit(f"({r_tmp}.{member_name} if ({r_tmp} := ")
        self.visit(node.receiver)
        self.emit(") is not None else None)")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    if id(node) in self._lifted_short_circuits:
      self.emit(self._lifted_short_circuits[id(node)])
      return
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
    resolved_exprs = getattr(node, "_resolved_field_exprs", None)
    use_positional = False
    last_provided = -1
    if resolved_exprs is not None and not getattr(
      node, "_requires_eval_order_temps", False
    ):
      for idx, expr in enumerate(resolved_exprs):
        if expr is not None:
          last_provided = idx
      use_positional = all(
        resolved_exprs[i] is not None for i in range(last_provided + 1)
      )
    if use_positional and resolved_exprs is not None:
      for idx in range(last_provided + 1):
        if idx > 0:
          self.emit(", ")
        expr = resolved_exprs[idx]
        if expr is not None:
          self.visit(expr)
    else:
      for idx, arg in enumerate(node.fields):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)}=")
        self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")
