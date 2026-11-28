"""Statement and control-flow code generation mixin for LuaTranspiler."""

from typing import TYPE_CHECKING, Any

from sapphire.code_gen.base_transpiler import (
  extract_type_name,
  get_default_value_for_type_node,
)
from sapphire.code_gen.intrinsics import _resolve_range_args
from sapphire.parser.ast import (
  AssignmentNode,
  ASTNode,
  BinaryOpNode,
  BlockNode,
  BreakNode,
  CallNode,
  CastExprNode,
  CloneNode,
  ContinueNode,
  EllipsisPatternNode,
  ExprStmtNode,
  ForNode,
  FuncDeclNode,
  GuardClauseNode,
  GuardStmtNode,
  IdentifierNode,
  IfNode,
  IndexExprNode,
  InterpolatedStringNode,
  LambdaNode,
  LiteralNode,
  MatchExprNode,
  MemberAccessNode,
  MoveNode,
  OptionalTypeNode,
  ReturnNode,
  TernaryExprNode,
  UnaryOpNode,
  VarDeclNode,
  WhileNode,
  YieldNode,
)
from sapphire.semantics.symbol_table import MapType, RangeType

_OPTIONAL_CAST_FN_MAP = {
  "float": "_SP_RT._sapphire_cast_float",
  "int": "_SP_RT._sapphire_cast_int",
  "bool": "_SP_RT._sapphire_cast_bool",
  "String": "tostring",
}


def _get_optional_cast_fn(node: CastExprNode) -> str | None:
  """Returns the Lua cast helper for an optional primitive cast, or None."""
  if not isinstance(node.target_type, OptionalTypeNode):
    return None
  inner = node.target_type.base_type
  target = inner.name if hasattr(inner, "name") else str(inner)
  return _OPTIONAL_CAST_FN_MAP.get(target)


def _extract_const_int(expr: Any) -> int | None:
  """Extracts a compile-time integer literal (with optional unary +/-)."""
  if isinstance(expr, LiteralNode) and expr.lit_type == "int":
    return int(expr.value)
  if isinstance(expr, UnaryOpNode) and expr.op in ("-", "+"):
    inner = _extract_const_int(expr.expr)
    if inner is not None:
      return -inner if expr.op == "-" else inner
  return None


def _has_continue_node(node: ASTNode) -> bool:
  if isinstance(node, ContinueNode):
    return True
  if isinstance(node, (WhileNode, ForNode, LambdaNode, FuncDeclNode)):
    return False
  for attr_name, attr_val in getattr(node, "__dict__", {}).items():
    if attr_name.startswith("_"):
      continue
    if isinstance(attr_val, ASTNode):
      if _has_continue_node(attr_val):
        return True
    elif isinstance(attr_val, list):
      for item in attr_val:
        if isinstance(item, ASTNode) and _has_continue_node(item):
          return True
  return False


if TYPE_CHECKING:
  from sapphire.code_gen.lua_transpiler import (
    LuaTranspiler as _LuaTranspilerBase,
  )
else:
  _LuaTranspilerBase = object


class LuaStmtMixin(_LuaTranspilerBase):
  """Provides statement and control-flow AST emission for Lua 5.1."""

  def _is_non_opt_array_expr(self, expr: Any) -> bool:
    """Returns True if *expr* evaluates to an Array of non-optional elements."""
    from sapphire.semantics.types import (
      ArrayType,
      OptionalType,
      RefType,
      SharedRefType,
    )

    t = self.get_inferred_type(expr)
    while isinstance(t, (OptionalType, RefType, SharedRefType)):
      t = t.base_type if isinstance(t, OptionalType) else t.inner_type
    return isinstance(t, ArrayType) and not isinstance(
      t.element_type, OptionalType
    )

  def _emit_value_expr(self, expr: Any) -> None:
    """Emits *expr*, choosing the fastest type-directed value copy helper."""
    kind, unwrapped_t = self._classify_value_copy(expr)
    if kind == "NONE":
      self.visit(expr)
    elif kind == "SHALLOW_ARRAY":
      self.emit("_SP_RT._sapphire_copy_array_flat(")
      self.visit(expr)
      self.emit(")")
    elif kind == "SHALLOW_MAP":
      self.emit("_SP_RT._sapphire_copy_map_flat(")
      self.visit(expr)
      self.emit(")")
    elif kind == "FLAT_STRUCT" and unwrapped_t is not None:
      self.emit(f"{self._mangle_dotted(unwrapped_t.name)}._copy(")
      self.visit(expr)
      self.emit(")")
    else:
      self.emit("_SP_RT._sapphire_copy(")
      self.visit(expr)
      self.emit(")")

  def _is_map_expr(self, expr: Any) -> bool:
    """Returns True if *expr* evaluates to a Map (unwrapping
    Optional/Ref/SharedRef).
    """
    from sapphire.semantics.types import OptionalType, RefType, SharedRefType

    t = self.get_inferred_type(expr)
    while isinstance(t, (OptionalType, RefType, SharedRefType)):
      t = t.base_type if isinstance(t, OptionalType) else t.inner_type
    return isinstance(t, MapType)

  def _is_string_expr(self, expr: Any) -> bool:
    """Returns True if *expr* has String type."""
    from sapphire.semantics.types import PrimitiveType

    if isinstance(expr, LiteralNode) and expr.lit_type == "string":
      return True
    if isinstance(expr, InterpolatedStringNode):
      return True
    t = self.get_inferred_type(expr)
    return isinstance(t, PrimitiveType) and t.name == "String"

  def _contains_liftable_expr(
    self, node: Any, include_moves: bool = False
  ) -> bool:
    """Returns True if *node* contains a liftable expression or (optionally)
    MoveNode.
    """
    if node is None:
      return False
    if isinstance(node, (MatchExprNode, TernaryExprNode)):
      return True
    if isinstance(node, BinaryOpNode) and node.op == "??":
      return True
    if (
      isinstance(node, CallNode)
      and isinstance(node.callee, MemberAccessNode)
      and node.callee.is_optional
    ):
      return True
    if isinstance(node, MemberAccessNode) and node.is_optional:
      return True
    if (
      isinstance(node, CastExprNode) and _get_optional_cast_fn(node) is not None
    ):
      return True
    if isinstance(node, MoveNode):
      return include_moves
    if isinstance(node, (LambdaNode, FuncDeclNode)):
      return False
    if isinstance(node, CloneNode):
      return self._contains_liftable_expr(
        node.expr, include_moves=include_moves
      ) or (
        bool(node.arena_expr)
        and self._contains_liftable_expr(
          node.arena_expr, include_moves=include_moves
        )
      )
    if isinstance(node, list):
      return any(
        self._contains_liftable_expr(item, include_moves=include_moves)
        for item in node
      )
    if isinstance(node, ASTNode):
      for k, v in node.__dict__.items():
        if k.startswith("_"):
          continue
        if isinstance(v, (ASTNode, list)):
          if self._contains_liftable_expr(v, include_moves=include_moves):
            return True
    return False

  def _stmt_contains_match_yield(self, node: Any) -> bool:
    """Returns True if *node* contains a YieldNode targeting the current match
    arm.
    """
    if node is None:
      return False
    if isinstance(node, YieldNode):
      return True
    if isinstance(node, (MatchExprNode, LambdaNode, FuncDeclNode)):
      return False
    if isinstance(node, list):
      return any(self._stmt_contains_match_yield(item) for item in node)
    if isinstance(node, ASTNode):
      for k, v in node.__dict__.items():
        if k.startswith("_"):
          continue
        if isinstance(v, (ASTNode, list)):
          if self._stmt_contains_match_yield(v):
            return True
    return False

  def _arm_needs_done_flag(self, body: Any) -> bool:
    """Returns True if a match block arm can yield before the end of the block.
    """
    if not isinstance(body, BlockNode) or not body.statements:
      return False
    for idx, stmt in enumerate(body.statements):
      if idx < len(body.statements) - 1 and self._stmt_contains_match_yield(
        stmt
      ):
        return True
      if not isinstance(stmt, YieldNode) and self._stmt_contains_match_yield(
        stmt
      ):
        return True
    return False

  def _visit_block(
    self,
    node: BlockNode,
    extra_destructibles: list[str] | None = None,
  ) -> None:
    """Visits a BlockNode with LIFO RAII teardown and Lua 5.1 terminator safety.
    """
    prev_wb = self._unwrap_writebacks.copy()
    self._unwrap_writebacks = dict(prev_wb)
    self.destructor_stack.append([])
    for d_var in extra_destructibles or []:
      self.destructor_stack[-1].append(d_var)
      self._var_branch_depth[d_var] = self._branch_depth
    prev_id_map = self._identifier_map.copy() if self._module_ns_names else None
    if getattr(node, "_block_destructibles", None):
      for d_var in node._block_destructibles:
        if d_var not in self.destructor_stack[-1]:
          self.destructor_stack[-1].append(d_var)
          self._var_branch_depth[d_var] = self._branch_depth

    terminated = False
    done_flag = self._current_match_done_flag
    guarded_indent = 0
    if not node.statements:
      self.newline()
      self.emit("-- pass")
    else:
      can_have_yielded = False
      for stmt in node.statements:
        if done_flag and can_have_yielded:
          self.newline()
          self.emit(f"if not {done_flag} then")
          self.indent()
          guarded_indent += 1
          can_have_yielded = False
        self.visit(stmt)
        if not isinstance(stmt, ReturnNode):
          self._drain_pending_null_vars("nil")
        if isinstance(stmt, (ReturnNode, BreakNode, ContinueNode)):
          terminated = True
          break
        if done_flag and self._stmt_contains_match_yield(stmt):
          can_have_yielded = True

    while guarded_indent > 0:
      self.dedent()
      self.newline()
      self.emit("end")
      guarded_indent -= 1

    current_destructors = self.destructor_stack.pop()
    if not terminated:
      for var_name in reversed(current_destructors):
        if var_name not in self.moved_vars:
          self.newline()
          self._emit_destructor_call(var_name)
    for var_name in current_destructors:
      self.moved_vars.discard(var_name)
      self._var_branch_depth.pop(var_name, None)
    if prev_id_map is not None:
      self._identifier_map = prev_id_map
    self._unwrap_writebacks = prev_wb

  def visit_BlockNode(self, node: BlockNode) -> None:
    self._visit_block(node)

  def _lift_match_expressions(self, node: Any) -> None:
    """Lifts MatchExprNode and IIFE-prone short-circuit/optional expressions."""
    if node is None:
      return

    if isinstance(node, TernaryExprNode):
      if id(node) not in self._lifted_short_circuits:
        self._lift_match_expressions(node.condition)
        res_var = self._next_temp_name("_sc")
        self.newline()
        self.emit(f"local {res_var}")
        self.newline()
        self.emit("if ")
        self.visit(node.condition)
        self.emit(" then")
        self.indent()
        self._branch_depth += 1
        try:
          self._lift_match_expressions(node.true_expr)
          self.newline()
          self.emit(f"{res_var} = ")
          self.visit(node.true_expr)
          self._drain_pending_null_vars("nil")
        finally:
          self._branch_depth -= 1
        self.dedent()
        self.newline()
        self.emit("else")
        self.indent()
        self._branch_depth += 1
        try:
          self._lift_match_expressions(node.false_expr)
          self.newline()
          self.emit(f"{res_var} = ")
          self.visit(node.false_expr)
          self._drain_pending_null_vars("nil")
        finally:
          self._branch_depth -= 1
        self.dedent()
        self.newline()
        self.emit("end")
        self._lifted_short_circuits[id(node)] = res_var
      return

    if isinstance(node, BinaryOpNode) and node.op in ("??", "&&", "||"):
      if node.op == "??" or self._contains_liftable_expr(
        node.right, include_moves=True
      ):
        if id(node) not in self._lifted_short_circuits:
          self._lift_match_expressions(node.left)
          res_var = self._next_temp_name("_sc")
          self.newline()
          self.emit(f"local {res_var} = ")
          self.visit(node.left)
          self.newline()
          if node.op == "??":
            self.emit(f"if {res_var} == nil then")
          elif node.op == "&&":
            self.emit(f"if {res_var} then")
          else:
            self.emit(f"if not {res_var} then")
          self.indent()
          self._branch_depth += 1
          try:
            self._lift_match_expressions(node.right)
            self.newline()
            self.emit(f"{res_var} = ")
            self.visit(node.right)
            self._drain_pending_null_vars("nil")
          finally:
            self._branch_depth -= 1
          self.dedent()
          self.newline()
          self.emit("end")
          self._lifted_short_circuits[id(node)] = res_var
        return
      self._lift_match_expressions(node.left)
      self._lift_match_expressions(node.right)
      return

    if (
      isinstance(node, CallNode)
      and isinstance(node.callee, MemberAccessNode)
      and node.callee.is_optional
    ):
      if id(node) not in self._lifted_short_circuits:
        self._lift_match_expressions(node.callee.receiver)
        recv_tmp = self._next_temp_name("_opt_r")
        res_var = self._next_temp_name("_opt_res")
        self.newline()
        self.emit(f"local {recv_tmp} = ")
        self.visit(node.callee.receiver)
        self.newline()
        self.emit(f"local {res_var} = nil")
        self.newline()
        self.emit(f"if {recv_tmp} ~= nil then")
        self.indent()
        self._branch_depth += 1
        orig_recv = node.callee.receiver
        orig_opt = node.callee.is_optional
        try:
          for arg in node.arguments:
            self._lift_match_expressions(arg.expr)
          recv_id = IdentifierNode(recv_tmp)
          recv_id.inferred_type = self.get_inferred_type(orig_recv)
          node.callee.receiver = recv_id
          node.callee.is_optional = False
          self.newline()
          self.emit(f"{res_var} = ")
          self.visit(node)
          self._drain_pending_null_vars("nil")
        finally:
          node.callee.receiver = orig_recv
          node.callee.is_optional = orig_opt
          self._branch_depth -= 1
        self.dedent()
        self.newline()
        self.emit("end")
        self._lifted_short_circuits[id(node)] = res_var
      return

    if isinstance(node, MemberAccessNode) and node.is_optional:
      if id(node) not in self._lifted_short_circuits:
        self._lift_match_expressions(node.receiver)
        recv_tmp = self._next_temp_name("_opt_r")
        res_var = self._next_temp_name("_opt_res")
        member_name = getattr(node, "target_name", None) or self._mangle_name(
          node.member
        )
        self.newline()
        self.emit(f"local {recv_tmp} = ")
        self.visit(node.receiver)
        self.newline()
        self.emit(f"local {res_var} = nil")
        self.newline()
        self.emit(f"if {recv_tmp} ~= nil then")
        self.indent()
        self.newline()
        self.emit(f"{res_var} = {recv_tmp}.{member_name}")
        self.dedent()
        self.newline()
        self.emit("end")
        self._lifted_short_circuits[id(node)] = res_var
      return

    if isinstance(node, CastExprNode):
      cast_fn = _get_optional_cast_fn(node)
      if cast_fn is not None:
        from sapphire.semantics.types import OptionalType, PrimitiveType

        src_t = self.get_inferred_type(node.expr)
        src_base = src_t.base_type if isinstance(src_t, OptionalType) else src_t
        inner = node.target_type.base_type
        target = inner.name if hasattr(inner, "name") else str(inner)
        if isinstance(src_base, PrimitiveType) and (
          src_base.name == target
          or (src_base.name == "int" and target == "float")
        ):
          self._lift_match_expressions(node.expr)
          return
        if (
          target == "int"
          and isinstance(src_t, OptionalType)
          and isinstance(src_t.base_type, PrimitiveType)
          and src_t.base_type.name == "float"
        ):
          cast_fn = "_SP_RT._sapphire_trunc"
        if id(node) not in self._lifted_short_circuits:
          self._lift_match_expressions(node.expr)
          res_var = self._next_temp_name("_sc")
          self.newline()
          self.emit(f"local {res_var} = ")
          self.visit(node.expr)
          self.newline()
          self.emit(f"if {res_var} ~= nil then")
          self.indent()
          self.newline()
          self.emit(f"{res_var} = {cast_fn}({res_var})")
          self.dedent()
          self.newline()
          self.emit("end")
          self._lifted_short_circuits[id(node)] = res_var
        return

    if isinstance(node, (LambdaNode, FuncDeclNode)):
      return

    if isinstance(node, CloneNode):
      self._lift_match_expressions(node.expr)
      if node.arena_expr:
        self._lift_match_expressions(node.arena_expr)
      if (
        node.initializer_block
        and id(node) not in self._lifted_short_circuits
      ):
        clone_var = self._next_temp_name("_clone")
        self.newline()
        self.emit(f"local {clone_var} = _SP_RT._clone_helper(")
        self.visit(node.expr)
        if node.arena_expr:
          self.emit(", nil, ")
          self.visit(node.arena_expr)
        self.emit(")")
        prev_id_map = self._identifier_map.copy()
        self._identifier_map["self"] = clone_var
        has_var_decl = any(
          isinstance(s, VarDeclNode) for s in node.initializer_block
        )
        try:
          if has_var_decl:
            self.newline()
            self.emit("do")
            self.indent()
            self.visit(BlockNode(node.initializer_block))
            self.dedent()
            self.newline()
            self.emit("end")
          else:
            self.visit(BlockNode(node.initializer_block))
        finally:
          self._identifier_map = prev_id_map
        self._lifted_short_circuits[id(node)] = clone_var
      return

    if isinstance(node, MatchExprNode):
      if id(node) not in self._lifted_matches:
        self._lifted_matches[id(node)] = self._emit_match_statement(node)
      return

    if isinstance(node, list):
      for item in node:
        self._lift_match_expressions(item)
      return

    if isinstance(node, ASTNode):
      for k, v in node.__dict__.items():
        if k.startswith("_"):
          continue
        if isinstance(v, (ASTNode, list)):
          self._lift_match_expressions(v)

  def _emit_writebacks(self, targets: list[Any]) -> None:
    """Emits writeback statements for any `if var`/`guard var`/`for var`
    bindings
    in *targets*.
    """
    wb_map = self._unwrap_writebacks
    if not wb_map:
      return
    for target in targets:
      if not isinstance(target, IdentifierNode):
        continue
      m_name = self._identifier_map.get(
        target.name, self._mangle_name(target.name)
      )
      entry = wb_map.get(m_name) or wb_map.get(target.name)
      if not entry:
        continue
      kind = entry[0]
      if kind == "direct_arr_index":
        _, wb_arr, wb_idx, is_opt_elem = entry
        self.newline()
        if is_opt_elem:
          self.emit(f"{wb_arr}[{wb_idx}] = _SP_RT._wrap_opt({m_name})")
        else:
          self.emit(f"{wb_arr}[{wb_idx}] = {m_name}")
      elif kind == "direct_map_index":
        _, wb_map, wb_key, is_opt_val = entry
        self.newline()
        if is_opt_val:
          self.emit(f"{wb_map}[{wb_key}] = _SP_RT._wrap_opt({m_name})")
        else:
          self.emit(f"{wb_map}[{wb_key}] = {m_name}")
      elif kind == "arr_index":
        _, wb_recv, wb_key = entry
        self.newline()
        self.emit(f"_SP_RT._sapphire_array_set({wb_recv}, {wb_key}, {m_name})")
      elif kind == "map_index":
        _, wb_recv, wb_key = entry
        self.newline()
        self.emit(f"_SP_RT._sapphire_map_set({wb_recv}, {wb_key}, {m_name})")
      elif kind == "attr":
        _, wb_recv, attr_name = entry
        self.newline()
        self.emit(f"{wb_recv}.{attr_name} = {m_name}")
      elif kind == "var":
        _, target_var = entry
        self.newline()
        self.emit(f"{target_var} = {m_name}")

  def _emit_binding_rhs_and_writeback(
    self, binding: Any, val_var: str
  ) -> tuple | None:
    """Emits evaluation of a header/guard binding into `val_var` and returns
    writeback metadata.
    """
    if hasattr(binding, "_writeback_container"):
      recv_expr, key_expr, is_arr = binding._writeback_container
      wb_recv = self._next_temp_name("_wb_recv")
      wb_key = self._next_temp_name("_wb_key")
      self.emit(f"local {wb_recv} = ")
      self.visit(recv_expr)
      self.newline()
      self.emit(f"local {wb_key} = ")
      self.visit(key_expr)
      self.newline()
      slot_expr = (
        f"_SP_RT._sapphire_array_get({wb_recv}, {wb_key})"
        if is_arr
        else f"_SP_RT._sapphire_map_get({wb_recv}, {wb_key})"
      )
      self.emit(f"local {val_var} = {slot_expr}")
      return ("arr_index" if is_arr else "map_index", wb_recv, wb_key)

    if binding.is_unwrap and getattr(binding, "is_mutable", False):
      expr = binding.expr
      if isinstance(expr, IdentifierNode):
        target_var = self._identifier_map.get(
          expr.name, self._mangle_name(expr.name)
        )
        self.emit(f"local {val_var} = {target_var}")
        return ("var", target_var)
      if isinstance(expr, MemberAccessNode) and not expr.is_optional:
        wb_recv = self._next_temp_name("_wb_recv")
        member_name = getattr(expr, "target_name", None) or self._mangle_name(
          expr.member
        )
        self.emit(f"local {wb_recv} = ")
        self.visit(expr.receiver)
        self.newline()
        self.emit(f"local {val_var} = {wb_recv}.{member_name}")
        return ("attr", wb_recv, member_name)
      if isinstance(expr, IndexExprNode):
        wb_recv = self._next_temp_name("_wb_recv")
        wb_key = self._next_temp_name("_wb_key")
        is_map = self._is_map_expr(expr.array)
        self.emit(f"local {wb_recv} = ")
        self.visit(expr.array)
        self.newline()
        self.emit(f"local {wb_key} = ")
        self.visit(expr.index)
        self.newline()
        slot_expr = (
          f"_SP_RT._sapphire_map_at({wb_recv}, {wb_key})"
          if is_map
          else f"_SP_RT._sapphire_array_at({wb_recv}, {wb_key})"
        )
        self.emit(f"local {val_var} = {slot_expr}")
        return ("map_index" if is_map else "arr_index", wb_recv, wb_key)

    self.emit(f"local {val_var} = ")
    self.visit(binding.expr)
    return None

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    self._lift_match_expressions(node.exprs)

    self.newline()
    is_mod_ns_top = bool(
      self._module_ns_names and self.indent_level == 0 and not self.dev_mode
    )
    if is_mod_ns_top:
      names_str = ", ".join(
        self._lua_mod_sym(n) for n in node.names
      )
    else:
      names_str = ", ".join([self._mangle_name(n) for n in node.names])
    if (
      self.dev_mode
      and self.indent_level == 0
      and len(node.names) == 1
      and node.exprs
    ):
      name = self._mangle_name(node.names[0])
      self.emit(f"if {name} == nil then {name} = ")
      self._emit_value_expr(node.exprs[0])
      self.emit(" end")
    elif is_mod_ns_top:
      self.emit(f"{names_str} = ")
      if node.exprs:
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self._emit_value_expr(expr)
      else:
        defaults = []
        for idx, _name in enumerate(node.names):
          val_type = node.val_types[idx] if idx < len(node.val_types) else None
          default_expr = get_default_value_for_type_node(val_type)
          if default_expr:
            defaults.append(self.capture_expr(default_expr))
          else:
            defaults.append("nil")
        self.emit(", ".join(defaults))
    else:
      self.emit(f"local {names_str}")
      if node.exprs:
        self.emit(" = ")
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self._emit_value_expr(expr)
      else:
        defaults = []
        has_non_nil = False
        for idx, _name in enumerate(node.names):
          val_type = node.val_types[idx] if idx < len(node.val_types) else None
          default_expr = get_default_value_for_type_node(val_type)
          if default_expr:
            defaults.append(self.capture_expr(default_expr))
            if default_expr.lit_type != "none":
              has_non_nil = True
          else:
            defaults.append("nil")
        if has_non_nil:
          self.emit(" = " + ", ".join(defaults))

    for idx, name in enumerate(node.names):
      if self._module_ns_names and self.indent_level > 0:
        self._identifier_map.pop(name, None)
      val_type = node.val_types[idx] if idx < len(node.val_types) else None
      type_name = extract_type_name(val_type) if val_type else None
      st_name = None
      if type_name and type_name in self.structs_with_destructor:
        st_name = type_name
      elif (
        val_type
        and (val_inferred := self.get_inferred_type(val_type)) is not None
      ):
        st_name = self._type_needs_destructor(val_inferred)
      elif node.exprs and idx < len(node.exprs):
        st_name = self._expr_destructible_struct(node.exprs[idx])
      elif node.exprs and len(node.exprs) == 1:
        st_name = self._expr_destructible_struct(
          node.exprs[0], return_index=idx
        )
      elif node.expr:
        st_name = self._expr_destructible_struct(node.expr, return_index=idx)

      if st_name:
        m_name = self._mangle_name(name)
        self.variable_types[m_name] = st_name
        if self.destructor_stack:
          self.destructor_stack[-1].append(m_name)
          self._var_branch_depth[m_name] = self._branch_depth
      if (
        self.indent_level > 0
        and node.exprs
        and len(node.exprs) == len(node.names)
        and self._is_fresh_plain_container_expr(node.exprs[idx])
      ):
        self._plain_local_containers.add(name)
      else:
        self._plain_local_containers.discard(name)

  def _is_int_div_assign(self, node: AssignmentNode) -> bool:
    """Returns True if *node* is an integer `/=` compound assignment."""
    if node.op != "/=":
      return False
    from sapphire.semantics.types import PrimitiveType

    tt = self.get_inferred_type(node.target)
    et = self.get_inferred_type(node.expr)
    return (
      isinstance(tt, PrimitiveType)
      and tt.name == "int"
      and isinstance(et, PrimitiveType)
      and et.name == "int"
    )

  def _is_string_concat_assign(self, node: AssignmentNode) -> bool:
    """Returns True if *node* is a String `+=` compound assignment."""
    if node.op != "+=":
      return False
    return (
      getattr(node, "is_string_concat", False)
      or self._is_string_expr(node.target)
      or self._is_string_expr(node.expr)
    )

  def _emit_compound_rhs(
    self,
    lhs_code: str,
    node: AssignmentNode,
    is_int_div: bool,
    is_str_concat: bool,
  ) -> None:
    """Emits the RHS computation for a compound assignment given already-safe
    *lhs_code*.
    """
    if is_int_div:
      self.emit(f"_SP_RT._sapphire_div({lhs_code}, ")
      self.visit(node.expr)
      self.emit(")")
    elif is_str_concat:
      self.emit(f"{lhs_code} .. ")
      self._visit_concat_operand(node.expr, is_string_concat=True)
    else:
      raw_op = node.op[:-1]
      self.emit(f"{lhs_code} {raw_op} ")
      self.visit(node.expr)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self._lift_match_expressions(node.targets)
    self._lift_match_expressions(node.exprs)

    if node.op == "=":
      has_index_target = any(isinstance(t, IndexExprNode) for t in node.targets)

      live_destructible_targets = [
        self._mangle_name(t.name)
        for t in node.targets
        if isinstance(t, IdentifierNode)
        and self._is_active_destructible_var(self._mangle_name(t.name))
        and self._mangle_name(t.name) not in self.moved_vars
      ]
      if live_destructible_targets or (
        has_index_target and len(node.targets) > 1
      ):
        tmp_base = self._next_temp_name("_reassign")
        tmp_names = [f"{tmp_base}_{i + 1}" for i in range(len(node.targets))]
        self.newline()
        self.emit("local " + ", ".join(tmp_names) + " = ")
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self._emit_value_expr(expr)
        for m_t in live_destructible_targets:
          if (
            m_t not in self.moved_vars
            and m_t not in self._pending_null_vars
            and m_t not in self._pending_unconditional_null_vars
          ):
            self.newline()
            self._emit_destructor_call(m_t)
        assigned_id_names = {
          self._mangle_name(t.name)
          for t in node.targets
          if isinstance(t, IdentifierNode)
        }
        self._drain_pending_null_vars("nil", exclude=assigned_id_names)
        for idx, target in enumerate(node.targets):
          if isinstance(target, IdentifierNode):
            self.moved_vars.discard(self._mangle_name(target.name))
          self.newline()
          if isinstance(target, IndexExprNode):
            setter = (
              "_SP_RT._sapphire_map_set"
              if self._is_map_expr(target.array)
              else "_SP_RT._sapphire_array_set"
            )
            self.emit(f"{setter}(")
            self.visit(target.array)
            self.emit(", ")
            self.visit(target.index)
            self.emit(f", {tmp_names[idx]})")
          else:
            self.visit(target)
            self.emit(f" = {tmp_names[idx]}")
        self._emit_writebacks(node.targets)
        return

      if has_index_target and len(node.targets) == 1:
        target = node.targets[0]
        if self._is_map_expr(target.array):
          setter = "_SP_RT._sapphire_map_set"
        elif self._is_non_opt_array_expr(target.array):
          setter = "_SP_RT._sapphire_array_set_val"
        else:
          setter = "_SP_RT._sapphire_array_set"
        self.newline()
        self.emit(f"{setter}(")
        self.visit(target.array)
        self.emit(", ")
        self.visit(target.index)
        self.emit(", ")
        self._emit_value_expr(node.exprs[0])
        self.emit(")")
        return

      self.newline()
      for idx, target in enumerate(node.targets):
        if isinstance(target, IdentifierNode):
          self.moved_vars.discard(self._mangle_name(target.name))
          if len(node.exprs) == len(node.targets) and (
            self._is_fresh_plain_container_expr(node.exprs[idx])
          ):
            pass
          else:
            self._plain_local_containers.discard(target.name)
        if idx > 0:
          self.emit(", ")
        self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self._emit_value_expr(expr)
      self._emit_writebacks(node.targets)
      return

    # Compound assignment (+=, -=, *=, /=, %=)
    is_int_div = self._is_int_div_assign(node)
    is_str_concat = self._is_string_concat_assign(node)
    self.newline()
    if isinstance(node.target, IdentifierNode):
      m_t = self._identifier_map.get(
        node.target.name, self._mangle_name(node.target.name)
      )
      self.moved_vars.discard(m_t)
      self.emit(f"{m_t} = ")
      self._emit_compound_rhs(m_t, node, is_int_div, is_str_concat)
    elif isinstance(node.target, MemberAccessNode):
      obj_tmp = self._next_temp_name("_cobj")
      member_name = getattr(
        node.target, "target_name", None
      ) or self._mangle_name(node.target.member)
      self.emit(f"local {obj_tmp} = ")
      self.visit(node.target.receiver)
      self.newline()
      lhs_code = f"{obj_tmp}.{member_name}"
      self.emit(f"{lhs_code} = ")
      self._emit_compound_rhs(lhs_code, node, is_int_div, is_str_concat)
    elif isinstance(node.target, IndexExprNode):
      arr_tmp = self._next_temp_name("_carr")
      idx_tmp = self._next_temp_name("_cidx")
      if self._is_map_expr(node.target.array):
        val_tmp = self._next_temp_name("_cval")
        self.emit(f"local {idx_tmp} = ")
        self.visit(node.target.index)
        self.newline()
        self.emit(f"local {arr_tmp}, {val_tmp} = _SP_RT._sapphire_map_ref(")
        self.visit(node.target.array)
        self.emit(f", {idx_tmp})")
        self.newline()
        self.emit(f"{arr_tmp}[{idx_tmp}] = ")
        self._emit_compound_rhs(val_tmp, node, is_int_div, is_str_concat)
      else:
        self.emit(f"local {arr_tmp}, {idx_tmp} = _SP_RT._sapphire_array_ref(")
        self.visit(node.target.array)
        self.emit(", ")
        self.visit(node.target.index)
        self.emit(")")
        self.newline()
        lhs_code = f"{arr_tmp}[{idx_tmp}]"
        self.emit(f"{lhs_code} = ")
        self._emit_compound_rhs(lhs_code, node, is_int_div, is_str_concat)
    else:
      lhs_code = self.capture_expr(node.target)
      self.emit(f"{lhs_code} = ")
      self._emit_compound_rhs(lhs_code, node, is_int_div, is_str_concat)
    self._emit_writebacks([node.target])

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self._lift_match_expressions(node.expr)
    self.newline()
    if (
      isinstance(node.expr, CallNode)
      and id(node.expr) not in self._lifted_short_circuits
    ):
      expr_out = self.capture_expr(node.expr)
      if expr_out.startswith("(") or not expr_out.endswith(")"):
        self.emit(f"do local _ = {expr_out} end")
      else:
        self.emit(expr_out)
    else:
      self.emit("do local _ = ")
      self.visit(node.expr)
      self.emit(" end")

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    all_active_destructors = [
      d for frame in reversed(self.destructor_stack) for d in reversed(frame)
    ]
    self._lift_match_expressions(node.expressions)

    # RVO: Identifiers returned directly are transferred to caller, so elide
    # local destructor
    returned_ids = {
      self._identifier_map.get(expr.name, self._mangle_name(expr.name))
      for expr in node.expressions
      if isinstance(expr, (IdentifierNode, MoveNode))
    }
    destructors_to_run = [
      d
      for d in all_active_destructors
      if d not in returned_ids
      and d not in self.moved_vars
      and d not in self._pending_null_vars
      and d not in self._pending_unconditional_null_vars
    ]

    # If return expressions exist alongside destructors, evaluate expressions
    # first
    should_evaluate_first = bool(
      node.expressions
      and destructors_to_run
      and not all(
        isinstance(e, (LiteralNode, IdentifierNode)) for e in node.expressions
      )
    )

    if should_evaluate_first:
      from sapphire.semantics.types import MultiReturnType

      if len(node.expressions) == 1:
        inferred = self.get_inferred_type(node.expressions[0])
        if isinstance(inferred, MultiReturnType):
          arity = len(inferred.types)
          ret_base = self._next_temp_name("_ret")
          ret_vars = [f"{ret_base}_{i + 1}" for i in range(arity)]
          ret_list = ", ".join(ret_vars)
          self.newline()
          self.emit(f"local {ret_list} = ")
          self.visit(node.expressions[0])
          self._drain_pending_destroy_moved_vars()
          for var_name in destructors_to_run:
            if (
              var_name not in self.moved_vars
              and var_name not in self._pending_null_vars
              and var_name not in self._pending_unconditional_null_vars
            ):
              self.newline()
              self._emit_destructor_call(var_name)
          self.newline()
          self.emit(f"return {ret_list}")
          self._pending_null_vars.clear()
          self._pending_unconditional_null_vars.clear()
          self._pending_destroy_moved_vars.clear()
          return

      ret_tmps = []
      for idx, expr in enumerate(node.expressions):
        tmp_name = f"_ret_val_{idx + 1}"
        ret_tmps.append(tmp_name)
        self.newline()
        self.emit(f"local {tmp_name} = ")
        self.visit(expr)

      self._drain_pending_destroy_moved_vars()
      for var_name in destructors_to_run:
        if (
          var_name not in self.moved_vars
          and var_name not in self._pending_null_vars
          and var_name not in self._pending_unconditional_null_vars
        ):
          self.newline()
          self._emit_destructor_call(var_name)

      self.newline()
      self.emit("return " + ", ".join(ret_tmps))
      self._pending_null_vars.clear()
      self._pending_unconditional_null_vars.clear()
      self._pending_destroy_moved_vars.clear()
      return

    for var_name in destructors_to_run:
      if (
        var_name not in self.moved_vars
        and var_name not in self._pending_null_vars
        and var_name not in self._pending_unconditional_null_vars
      ):
        self.newline()
        self._emit_destructor_call(var_name)

    self.newline()
    if node.expressions:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    elif getattr(self, "_in_del_repeat", False):
      self.emit("break")
    else:
      self.emit("return")
    self._pending_null_vars.clear()
    self._pending_unconditional_null_vars.clear()
    self._pending_destroy_moved_vars.clear()

  def _scan_match_yield_arity(self, node: MatchExprNode) -> int:
    """Returns the output arity (>= 1) of a MatchExprNode."""
    from sapphire.semantics.types import MultiReturnType

    inferred = self.get_inferred_type(node)
    if isinstance(inferred, MultiReturnType):
      return max(1, len(inferred.types))
    max_arity = 1

    def _walk(n: Any) -> None:
      nonlocal max_arity
      if n is None or isinstance(n, (MatchExprNode, LambdaNode, FuncDeclNode)):
        return
      if isinstance(n, YieldNode):
        exprs = getattr(n, "expressions", None) or ([n.expr] if n.expr else [])
        if len(exprs) > max_arity:
          max_arity = len(exprs)
        return
      if isinstance(n, list):
        for item in n:
          _walk(item)
        return
      if isinstance(n, ASTNode):
        for k, v in n.__dict__.items():
          if not k.startswith("_") and isinstance(v, (ASTNode, list)):
            _walk(v)

    for case in node.cases:
      if isinstance(case.body, BlockNode):
        _walk(case.body)
    return max_arity

  def _emit_match_statement(
    self, node: MatchExprNode, target_var: str | None = ""
  ) -> str:
    self._lift_match_expressions(node.subject)

    if target_var == "":
      arity = self._scan_match_yield_arity(node)
      base_var = self._next_temp_name("_match_res")
      if arity > 1:
        vars_list = [f"{base_var}_{i + 1}" for i in range(arity)]
        target_var = ", ".join(vars_list)
        self.newline()
        self.emit(f"local {target_var}")
      else:
        target_var = base_var
        self.newline()
        self.emit(f"local {target_var} = nil")

    subj_var = self._next_temp_name("_subj")
    self.newline()
    self.emit(f"local {subj_var} = ")
    self.visit(node.subject)

    done_flag: str | None = None
    if target_var and any(
      self._arm_needs_done_flag(c.body) for c in node.cases
    ):
      done_flag = self._next_temp_name("_match_done")
      self.newline()
      self.emit(f"local {done_flag} = false")

    prev_target = self._current_match_target
    prev_match_node = self._current_match_node
    prev_done = self._current_match_done_flag
    prev_loop_depth = self._match_loop_depth
    self._current_match_target = target_var
    self._current_match_node = node
    self._current_match_done_flag = done_flag
    self._match_loop_depth = 0

    try:
      for idx, case in enumerate(node.cases):
        has_ellipsis = any(
          isinstance(p, EllipsisPatternNode) for p in case.patterns
        )
        self.newline()
        if has_ellipsis:
          if idx == 0:
            self.emit("if true then")
          elif idx == len(node.cases) - 1:
            self.emit("else")
          else:
            self.emit("elseif true then")
        else:
          kw = "if" if idx == 0 else "elseif"
          self.emit(f"{kw} ")
          for p_idx, pat in enumerate(case.patterns):
            if p_idx > 0:
              self.emit(" or ")
            if isinstance(pat, EllipsisPatternNode):
              self.emit("true")
            else:
              self.emit(f"{subj_var} == ")
              self.visit(pat)
          self.emit(" then")

        self.indent()
        self._branch_depth += 1
        try:
          if isinstance(case.body, BlockNode):
            self.visit(case.body)
          else:
            self._lift_match_expressions(case.body)
            self.newline()
            if target_var:
              self.emit(f"{target_var} = ")
              self.visit(case.body)
            else:
              self.visit(case.body)  # pragma: no cover
          self._drain_pending_null_vars("nil")
        finally:
          self._branch_depth -= 1
        self.dedent()

      self.newline()
      self.emit("end")
    finally:
      self._current_match_target = prev_target
      self._current_match_node = prev_match_node
      self._current_match_done_flag = prev_done
      self._match_loop_depth = prev_loop_depth

    return target_var or ""

  def visit_YieldNode(self, node: YieldNode) -> None:
    exprs = getattr(node, "expressions", None) or (
      [node.expr] if node.expr else []
    )
    self._lift_match_expressions(exprs)
    target = self._current_match_target
    done_flag = self._current_match_done_flag
    self.newline()
    if target:
      self.emit(f"{target} = ")
      if not exprs:
        self.emit("nil")
      else:
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
      if done_flag:
        self.newline()
        self.emit(f"{done_flag} = true")
        if self._match_loop_depth > 0:
          self._emit_loop_destructors()
          self.newline()
          if self._loop_stack and self._loop_stack[-1]:
            self.emit("_break_outer = true")
            self.newline()
          self.emit("break")
    else:
      if not exprs:
        self.emit("coroutine.yield()")
      elif len(exprs) == 1:
        self.emit("coroutine.yield(")
        self.visit(exprs[0])
        self.emit(")")
      else:
        self.emit("coroutine.yield(")
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        self.emit(")")

  def visit_MatchExprNode(self, node: MatchExprNode) -> None:
    if id(node) not in self._lifted_matches:
      self._lifted_matches[id(node)] = self._emit_match_statement(node)
    self.emit(self._lifted_matches[id(node)])

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    pass

  def _emit_simple_if(self, node: IfNode) -> None:
    """Emits a standard `if cond then ... else ... end` statement."""
    if node.condition:
      self._lift_match_expressions(node.condition)
    self.newline()
    self.emit("if ")
    self.visit(node.condition)
    self.emit(" then")
    self.indent()
    self._visit_in_branch(node.then_block)
    self.dedent()
    if node.else_block:
      self.newline()
      self.emit("else")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()
    self.newline()
    self.emit("end")

  def _emit_single_binding_if(self, node: IfNode, binding: Any) -> None:
    """Emits a single `if let`/`if var` (optional unwrap or init) statement."""
    self._lift_match_expressions(binding.expr)
    let_names = getattr(binding, "let_names", [binding.let_name])
    let_name = binding.let_name

    st_name = self._expr_destructible_struct(binding.expr)
    is_owned_destructible = bool(
      st_name
      and (not binding.is_unwrap or self._is_owned_unwrap_expr(binding.expr))
    )
    cond_has_liftable = bool(
      node.condition
      and self._contains_liftable_expr(node.condition, include_moves=True)
    )

    if node.condition and (cond_has_liftable or is_owned_destructible):
      self._emit_multi_binding_if(node, [binding])
      return

    self.newline()
    if binding.is_unwrap:
      val_var = self._next_temp_name(f"_val_{self._mangle_name(let_name)}")
      wb_entry = self._emit_binding_rhs_and_writeback(binding, val_var)
      self.newline()

      # Map unwrapped identifier(s) to the temporary during condition eval.
      old_map = self._identifier_map.copy()
      if len(let_names) == 1:
        self._identifier_map[let_name] = val_var
      else:
        for idx, name in enumerate(let_names):
          self._identifier_map[name] = f"{val_var}[{idx + 1}]"

      self.emit(f"if {val_var} ~= nil")
      if node.condition:
        self.emit(" and ")
        self.visit(node.condition)
      self.emit(" then")
      self._identifier_map = old_map

      self.indent()
      self.newline()
      mangled_names: list[str] = []
      if len(let_names) > 1:
        for idx, name in enumerate(let_names):
          m_n = self._mangle_name(name)
          mangled_names.append(m_n)
          self.emit(f"local {m_n} = {val_var}[{idx + 1}]")
          if idx < len(let_names) - 1:
            self.newline()
      else:
        m_n = self._mangle_name(let_name)
        mangled_names.append(m_n)
        self.emit(f"local {m_n} = {val_var}")

      extra_destructibles: list[str] = []
      if is_owned_destructible:
        for m_n in mangled_names:
          self.variable_types[m_n] = st_name
          extra_destructibles.append(m_n)

      prev_wb = self._unwrap_writebacks.copy()
      if wb_entry and len(mangled_names) == 1:
        self._unwrap_writebacks[mangled_names[0]] = wb_entry
      self._branch_depth += 1
      try:
        self._visit_block(
          node.then_block, extra_destructibles=extra_destructibles
        )
      finally:
        self._branch_depth -= 1
        self._unwrap_writebacks = prev_wb
      self.dedent()
    else:
      m_n = self._mangle_name(let_name)
      self.emit(f"local {m_n} = ")
      self._emit_value_expr(binding.expr)
      self.newline()
      extra_destructibles = []
      if st_name:
        self.variable_types[m_n] = st_name
        extra_destructibles.append(m_n)
      self.emit("if ")
      self.visit(node.condition)
      self.emit(" then")
      self.indent()
      self._branch_depth += 1
      try:
        self._visit_block(
          node.then_block, extra_destructibles=extra_destructibles
        )
      finally:
        self._branch_depth -= 1
      self.dedent()

    if node.else_block:
      self.newline()
      self.emit("else")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()

    self.newline()
    self.emit("end")

  def _emit_multi_binding_if(self, node: IfNode, bindings: list[Any]) -> None:
    """Emits multi-binding `if` with sequential short-circuiting and LIFO
    cleanup.
    """
    cond_flag = self._next_temp_name("_if_ok")

    self.newline()
    self.emit(f"local {cond_flag} = false")

    def emit_binding_level(
      idx: int,
      prior_destructibles: list[str],
      wb_entries: dict[str, tuple],
    ) -> None:
      if idx < len(bindings):
        b = bindings[idx]
        let_names = getattr(b, "let_names", [b.let_name])
        let_name = b.let_name
        self._lift_match_expressions(b.expr)
        st_name = self._expr_destructible_struct(b.expr)
        is_owned = bool(
          st_name and (not b.is_unwrap or self._is_owned_unwrap_expr(b.expr))
        )

        if b.is_unwrap:
          val_var = self._next_temp_name(f"_val_{self._mangle_name(let_name)}")
          self.newline()
          wb_entry = self._emit_binding_rhs_and_writeback(b, val_var)
          self.newline()
          self.emit(f"if {val_var} ~= nil then")
          self.indent()
          self.newline()
          mangled_names: list[str] = []
          if len(let_names) > 1:
            for n_idx, name in enumerate(let_names):
              m_n = self._mangle_name(name)
              mangled_names.append(m_n)
              self.emit(f"local {m_n} = {val_var}[{n_idx + 1}]")
              if n_idx < len(let_names) - 1:
                self.newline()
          else:
            m_n = self._mangle_name(let_name)
            mangled_names.append(m_n)
            self.emit(f"local {m_n} = {val_var}")

          current_destructibles = list(prior_destructibles)
          if is_owned:
            for m_n in mangled_names:
              self.variable_types[m_n] = st_name
              current_destructibles.append(m_n)

          next_wbs = dict(wb_entries)
          if wb_entry and len(mangled_names) == 1:
            next_wbs[mangled_names[0]] = wb_entry

          emit_binding_level(idx + 1, current_destructibles, next_wbs)
          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self._emit_destructor_call(d_var)
            self.dedent()
          self.newline()
          self.emit("end")
        else:
          self.newline()
          m_n = self._mangle_name(let_name)
          self.emit(f"local {m_n} = ")
          self._emit_value_expr(b.expr)
          current_destructibles = list(prior_destructibles)
          if is_owned:
            self.variable_types[m_n] = st_name
            current_destructibles.append(m_n)
          emit_binding_level(idx + 1, current_destructibles, wb_entries)
      else:
        prev_wb = self._unwrap_writebacks.copy()
        self._unwrap_writebacks = dict(prev_wb)
        self._unwrap_writebacks.update(wb_entries)
        try:
          if node.condition:
            self._lift_match_expressions(node.condition)
            self.newline()
            self.emit("if ")
            self.visit(node.condition)
            self.emit(" then")
            self.indent()
            self.newline()
            self.emit(f"{cond_flag} = true")
            self._branch_depth += 1
            try:
              self._visit_block(
                node.then_block, extra_destructibles=prior_destructibles
              )
            finally:
              self._branch_depth -= 1
            self.dedent()
            if prior_destructibles:
              self.newline()
              self.emit("else")
              self.indent()
              for d_var in reversed(prior_destructibles):
                self.newline()
                self._emit_destructor_call(d_var)
              self.dedent()
            self.newline()
            self.emit("end")
          else:
            self.newline()
            self.emit(f"{cond_flag} = true")
            self._branch_depth += 1
            try:
              self._visit_block(
                node.then_block, extra_destructibles=prior_destructibles
              )
            finally:
              self._branch_depth -= 1
        finally:
          self._unwrap_writebacks = prev_wb

    emit_binding_level(0, [], {})

    if node.else_block:
      self.newline()
      self.emit(f"if not {cond_flag} then")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()
      self.newline()
      self.emit("end")

  def visit_IfNode(self, node: IfNode) -> None:
    bindings = getattr(
      node,
      "bindings",
      [node.init_binding] if getattr(node, "init_binding", None) else [],
    )
    if not bindings:
      self._emit_simple_if(node)
    elif len(bindings) == 1:
      self._emit_single_binding_if(node, bindings[0])
    else:
      self._emit_multi_binding_if(node, bindings)

  def _visit_loop_body(self, block: BlockNode, has_continue: bool) -> None:
    done_flag = self._current_match_done_flag
    if has_continue:
      self.newline()
      self.emit("local _break_outer = false")
      self.newline()
      self.emit("repeat")
      self.indent()
      self.visit(block)
      self.dedent()
      self.newline()
      self.emit("until true")
      self.newline()
      self.emit("if _break_outer then break end")
    else:
      self.visit(block)
    if done_flag and self._stmt_contains_match_yield(block):
      self.newline()
      self.emit(f"if {done_flag} then break end")

  def visit_WhileNode(self, node: WhileNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    self.loop_destructor_depth.append(len(self.destructor_stack))
    self._match_loop_depth = self._match_loop_depth + 1
    try:
      cond_liftable = bool(
        node.condition
        and self._contains_liftable_expr(node.condition, include_moves=True)
      )
      if cond_liftable:
        self.newline()
        self.emit("while true do")
        self.indent()
        self._lift_match_expressions(node.condition)
        self.newline()
        self.emit("if not (")
        self.visit(node.condition)
        self.emit(") then break end")
        self._visit_loop_body(node.block, has_continue)
        self.dedent()
        self.newline()
        self.emit("end")
      else:
        self.newline()
        self.emit("while ")
        self.visit(node.condition)
        self.emit(" do")
        self.indent()
        self._visit_loop_body(node.block, has_continue)
        self.dedent()
        self.newline()
        self.emit("end")
    finally:
      self._match_loop_depth -= 1
      self.loop_destructor_depth.pop()
      self._loop_stack.pop()

  def visit_ForNode(self, node: ForNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    self.loop_destructor_depth.append(len(self.destructor_stack))
    self._match_loop_depth = self._match_loop_depth + 1
    prev_wb = self._unwrap_writebacks.copy()
    prev_plain = self._plain_local_containers.copy()
    try:
      from sapphire.semantics.types import MapType, OptionalType

      self._lift_match_expressions(node.iterable)
      val_var = self._mangle_name(node.val_var)
      key_var = (
        self._mangle_name(node.key_var) if node.key_var is not None else None
      )
      self._plain_local_containers.discard(node.val_var)
      if node.key_var is not None:
        self._plain_local_containers.discard(node.key_var)
      is_mut = getattr(node, "is_mutable", False)
      is_non_opt_arr = self._is_non_opt_array_expr(node.iterable)

      close_guard_if = False
      array_elem_binding: str | None = None
      is_direct_range = (
        isinstance(node.iterable, CallNode)
        and isinstance(node.iterable.callee, IdentifierNode)
        and node.iterable.callee.name == "range"
        and not getattr(node.iterable, "_requires_eval_order_temps", False)
      )

      if node.key_var is not None:
        iter_t = self.get_inferred_type(node.iterable)
        while isinstance(iter_t, OptionalType) or hasattr(iter_t, "inner_type"):
          iter_t = (
            iter_t.base_type
            if isinstance(iter_t, OptionalType)
            else iter_t.inner_type
          )
        is_non_opt_map = isinstance(iter_t, MapType) and not isinstance(
          iter_t.value_type, OptionalType
        )
        if is_non_opt_map:
          map_tmp = self._next_temp_name("_for_map")
          unwrap_fn = (
            "_SP_RT._unwrap_write" if is_mut else "_SP_RT._unwrap_read"
          )
          self.newline()
          self.emit(f"local {map_tmp} = {unwrap_fn}(")
          self.visit(node.iterable)
          self.emit(")")
          self.newline()
          self.emit(f'if type({map_tmp}) == "table" then')
          self.indent()
          self.newline()
          self.emit(f"for {key_var}, {val_var} in pairs({map_tmp}) do")
          if is_mut:
            self._unwrap_writebacks[val_var] = (
              "direct_map_index",
              map_tmp,
              key_var,
              False,
            )
          close_guard_if = True
        elif is_mut:
          iter_tmp = self._next_temp_name("_for_iter")
          self.newline()
          self.emit(f"local {iter_tmp} = ")
          self.visit(node.iterable)
          self.newline()
          self.emit(
            f"for {key_var}, {val_var} in "
            f"_SP_RT._sapphire_iter_map({iter_tmp}) do"
          )
          self._unwrap_writebacks[val_var] = ("map_index", iter_tmp, key_var)
        else:
          self.newline()
          self.emit(f"for {key_var}, {val_var} in _SP_RT._sapphire_iter_map(")
          self.visit(node.iterable)
          self.emit(") do")
      elif is_direct_range:
        range_args = _resolve_range_args(node.iterable)
        if len(range_args) == 1:
          self.newline()
          self.emit(f"for {val_var} = 0, (")
          self.visit(range_args[0])
          self.emit(") - 1 do")
        elif len(range_args) == 2:
          self.newline()
          self.emit(f"for {val_var} = (")
          self.visit(range_args[0])
          self.emit("), (")
          self.visit(range_args[1])
          self.emit(") - 1 do")
        else:
          const_step = _extract_const_int(range_args[2])
          if const_step is not None and const_step > 0:
            self.newline()
            self.emit(f"for {val_var} = (")
            self.visit(range_args[0])
            self.emit("), (")
            self.visit(range_args[1])
            self.emit(f") - 1, {const_step} do")
          elif const_step is not None and const_step < 0:
            self.newline()
            self.emit(f"for {val_var} = (")
            self.visit(range_args[0])
            self.emit("), (")
            self.visit(range_args[1])
            self.emit(f") + 1, {const_step} do")
          else:
            start_tmp = self._next_temp_name("_r_start")
            stop_raw_tmp = self._next_temp_name("_r_stop_raw")
            step_tmp = self._next_temp_name("_r_step")
            stop_tmp = self._next_temp_name("_r_stop")
            self.newline()
            self.emit(f"local {start_tmp} = ")
            self.visit(range_args[0])
            self.newline()
            self.emit(f"local {stop_raw_tmp} = ")
            self.visit(range_args[1])
            self.newline()
            self.emit(f"local {step_tmp} = ")
            self.visit(range_args[2])
            self.newline()
            self.emit(f"if {step_tmp} ~= 0 then")
            self.indent()
            self.newline()
            self.emit(
              f"local {stop_tmp} = ({step_tmp} > 0) and "
              f"({stop_raw_tmp} - 1) or ({stop_raw_tmp} + 1)"
            )
            self.newline()
            self.emit(f"for {val_var} = {start_tmp}, {stop_tmp}, {step_tmp} do")
            close_guard_if = True
      elif isinstance(self.get_inferred_type(node.iterable), RangeType) or (
        isinstance(node.iterable, CallNode)
        and isinstance(node.iterable.callee, IdentifierNode)
        and node.iterable.callee.name == "range"
      ):
        self.newline()
        self.emit(f"for {val_var} in ")
        self.visit(node.iterable)
        self.emit(" do")
      elif is_mut:
        arr_tmp = self._next_temp_name("_for_arr")
        idx_tmp = self._next_temp_name("_for_idx")
        self.newline()
        self.emit(f"local {arr_tmp} = _SP_RT._unwrap_write(")
        self.visit(node.iterable)
        self.emit(")")
        self.newline()
        self.emit(f'if type({arr_tmp}) == "table" then')
        self.indent()
        self.newline()
        self.emit(f"for {idx_tmp} = 1, #{arr_tmp} do")
        self._unwrap_writebacks[val_var] = (
          "direct_arr_index",
          arr_tmp,
          idx_tmp,
          not is_non_opt_arr,
        )
        close_guard_if = True
        if is_non_opt_arr:
          array_elem_binding = f"local {val_var} = {arr_tmp}[{idx_tmp}]"
        else:
          array_elem_binding = (
            f"local {val_var} = _SP_RT._unwrap_opt({arr_tmp}[{idx_tmp}])"
          )
      else:
        arr_tmp = self._next_temp_name("_for_arr")
        idx_tmp = self._next_temp_name("_for_idx")
        self.newline()
        self.emit(f"local {arr_tmp} = _SP_RT._unwrap_read(")
        self.visit(node.iterable)
        self.emit(")")
        self.newline()
        self.emit(f'if type({arr_tmp}) == "table" then')
        self.indent()
        self.newline()
        self.emit(f"for {idx_tmp} = 1, #{arr_tmp} do")
        close_guard_if = True
        if is_non_opt_arr:
          array_elem_binding = f"local {val_var} = {arr_tmp}[{idx_tmp}]"
        else:
          array_elem_binding = (
            f"local {val_var} = _SP_RT._unwrap_opt({arr_tmp}[{idx_tmp}])"
          )
      self.indent()
      if array_elem_binding:
        self.newline()
        self.emit(array_elem_binding)
      self._visit_loop_body(node.block, has_continue)
      self.dedent()
      self.newline()
      self.emit("end")
      if close_guard_if:
        self.dedent()
        self.newline()
        self.emit("end")
    finally:
      self._unwrap_writebacks = prev_wb
      self._plain_local_containers = prev_plain
      self._match_loop_depth -= 1
      self.loop_destructor_depth.pop()
      self._loop_stack.pop()

  def visit_BreakNode(self, node: BreakNode) -> None:
    self._emit_loop_destructors()
    self.newline()
    if self._loop_stack and self._loop_stack[-1]:
      self.emit("_break_outer = true")
      self.newline()
    self.emit("break")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    self._emit_loop_destructors()
    self.newline()
    self.emit("break")

  # ==========================================
  # Guard Statements Visitor
  # ==========================================

  def visit_GuardStmtNode(self, node: GuardStmtNode) -> None:
    for clause in node.clauses:
      if clause.binding:
        binding = clause.binding
        self._lift_match_expressions(binding.expr)
        let_names = getattr(binding, "let_names", [binding.let_name])
        tmp_var = self._next_temp_name("_guard_val")

        self.newline()
        wb_entry = self._emit_binding_rhs_and_writeback(binding, tmp_var)
        self.newline()

        if binding.is_unwrap:
          self.emit(f"if {tmp_var} == nil then")
          self.indent()
          self._visit_in_branch(node.else_block)
          self.dedent()
          self.newline()
          self.emit("end")
          self.newline()

        mangled_names: list[str] = []
        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            m_n = self._mangle_name(name)
            mangled_names.append(m_n)
            self.emit(f"local {m_n} = {tmp_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          m_n = self._mangle_name(binding.let_name)
          mangled_names.append(m_n)
          self.emit(f"local {m_n} = {tmp_var}")

        st_name = self._expr_destructible_struct(binding.expr)
        if st_name and (
          not binding.is_unwrap or self._is_owned_unwrap_expr(binding.expr)
        ):
          for m_n in mangled_names:
            self.variable_types[m_n] = st_name
            if self.destructor_stack:
              self.destructor_stack[-1].append(m_n)
              self._var_branch_depth[m_n] = self._branch_depth

        if wb_entry and len(mangled_names) == 1:
          self._unwrap_writebacks[mangled_names[0]] = wb_entry
      elif clause.condition:
        self._lift_match_expressions(clause.condition)
        self.newline()
        self.emit("if not (")
        self.visit(clause.condition)
        self.emit(") then")
        self.indent()
        self._visit_in_branch(node.else_block)
        self.dedent()
        self.newline()
        self.emit("end")

  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None:
    if node.binding:
      self.visit(node.binding.expr)
    elif node.condition:
      self.visit(node.condition)
