"""Statement and control-flow code generation mixin for LuaTranspiler."""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import ArrayType, MapType, RangeType
from src.code_gen.base_transpiler import extract_type_name, get_default_value_for_type_node, is_coroutine_func
from src.code_gen.intrinsics import IntrinsicRegistry


def _has_continue_node(node: ASTNode) -> bool:
  if isinstance(node, ContinueNode):
    return True
  if isinstance(node, (WhileNode, ForNode)):
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



class LuaStmtMixin:
  """Provides statement and control-flow AST emission for Lua 5.1."""

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.destructor_stack.append([])
    if getattr(node, "_block_destructibles", None):
      for d_var in node._block_destructibles:
        self.destructor_stack[-1].append(d_var)
        self._var_branch_depth[d_var] = self._branch_depth
    if not node.statements:
      self.newline()
      self.emit("-- pass")
    else:
      for stmt in node.statements:
        self.visit(stmt)
        if not isinstance(stmt, ReturnNode):
          self._drain_pending_null_vars("nil")

    current_destructors = self.destructor_stack.pop()
    has_returned = bool(node.statements and isinstance(node.statements[-1], ReturnNode))
    if not has_returned:
      for var_name in reversed(current_destructors):
        if var_name not in self.moved_vars:
          self.newline()
          self._emit_destructor_call(var_name)
    for var_name in current_destructors:
      self.moved_vars.discard(var_name)
      self._var_branch_depth.pop(var_name, None)

  def _lift_match_expressions(self, node: Any) -> None:
    """Finds all MatchExprNode in the AST subtree and emits their match statement blocks first."""
    if node is None:
      return
    if isinstance(node, MatchExprNode):
      if not getattr(node, "_is_lifted", False):
        node._is_lifted = True
        for case in node.cases:
          self._lift_match_expressions(case.body)
        node._lifted_var = self._emit_match_statement(node)
      return
    if isinstance(node, list):
      for item in node:
        self._lift_match_expressions(item)
      return
    if isinstance(node, ASTNode):
      for v in node.__dict__.values():
        if isinstance(v, (ASTNode, list)):
          self._lift_match_expressions(v)

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    for idx, name in enumerate(node.names):
      val_type = node.val_types[idx] if idx < len(node.val_types) else None
      type_name = extract_type_name(val_type) if val_type else None
      st_name = None
      if type_name and type_name in self.structs_with_destructor:
        st_name = type_name
      elif node.exprs and idx < len(node.exprs):
        st_name = self._expr_destructible_struct(node.exprs[idx])
      elif node.exprs and len(node.exprs) == 1:
        st_name = self._expr_destructible_struct(node.exprs[0], return_index=idx)
      elif node.expr:
        st_name = self._expr_destructible_struct(node.expr, return_index=idx)

      if st_name:
        m_name = self._mangle_name(name)
        self.variable_types[m_name] = st_name
        if self.destructor_stack:
          self.destructor_stack[-1].append(m_name)
          self._var_branch_depth[m_name] = self._branch_depth

    self._lift_match_expressions(node.exprs)

    self.newline()
    names_str = ", ".join([self._mangle_name(n) for n in node.names])
    if self.dev_mode and self.indent_level == 0 and len(node.names) == 1 and node.exprs:
      name = self._mangle_name(node.names[0])
      self.emit(f"{name} = {name} ~= nil and {name} or ")
      self.visit(node.exprs[0])
      return

    self.emit(f"local {names_str}")
    if node.exprs:
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      defaults = []
      has_non_nil = False
      for idx, name in enumerate(node.names):
        val_type = node.val_types[idx] if idx < len(node.val_types) else None
        default_expr = get_default_value_for_type_node(val_type)
        if default_expr:
          temp = type(self)()
          temp.known_structs = self.known_structs
          temp.visit(default_expr)
          defaults.append(temp.get_output())
          if default_expr.lit_type != "none":
            has_non_nil = True
        else:
          defaults.append("nil")
      if has_non_nil:
        self.emit(" = " + ", ".join(defaults))

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self._lift_match_expressions(node.targets)
    self._lift_match_expressions(node.exprs)

    if node.op == "=":
      live_destructible_targets = [
          self._mangle_name(t.name)
          for t in node.targets
          if isinstance(t, IdentifierNode)
          and self._is_active_destructible_var(self._mangle_name(t.name))
          and self._mangle_name(t.name) not in self.moved_vars
      ]
      if live_destructible_targets:
        self._temp_reassign_count = getattr(self, "_temp_reassign_count", 0) + 1
        tmp_names = [
            f"_reassign_{self._temp_reassign_count}_{i + 1}"
            for i in range(len(node.targets))
        ]
        self.newline()
        self.emit("local " + ", ".join(tmp_names) + " = ")
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        for m_t in live_destructible_targets:
          if m_t not in self.moved_vars and m_t not in self._pending_null_vars:
            self.newline()
            self._emit_destructor_call(m_t)
        assigned_id_names = {
            self._mangle_name(t.name)
            for t in node.targets
            if isinstance(t, IdentifierNode)
        }
        self._drain_pending_null_vars("nil", exclude=assigned_id_names)
        self.newline()
        for idx, target in enumerate(node.targets):
          if isinstance(target, IdentifierNode):
            self.moved_vars.discard(self._mangle_name(target.name))
          if idx > 0:
            self.emit(", ")
          self.visit(target)
        self.emit(" = " + ", ".join(tmp_names))
        return

    self.newline()
    if node.op == "=":
      for idx, target in enumerate(node.targets):
        if isinstance(target, IdentifierNode):
          self.moved_vars.discard(self._mangle_name(target.name))
        if idx > 0:
          self.emit(", ")
        self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      if isinstance(node.target, IdentifierNode):
        self.moved_vars.discard(self._mangle_name(node.target.name))
      raw_op = node.op[:-1]
      self.visit(node.target)
      self.emit(" = ")
      self.visit(node.target)
      self.emit(f" {raw_op} ")
      self.visit(node.expr)

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self._lift_match_expressions(node.expr)
    self.newline()
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    all_active_destructors = [
        d for frame in reversed(self.destructor_stack) for d in reversed(frame)
    ]
    self._lift_match_expressions(node.expressions)

    # RVO: Identifiers returned directly are transferred to caller, so elide local destructor
    returned_ids = {
        self._mangle_name(expr.name)
        for expr in node.expressions
        if isinstance(expr, (IdentifierNode, MoveNode))
    }
    destructors_to_run = [
        d for d in all_active_destructors
        if d not in returned_ids and d not in self.moved_vars
    ]

    # If return expressions exist alongside destructors, evaluate expressions first
    should_evaluate_first = bool(
        node.expressions
        and destructors_to_run
        and not all(isinstance(e, (LiteralNode, IdentifierNode)) for e in node.expressions)
    )

    if should_evaluate_first:
      ret_tmps = []
      for idx, expr in enumerate(node.expressions):
        tmp_name = f"_ret_val_{idx + 1}"
        ret_tmps.append(tmp_name)
        self.newline()
        self.emit(f"local {tmp_name} = ")
        self.visit(expr)

      for var_name in destructors_to_run:
        if var_name not in self.moved_vars:
          self.newline()
          self._emit_destructor_call(var_name)

      self.newline()
      self.emit("return " + ", ".join(ret_tmps))
      self._pending_null_vars.clear()
      return

    for var_name in destructors_to_run:
      if var_name not in self.moved_vars:
        self.newline()
        self._emit_destructor_call(var_name)

    self.newline()
    if node.expressions:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    else:
      self.emit("return")
    self._pending_null_vars.clear()

  def _emit_match_statement(self, node: MatchExprNode, target_var: Optional[str] = "") -> str:
    if target_var == "":
      self._temp_match_count = getattr(self, "_temp_match_count", 0) + 1
      target_var = f"_match_res_{self._temp_match_count}"
      self.newline()
      self.emit(f"local {target_var} = nil")

    self._temp_subj_count = getattr(self, "_temp_subj_count", 0) + 1
    subj_var = f"_subj_{self._temp_subj_count}"
    self.newline()
    self.emit(f"local {subj_var} = ")
    self.visit(node.subject)

    prev_target = getattr(self, "_current_match_target", None)
    prev_match_node = getattr(self, "_current_match_node", None)
    self._current_match_target = target_var
    self._current_match_node = node

    for idx, case in enumerate(node.cases):
      self.newline()
      if isinstance(case.pattern, EllipsisPatternNode):
        if idx == 0:
          self.emit("if true then")
        else:
          self.emit("else")
      else:
        if idx == 0:
          self.emit(f"if {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")
        else:
          self.emit(f"elseif {subj_var} == ")
          self.visit(case.pattern)
          self.emit(" then")

      self.indent()
      self._branch_depth += 1
      try:
        if isinstance(case.body, BlockNode):
          self.visit(case.body)
        else:
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
    self._current_match_target = prev_target
    self._current_match_node = prev_match_node
    return target_var or ""

  def visit_YieldNode(self, node: YieldNode) -> None:
    exprs = getattr(node, "expressions", None) or ([node.expr] if node.expr else [])
    self._lift_match_expressions(exprs)
    target = getattr(self, "_current_match_target", None)
    match_node = getattr(self, "_current_match_node", None)
    self.newline()
    if target:
      self.emit(f"{target} = ")
      if not exprs:
        self.emit("nil")
      elif len(exprs) == 1:
        self.visit(exprs[0])
      else:
        if match_node:
          match_node._is_multi_yield = True
        self.emit("{ ")
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
        self.emit(" }")
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
    if not getattr(node, "_is_lifted", False):
      node._is_lifted = True
      node._lifted_var = self._emit_match_statement(node)
    if getattr(node, "_is_multi_yield", False):
      self.emit(f"(table.unpack or unpack)({node._lifted_var})")
    else:
      self.emit(node._lifted_var)

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    pass

  def visit_IfNode(self, node: IfNode) -> None:
    bindings = getattr(node, "bindings", [node.init_binding] if getattr(node, "init_binding", None) else [])

    if not bindings:
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
      return

    if len(bindings) == 1:
      binding = bindings[0]
      self._lift_match_expressions(binding.expr)
      if node.condition:
        self._lift_match_expressions(node.condition)
      let_names = getattr(binding, "let_names", [binding.let_name])
      let_name = binding.let_name

      self.newline()
      if binding.is_unwrap:
        val_var = f"_val_{let_name}"
        self.emit(f"local {val_var} = ")
        self.visit(binding.expr)
        self.newline()

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
        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            self.emit(f"local {self._mangle_name(name)} = {val_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          self.emit(f"local {self._mangle_name(let_name)} = {val_var}")

        st_name = self._expr_destructible_struct(binding.expr)
        if st_name and self._is_owned_unwrap_expr(binding.expr):
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
        self._visit_in_branch(node.then_block)
        self.dedent()
      else:
        # Standard bind + condition
        self.emit(f"local {let_name} = ")
        self.visit(binding.expr)
        self.newline()
        st_name = self._expr_destructible_struct(binding.expr)
        if st_name:
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
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
      return

    # Multi-binding (len(bindings) > 1) with sequential short-circuiting and LIFO destructors
    self._temp_if_count = getattr(self, "_temp_if_count", 0) + 1
    cond_flag = f"_if_ok_{self._temp_if_count}"

    for b in bindings:
      self._lift_match_expressions(b.expr)
    if node.condition:
      self._lift_match_expressions(node.condition)

    self.newline()
    self.emit(f"local {cond_flag} = false")

    def emit_binding_level(idx: int, prior_destructibles: List[str]):
      if idx < len(bindings):
        b = bindings[idx]
        let_names = getattr(b, "let_names", [b.let_name])
        let_name = b.let_name
        st_name = self._expr_destructible_struct(b.expr)
        current_destructibles = list(prior_destructibles)
        if st_name and (not b.is_unwrap or self._is_owned_unwrap_expr(b.expr)):
          for name in let_names:
            self.variable_types[name] = st_name
            if not hasattr(node.then_block, "_block_destructibles"):
              node.then_block._block_destructibles = []
            node.then_block._block_destructibles.append(name)
          current_destructibles.extend(let_names)

        if b.is_unwrap:
          val_var = f"_val_{let_name}_{idx + 1}"
          self.newline()
          self.emit(f"local {val_var} = ")
          self.visit(b.expr)
          self.newline()
          self.emit(f"if {val_var} ~= nil then")
          self.indent()
          self.newline()
          if len(let_names) > 1:
            for n_idx, name in enumerate(let_names):
              self.emit(f"local {name} = {val_var}[{n_idx + 1}]")
              if n_idx < len(let_names) - 1:
                self.newline()
          else:
            self.emit(f"local {let_name} = {val_var}")

          emit_binding_level(idx + 1, current_destructibles)
          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self.emit(f"_sapphire_del({d_var})")
            self.dedent()
          self.newline()
          self.emit("end")
        else:
          self.newline()
          self.emit(f"local {let_name} = ")
          self.visit(b.expr)
          emit_binding_level(idx + 1, current_destructibles)
      else:
        # All bindings acquired; check condition if present
        if node.condition:
          self.newline()
          self.emit("if ")
          self.visit(node.condition)
          self.emit(" then")
          self.indent()
          self.newline()
          self.emit(f"{cond_flag} = true")
          self._visit_in_branch(node.then_block)
          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self.emit(f"_sapphire_del({d_var})")
            self.dedent()
          self.newline()
          self.emit("end")
        else:
          self.newline()
          self.emit(f"{cond_flag} = true")
          self._visit_in_branch(node.then_block)

    emit_binding_level(0, [])

    if node.else_block:
      self.newline()
      self.emit(f"if not {cond_flag} then")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()
      self.newline()
      self.emit("end")

  def _visit_loop_body(self, block: BlockNode, has_continue: bool) -> None:
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

  def visit_WhileNode(self, node: WhileNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    self.loop_destructor_depth.append(len(self.destructor_stack))
    try:
      if node.condition:
        self._lift_match_expressions(node.condition)

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
      self.loop_destructor_depth.pop()
      self._loop_stack.pop()

  def visit_ForNode(self, node: ForNode) -> None:
    has_continue = _has_continue_node(node.block)
    self._loop_stack.append(has_continue)
    self.loop_destructor_depth.append(len(self.destructor_stack))
    try:
      self._lift_match_expressions(node.iterable)
      self.newline()
      val_var = self._mangle_name(node.val_var)
      key_var = self._mangle_name(node.key_var) if node.key_var is not None else None
      if node.key_var is not None:
        self.emit(f"for {key_var}, {val_var} in pairs(")
        self.visit(node.iterable)
        self.emit(") do")
      elif (
          isinstance(getattr(node.iterable, "inferred_type", None), RangeType)
          or (isinstance(node.iterable, CallNode) and isinstance(node.iterable.callee, IdentifierNode) and node.iterable.callee.name == "range")
      ):
        self.emit(f"for {val_var} in ")
        self.visit(node.iterable)
        self.emit(" do")
      else:
        self.emit(f"for _, {val_var} in _sapphire_iter_array(")
        self.visit(node.iterable)
        self.emit(") do")
      self.indent()
      self._visit_loop_body(node.block, has_continue)
      self.dedent()
      self.newline()
      self.emit("end")
    finally:
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
  # Expressions Visitor
  # ==========================================

  def visit_GuardStmtNode(self, node: GuardStmtNode) -> None:
    for clause in node.clauses:
      self.newline()
      if clause.binding:
        binding = clause.binding
        let_names = getattr(binding, "let_names", [binding.let_name])
        self._temp_guard_count = getattr(self, "_temp_guard_count", 0) + 1
        tmp_var = f"_guard_val_{self._temp_guard_count}"

        self.emit(f"local {tmp_var} = ")
        self.visit(binding.expr)
        self.newline()

        if binding.is_unwrap:
          self.emit(f"if {tmp_var} == nil then")
          self.indent()
          self.visit(node.else_block)
          self.dedent()
          self.newline()
          self.emit("end")
          self.newline()

        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            self.emit(f"local {self._mangle_name(name)} = {tmp_var}[{idx + 1}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          self.emit(f"local {self._mangle_name(binding.let_name)} = {tmp_var}")
      elif clause.condition:
        self.emit("if not (")
        self.visit(clause.condition)
        self.emit(") then")
        self.indent()
        self.visit(node.else_block)
        self.dedent()
        self.newline()
        self.emit("end")

  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None:
    if node.binding:
      self.visit(node.binding.expr)
    elif node.condition:
      self.visit(node.condition)

