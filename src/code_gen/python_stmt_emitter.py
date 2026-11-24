"""Statement and control-flow code generation mixin for PythonTranspiler."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from src.code_gen.base_transpiler import (
  extract_type_name,
  get_default_value_for_type_node,
)
from src.parser.ast import (
  ArrayLiteralNode,
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
  MapLiteralNode,
  MatchExprNode,
  MemberAccessNode,
  MoveNode,
  ReturnNode,
  StructInitializerNode,
  TernaryExprNode,
  UnaryOpNode,
  VarDeclNode,
  WhileNode,
  YieldNode,
)

if TYPE_CHECKING:
  from src.code_gen.python_transpiler import (
    PythonTranspiler as _PythonTranspilerBase,
  )
else:
  _PythonTranspilerBase = object


class PythonStmtMixin(_PythonTranspilerBase):
  """Provides statement and control-flow AST emission for Python."""

  def _needs_value_copy(self, expr: Any) -> bool:
    """Returns True if *expr* may alias a value-type struct/array/map and needs
    shallow copy.
    """
    if expr is None:
      return False
    if isinstance(
      expr,
      (
        LiteralNode,
        InterpolatedStringNode,
        ArrayLiteralNode,
        MapLiteralNode,
        StructInitializerNode,
        MoveNode,
        CloneNode,
        LambdaNode,
        BinaryOpNode,
        UnaryOpNode,
        CastExprNode,
      ),
    ):
      return False
    if isinstance(expr, CallNode):
      if not (
        isinstance(expr.callee, MemberAccessNode)
        and expr.callee.member == "get"
        and (
          getattr(expr.callee, "is_array_method", False)
          or getattr(expr.callee, "is_map_method", False)
        )
      ):
        return False
    inferred = getattr(expr, "inferred_type", None)
    if inferred is None:
      return False
    from src.semantics.types import (
      ArrayType,
      MapType,
      OptionalType,
      StructType,
    )

    t = inferred.base_type if isinstance(inferred, OptionalType) else inferred
    if isinstance(t, (ArrayType, MapType)):
      return True
    if isinstance(t, StructType):
      if t.is_prototype:
        return False
      if self._type_needs_destructor(t):
        return False
      return True
    return False

  def _emit_value_expr(self, expr: Any) -> None:
    """Emits *expr*, wrapping in `_sapphire_copy(...)` when value semantics
    apply.
    """
    if self._needs_value_copy(expr):
      self.emit("_sapphire_copy(")
      self.visit(expr)
      self.emit(")")
    else:
      self.visit(expr)

  def _contains_liftable_expr(
    self, node: Any, include_moves: bool = False
  ) -> bool:
    """Returns True if *node* contains a match, block lambda, complex clone, or
    (optionally) move.
    """
    if node is None:
      return False
    if isinstance(node, MatchExprNode):
      return True
    if isinstance(node, MoveNode):
      return include_moves
    if isinstance(node, CloneNode) and node.initializer_block:
      return True
    if isinstance(node, LambdaNode):
      if isinstance(node.body, BlockNode):
        return True
      return self._contains_liftable_expr(node.body, include_moves=False)
    if isinstance(node, FuncDeclNode):
      return False
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
    """Returns True if a block arm can yield before the end of the block."""
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

  def _find_assigned_nonlocals(
    self, node: Any, local_params: Optional[Set[str]] = None
  ) -> Set[str]:
    """Finds enclosing function-local Python var names assigned within *node*.
    """
    if not self._lexical_scopes:
      return set()
    outer_raws: Set[str] = set()
    for scope in self._lexical_scopes:
      outer_raws.update(scope)
    if not outer_raws:
      return set()

    param_raws = set(local_params) if local_params else set()
    assigned_py: Set[str] = set()

    def _walk(n: Any, inner_locals: Set[str]) -> None:
      if n is None:
        return
      if isinstance(n, FuncDeclNode):
        return
      if isinstance(n, LambdaNode):
        lam_locals = set(inner_locals)
        for p in n.parameters:
          lam_locals.add(p.name)
        _walk(n.body, lam_locals)
        return
      if isinstance(n, BlockNode):
        blk = set(inner_locals)
        for s in n.statements:
          _walk(s, blk)
        return
      if isinstance(n, VarDeclNode):
        for e in n.exprs or []:
          _walk(e, inner_locals)
        for name in n.names:
          inner_locals.add(name)
        return
      if isinstance(n, IfNode):
        bindings = getattr(
          n,
          "bindings",
          [n.init_binding] if getattr(n, "init_binding", None) else [],
        )
        br = set(inner_locals)
        for b in bindings:
          _walk(b.expr, br)
          for name in getattr(b, "let_names", [b.let_name]):
            if name:
              br.add(name)
        if n.condition:
          _walk(n.condition, br)
        _walk(n.then_block, set(br))
        if n.else_block:
          _walk(n.else_block, set(inner_locals))
        return
      if isinstance(n, ForNode):
        _walk(n.iterable, inner_locals)
        lp = set(inner_locals)
        if n.val_var:
          lp.add(n.val_var)
        if getattr(n, "key_var", None):
          lp.add(n.key_var)
        _walk(n.block, lp)
        return
      if isinstance(n, WhileNode):
        _walk(n.condition, inner_locals)
        _walk(n.block, set(inner_locals))
        return
      if isinstance(n, GuardStmtNode):
        for cl in n.clauses:
          if cl.binding:
            _walk(cl.binding.expr, inner_locals)
            for name in getattr(cl.binding, "let_names", [cl.binding.let_name]):
              if name:
                inner_locals.add(name)
          elif cl.condition:
            _walk(cl.condition, inner_locals)
        _walk(n.else_block, set(inner_locals))
        return
      if isinstance(n, AssignmentNode):
        targets = getattr(n, "targets", [])
        if not targets and getattr(n, "target", None):
          targets = [n.target]
        for t in targets:
          if isinstance(t, IdentifierNode):
            if (
              t.name in outer_raws
              and t.name not in inner_locals
              and t.name not in param_raws
            ):
              py_n = self._resolve_var_name(t.name)
              if py_n not in self._current_func_globals:
                assigned_py.add(py_n)
      if isinstance(n, ASTNode):
        for k, v in n.__dict__.items():
          if k.startswith("_"):
            continue
          if isinstance(v, list):
            for item in v:
              _walk(item, inner_locals)
          elif isinstance(v, ASTNode):
            _walk(v, inner_locals)

    _walk(node, set(param_raws))
    return assigned_py

  def _find_captured_loop_vars(
    self, node: Any, local_params: Optional[Set[str]] = None
  ) -> List[str]:
    """Finds loop-local Python var names referenced inside a lambda body."""
    if not self._loop_vars_stack:
      return []
    all_loop_vars: List[str] = []
    seen_lv: Set[str] = set()
    for frame in self._loop_vars_stack:
      for v in frame:
        if v not in seen_lv:
          seen_lv.add(v)
          all_loop_vars.append(v)
    if not all_loop_vars:
      return []

    param_raws = set(local_params) if local_params else set()
    param_pys = {self._mangle_name(p) for p in param_raws}
    referenced_pys: Set[str] = set()

    def _walk(n: Any, inner_locals: Set[str]) -> None:
      if n is None:
        return
      if isinstance(n, FuncDeclNode):
        return
      if isinstance(n, LambdaNode):
        lam = set(inner_locals)
        for p in n.parameters:
          lam.add(p.name)
        _walk(n.body, lam)
        return
      if isinstance(n, BlockNode):
        blk = set(inner_locals)
        for s in n.statements:
          _walk(s, blk)
        return
      if isinstance(n, VarDeclNode):
        for e in n.exprs or []:
          _walk(e, inner_locals)
        for name in n.names:
          inner_locals.add(name)
        return
      if isinstance(n, (IdentifierNode, MoveNode)):
        if n.name not in inner_locals and n.name not in param_raws:
          referenced_pys.add(self._resolve_var_name(n.name))
        return
      if isinstance(n, ASTNode):
        for k, v in n.__dict__.items():
          if k.startswith("_"):
            continue
          if isinstance(v, list):
            for item in v:
              _walk(item, inner_locals)
          elif isinstance(v, ASTNode):
            _walk(v, inner_locals)

    _walk(node, set(param_raws))
    return [
      v for v in all_loop_vars if v in referenced_pys and v not in param_pys
    ]

  def _visit_block(
    self,
    node: BlockNode,
    extra_destructibles: Optional[List[str]] = None,
  ) -> None:
    """Visits a BlockNode with lexical scope isolation and LIFO RAII teardown.
    """
    prev_wb = self._unwrap_writebacks.copy()
    self._unwrap_writebacks = dict(prev_wb)
    prev_id_map = self._identifier_map.copy()
    pushed_scope = bool(self._lexical_scopes)
    if pushed_scope:
      self._lexical_scopes.append(set())
    loop_frame_len = (
      len(self._loop_vars_stack[-1]) if self._loop_vars_stack else None
    )

    self.destructor_stack.append([])
    for d_var in extra_destructibles or []:
      self.destructor_stack[-1].append(d_var)
      self._var_branch_depth[d_var] = self._branch_depth
    if getattr(node, "_block_destructibles", None):
      for d_var in node._block_destructibles:
        if d_var not in self.destructor_stack[-1]:
          self.destructor_stack[-1].append(d_var)
          self._var_branch_depth[d_var] = self._branch_depth

    try:
      if not node.statements:
        self.newline()
        self.emit("pass")
      else:
        self._visit_statements(node.statements)
      current_destructors = self.destructor_stack.pop()
      has_returned = bool(
        node.statements and isinstance(node.statements[-1], ReturnNode)
      )
      if not has_returned:
        for var_name in reversed(current_destructors):
          if var_name not in self.moved_vars:
            self.newline()
            self.emit(f"_sapphire_del({var_name})")
      for var_name in current_destructors:
        self.moved_vars.discard(var_name)
        self._var_branch_depth.pop(var_name, None)
    finally:
      if pushed_scope:
        self._lexical_scopes.pop()
      if loop_frame_len is not None and self._loop_vars_stack:
        del self._loop_vars_stack[-1][loop_frame_len:]
      self._identifier_map = prev_id_map
      self._unwrap_writebacks = prev_wb

  def visit_BlockNode(self, node: BlockNode) -> None:
    self._visit_block(node)

  def _emit_lifted_lambda(self, node: LambdaNode) -> str:
    fn_name = self._next_temp_name("_lambda")
    params = [self._mangle_name(p.name) for p in node.parameters]
    param_raw_names = {p.name for p in node.parameters}

    caps = self._find_captured_loop_vars(node.body, param_raw_names)
    assigned_nonlocals = self._find_assigned_nonlocals(
      node.body, param_raw_names
    )
    assigned_globals = self._find_assigned_globals(
      node.body, local_params=set(params)
    )
    # Any outer local that is NOT a global uses nonlocal; globals that are not
    # shadowed use global.
    assigned_globals = assigned_globals - assigned_nonlocals

    # Save and isolate outer RAII / control-flow / match state.
    saved_state = (
      self.destructor_stack,
      self.loop_destructor_depth,
      self.moved_vars,
      self._var_branch_depth,
      self._pending_null_vars,
      self._pending_unconditional_null_vars,
      self._branch_depth,
      self._current_match_target,
      self._current_match_done_flag,
      self._match_loop_depth,
      self._unwrap_writebacks,
      self._current_func_globals,
      self._loop_vars_stack,
    )
    prev_id_map = self._identifier_map.copy()
    for p in node.parameters:
      self._identifier_map.pop(p.name, None)
    self._lexical_scopes.append(set(param_raw_names))

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
    self._current_func_globals = set(assigned_globals)
    self._loop_vars_stack = []

    try:
      if caps:
        make_fn = f"_make_{fn_name}"
        cap_str = ", ".join(caps)
        self.newline()
        self.emit(f"def {make_fn}({cap_str}):")
        self.indent()

      self.newline()
      self.emit(f"def {fn_name}({', '.join(params)}):")
      self.indent()
      if assigned_nonlocals:
        self.newline()
        self.emit(f"nonlocal {', '.join(sorted(assigned_nonlocals))}")
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")

      if isinstance(node.body, BlockNode):
        self.visit(node.body)
      else:
        self._lift_match_expressions(node.body)
        self.newline()
        self.emit("return ")
        self.visit(node.body)
        self._drain_pending_null_vars("None")

      self.dedent()

      if caps:
        self.newline()
        self.emit(f"return {fn_name}")
        self.dedent()
        self.newline()
        self.emit(f"{fn_name} = {make_fn}({cap_str})")
    finally:
      self._lexical_scopes.pop()
      self._identifier_map = prev_id_map
      (
        self.destructor_stack,
        self.loop_destructor_depth,
        self.moved_vars,
        self._var_branch_depth,
        self._pending_null_vars,
        self._pending_unconditional_null_vars,
        self._branch_depth,
        self._current_match_target,
        self._current_match_done_flag,
        self._match_loop_depth,
        self._unwrap_writebacks,
        self._current_func_globals,
        self._loop_vars_stack,
      ) = saved_state

    return fn_name

  def _emit_lifted_clone_init(self, node: CloneNode) -> str:
    """Emits a helper function `def _clone_init_N(self):` for a CloneNode
    initializer block.
    """
    fn_name = self._next_temp_name("_clone_init")
    init_block = BlockNode(node.initializer_block)
    param_raw_names = {"self"}
    assigned_nonlocals = self._find_assigned_nonlocals(
      init_block, param_raw_names
    )
    assigned_globals = self._find_assigned_globals(
      init_block, local_params={"self"}
    )
    assigned_globals = assigned_globals - assigned_nonlocals

    saved_state = (
      self.destructor_stack,
      self.loop_destructor_depth,
      self.moved_vars,
      self._var_branch_depth,
      self._pending_null_vars,
      self._pending_unconditional_null_vars,
      self._branch_depth,
      self._current_match_target,
      self._current_match_done_flag,
      self._match_loop_depth,
      self._unwrap_writebacks,
      self._current_func_globals,
      self._loop_vars_stack,
    )
    prev_id_map = self._identifier_map.copy()
    self._identifier_map.pop("self", None)
    self._lexical_scopes.append({"self"})

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
    self._current_func_globals = set(assigned_globals)
    self._loop_vars_stack = []

    try:
      self.newline()
      self.emit(f"def {fn_name}(self):")
      self.indent()
      if assigned_nonlocals:
        self.newline()
        self.emit(f"nonlocal {', '.join(sorted(assigned_nonlocals))}")
      if assigned_globals:
        self.newline()
        self.emit(f"global {', '.join(sorted(assigned_globals))}")
      self._visit_block(init_block)
      self.dedent()
    finally:
      self._lexical_scopes.pop()
      self._identifier_map = prev_id_map
      (
        self.destructor_stack,
        self.loop_destructor_depth,
        self.moved_vars,
        self._var_branch_depth,
        self._pending_null_vars,
        self._pending_unconditional_null_vars,
        self._branch_depth,
        self._current_match_target,
        self._current_match_done_flag,
        self._match_loop_depth,
        self._unwrap_writebacks,
        self._current_func_globals,
        self._loop_vars_stack,
      ) = saved_state

    return fn_name

  def _lift_match_expressions(self, node: Any) -> None:
    """Lifts MatchExprNode, block/complex LambdaNode, CloneNode init, and
    short-circuiting exprs.
    """
    if node is None:
      return

    if isinstance(node, TernaryExprNode):
      if self._contains_liftable_expr(
        node.true_expr, include_moves=True
      ) or self._contains_liftable_expr(node.false_expr, include_moves=True):
        if id(node) not in self._lifted_short_circuits:
          self._lift_match_expressions(node.condition)
          res_var = self._next_temp_name("_cond_res")
          self.newline()
          self.emit("if ")
          self.visit(node.condition)
          self.emit(":")
          self.indent()
          self._branch_depth += 1
          try:
            self._lift_match_expressions(node.true_expr)
            self.newline()
            self.emit(f"{res_var} = ")
            self.visit(node.true_expr)
            self._drain_pending_null_vars("None")
          finally:
            self._branch_depth -= 1
          self.dedent()
          self.newline()
          self.emit("else:")
          self.indent()
          self._branch_depth += 1
          try:
            self._lift_match_expressions(node.false_expr)
            self.newline()
            self.emit(f"{res_var} = ")
            self.visit(node.false_expr)
            self._drain_pending_null_vars("None")
          finally:
            self._branch_depth -= 1
          self.dedent()
          self._lifted_short_circuits[id(node)] = res_var
        return
      self._lift_match_expressions(node.condition)
      self._lift_match_expressions(node.true_expr)
      self._lift_match_expressions(node.false_expr)
      return

    if isinstance(node, BinaryOpNode) and node.op in ("??", "&&", "||"):
      if self._contains_liftable_expr(node.right, include_moves=True):
        if id(node) not in self._lifted_short_circuits:
          self._lift_match_expressions(node.left)
          res_var = self._next_temp_name("_sc_res")
          self.newline()
          self.emit(f"{res_var} = ")
          self.visit(node.left)
          self.newline()
          if node.op == "??":
            self.emit(f"if {res_var} is None:")
          elif node.op == "&&":
            self.emit(f"if {res_var}:")
          else:
            self.emit(f"if not {res_var}:")
          self.indent()
          self._branch_depth += 1
          try:
            self._lift_match_expressions(node.right)
            self.newline()
            self.emit(f"{res_var} = ")
            self.visit(node.right)
            self._drain_pending_null_vars("None")
          finally:
            self._branch_depth -= 1
          self.dedent()
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
      if any(
        self._contains_liftable_expr(arg.expr, include_moves=True)
        for arg in node.arguments
      ):
        if id(node) not in self._lifted_short_circuits:
          self._lift_match_expressions(node.callee.receiver)
          recv_tmp = self._next_temp_name("_opt_r")
          res_var = self._next_temp_name("_opt_res")
          self.newline()
          self.emit(f"{recv_tmp} = ")
          self.visit(node.callee.receiver)
          self.newline()
          self.emit(f"if {recv_tmp} is not None:")
          self.indent()
          self._branch_depth += 1
          orig_recv = node.callee.receiver
          orig_opt = node.callee.is_optional
          try:
            for arg in node.arguments:
              self._lift_match_expressions(arg.expr)
            node.callee.receiver = IdentifierNode(recv_tmp)
            node.callee.is_optional = False
            self.newline()
            self.emit(f"{res_var} = ")
            self.visit(node)
            self._drain_pending_null_vars("None")
          finally:
            node.callee.receiver = orig_recv
            node.callee.is_optional = orig_opt
            self._branch_depth -= 1
          self.dedent()
          self.newline()
          self.emit("else:")
          self.indent()
          self.newline()
          self.emit(f"{res_var} = None")
          self.dedent()
          self._lifted_short_circuits[id(node)] = res_var
        return

    if isinstance(node, LambdaNode):
      if isinstance(node.body, BlockNode) or self._contains_liftable_expr(
        node.body
      ):
        if id(node) not in self._lifted_lambdas:
          self._lifted_lambdas[id(node)] = self._emit_lifted_lambda(node)
      return

    if isinstance(node, CloneNode):
      self._lift_match_expressions(node.expr)
      if node.arena_expr:
        self._lift_match_expressions(node.arena_expr)
      if node.initializer_block and id(node) not in self._lifted_clones:
        self._lifted_clones[id(node)] = self._emit_lifted_clone_init(node)
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

  def _emit_writebacks(self, targets: List[Any]) -> None:
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
      py_name = self._resolve_var_name(target.name)
      entry = wb_map.get(py_name)
      if not entry:
        continue
      kind = entry[0]
      if kind == "index":
        _, wb_recv, wb_key = entry
        self.newline()
        self.emit(f"{wb_recv}[{wb_key}] = {py_name}")
      elif kind == "attr":
        _, wb_recv, attr_name = entry
        self.newline()
        self.emit(f"{wb_recv}.{attr_name} = {py_name}")
      elif kind == "var":
        _, target_var = entry
        self.newline()
        self.emit(f"{target_var} = {py_name}")

  def _emit_binding_rhs_and_writeback(
    self, binding: Any, val_var: str
  ) -> Optional[tuple]:
    """Emits evaluation of a header/guard binding into `val_var` and returns
    writeback metadata.
    """
    if hasattr(binding, "_writeback_container"):
      recv_expr, key_expr, is_arr = binding._writeback_container
      wb_recv = self._next_temp_name("_wb_recv")
      wb_key = self._next_temp_name("_wb_key")
      self.emit(f"{wb_recv} = ")
      self.visit(recv_expr)
      self.newline()
      self.emit(f"{wb_key} = ")
      self.visit(key_expr)
      self.newline()
      slot_expr = (
        f"_sapphire_array_get({wb_recv}, {wb_key})"
        if is_arr
        else f"_sapphire_map_get({wb_recv}, {wb_key})"
      )
      self.emit(f"{val_var} = {slot_expr}")
      return ("index", wb_recv, wb_key)

    if binding.is_unwrap and getattr(binding, "is_mutable", False):
      expr = binding.expr
      if isinstance(expr, IdentifierNode):
        target_var = self._resolve_var_name(expr.name)
        self.emit(f"{val_var} = {target_var}")
        return ("var", target_var)
      if isinstance(expr, MemberAccessNode) and not expr.is_optional:
        wb_recv = self._next_temp_name("_wb_recv")
        member_name = getattr(expr, "target_name", None) or self._mangle_name(
          expr.member
        )
        self.emit(f"{wb_recv} = ")
        self.visit(expr.receiver)
        self.newline()
        self.emit(f"{val_var} = {wb_recv}.{member_name}")
        return ("attr", wb_recv, member_name)
      if isinstance(expr, IndexExprNode):
        wb_recv = self._next_temp_name("_wb_recv")
        wb_key = self._next_temp_name("_wb_key")
        self.emit(f"{wb_recv} = ")
        self.visit(expr.array)
        self.newline()
        self.emit(f"{wb_key} = ")
        self.visit(expr.index)
        self.newline()
        self.emit(f"{val_var} = {wb_recv}[{wb_key}]")
        return ("index", wb_recv, wb_key)

    self.emit(f"{val_var} = ")
    self.visit(binding.expr)
    return None

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    extern_ann = next(
      (a for a in getattr(node, "annotations", []) if a.name == "extern"), None
    )
    if extern_ann:
      # @extern variables represent ambient host symbols (e.g. Love2D engine
      # `love`
      # or Python standard library / host modules).
      for name in node.names:
        m_name = self._mangle_name(name)
        ext_target = extern_ann.arg if extern_ann.arg else name
        self.extern_vars[name] = ext_target
        if extern_ann.arg:
          self.newline()
          self.emit("try:")
          self.indent()
          self.newline()
          self.emit(f"import {extern_ann.arg} as {m_name}")
          self.dedent()
          self.newline()
          self.emit("except ImportError:")
          self.indent()
          self.newline()
          self.emit("pass")
          self.dedent()
      return

    # Lift any match / block-lambda / clone expressions in RHS BEFORE declaring
    # new locals
    # so `var x = match x { ... };` resolves RHS `x` to the outer binding!
    self._lift_match_expressions(node.exprs)

    # Pre-emit RHS into a buffer? No — emit RHS directly via sub-transpiler ONLY
    # if needed,
    # OR simply compute target Python names BEFORE mutating `_identifier_map`!
    planned_decls: List[tuple] = []
    for idx, name in enumerate(node.names):
      mangled = self._mangle_name(name)
      if self._lexical_scopes:
        enclosing_has = any(
          name in scope for scope in self._lexical_scopes[:-1]
        )
        clashes_global = mangled in self._current_func_globals
        if enclosing_has or clashes_global:
          py_name = self._next_temp_name(f"_{mangled}_s")
        else:
          py_name = mangled
      else:
        py_name = mangled
      planned_decls.append((idx, name, py_name))

    self.newline()
    self.record_line(getattr(node, "start_line", None))
    names_str = ", ".join(py_name for _, _, py_name in planned_decls)
    self.emit(f"{names_str}")
    if node.exprs:
      self.emit(" = ")
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
          defaults.append("None")
      self.emit(" = " + ", ".join(defaults))

    # Now commit the newly declared names into lexical scope, shadowing map, and
    # destructor_stack.
    for idx, name, py_name in planned_decls:
      if self._lexical_scopes:
        self._lexical_scopes[-1].add(name)
        if py_name != self._mangle_name(name):
          self._identifier_map[name] = py_name
        else:
          self._identifier_map.pop(name, None)
        if self._loop_vars_stack and py_name not in self._loop_vars_stack[-1]:
          self._loop_vars_stack[-1].append(py_name)

      val_type = node.val_types[idx] if idx < len(node.val_types) else None
      type_name = extract_type_name(val_type) if val_type else None
      st_name = None
      if type_name and type_name in self.structs_with_destructor:
        st_name = type_name
      elif val_type and getattr(val_type, "inferred_type", None) is not None:
        st_name = self._type_needs_destructor(val_type.inferred_type)
      elif node.exprs and idx < len(node.exprs):
        st_name = self._expr_destructible_struct(node.exprs[idx])
      elif node.exprs and len(node.exprs) == 1:
        st_name = self._expr_destructible_struct(
          node.exprs[0], return_index=idx
        )
      elif node.expr:
        st_name = self._expr_destructible_struct(node.expr, return_index=idx)

      if st_name:
        self.variable_types[py_name] = st_name
        if self.destructor_stack:
          self.destructor_stack[-1].append(py_name)
          self._var_branch_depth[py_name] = self._branch_depth

  def _is_int_div_assign(self, node: AssignmentNode) -> bool:
    """Returns True if `node` is an integer `/=` compound assignment."""
    if node.op != "/=":
      return False
    from src.semantics.types import PrimitiveType

    tt = getattr(node.target, "inferred_type", None)
    et = getattr(node.expr, "inferred_type", None)
    return (
      isinstance(tt, PrimitiveType)
      and tt.name == "int"
      and isinstance(et, PrimitiveType)
      and et.name == "int"
    )

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    self._lift_match_expressions(node.targets)
    self._lift_match_expressions(node.exprs)

    if node.op == "=":
      live_destructible_targets = [
        self._resolve_var_name(t.name)
        for t in node.targets
        if isinstance(t, IdentifierNode)
        and self._is_active_destructible_var(self._resolve_var_name(t.name))
        and self._resolve_var_name(t.name) not in self.moved_vars
      ]
      if live_destructible_targets:
        tmp_base = self._next_temp_name("_reassign")
        tmp_names = [f"{tmp_base}_{i + 1}" for i in range(len(node.targets))]
        self.newline()
        self.record_line(getattr(node, "start_line", None))
        self.emit(", ".join(tmp_names) + " = ")
        for idx, expr in enumerate(node.exprs):
          if idx > 0:
            self.emit(", ")
          self._emit_value_expr(expr)
        for py_t in live_destructible_targets:
          if (
            py_t not in self.moved_vars
            and py_t not in self._pending_null_vars
            and py_t not in self._pending_unconditional_null_vars
          ):
            self.newline()
            self.emit(f"_sapphire_del({py_t})")
        assigned_id_names = {
          self._resolve_var_name(t.name)
          for t in node.targets
          if isinstance(t, IdentifierNode)
        }
        self._drain_pending_null_vars("None", exclude=assigned_id_names)
        self.newline()
        for idx, target in enumerate(node.targets):
          if isinstance(target, IdentifierNode):
            self.moved_vars.discard(self._resolve_var_name(target.name))
          if idx > 0:
            self.emit(", ")
          if (
            isinstance(target, IdentifierNode)
            and target.name in self.extern_vars
          ):
            ext_name = self.extern_vars[target.name]
            self.emit(f"__import__('builtins').{ext_name}")
          else:
            self.visit(target)
        self.emit(" = " + ", ".join(tmp_names))
        self._emit_writebacks(node.targets)
        return

      self.newline()
      self.record_line(getattr(node, "start_line", None))
      for idx, target in enumerate(node.targets):
        if isinstance(target, IdentifierNode):
          self.moved_vars.discard(self._resolve_var_name(target.name))
        if idx > 0:
          self.emit(", ")
        if (
          isinstance(target, IdentifierNode) and target.name in self.extern_vars
        ):
          ext_name = self.extern_vars[target.name]
          self.emit(f"__import__('builtins').{ext_name}")
        else:
          self.visit(target)
      self.emit(" = ")
      for idx, expr in enumerate(node.exprs):
        if idx > 0:
          self.emit(", ")
        self._emit_value_expr(expr)
      self._emit_writebacks(node.targets)
      return

    # Compound assignment (+=, -=, *=, /=, %=)
    if self._is_int_div_assign(node):
      self.newline()
      self.record_line(getattr(node, "start_line", None))
      if isinstance(node.target, IdentifierNode):
        py_t = self._resolve_var_name(node.target.name)
        self.moved_vars.discard(py_t)
        if node.target.name in self.extern_vars:
          ext_lhs = (
            f"__import__('builtins').{self.extern_vars[node.target.name]}"
          )
          self.emit(f"{ext_lhs} = _sapphire_div({ext_lhs}, ")
          self.visit(node.expr)
          self.emit(")")
        else:
          self.emit(f"{py_t} = _sapphire_div({py_t}, ")
          self.visit(node.expr)
          self.emit(")")
      elif isinstance(node.target, MemberAccessNode):
        obj_tmp = self._next_temp_name("_div_obj")
        member_name = getattr(
          node.target, "target_name", None
        ) or self._mangle_name(node.target.member)
        self.emit(f"{obj_tmp} = ")
        self.visit(node.target.receiver)
        self.newline()
        self.emit(
          f"{obj_tmp}.{member_name} = _sapphire_div({obj_tmp}.{member_name}, "
        )
        self.visit(node.expr)
        self.emit(")")
      elif isinstance(node.target, IndexExprNode):
        arr_tmp = self._next_temp_name("_div_arr")
        idx_tmp = self._next_temp_name("_div_idx")
        self.emit(f"{arr_tmp} = ")
        self.visit(node.target.array)
        self.newline()
        self.emit(f"{idx_tmp} = ")
        self.visit(node.target.index)
        self.newline()
        self.emit(
          f"{arr_tmp}[{idx_tmp}] = _sapphire_div({arr_tmp}[{idx_tmp}], "
        )
        self.visit(node.expr)
        self.emit(")")
      else:
        self.visit(node.target)
        self.emit(" = _sapphire_div(")
        self.visit(node.target)
        self.emit(", ")
        self.visit(node.expr)
        self.emit(")")
      self._emit_writebacks([node.target])
      return

    self.newline()
    self.record_line(getattr(node, "start_line", None))
    if isinstance(node.target, IdentifierNode):
      self.moved_vars.discard(self._resolve_var_name(node.target.name))
      if node.target.name in self.extern_vars:
        ext_name = self.extern_vars[node.target.name]
        self.emit(f"__import__('builtins').{ext_name}")
      else:
        self.visit(node.target)
    else:
      self.visit(node.target)
    self.emit(f" {node.op} ")
    self.visit(node.expr)
    self._emit_writebacks([node.target])

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    if isinstance(node.expr, MatchExprNode):
      self._emit_match_statement(node.expr, target_var=None)
      return
    self._lift_match_expressions(node.expr)
    self.newline()
    self.record_line(getattr(node, "start_line", None))
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    self._lift_match_expressions(node.expressions)
    all_active_destructors = [
      d for frame in reversed(self.destructor_stack) for d in reversed(frame)
    ]
    returned_ids = {
      self._resolve_var_name(expr.name)
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

    if (
      node.expressions
      and destructors_to_run
      and not all(
        isinstance(e, (LiteralNode, IdentifierNode)) for e in node.expressions
      )
    ):
      ret_tmps = []
      for idx, expr in enumerate(node.expressions):
        tmp_name = f"_ret_val_{idx + 1}"
        ret_tmps.append(tmp_name)
        self.newline()
        self.emit(f"{tmp_name} = ")
        self.visit(expr)

      self._drain_pending_destroy_moved_vars()
      for var_name in destructors_to_run:
        if (
          var_name not in self.moved_vars
          and var_name not in self._pending_null_vars
          and var_name not in self._pending_unconditional_null_vars
        ):
          self.newline()
          self.emit(f"_sapphire_del({var_name})")

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
        self.emit(f"_sapphire_del({var_name})")

    self.newline()
    if not node.expressions:
      self.emit("return")
    else:
      self.emit("return ")
      for idx, expr in enumerate(node.expressions):
        if idx > 0:
          self.emit(", ")
        self.visit(expr)
    self._pending_null_vars.clear()
    self._pending_unconditional_null_vars.clear()
    self._pending_destroy_moved_vars.clear()

  def _emit_match_statement(
    self, node: MatchExprNode, target_var: Optional[str] = ""
  ) -> str:
    self._lift_match_expressions(node.subject)

    if target_var == "":
      target_var = self._next_temp_name("_match_res")
      self.newline()
      self.emit(f"{target_var} = None")

    subj_var = self._next_temp_name("_match_subj")
    self.newline()
    self.emit(f"{subj_var} = ")
    self.visit(node.subject)

    done_flag: Optional[str] = None
    if target_var and any(
      self._arm_needs_done_flag(c.body) for c in node.cases
    ):
      done_flag = self._next_temp_name("_match_done")
      self.newline()
      self.emit(f"{done_flag} = False")

    prev_target = self._current_match_target
    prev_done = self._current_match_done_flag
    prev_loop_depth = self._match_loop_depth
    self._current_match_target = target_var
    self._current_match_done_flag = done_flag
    self._match_loop_depth = 0

    try:
      for c_idx, case in enumerate(node.cases):
        has_ellipsis = any(
          isinstance(p, EllipsisPatternNode) for p in case.patterns
        )
        self.newline()
        if has_ellipsis:
          if c_idx == 0:
            self.emit("if True:")
          elif c_idx == len(node.cases) - 1:
            self.emit("else:")
          else:
            self.emit("elif True:")
        else:
          kw = "if" if c_idx == 0 else "elif"
          self.emit(f"{kw} ")
          for p_idx, pat in enumerate(case.patterns):
            if p_idx > 0:
              self.emit(" or ")
            if isinstance(pat, LiteralNode) and pat.lit_type == "none":
              self.emit(f"({subj_var} is None)")
            else:
              self.emit(f"({subj_var} == ")
              self.visit(pat)
              self.emit(")")
          self.emit(":")

        self.indent()
        self._branch_depth += 1
        try:
          if isinstance(case.body, BlockNode):
            if not case.body.statements:
              self.newline()
              self.emit("pass")
            else:
              self.visit(case.body)
          else:
            self._lift_match_expressions(case.body)
            self.newline()
            if target_var:
              self.emit(f"{target_var} = ")
              self.visit(case.body)
            else:
              self.visit(case.body)
          self._drain_pending_null_vars("None")
        finally:
          self._branch_depth -= 1
        self.dedent()
    finally:
      self._current_match_target = prev_target
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
        self.emit("None")
      elif len(exprs) == 1:
        self.visit(exprs[0])
      else:
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)
      if done_flag:
        self.newline()
        self.emit(f"{done_flag} = True")
    else:
      self.emit("yield")
      if not exprs:
        self.emit(" None")
      elif len(exprs) == 1:
        self.emit(" ")
        self.visit(exprs[0])
      else:
        self.emit(" ")
        for idx, expr in enumerate(exprs):
          if idx > 0:
            self.emit(", ")
          self.visit(expr)

  def visit_MatchExprNode(self, node: MatchExprNode) -> None:
    if id(node) not in self._lifted_matches:
      self._lifted_matches[id(node)] = self._emit_match_statement(node)
    self.emit(self._lifted_matches[id(node)])

  def visit_EllipsisPatternNode(self, node: EllipsisPatternNode) -> None:
    self.emit("_")

  def _emit_simple_if(self, node: IfNode) -> None:
    """Emits a standard `if cond: ... else: ...` statement."""
    if node.condition:
      self._lift_match_expressions(node.condition)
    self.newline()
    self.emit("if ")
    self.visit(node.condition)
    self.emit(":")
    self.indent()
    self._visit_in_branch(node.then_block)
    self.dedent()
    if node.else_block:
      self.newline()
      self.emit("else:")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()

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

    # Use sequential flag form when a condition exists with either liftable
    # expressions or owned destructibles.
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
          self._identifier_map[name] = f"{val_var}[{idx}]"

      self.emit(f"if {val_var} is not None")
      if node.condition:
        self.emit(" and ")
        self.visit(node.condition)
      self.emit(":")
      self._identifier_map = old_map

      self.indent()
      prev_id_map = self._identifier_map.copy()
      pushed_scope = bool(self._lexical_scopes)
      if pushed_scope:
        self._lexical_scopes.append(set())
      prev_wb = self._unwrap_writebacks.copy()
      extra_destructibles: List[str] = []
      try:
        py_let_names: List[str] = []
        self.newline()
        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            py_n = self._declare_local_var(name)
            py_let_names.append(py_n)
            self.emit(f"{py_n} = {val_var}[{idx}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          py_n = self._declare_local_var(let_name)
          py_let_names.append(py_n)
          self.emit(f"{py_n} = {val_var}")

        if is_owned_destructible:
          for py_n in py_let_names:
            self.variable_types[py_n] = st_name
            extra_destructibles.append(py_n)
        if wb_entry and len(py_let_names) == 1:
          self._unwrap_writebacks[py_let_names[0]] = wb_entry

        self._branch_depth += 1
        try:
          self._visit_block(
            node.then_block, extra_destructibles=extra_destructibles
          )
        finally:
          self._branch_depth -= 1
      finally:
        if pushed_scope:
          self._lexical_scopes.pop()
        self._identifier_map = prev_id_map
        self._unwrap_writebacks = prev_wb
      self.dedent()
    else:
      prev_id_map = self._identifier_map.copy()
      pushed_scope = bool(self._lexical_scopes)
      if pushed_scope:
        self._lexical_scopes.append(set())
      extra_destructibles = []
      try:
        py_n = self._declare_local_var(let_name)
        self.emit(f"{py_n} = ")
        self._emit_value_expr(binding.expr)
        if st_name:
          self.variable_types[py_n] = st_name
          extra_destructibles.append(py_n)
        if node.condition:
          self._lift_match_expressions(node.condition)
        self.newline()
        self.emit("if ")
        self.visit(node.condition)
        self.emit(":")
        self.indent()
        self._branch_depth += 1
        try:
          self._visit_block(
            node.then_block, extra_destructibles=extra_destructibles
          )
        finally:
          self._branch_depth -= 1
        self.dedent()
      finally:
        if pushed_scope:
          self._lexical_scopes.pop()
        self._identifier_map = prev_id_map

    if node.else_block:
      self.newline()
      self.emit("else:")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()

  def _emit_multi_binding_if(self, node: IfNode, bindings: List[Any]) -> None:
    """Emits multi-binding `if` with sequential short-circuiting and LIFO
    cleanup.
    """
    cond_flag = self._next_temp_name("_if_ok")

    self.newline()
    self.emit(f"{cond_flag} = False")

    def emit_binding_level(
      idx: int,
      prior_destructibles: List[str],
      wb_entries: Dict[str, tuple],
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
          self.emit(f"if {val_var} is not None:")
          self.indent()

          prev_id_map = self._identifier_map.copy()
          pushed_scope = bool(self._lexical_scopes)
          if pushed_scope:
            self._lexical_scopes.append(set())
          try:
            py_let_names: List[str] = []
            self.newline()
            if len(let_names) > 1:
              for n_idx, name in enumerate(let_names):
                py_n = self._declare_local_var(name)
                py_let_names.append(py_n)
                self.emit(f"{py_n} = {val_var}[{n_idx}]")
                if n_idx < len(let_names) - 1:
                  self.newline()
            else:
              py_n = self._declare_local_var(let_name)
              py_let_names.append(py_n)
              self.emit(f"{py_n} = {val_var}")

            current_destructibles = list(prior_destructibles)
            if is_owned:
              for py_n in py_let_names:
                self.variable_types[py_n] = st_name
                current_destructibles.append(py_n)

            next_wbs = dict(wb_entries)
            if wb_entry and len(py_let_names) == 1:
              next_wbs[py_let_names[0]] = wb_entry

            emit_binding_level(idx + 1, current_destructibles, next_wbs)
          finally:
            if pushed_scope:
              self._lexical_scopes.pop()
            self._identifier_map = prev_id_map

          self.dedent()
          if prior_destructibles:
            self.newline()
            self.emit("else:")
            self.indent()
            for d_var in reversed(prior_destructibles):
              self.newline()
              self.emit(f"_sapphire_del({d_var})")
            self.dedent()
        else:
          prev_id_map = self._identifier_map.copy()
          pushed_scope = bool(self._lexical_scopes)
          if pushed_scope:
            self._lexical_scopes.append(set())
          try:
            self.newline()
            py_n = self._declare_local_var(let_name)
            self.emit(f"{py_n} = ")
            self._emit_value_expr(b.expr)
            current_destructibles = list(prior_destructibles)
            if is_owned:
              self.variable_types[py_n] = st_name
              current_destructibles.append(py_n)
            emit_binding_level(idx + 1, current_destructibles, wb_entries)
          finally:
            if pushed_scope:
              self._lexical_scopes.pop()
            self._identifier_map = prev_id_map
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
            self.emit(":")
            self.indent()
            self.newline()
            self.emit(f"{cond_flag} = True")
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
              self.emit("else:")
              self.indent()
              for d_var in reversed(prior_destructibles):
                self.newline()
                self.emit(f"_sapphire_del({d_var})")
              self.dedent()
          else:
            self.newline()
            self.emit(f"{cond_flag} = True")
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
      self.emit(f"if not {cond_flag}:")
      self.indent()
      self._visit_in_branch(node.else_block)
      self.dedent()

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

  def visit_WhileNode(self, node: WhileNode) -> None:
    self.loop_destructor_depth.append(len(self.destructor_stack))
    self._loop_vars_stack.append([])
    self._match_loop_depth += 1
    try:
      cond_liftable = bool(
        node.condition
        and self._contains_liftable_expr(node.condition, include_moves=True)
      )
      if cond_liftable:
        self.newline()
        self.emit("while True:")
        self.indent()
        self._lift_match_expressions(node.condition)
        self.newline()
        self.emit("if not (")
        self.visit(node.condition)
        self.emit("):")
        self.indent()
        self.newline()
        self.emit("break")
        self.dedent()
        self.visit(node.block)
        done_flag = self._current_match_done_flag
        if done_flag and self._stmt_contains_match_yield(node.block):
          self.newline()
          self.emit(f"if {done_flag}:")
          self.indent()
          self.newline()
          self.emit("break")
          self.dedent()
        self.dedent()
      else:
        if node.condition:
          self._lift_match_expressions(node.condition)
        self.newline()
        self.emit("while ")
        self.visit(node.condition)
        self.emit(":")
        self.indent()
        self.visit(node.block)
        done_flag = self._current_match_done_flag
        if done_flag and self._stmt_contains_match_yield(node.block):
          self.newline()
          self.emit(f"if {done_flag}:")
          self.indent()
          self.newline()
          self.emit("break")
          self.dedent()
        self.dedent()
    finally:
      self._match_loop_depth -= 1
      self._loop_vars_stack.pop()
      self.loop_destructor_depth.pop()

  def visit_ForNode(self, node: ForNode) -> None:
    self.loop_destructor_depth.append(len(self.destructor_stack))
    self._match_loop_depth += 1
    prev_id_map = self._identifier_map.copy()
    prev_wb = self._unwrap_writebacks.copy()
    pushed_scope = bool(self._lexical_scopes)
    if pushed_scope:
      self._lexical_scopes.append(set())
    self._loop_vars_stack.append([])
    try:
      self._lift_match_expressions(node.iterable)
      is_mut = getattr(node, "is_mutable", False)
      is_range_call = (
        isinstance(node.iterable, CallNode)
        and isinstance(node.iterable.callee, IdentifierNode)
        and node.iterable.callee.name == "range"
      )

      if node.key_var is not None:
        if is_mut:
          iter_tmp = self._next_temp_name("_for_iter")
          self.newline()
          self.emit(f"{iter_tmp} = ")
          self.visit(node.iterable)
          k_py = self._declare_local_var(node.key_var)
          v_py = self._declare_local_var(node.val_var)
          self.newline()
          self.emit(
            f"for {k_py}, {v_py} in _sapphire_unwrap_read({iter_tmp}).items():"
          )
          self._unwrap_writebacks[v_py] = ("index", iter_tmp, k_py)
        else:
          iter_code = self.capture_expr(node.iterable)
          k_py = self._declare_local_var(node.key_var)
          v_py = self._declare_local_var(node.val_var)
          self.newline()
          self.emit(
            f"for {k_py}, {v_py} in _sapphire_unwrap_read({iter_code}).items():"
          )
      else:
        if is_mut and not is_range_call:
          iter_tmp = self._next_temp_name("_for_iter")
          idx_tmp = self._next_temp_name("_for_idx")
          self.newline()
          self.emit(f"{iter_tmp} = ")
          self.visit(node.iterable)
          v_py = self._declare_local_var(node.val_var)
          self.newline()
          self.emit(f"for {idx_tmp}, {v_py} in enumerate({iter_tmp}):")
          self._unwrap_writebacks[v_py] = ("index", iter_tmp, idx_tmp)
        else:
          iter_code = self.capture_expr(node.iterable)
          v_py = self._declare_local_var(node.val_var)
          self.newline()
          self.emit(f"for {v_py} in {iter_code}:")

      self.indent()
      self.visit(node.block)
      done_flag = self._current_match_done_flag
      if done_flag and self._stmt_contains_match_yield(node.block):
        self.newline()
        self.emit(f"if {done_flag}:")
        self.indent()
        self.newline()
        self.emit("break")
        self.dedent()
      self.dedent()
    finally:
      self._match_loop_depth -= 1
      self._loop_vars_stack.pop()
      if pushed_scope:
        self._lexical_scopes.pop()
      self._identifier_map = prev_id_map
      self._unwrap_writebacks = prev_wb
      self.loop_destructor_depth.pop()

  def visit_BreakNode(self, node: BreakNode) -> None:
    self._emit_loop_destructors()
    self.newline()
    self.emit("break")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    self._emit_loop_destructors()
    self.newline()
    self.emit("continue")

  def visit_GuardClauseNode(self, node: GuardClauseNode) -> None:
    if node.binding:
      self.visit(node.binding.expr)
    elif node.condition:
      self.visit(node.condition)

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
          self.emit(f"if {tmp_var} is None:")
          self.indent()
          self._visit_in_branch(node.else_block)
          self.dedent()
          self.newline()

        py_let_names: List[str] = []
        if len(let_names) > 1:
          for idx, name in enumerate(let_names):
            py_n = self._declare_local_var(name)
            py_let_names.append(py_n)
            self.emit(f"{py_n} = {tmp_var}[{idx}]")
            if idx < len(let_names) - 1:
              self.newline()
        else:
          py_n = self._declare_local_var(binding.let_name)
          py_let_names.append(py_n)
          self.emit(f"{py_n} = {tmp_var}")

        st_name = self._expr_destructible_struct(binding.expr)
        if st_name and (
          not binding.is_unwrap or self._is_owned_unwrap_expr(binding.expr)
        ):
          for py_n in py_let_names:
            self.variable_types[py_n] = st_name
            if self.destructor_stack:
              self.destructor_stack[-1].append(py_n)
              self._var_branch_depth[py_n] = self._branch_depth

        if wb_entry and len(py_let_names) == 1:
          self._unwrap_writebacks[py_let_names[0]] = wb_entry
      elif clause.condition:
        self._lift_match_expressions(clause.condition)
        self.newline()
        self.emit("if not (")
        self.visit(clause.condition)
        self.emit("):")
        self.indent()
        self._visit_in_branch(node.else_block)
        self.dedent()
