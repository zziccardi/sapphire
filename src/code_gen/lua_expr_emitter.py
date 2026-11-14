"""Expression, literal, and initializer code generation mixin for LuaTranspiler."""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import ArrayType, MapType, RangeType
from src.code_gen.base_transpiler import extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.intrinsics import IntrinsicRegistry


class LuaExprMixin:
  """Provides expression, call, and literal AST emission for Lua 5.1."""

  def visit_LiteralNode(self, node: LiteralNode) -> None:
    if node.lit_type == "bool":
      self.emit("true" if node.value else "false")
    elif node.lit_type == "none":
      self.emit("nil")
    elif node.lit_type == "string":
      val = str(node.value).replace("\r", "\\r").replace("\n", "\\n")
      self.emit(f'"{val}"')
    else:
      self.emit(str(node.value))

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> None:
    if not node.parts:
      self.emit('""')
      return

    if len(node.parts) == 1:
      part = node.parts[0]
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("tostring(")
        self.visit(part)
        self.emit(")")
      return

    self.emit("(")
    for idx, part in enumerate(node.parts):
      if idx > 0:
        self.emit(" .. ")
      if isinstance(part, LiteralNode) and part.lit_type == "string":
        escaped_val = part.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        self.emit(f'"{escaped_val}"')
      else:
        self.emit("tostring(")
        self.visit(part)
        self.emit(")")
    self.emit(")")

  def visit_IdentifierNode(self, node: IdentifierNode) -> None:
    if node.name == "Arena":
      self.emit("Arena.init")
    else:
      name = self._identifier_map.get(node.name, self._mangle_name(node.name))
      self.emit(name)

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> None:
    if node.op == "??":
      self.emit("((function() local _v = ")
      self.visit(node.left)
      self.emit("; if _v ~= nil then return _v else return ")
      self.visit(node.right)
      self.emit(" end end)())")
      return

    op_map = {"&&": "and", "||": "or", "!=": "~="}
    op = op_map.get(node.op, node.op)

    if op == "+":
      if getattr(node, "is_string_concat", False) or (isinstance(node.left, LiteralNode) and node.left.lit_type == "string") or (isinstance(node.right, LiteralNode) and node.right.lit_type == "string"):
        op = ".."

    self.emit("(")
    self._visit_concat_operand(node.left, is_string_concat=(op == ".."))
    self.emit(f" {op} ")
    self._visit_concat_operand(node.right, is_string_concat=(op == ".."))
    self.emit(")")

  def _visit_concat_operand(self, expr: ASTNode, is_string_concat: bool) -> None:
    if not is_string_concat:
      self.visit(expr)
      return
    if isinstance(expr, LiteralNode) and expr.lit_type in ("string", "int", "float"):
      self.visit(expr)
    elif isinstance(expr, (CallNode, IdentifierNode, MemberAccessNode, IndexExprNode)):
      self.emit("tostring(")
      self.visit(expr)
      self.emit(")")
    else:
      self.visit(expr)

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None:
    self.emit("((function() if ")
    self.visit(node.condition)
    self.emit(" then return ")
    self.visit(node.true_expr)
    self.emit(" else return ")
    self.visit(node.false_expr)
    self.emit(" end end)())")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> None:
    if node.op == "+":
      self.emit("(")
      self.visit(node.expr)
      self.emit(")")
      return
    op_map = {"!": "not "}
    op = op_map.get(node.op, node.op)
    self.emit(f"({op}")
    self.visit(node.expr)
    self.emit(")")

  def visit_CastExprNode(self, node: CastExprNode) -> None:
    target = node.target_type.name if hasattr(node.target_type, "name") else str(node.target_type)
    if target == "float":
      self.emit("tonumber(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "int":
      self.emit("_sapphire_cast_int(")
      self.visit(node.expr)
      self.emit(")")
    elif target == "bool":
      self.emit("(not not ")
      self.visit(node.expr)
      self.emit(")")
    elif target == "String":
      self.emit("tostring(")
      self.visit(node.expr)
      self.emit(")")
    else:
      self.visit(node.expr)

  def visit_CallNode(self, node: CallNode) -> None:
    if IntrinsicRegistry.try_emit("lua", self, node):
      return

    # Check if this call is calling a struct constructor, e.g. Weapon(...)
    if (isinstance(node.callee, IdentifierNode) and
        node.callee.name in self.known_structs):
      struct_name = node.callee.name
      if node.arena_expr:
        self.visit(node.arena_expr)
        self.emit(":register(")
      self.emit(f"{struct_name}.init({{")
      for idx, arg in enumerate(node.arguments):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)} = ")
        else:
          self.emit(f"[{idx + 1}] = ")
        self.visit(arg.expr)
      self.emit("})")
      if node.arena_expr:
        self.emit(")")
      return

    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")

    if isinstance(node.callee, MemberAccessNode):
      member_name = getattr(node.callee, "target_name", None) or self._mangle_name(node.callee.member)
      receiver_name = getattr(node.callee.receiver, "name", None)
      if node.callee.is_optional:
        sep = ":" if getattr(node.callee, "is_instance_method", False) else "."
        self.emit("((function(_r) if _r ~= nil then return _r")
        self.emit(f"{sep}{member_name}(")
        for idx, arg in enumerate(node.arguments):
          if idx > 0:
            self.emit(", ")
          self.visit(arg.expr)
        self.emit(") else return nil end end)(")
        self.visit(node.callee.receiver)
        self.emit("))")
        return
      if getattr(node.callee, "is_instance_method", False):
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
      elif getattr(node.callee, "is_static_method", False) or (receiver_name and (receiver_name in self.known_structs or receiver_name in self.imported_modules)):
        self.visit(node.callee.receiver)
        self.emit(f".{member_name}(")
      elif isinstance(node.callee.receiver, MemberAccessNode):
        self.visit(node.callee.receiver)
        self.emit(f".{member_name}(")
      else:
        self.visit(node.callee.receiver)
        self.emit(f":{member_name}(")
    else:
      self.visit(node.callee)
      self.emit("(")

    for idx, arg in enumerate(node.arguments):
      if idx > 0:
        self.emit(", ")
      self.visit(arg.expr)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    member_name = getattr(node, "target_name", None) or self._mangle_name(node.member)
    if node.is_optional:
      self.emit("((function(_r) if _r ~= nil then return _r.")
      self.emit(member_name)
      self.emit(" else return nil end end)(")
      self.visit(node.receiver)
      self.emit("))")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", function(self)")
      self.indent()
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.dedent()
      self.newline()
      self.emit("end")
    else:
      if node.arena_expr:
        self.emit(", nil")

    if node.arena_expr:
      self.emit(", ")
      self.visit(node.arena_expr)

    self.emit(")")

  def visit_MoveNode(self, node: MoveNode) -> None:
    m_name = self._mangle_name(node.name)
    name = self._identifier_map.get(m_name, m_name)
    self._record_move(m_name)
    self.emit(name)

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    params = [self._mangle_name(p.name) for p in node.parameters]
    self.emit(f"(function({', '.join(params)})")
    self.indent()
    if isinstance(node.body, BlockNode):
      self.visit(node.body)
    else:
      self.newline()
      self.emit("return ")
      self.visit(node.body)
    self.dedent()
    self.newline()
    self.emit("end)")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    self.emit("{")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self.visit(elem)
    self.emit("}")

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.emit("[")
      self.visit(entry.key)
      self.emit("] = ")
      self.visit(entry.value)
    self.emit("}")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    is_map = isinstance(getattr(node.array, 'inferred_type', None), MapType)
    if is_map:
      self.visit(node.array)
      self.emit("[")
      self.visit(node.index)
      self.emit("]")
      return

    if isinstance(node.index, LiteralNode) and node.index.lit_type == "int" and int(node.index.value) >= 0:
      self.visit(node.array)
      self.emit("[")
      self.emit(str(int(node.index.value) + 1))
      self.emit("]")
      return

    const_val = None
    if isinstance(node.index, LiteralNode) and node.index.lit_type == "int":
      const_val = int(node.index.value)
    elif (
        isinstance(node.index, UnaryOpNode)
        and node.index.op == "-"
        and isinstance(node.index.expr, LiteralNode)
        and node.index.expr.lit_type == "int"
    ):
      const_val = -int(node.index.expr.value)

    arr_type = getattr(node.array, 'inferred_type', None)
    if const_val is not None and const_val < 0 and isinstance(arr_type, ArrayType) and arr_type.size is not None:
      self.visit(node.array)
      self.emit("[")
      self.emit(str(arr_type.size + const_val + 1))
      self.emit("]")
      return

    self.visit(node.array)
    self.emit("[_sapphire_array_idx(")
    self.visit(node.array)
    self.emit(", ")
    self.visit(node.index)
    self.emit(")]")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")
    self.emit(f"{node.struct_name}.init({{")
    for idx, arg in enumerate(node.fields):
      if idx > 0:
        self.emit(", ")
      if arg.name:
        self.emit(f"{self._mangle_name(arg.name)} = ")
      else:
        self.emit(f"[{idx + 1}] = ")
      self.visit(arg.expr)
    self.emit("})")
    if node.arena_expr:
      self.emit(")")
