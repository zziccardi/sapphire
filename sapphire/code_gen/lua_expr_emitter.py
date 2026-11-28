"""Expression, literal, and initializer code generation mixin for LuaTranspiler.
"""

from typing import TYPE_CHECKING, Any

from sapphire.code_gen.intrinsics import IntrinsicRegistry
from sapphire.parser.ast import (
  ArrayLiteralNode,
  ASTNode,
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
from sapphire.semantics.symbol_table import ArrayType, MapType


def _unwrap_ref_opt_type(t: Any) -> Any:
  """Unwraps OptionalType / RefType / SharedRefType wrappers to their inner
  type.
  """
  from sapphire.semantics.types import OptionalType, RefType, SharedRefType

  while isinstance(t, (OptionalType, RefType, SharedRefType)):
    t = t.base_type if isinstance(t, OptionalType) else t.inner_type
  return t


if TYPE_CHECKING:
  from sapphire.code_gen.lua_transpiler import (
    LuaTranspiler as _LuaTranspilerBase,
  )
else:
  _LuaTranspilerBase = object


class LuaExprMixin(_LuaTranspilerBase):
  """Provides expression, call, and literal AST emission for Lua 5.1."""

  def _emit_opt_wrapped(
    self, expr: ASTNode, is_optional_slot: bool = False
  ) -> None:
    """Emits *expr*, preserving explicit/runtime `none` via `_SP_NONE` when
    needed.
    """
    from sapphire.semantics.types import OptionalType

    if isinstance(expr, LiteralNode) and expr.lit_type == "none":
      self.emit("_SP_RT._SP_NONE")
      return
    inferred = self.get_inferred_type(expr)
    if is_optional_slot or isinstance(inferred, OptionalType):
      self.emit("_SP_RT._wrap_opt(")
      self.visit(expr)
      self.emit(")")
      return
    self.visit(expr)

  def _is_runtime_method_call(self, member_node: MemberAccessNode) -> bool:
    """Returns True if *member_node* invokes a Lua runtime method needing `:`.
    """
    if (
      getattr(member_node, "is_shared_ref_share", False)
      or getattr(member_node, "is_shared_ref_downgrade", False)
      or getattr(member_node, "is_weak_ref_upgrade", False)
    ):
      return True
    from sapphire.semantics.types import (
      ArenaType,
      CoroutineType,
      OptionalType,
      RefType,
      SharedRefType,
      WeakRefType,
    )

    recv_t = self.get_inferred_type(member_node.receiver)
    if isinstance(recv_t, OptionalType):
      recv_t = recv_t.base_type
    if isinstance(recv_t, CoroutineType) and member_node.member in (
      "step",
      "is_done",
      "reset",
    ):
      return True
    if isinstance(recv_t, ArenaType) and member_node.member in (
      "destroy",
      "register",
    ):
      return True
    if isinstance(recv_t, SharedRefType) and member_node.member in (
      "share",
      "downgrade",
    ):
      return True
    if isinstance(recv_t, WeakRefType) and member_node.member == "upgrade":
      return True
    if isinstance(recv_t, RefType) and member_node.member in ("get",):
      return True
    return False

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
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
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
        escaped_val = (
          part.value.replace("\\", "\\\\")
          .replace('"', '\\"')
          .replace("\r", "\\r")
          .replace("\n", "\\n")
        )
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
    lifted = getattr(self, "_lifted_short_circuits", None)
    if lifted and id(node) in lifted:
      self.emit(lifted[id(node)])
      return

    if node.op == "??":
      v_tmp = self._next_temp_name("_v")
      self.emit(f"((function() local {v_tmp} = ")
      self.visit(node.left)
      self.emit(f"; if {v_tmp} ~= nil then return {v_tmp} else return ")
      self.visit(node.right)
      self.emit(" end end)())")
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
        self.emit("_SP_RT._sapphire_div(")
        self.visit(node.left)
        self.emit(", ")
        self.visit(node.right)
        self.emit(")")
        return

    if node.op in ("==", "!="):
      lt = _unwrap_ref_opt_type(self.get_inferred_type(node.left))
      rt = _unwrap_ref_opt_type(self.get_inferred_type(node.right))
      if isinstance(lt, (ArrayType, MapType)) or isinstance(
        rt, (ArrayType, MapType)
      ):
        eq_fn = (
          "_SP_RT._sapphire_array_eq"
          if isinstance(lt, ArrayType) and isinstance(rt, ArrayType)
          else "_SP_RT._sapphire_eq"
        )
        if node.op == "!=":
          self.emit(f"(not {eq_fn}(")
          self.visit(node.left)
          self.emit(", ")
          self.visit(node.right)
          self.emit("))")
        else:
          self.emit(f"{eq_fn}(")
          self.visit(node.left)
          self.emit(", ")
          self.visit(node.right)
          self.emit(")")
        return

    op_map = {"&&": "and", "||": "or", "!=": "~="}
    op = op_map.get(node.op, node.op)

    if op == "+":
      if (
        getattr(node, "is_string_concat", False)
        or (
          isinstance(node.left, LiteralNode) and node.left.lit_type == "string"
        )
        or (
          isinstance(node.right, LiteralNode)
          and node.right.lit_type == "string"
        )
      ):
        op = ".."

    self.emit("(")
    self._visit_concat_operand(node.left, is_string_concat=(op == ".."))
    self.emit(f" {op} ")
    self._visit_concat_operand(node.right, is_string_concat=(op == ".."))
    self.emit(")")

  def _visit_concat_operand(
    self, expr: ASTNode, is_string_concat: bool
  ) -> None:
    if not is_string_concat:
      self.visit(expr)
      return
    if isinstance(expr, LiteralNode) and expr.lit_type in (
      "string",
      "int",
      "float",
    ):
      self.visit(expr)
    elif (
      isinstance(expr, UnaryOpNode)
      and expr.op in ("-", "+")
      and isinstance(expr.expr, LiteralNode)
      and expr.expr.lit_type in ("int", "float")
    ):
      self.visit(expr)
    else:
      self.emit("tostring(")
      self.visit(expr)
      self.emit(")")

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> None:
    lifted = getattr(self, "_lifted_short_circuits", None)
    if lifted and id(node) in lifted:
      self.emit(lifted[id(node)])
      return
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
    lifted = getattr(self, "_lifted_short_circuits", None)
    if lifted and id(node) in lifted:
      self.emit(lifted[id(node)])
      return
    if isinstance(node.target_type, OptionalTypeNode):
      is_opt_target = True
      inner_type = node.target_type.base_type
    else:
      is_opt_target = False
      inner_type = node.target_type
    target = getattr(inner_type, "name", str(inner_type))
    cast_fn_map = {
      "float": "_SP_RT._sapphire_cast_float",
      "int": "_SP_RT._sapphire_cast_int",
      "bool": "_SP_RT._sapphire_cast_bool",
      "String": "tostring",
    }
    cast_fn = cast_fn_map.get(target)
    if not cast_fn:
      self.visit(node.expr)
      return
    if is_opt_target:
      c_tmp = self._next_temp_name("_c")
      self.emit(
        f"((function({c_tmp}) if {c_tmp} ~= nil then "
        f"return {cast_fn}({c_tmp}) else return nil end end)("
      )
      self.visit(node.expr)
      self.emit("))")
      return
    self.emit(f"{cast_fn}(")
    self.visit(node.expr)
    self.emit(")")

  def _is_optional_param_slot(self, node: CallNode, slot_idx: int) -> bool:
    """Returns True if *slot_idx* on *node*'s callee is an OptionalType
    parameter.
    """
    from sapphire.semantics.types import FunctionType, OptionalType, StructType

    callee_t = self.get_inferred_type(node.callee)
    if (
      isinstance(callee_t, FunctionType)
      and slot_idx < len(callee_t.param_types)
      and isinstance(callee_t.param_types[slot_idx], OptionalType)
    ):
      return True
    if isinstance(callee_t, StructType):
      init_m = callee_t.methods.get("__init__")
      if init_m is not None:
        sig = init_m.method_type
        p_types = (
          sig.param_types[1:]
          if (sig.has_self and sig.param_names and sig.param_names[0] == "self")
          else sig.param_types
        )
        if slot_idx < len(p_types) and isinstance(
          p_types[slot_idx], OptionalType
        ):
          return True
    return False

  def _emit_lua_call_args_list(
    self, exprs: list[ASTNode], node: CallNode | None = None
  ) -> None:
    """Emits comma-separated Lua argument expressions, preserving omitted
    optional
    slots.
    """
    omitted_slots = (
      getattr(node, "_omitted_arg_slots", set()) if node else set()
    )
    for idx, expr in enumerate(exprs):
      if idx > 0:
        self.emit(", ")
      if (
        idx in omitted_slots
        and node is not None
        and self._is_optional_param_slot(node, idx)
      ):
        self.emit("_SP_RT._SP_UNSET")
      else:
        self.visit(expr)

  def _format_reordered_slot_temps(
    self, node: CallNode, total_slots: int
  ) -> list[str]:
    """Binds side-effecting call args in source order and returns slot list."""
    for arg_idx, arg in enumerate(node.arguments):
      self.emit(f"local _a{arg_idx} = ")
      self.visit(arg.expr)
      self.emit("; ")
    slot_to_temp = {
      slot: f"_a{arg_idx}"
      for arg_idx, slot in enumerate(getattr(node, "_eval_order_slots", []))
    }
    res: list[str] = []
    for i in range(total_slots):
      if i in slot_to_temp:
        res.append(slot_to_temp[i])
      elif self._is_optional_param_slot(node, i):
        res.append("_SP_RT._SP_UNSET")
      else:
        res.append("nil")
    return res

  def visit_CallNode(self, node: CallNode) -> None:
    lifted = getattr(self, "_lifted_short_circuits", None)
    if lifted and id(node) in lifted:
      self.emit(lifted[id(node)])
      return

    if IntrinsicRegistry.try_emit("lua", self, node):
      return

    # Check if this call is calling a struct constructor, e.g. Weapon(...)
    is_local_struct = (
      isinstance(node.callee, IdentifierNode)
      and node.callee.name in self.known_structs
    )
    if getattr(node, "_is_struct_constructor", False) or is_local_struct:
      if node.arena_expr:
        self.visit(node.arena_expr)
        self.emit(":register(")
      resolved_exprs = getattr(node, "_resolved_arguments", None)
      if resolved_exprs is not None:
        needs_temps = bool(getattr(node, "_requires_eval_order_temps", False))
        if needs_temps:
          self.emit("(function() ")
          temp_args = self._format_reordered_slot_temps(
            node, len(resolved_exprs)
          )
          self.emit("return ")
          self.visit(node.callee)
          self.emit(f"._new({', '.join(temp_args)}) end)()")
        else:
          self.visit(node.callee)
          self.emit("._new(")
          self._emit_lua_call_args_list(resolved_exprs, node)
          self.emit(")")
      else:
        self.visit(node.callee)
        self.emit(".init({")
        for idx, arg in enumerate(node.arguments):
          if idx > 0:
            self.emit(", ")
          if arg.name:
            self.emit(f"{self._mangle_name(arg.name)} = ")
          else:
            self.emit(f"[{idx + 1}] = ")
          self._emit_opt_wrapped(arg.expr)
        self.emit("})")
      if node.arena_expr:
        self.emit(")")
      return

    self._record_consumed_call_moves(node.arguments)

    resolved_exprs = getattr(node, "_resolved_arguments", None)
    if resolved_exprs is None:
      resolved_exprs = [arg.expr for arg in node.arguments]
    needs_temps = bool(getattr(node, "_requires_eval_order_temps", False))

    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      member_name = getattr(
        node.callee, "target_name", None
      ) or self._mangle_name(node.callee.member)
      use_colon = getattr(
        node.callee, "is_instance_method", False
      ) or self._is_runtime_method_call(node.callee)
      sep = ":" if use_colon else "."
      self.emit("((function(_r) if _r ~= nil then ")
      if needs_temps:
        temp_args = self._format_reordered_slot_temps(node, len(resolved_exprs))
        self.emit(f"return _r{sep}{member_name}({', '.join(temp_args)})")
      else:
        self.emit(f"return _r{sep}{member_name}(")
        self._emit_lua_call_args_list(resolved_exprs, node)
        self.emit(")")
      self.emit(" else return nil end end)(")
      self.visit(node.callee.receiver)
      self.emit("))")
      return

    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")

    if isinstance(node.callee, MemberAccessNode):
      from sapphire.semantics.types import (
        FunctionType,
        OptionalType,
        RefType,
        SharedRefType,
      )

      member_name = getattr(
        node.callee, "target_name", None
      ) or self._mangle_name(node.callee.member)
      receiver_name = getattr(node.callee.receiver, "name", None)
      mangled_recv = self._mangle_name(receiver_name) if receiver_name else None
      is_rt_method = self._is_runtime_method_call(node.callee)
      if getattr(node.callee, "is_instance_method", False) or is_rt_method:
        use_colon = True
      elif getattr(node.callee, "is_static_method", False):
        use_colon = False
      elif isinstance(self.get_inferred_type(node.callee), FunctionType):
        use_colon = False
      else:
        use_colon = not (
          (
            receiver_name
            and (
              receiver_name in self.known_structs
              or receiver_name in self.imported_modules
              or mangled_recv in self.imported_modules
            )
          )
          or isinstance(node.callee.receiver, MemberAccessNode)
        )
      recv_t = self.get_inferred_type(node.callee.receiver)
      if isinstance(recv_t, OptionalType):
        recv_t = recv_t.base_type
      unwrap_smart_ref = (
        use_colon
        and not is_rt_method
        and isinstance(recv_t, (RefType, SharedRefType))
      )
      if needs_temps:
        self.emit("(function() ")
        if use_colon:
          self.emit("local _r = ")
          if unwrap_smart_ref:
            self.emit("_SP_RT._unwrap_read(")
            self.visit(node.callee.receiver)
            self.emit(")")
          else:
            self.visit(node.callee.receiver)
          self.emit("; ")
          temp_args = self._format_reordered_slot_temps(
            node, len(resolved_exprs)
          )
          self.emit(f"return _r:{member_name}({', '.join(temp_args)}) end)()")
        else:
          self.emit("local _f = ")
          self.visit(node.callee.receiver)
          self.emit(f".{member_name}; ")
          temp_args = self._format_reordered_slot_temps(
            node, len(resolved_exprs)
          )
          self.emit(f"return _f({', '.join(temp_args)}) end)()")
        if node.arena_expr:
          self.emit(")")
        return
      sep = ":" if use_colon else "."
      if unwrap_smart_ref:
        self.emit("_SP_RT._unwrap_read(")
        self.visit(node.callee.receiver)
        self.emit(")")
      else:
        self.visit(node.callee.receiver)
      self.emit(f"{sep}{member_name}(")
    elif needs_temps:
      self.emit("(function() local _f = ")
      self.visit(node.callee)
      self.emit("; ")
      temp_args = self._format_reordered_slot_temps(node, len(resolved_exprs))
      self.emit(f"return _f({', '.join(temp_args)}) end)()")
      if node.arena_expr:
        self.emit(")")
      return
    else:
      self.visit(node.callee)
      self.emit("(")

    self._emit_lua_call_args_list(resolved_exprs, node)
    self.emit(")")
    if node.arena_expr:
      self.emit(")")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> None:
    lifted = getattr(self, "_lifted_short_circuits", None)
    if lifted and id(node) in lifted:
      self.emit(lifted[id(node)])
      return
    member_name = getattr(node, "target_name", None) or self._mangle_name(
      node.member
    )
    if node.is_optional:
      self.emit("((function(_r) if _r ~= nil then return _r.")
      self.emit(member_name)
      self.emit(" else return nil end end)(")
      self.visit(node.receiver)
      self.emit("))")
    else:
      self.visit(node.receiver)
      self.emit(f".{member_name}")

  def _save_nested_fn_state(self) -> dict[str, Any]:
    """Saves outer RAII, loop, match, and writeback state before a nested
    function
    body.
    """
    saved = {
      "destructor_stack": self.destructor_stack,
      "loop_destructor_depth": self.loop_destructor_depth,
      "moved_vars": self.moved_vars,
      "_var_branch_depth": self._var_branch_depth,
      "_pending_null_vars": self._pending_null_vars,
      "_pending_unconditional_null_vars": self._pending_unconditional_null_vars,
      "_branch_depth": self._branch_depth,
      "_current_match_target": self._current_match_target,
      "_current_match_done_flag": self._current_match_done_flag,
      "_match_loop_depth": self._match_loop_depth,
      "_unwrap_writebacks": self._unwrap_writebacks,
      "_loop_stack": self._loop_stack,
      "_plain_local_containers": self._plain_local_containers,
    }
    self.destructor_stack = []
    self.loop_destructor_depth = []
    self.moved_vars = set()
    self._var_branch_depth = {}
    self._pending_null_vars = []
    self._pending_unconditional_null_vars = []
    self._branch_depth = 0
    self._current_match_target = None
    self._current_match_done_flag = None
    self._match_loop_depth = 0
    self._unwrap_writebacks = {}
    self._loop_stack = []
    self._plain_local_containers = set()
    return saved

  def _restore_nested_fn_state(self, saved: dict[str, Any]) -> None:
    """Restores outer RAII, loop, match, and writeback state after a nested
    function body.
    """
    for k, v in saved.items():
      setattr(self, k, v)

  def visit_CloneNode(self, node: CloneNode) -> None:
    self.emit("_SP_RT._clone_helper(")
    self.visit(node.expr)

    if node.initializer_block:
      self.emit(", function(self)")
      self.indent()
      saved = self._save_nested_fn_state()
      try:
        self.visit(BlockNode(node.initializer_block))
      finally:
        self._restore_nested_fn_state(saved)
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
    m_name = self._identifier_map.get(node.name, self._mangle_name(node.name))
    self._record_move(m_name)
    self.emit(m_name)

  def visit_LambdaNode(self, node: LambdaNode) -> None:
    params = [self._mangle_name(p.name) for p in node.parameters]
    self.emit(f"(function({', '.join(params)})")
    self.indent()
    saved = self._save_nested_fn_state()
    try:
      if isinstance(node.body, BlockNode):
        self.visit(node.body)
      else:
        if self._contains_liftable_expr(node.body, include_moves=True):
          self._lift_match_expressions(node.body)
        self.newline()
        self.emit("return ")
        self.visit(node.body)
    finally:
      self._restore_nested_fn_state(saved)
    self.dedent()
    self.newline()
    self.emit("end)")

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> None:
    from sapphire.semantics.types import OptionalType

    arr_t = self.get_inferred_type(node)
    is_opt_arr = isinstance(arr_t, ArrayType) and isinstance(
      arr_t.element_type, OptionalType
    )
    self.emit("{")
    for idx, elem in enumerate(node.elements):
      if idx > 0:
        self.emit(", ")
      self._emit_opt_wrapped(elem, is_optional_slot=is_opt_arr)
    self.emit("}")

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> None:
    from sapphire.semantics.types import OptionalType

    map_t = self.get_inferred_type(node)
    is_opt_map = isinstance(map_t, MapType) and isinstance(
      map_t.value_type, OptionalType
    )
    self.emit("{")
    for idx, entry in enumerate(node.entries):
      if idx > 0:
        self.emit(", ")
      self.emit("[")
      self.visit(entry.key)
      self.emit("] = ")
      self._emit_opt_wrapped(entry.value, is_optional_slot=is_opt_map)
    self.emit("}")

  def visit_IndexExprNode(self, node: IndexExprNode) -> None:
    from sapphire.semantics.types import OptionalType

    recv_t = _unwrap_ref_opt_type(self.get_inferred_type(node.array))
    if isinstance(recv_t, MapType):
      self.emit("_SP_RT._sapphire_map_at(")
      self.visit(node.array)
      self.emit(", ")
      self.visit(node.index)
      self.emit(")")
      return

    at_fn = (
      "_SP_RT._sapphire_array_at_val"
      if isinstance(recv_t, ArrayType)
      and not isinstance(recv_t.element_type, OptionalType)
      else "_SP_RT._sapphire_array_at"
    )
    self.emit(f"{at_fn}(")
    self.visit(node.array)
    self.emit(", ")
    self.visit(node.index)
    self.emit(")")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> None:
    if node.arena_expr:
      self.visit(node.arena_expr)
      self.emit(":register(")

    mangled_struct = self._mangle_dotted(node.struct_name)
    resolved_exprs = getattr(node, "_resolved_field_exprs", None)
    if resolved_exprs is not None:
      opt_explicit_defaults = getattr(
        node, "_optional_explicit_default_slots", set()
      )
      last_needed = -1
      for idx, expr in enumerate(resolved_exprs):
        if expr is not None or idx in opt_explicit_defaults:
          last_needed = idx

      if getattr(node, "_requires_eval_order_temps", False):
        self.emit("(function() ")
        for f_idx, f_arg in enumerate(node.fields):
          self.emit(f"local _a{f_idx} = ")
          self.visit(f_arg.expr)
          self.emit("; ")
        slot_to_temp = {
          slot: f"_a{f_idx}"
          for f_idx, slot in enumerate(getattr(node, "_eval_order_slots", []))
        }
        args_out: list[str] = []
        for idx in range(last_needed + 1):
          if idx in slot_to_temp:
            args_out.append(slot_to_temp[idx])
          elif idx in opt_explicit_defaults:
            args_out.append("_SP_RT._SP_UNSET")
          else:
            args_out.append("nil")
        self.emit(f"return {mangled_struct}._new({', '.join(args_out)}) end)()")
      else:
        self.emit(f"{mangled_struct}._new(")
        for idx in range(last_needed + 1):
          if idx > 0:
            self.emit(", ")
          expr = resolved_exprs[idx]
          if expr is not None:
            self.visit(expr)
          elif idx in opt_explicit_defaults:
            self.emit("_SP_RT._SP_UNSET")
          else:
            self.emit("nil")
        self.emit(")")
    else:
      self.emit(f"{mangled_struct}.init({{")
      for idx, arg in enumerate(node.fields):
        if idx > 0:
          self.emit(", ")
        if arg.name:
          self.emit(f"{self._mangle_name(arg.name)} = ")
        else:
          self.emit(f"[{idx + 1}] = ")
        self._emit_opt_wrapped(arg.expr)
      self.emit("})")

    if node.arena_expr:
      self.emit(")")
