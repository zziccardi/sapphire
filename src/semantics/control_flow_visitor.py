"""Control-flow AST visitor methods for TypeChecker (if, guard, match, loops).
"""

from typing import Any, List, Optional, Set, Tuple

from src.parser.ast import (
  ASTNode,
  BlockNode,
  BreakNode,
  CallNode,
  ContinueNode,
  EllipsisPatternNode,
  ExprStmtNode,
  ForNode,
  GuardStmtNode,
  HeaderBindingNode,
  IdentifierNode,
  IfNode,
  IndexExprNode,
  LambdaNode,
  LiteralNode,
  MatchExprNode,
  MemberAccessNode,
  MoveNode,
  ReturnNode,
  WhileNode,
  YieldNode,
)
from src.semantics.arena_checker import ArenaChecker
from src.semantics.lints import (
  check_guard_contains_access,
  check_if_contains_access,
)
from src.semantics.symbol_table import (
  ArrayType,
  EnumSymbol,
  EnumType,
  MapType,
  MultiReturnType,
  NoneType,
  OptionalType,
  PrimitiveType,
  RangeType,
  Type,
  VariableSymbol,
)


class ControlFlowVisitorMixin:
  """Provides AST visitor methods for branches, pattern matching, and loops."""

  def _bind_header_binding(
    self,
    binding: HeaderBindingNode,
    owner_node: ASTNode,
    freeze_label: str,
    non_optional_msg: str,
  ) -> Optional[Tuple[str, Tuple[str, List[str], str]]]:
    """Resolves and defines a `let`/`var` or `?=` header binding for
    `if`/`guard`.
    """
    expr_type = self.visit(binding.expr)
    is_borrowed_unwrap = False
    if binding.is_unwrap:
      if not isinstance(expr_type, OptionalType):
        self.error(non_optional_msg.format(expr_t=expr_type), node=binding.expr)
        unwrapped_type = expr_type
      else:
        unwrapped_type = expr_type.base_type
      # Borrowing an lvalue via `if let`/`if var` avoids moving the source.
      if isinstance(
        binding.expr, (IdentifierNode, MemberAccessNode, IndexExprNode)
      ) and not isinstance(binding.expr, MoveNode):
        is_borrowed_unwrap = True
    else:
      unwrapped_type = expr_type
      self._check_value_ownership_transfer(
        binding.expr, expr_type, node=binding.expr
      )

    let_names = getattr(binding, "let_names", [binding.let_name])
    self.node_types[binding] = unwrapped_type
    if len(let_names) > 1:
      if isinstance(unwrapped_type, MultiReturnType):
        if len(unwrapped_type.types) != len(let_names):
          self.error(
            f"Cannot unpack {len(unwrapped_type.types)} value(s) into "
            f"{len(let_names)} variable(s).",
            node=binding,
          )
          names_and_types = [
            (
              name,
              unwrapped_type.types[i]
              if i < len(unwrapped_type.types)
              else PrimitiveType("none"),
            )
            for i, name in enumerate(let_names)
          ]
        else:
          names_and_types = list(
            zip(let_names, unwrapped_type.types, strict=False)
          )
      elif isinstance(unwrapped_type, ArrayType):
        names_and_types = [
          (name, unwrapped_type.element_type) for name in let_names
        ]
      else:
        self.error(
          f"Cannot unpack single value of type '{unwrapped_type}' into "
          f"{len(let_names)} variable(s).",
          node=binding,
        )
        names_and_types = [(name, unwrapped_type) for name in let_names]
    else:
      names_and_types = [(binding.let_name, unwrapped_type)]

    binding._bound_names = [name for name, _ in names_and_types]
    for name, b_type in names_and_types:
      sym = VariableSymbol(name, b_type, is_mutable=binding.is_mutable)
      sym.is_borrowed_unwrap = is_borrowed_unwrap
      sym.ast_decl = binding
      self.symbol_table.define(name, sym)
      ArenaChecker.validate_arena_escape(
        self.symbol_table,
        sym,
        binding.expr,
        lambda msg: self.error(msg, node=owner_node),
        checker=self,
      )

    return self._register_unwrap_binding_freeze(binding, freeze_label)

  def _stmt_always_yields(self, stmt: ASTNode) -> bool:
    """Returns True if *stmt* unconditionally yields or diverges from a match
    block.
    """
    if isinstance(stmt, (YieldNode, ReturnNode, BreakNode, ContinueNode)):
      return True
    if isinstance(stmt, IfNode):
      if stmt.then_block and stmt.else_block:
        then_y = self._block_always_yields(stmt.then_block)
        else_y = (
          self._stmt_always_yields(stmt.else_block)
          if isinstance(stmt.else_block, ASTNode)
          else self._block_always_yields(stmt.else_block)
        )
        return then_y and else_y
      return False
    if isinstance(stmt, BlockNode):
      return self._block_always_yields(stmt)
    if isinstance(stmt, ExprStmtNode) and isinstance(stmt.expr, MatchExprNode):
      stmt = stmt.expr
    if isinstance(stmt, MatchExprNode) and getattr(
      stmt, "_is_exhaustive", False
    ):
      return bool(stmt.cases) and all(
        self._stmt_always_yields(c.body) for c in stmt.cases
      )
    return False

  def _block_always_yields(self, block: BlockNode) -> bool:
    for stmt in getattr(block, "statements", []):
      if self._stmt_always_yields(stmt):
        return True
    return False

  def _check_match_pattern(
    self,
    pattern: Any,
    subject_type: Type,
    seen_enum_variants: Set[str],
    bool_flags: List[bool],
    opt_flags: List[bool],
  ) -> None:
    """Validates a single match pattern against the subject type and updates
    coverage.
    """
    if isinstance(pattern, EllipsisPatternNode):
      opt_flags[2] = True  # has_ellipsis
      return

    if isinstance(subject_type, EnumType):
      if isinstance(pattern, MemberAccessNode):
        pat_type = self.visit(pattern)
        if isinstance(pat_type, EnumType) and pat_type == subject_type:
          seen_enum_variants.add(pattern.member)
        else:
          self.error(
            f"Pattern '{pattern}' is not a valid variant of enum "
            f"'{subject_type.name}'."
          )
      elif isinstance(pattern, IdentifierNode):
        if pattern.name in subject_type.variants:
          seen_enum_variants.add(pattern.name)
        else:
          sym = self.symbol_table.lookup(pattern.name)
          if not (
            isinstance(sym, EnumSymbol) and sym.name == subject_type.name
          ):
            self.error(f"Undefined identifier '{pattern.name}'.")
      else:
        pat_type = self.visit(pattern)
        if not (isinstance(pat_type, EnumType) and pat_type == subject_type):
          self.error(
            f"Pattern '{pattern}' is not a valid variant of enum "
            f"'{subject_type.name}'."
          )
      return

    if isinstance(subject_type, PrimitiveType) and subject_type.name == "bool":
      self.visit(pattern)
      if isinstance(pattern, LiteralNode) and pattern.lit_type == "bool":
        if pattern.value is True or pattern.value == "true":
          bool_flags[0] = True
        elif pattern.value is False or pattern.value == "false":
          bool_flags[1] = True
      else:
        self.error("Bool match pattern must be 'true' or 'false'.")
      return

    if isinstance(subject_type, OptionalType):
      if isinstance(pattern, LiteralNode) and pattern.lit_type == "none":
        self.visit(pattern)
        opt_flags[0] = True  # seen_optional_none
        return
      if isinstance(subject_type.base_type, EnumType):
        if (
          isinstance(pattern, IdentifierNode)
          and pattern.name in subject_type.base_type.variants
        ):
          seen_enum_variants.add(pattern.name)
          opt_flags[1] = True
          return
        pat_type = self.visit(pattern)
        if isinstance(pat_type, NoneType) or (
          isinstance(pat_type, PrimitiveType) and pat_type.name == "none"
        ):
          opt_flags[0] = True
        elif (
          isinstance(pat_type, EnumType) and pat_type == subject_type.base_type
        ):
          if isinstance(pattern, MemberAccessNode):
            seen_enum_variants.add(pattern.member)
          opt_flags[1] = True
        else:
          self.error(
            f"Pattern type '{pat_type}' is incompatible with optional inner "
            f"type '{subject_type.base_type}'."
          )
        return
      pat_type = self.visit(pattern)
      if isinstance(pat_type, NoneType) or (
        isinstance(pat_type, PrimitiveType) and pat_type.name == "none"
      ):
        opt_flags[0] = True  # seen_optional_none
      elif (
        isinstance(subject_type.base_type, PrimitiveType)
        and subject_type.base_type.name == "bool"
      ):
        if isinstance(pattern, LiteralNode) and pattern.lit_type == "bool":
          if pattern.value is True or pattern.value == "true":
            bool_flags[0] = True
          elif pattern.value is False or pattern.value == "false":
            bool_flags[1] = True
          opt_flags[1] = True
        elif pat_type == PrimitiveType("bool"):
          opt_flags[1] = True
        else:
          self.error(
            f"Pattern type '{pat_type}' is incompatible with optional inner "
            f"type '{subject_type.base_type}'."
          )
      elif pat_type.is_compatible(
        subject_type.base_type
      ) or subject_type.base_type.is_compatible(pat_type):
        opt_flags[1] = True  # seen_optional_some (not exhaustive by itself)
      else:
        self.error(
          f"Pattern type '{pat_type}' is incompatible with optional "
          f"inner type '{subject_type.base_type}'."
        )
      return

    pat_type = self.visit(pattern)
    if not pat_type.is_compatible(
      subject_type
    ) and not subject_type.is_compatible(pat_type):
      self.error(
        f"Pattern type '{pat_type}' is incompatible with subject type "
        f"'{subject_type}'."
      )
    opt_flags[1] = True

  def visit_MatchExprNode(self, node: MatchExprNode) -> Type:
    """Type-checks `match` statements and value-producing expressions."""
    old_expected = self.expected_type
    self.expected_type = None
    try:
      subject_type = self.visit(node.subject)
    finally:
      self.expected_type = old_expected
    is_stmt = getattr(node, "is_statement", False)

    seen_enum_variants: Set[str] = set()
    # [seen_true, seen_false] and [seen_none, seen_some, has_ellipsis]
    bool_flags = [False, False]
    opt_flags = [False, False, False]
    has_unyielded_block = False

    case_types: List[Type] = []
    pre_match_moved = set(self.moved_symbols)
    union_moved: Set[VariableSymbol] = set(pre_match_moved)
    pre_match_uninit = set(self.uninitialized_symbols)
    pre_match_init_fields = set(self.initialized_fields)
    fallthrough_uninit: List[Set[VariableSymbol]] = []
    fallthrough_init_fields: List[Set[str]] = []

    for case in node.cases:
      # Each arm starts from the pre-match state.
      self._restore_moved_symbols(pre_match_moved)
      self.uninitialized_symbols = set(pre_match_uninit)
      self.initialized_fields = set(pre_match_init_fields)

      pat_old_expected = self.expected_type
      self.expected_type = None
      try:
        for pattern in case.patterns:
          self._check_match_pattern(
            pattern, subject_type, seen_enum_variants, bool_flags, opt_flags
          )
      finally:
        self.expected_type = pat_old_expected

      arm_diverges = False
      if is_stmt:
        self.visit(case.body)
        if isinstance(case.body, BlockNode):
          arm_diverges = self._block_terminates(case.body)
        else:
          arm_diverges = self._statement_terminates(case.body)
        case_types.append(NoneType())
      else:
        self._match_stack.append([])
        if isinstance(case.body, BlockNode):
          self.visit(case.body)
          yields = self._match_stack.pop()
          all_yield_or_diverge = self._block_always_yields(case.body)
          arm_diverges = self._block_terminates(case.body)
          if yields:
            widened_yield = yields[0]
            for y in yields[1:]:
              merged = self._widen_types(widened_yield, y)
              if merged is None:
                self.error(
                  f"Incompatible yield types in match case: '{widened_yield}' "
                  f"and '{y}'."
                )
              else:
                widened_yield = merged
            case_types.append(widened_yield)
            if not all_yield_or_diverge:
              has_unyielded_block = True
          elif arm_diverges:
            # Block unconditionally exits via return/break/continue; no yield
            # needed.
            pass
          else:
            case_types.append(NoneType())
            has_unyielded_block = True
        else:
          self._match_stack.pop()
          expr_type = self.visit(case.body)
          self._check_value_ownership_transfer(
            case.body, expr_type, node=case.body
          )
          case_types.append(expr_type)
      union_moved |= self.moved_symbols
      if not arm_diverges:
        fallthrough_uninit.append(set(self.uninitialized_symbols))
        fallthrough_init_fields.append(set(self.initialized_fields))

    if node.cases:
      self._restore_moved_symbols(union_moved)

    has_ellipsis = opt_flags[2]
    is_exhaustive = True
    if not has_ellipsis:
      if isinstance(subject_type, EnumType):
        missing = set(subject_type.variants.keys()) - seen_enum_variants
        if missing:
          is_exhaustive = False
          self.error(
            f"Match expression for enum '{subject_type.name}' is not "
            f"exhaustive. Missing case: '{next(iter(missing))}'."
          )
      elif (
        isinstance(subject_type, PrimitiveType) and subject_type.name == "bool"
      ):
        if not (bool_flags[0] and bool_flags[1]):
          is_exhaustive = False
          self.error("Match expression for bool is not exhaustive.")
      elif isinstance(subject_type, OptionalType):
        base = subject_type.base_type
        if isinstance(base, EnumType):
          missing = set(base.variants.keys()) - seen_enum_variants
          if not opt_flags[0] or missing:
            is_exhaustive = False
            self.error(
              f"Match expression for optional '{subject_type}' is not "
              "exhaustive."
            )
        elif isinstance(base, PrimitiveType) and base.name == "bool":
          if not (opt_flags[0] and bool_flags[0] and bool_flags[1]):
            is_exhaustive = False
            self.error(
              f"Match expression for optional '{subject_type}' is not "
              "exhaustive."
            )
        else:
          is_exhaustive = False
          self.error(
            f"Match expression for optional '{subject_type}' is not "
            "exhaustive. Add a wildcard '...' arm."
          )
      elif not isinstance(subject_type, NoneType):
        is_exhaustive = False
        self.error(
          f"Match expression for type '{subject_type}' is not exhaustive. Add "
          "a wildcard '...' arm."
        )

    node._is_exhaustive = is_exhaustive
    if is_exhaustive and fallthrough_uninit:
      merged_uninit: Set[VariableSymbol] = set()
      for u_set in fallthrough_uninit:
        merged_uninit |= u_set
      self.uninitialized_symbols = merged_uninit
      merged_fields = set(fallthrough_init_fields[0])
      for f_set in fallthrough_init_fields[1:]:
        merged_fields &= f_set
      self.initialized_fields = merged_fields
    elif not is_exhaustive:
      self.uninitialized_symbols = set(pre_match_uninit)
      self.initialized_fields = set(pre_match_init_fields)

    if is_stmt:
      return PrimitiveType("none")

    non_none_types = [
      t
      for t in case_types
      if not (
        isinstance(t, NoneType)
        or (isinstance(t, PrimitiveType) and t.name == "none")
      )
    ]
    if not non_none_types:
      if has_unyielded_block:
        self.error(
          "Match case block in value-producing match expression must "
          "explicitly yield a value."
        )
      return PrimitiveType("none")

    if has_unyielded_block:
      self.error(
        "Match case block in value-producing match expression must explicitly "
        "yield a value."
      )

    result_type = non_none_types[0]
    for t in non_none_types[1:]:
      widened = self._widen_types(result_type, t)
      if widened is None:
        self.error(
          f"Incompatible return types in match branches: '{result_type}' and "
          f"'{t}'."
        )
      else:
        result_type = widened

    has_none = any(
      isinstance(t, NoneType)
      or (isinstance(t, PrimitiveType) and t.name == "none")
      for t in case_types
    )
    if has_none or len(non_none_types) < len(case_types):
      return (
        result_type
        if isinstance(result_type, OptionalType)
        else OptionalType(result_type)
      )
    return result_type

  def _visit_if_else_branch(
    self,
    node: IfNode,
    pre_branch_moved: Set[VariableSymbol],
    pre_uninit: Set[VariableSymbol],
    pre_init_fields: Set[str],
    then_moved: Optional[Set[VariableSymbol]] = None,
    then_uninit: Optional[Set[VariableSymbol]] = None,
    then_init_fields: Optional[Set[str]] = None,
  ) -> None:
    """Visits an `else` branch with `if var` freezes cleared and merges branch
    states.
    """
    if then_moved is None:
      then_moved = set(self.moved_symbols)
    if then_uninit is None:
      then_uninit = set(self.uninitialized_symbols)
    if then_init_fields is None:
      then_init_fields = set(self.initialized_fields)
    then_term = (
      self._block_terminates(node.then_block)
      if isinstance(node.then_block, BlockNode)
      else self._statement_terminates(node.then_block)
    )
    if node.else_block:
      saved_frozen = list(self.symbol_table.current_scope.frozen_lvalues)
      # `if var` unwrap only freezes the source in the `then` branch.
      self.symbol_table.current_scope.frozen_lvalues = [
        f for f in saved_frozen if f[2] != "active 'if var' unwrap"
      ]
      self._restore_moved_symbols(pre_branch_moved)
      self.uninitialized_symbols = set(pre_uninit)
      self.initialized_fields = set(pre_init_fields)
      self.visit(node.else_block)
      else_moved = set(self.moved_symbols)
      else_uninit = set(self.uninitialized_symbols)
      else_init_fields = set(self.initialized_fields)
      else_term = (
        self._statement_terminates(node.else_block)
        if isinstance(node.else_block, ASTNode)
        else self._block_terminates(node.else_block)
      )
      self._restore_moved_symbols(then_moved | else_moved)
      self.symbol_table.current_scope.frozen_lvalues = saved_frozen

      if then_term and not else_term:
        self.uninitialized_symbols = else_uninit
        self.initialized_fields = else_init_fields
      elif else_term and not then_term:
        self.uninitialized_symbols = then_uninit
        self.initialized_fields = then_init_fields
      else:
        self.uninitialized_symbols = then_uninit | else_uninit
        self.initialized_fields = then_init_fields & else_init_fields
    else:
      self._restore_moved_symbols(then_moved)
      self.uninitialized_symbols = set(pre_uninit)
      self.initialized_fields = set(pre_init_fields)

  def visit_IfNode(self, node: IfNode) -> None:
    """Type-checks `if` statements, optional-unwrap bindings, and NLL freezes.
    """
    if node.bindings:
      pre_branch_moved = set(self.moved_symbols)
      pre_uninit = set(self.uninitialized_symbols)
      pre_init_fields = set(self.initialized_fields)
      self.symbol_table.enter_scope()
      if_header_scope = self.symbol_table.current_scope
      has_unwrap = False
      unwrap_freezes: List[Tuple[str, Tuple[str, List[str], str]]] = []
      for binding in node.bindings:
        if binding.is_unwrap:
          has_unwrap = True
        unwrap_entry = self._bind_header_binding(
          binding,
          node,
          "active 'if var' unwrap",
          "Expression in optional unwrapping must resolve to an optional type.",
        )
        if unwrap_entry:
          unwrap_freezes.append(unwrap_entry)

      if node.condition:
        cond_type = self.visit(node.condition)
        if cond_type != PrimitiveType("bool"):
          c_node = (
            node.condition
            if (
              hasattr(node.condition, "start_line")
              and isinstance(node.condition.start_line, int)
            )
            else None
          )
          self.error("If condition must resolve to 'bool'.", node=c_node)
      elif not has_unwrap:
        self.error(
          "Init-statement in 'if' must be followed by a condition unless "
          "using optional unwrapping '?='."
        )

      post_header_moved = set(self.moved_symbols)
      self._branch_depth += 1
      try:
        try:
          if unwrap_freezes and isinstance(node.then_block, BlockNode):
            if_scope = self.symbol_table.current_scope
            self.symbol_table.enter_scope()
            try:
              self._visit_stmts_with_unwrap_nll(
                node.then_block.statements,
                initial_freezes=unwrap_freezes,
                freeze_scope=if_scope,
              )
            finally:
              cur_scope = self.symbol_table.current_scope
              self._restore_moved_symbols(
                {s for s in self.moved_symbols if s.scope_defined != cur_scope}
              )
              self.symbol_table.exit_scope()
          else:
            self.visit(node.then_block)
          check_if_contains_access(self, node)
          then_moved = {
            s for s in self.moved_symbols if s.scope_defined != if_header_scope
          }
          then_uninit = {
            s
            for s in self.uninitialized_symbols
            if s.scope_defined != if_header_scope
          }
          then_init_fields = set(self.initialized_fields)
        finally:
          # Exit `if_header_scope` BEFORE visiting `else_block` so `if let`/`if
          # var`
          # bindings are strictly scoped to the `then` branch (not `else`).
          self._restore_moved_symbols(
            {
              s
              for s in self.moved_symbols
              if s.scope_defined != if_header_scope
            }
          )
          self.symbol_table.exit_scope()

        else_pre_moved = {
          s for s in post_header_moved if s.scope_defined != if_header_scope
        }
        self._visit_if_else_branch(
          node,
          else_pre_moved,
          pre_uninit,
          pre_init_fields,
          then_moved=then_moved,
          then_uninit=then_uninit,
          then_init_fields=then_init_fields,
        )
      finally:
        self._branch_depth -= 1
      return

    cond_type = self.visit(node.condition)
    if cond_type != PrimitiveType("bool"):
      c_node = (
        node.condition
        if (
          hasattr(node.condition, "start_line")
          and isinstance(node.condition.start_line, int)
        )
        else None
      )
      self.error("If condition must resolve to 'bool'.", node=c_node)

    pre_branch_moved = set(self.moved_symbols)
    pre_uninit = set(self.uninitialized_symbols)
    pre_init_fields = set(self.initialized_fields)
    self._branch_depth += 1
    try:
      self._visit_block_with_terminating_unfreeze(node.then_block)
      check_if_contains_access(self, node)
      self._visit_if_else_branch(
        node, pre_branch_moved, pre_uninit, pre_init_fields
      )
    finally:
      self._branch_depth -= 1

  def visit_WhileNode(self, node: WhileNode) -> None:
    """Type-checks `while` loops and ensures no move-only vars are consumed
    across
    iterations.
    """
    self.loop_depth += 1
    self._branch_depth += 1
    pre_loop_moved = set(self.moved_symbols)
    pre_loop_uninit = set(self.uninitialized_symbols)
    pre_loop_init_fields = set(self.initialized_fields)
    loop_outer_scope = self.symbol_table.current_scope
    self._loop_context_stack.append((pre_loop_moved, loop_outer_scope))
    try:
      cond_type = self.visit(node.condition)
      if cond_type != PrimitiveType("bool"):
        self.error("While condition must resolve to 'bool'.")
      self.visit(node.block)

      for sym in self.moved_symbols - pre_loop_moved:
        self.error(
          f"Cannot move variable '{sym.name}' inside a loop without "
          "re-assigning it before the next iteration.",
          node=node,
        )
    finally:
      self._loop_context_stack.pop()
      self._branch_depth -= 1
      self.loop_depth -= 1
      # Loop body may execute 0 times; restore pre-loop initialization
      # guarantees.
      self.uninitialized_symbols = set(pre_loop_uninit)
      self.initialized_fields = set(pre_loop_init_fields)

  def visit_ForNode(self, node: ForNode) -> None:
    """Type-checks `for-in` loops and freezes the iterated collection against
    mutation.
    """
    self.loop_depth += 1
    self._branch_depth += 1
    pre_loop_moved = set(self.moved_symbols)
    pre_loop_uninit = set(self.uninitialized_symbols)
    pre_loop_init_fields = set(self.initialized_fields)
    loop_outer_scope = self.symbol_table.current_scope
    self._loop_context_stack.append((pre_loop_moved, loop_outer_scope))
    try:
      iter_type = self.visit(node.iterable)
      self.symbol_table.enter_scope()
      for_scope = self.symbol_table.current_scope
      iter_res = ArenaChecker.get_lvalue_path(self.symbol_table, node.iterable)
      if iter_res:
        self.symbol_table.current_scope.frozen_lvalues.append(
          (iter_res[0], iter_res[1], "for-in loop iteration")
        )

      if isinstance(iter_type, ArrayType):
        if node.key_var is not None:
          self.error(
            "Cannot iterate over an array with key-value syntax; use a single "
            "loop variable."
          )
        elem_type = iter_type.element_type
        self.node_types[node] = elem_type
        val_sym = VariableSymbol(node.val_var, elem_type, node.is_mutable)
        val_sym.is_borrowed_unwrap = True
        self.symbol_table.define(node.val_var, val_sym)
        ArenaChecker.validate_arena_escape(
          self.symbol_table,
          val_sym,
          node.iterable,
          lambda msg: self.error(msg, node=node),
          checker=self,
        )
      elif isinstance(iter_type, RangeType):
        if node.key_var is not None:
          self.error(
            "Cannot iterate over a range with key-value syntax; use a single "
            "loop variable."
          )
        self.node_types[node] = PrimitiveType("int")
        self.symbol_table.define(
          node.val_var,
          VariableSymbol(node.val_var, PrimitiveType("int"), node.is_mutable),
        )
      elif isinstance(iter_type, MapType):
        self.node_types[node] = iter_type.value_type
        if node.key_var is None:
          self.error(
            "Map iteration requires key and value loop variables: 'for key, "
            "val in map'."
          )
          val_sym = VariableSymbol(
            node.val_var, iter_type.value_type, node.is_mutable
          )
          val_sym.is_borrowed_unwrap = True
          self.symbol_table.define(node.val_var, val_sym)
          ArenaChecker.validate_arena_escape(
            self.symbol_table,
            val_sym,
            node.iterable,
            lambda msg: self.error(msg, node=node),
            checker=self,
          )
        else:
          key_sym = VariableSymbol(
            node.key_var, iter_type.key_type, node.is_mutable
          )
          val_sym = VariableSymbol(
            node.val_var, iter_type.value_type, node.is_mutable
          )
          key_sym.is_borrowed_unwrap = True
          val_sym.is_borrowed_unwrap = True
          self.symbol_table.define(node.key_var, key_sym)
          self.symbol_table.define(node.val_var, val_sym)
          for sym in (key_sym, val_sym):
            ArenaChecker.validate_arena_escape(
              self.symbol_table,
              sym,
              node.iterable,
              lambda msg: self.error(msg, node=node),
              checker=self,
            )
      else:
        self.error("For-in loop source must be an array, map, or range type.")
        self.node_types[node] = PrimitiveType("none")
        if node.key_var is not None:
          self.symbol_table.define(
            node.key_var,
            VariableSymbol(
              node.key_var, PrimitiveType("none"), node.is_mutable
            ),
          )
        self.symbol_table.define(
          node.val_var,
          VariableSymbol(node.val_var, PrimitiveType("none"), node.is_mutable),
        )

      self.visit(node.block)
      self._restore_moved_symbols(
        {s for s in self.moved_symbols if s.scope_defined != for_scope}
      )
      self.symbol_table.exit_scope()

      for sym in self.moved_symbols - pre_loop_moved:
        self.error(
          f"Cannot move variable '{sym.name}' inside a loop without "
          "re-assigning it before the next iteration.",
          node=node,
        )
    finally:
      self._loop_context_stack.pop()
      self._branch_depth -= 1
      self.loop_depth -= 1
      # Loop body may execute 0 times; restore pre-loop initialization
      # guarantees.
      self.uninitialized_symbols = set(pre_loop_uninit)
      self.initialized_fields = set(pre_loop_init_fields)

  def visit_BreakNode(self, node: BreakNode) -> None:
    if self.loop_depth <= 0:
      self.error("'break' statement outside of loop.")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    if self.loop_depth <= 0:
      self.error("'continue' statement outside of loop.")
      return
    if self._loop_context_stack:
      pre_loop_moved, loop_outer_scope = self._loop_context_stack[-1]
      for sym in self.moved_symbols - pre_loop_moved:
        if sym.scope_defined is None or ArenaChecker.is_descendant_scope(
          loop_outer_scope, sym.scope_defined
        ):
          self.error(
            f"Cannot move variable '{sym.name}' before 'continue' without "
            "re-assigning it before the next iteration.",
            node=node,
          )

  def _statement_terminates(self, stmt: ASTNode) -> bool:
    if isinstance(stmt, (ReturnNode, BreakNode, ContinueNode)):
      return True
    if isinstance(stmt, IfNode):
      if stmt.then_block and stmt.else_block:
        then_term = self._block_terminates(stmt.then_block)
        else_term = (
          self._statement_terminates(stmt.else_block)
          if isinstance(stmt.else_block, ASTNode)
          else self._block_terminates(stmt.else_block)
        )
        return then_term and else_term
    if isinstance(stmt, BlockNode):
      return self._block_terminates(stmt)
    if isinstance(stmt, ExprStmtNode) and isinstance(stmt.expr, MatchExprNode):
      stmt = stmt.expr
    if isinstance(stmt, MatchExprNode) and getattr(
      stmt, "_is_exhaustive", False
    ):
      return bool(stmt.cases) and all(
        self._statement_terminates(c.body) for c in stmt.cases
      )
    return False

  def _stmt_always_returns(self, stmt: ASTNode) -> bool:
    """Returns True if *stmt* unconditionally exits the enclosing function via
    `return`.
    """
    if isinstance(stmt, ReturnNode):
      return True
    if isinstance(stmt, IfNode):
      if stmt.then_block and stmt.else_block:
        then_ret = self._block_always_returns(stmt.then_block)
        else_ret = (
          self._stmt_always_returns(stmt.else_block)
          if isinstance(stmt.else_block, ASTNode)
          else self._block_always_returns(stmt.else_block)
        )
        return then_ret and else_ret
    if isinstance(stmt, BlockNode):
      return self._block_always_returns(stmt)
    if isinstance(stmt, ExprStmtNode) and isinstance(stmt.expr, MatchExprNode):
      stmt = stmt.expr
    if isinstance(stmt, MatchExprNode) and getattr(
      stmt, "_is_exhaustive", False
    ):
      return bool(stmt.cases) and all(
        self._stmt_always_returns(c.body) for c in stmt.cases
      )
    return False

  def _block_always_returns(self, block: BlockNode) -> bool:
    for stmt in getattr(block, "statements", []):
      if self._stmt_always_returns(stmt):
        return True
    return False

  def _visit_block_with_terminating_unfreeze(self, block: BlockNode) -> None:
    """Temporarily unfreezes active `if var` bindings on branches that exit the
    unwrap scope.

    Under control-flow-aware non-lexical lifetime analysis, a terminating branch
    that leaves the enclosing `if var` / `guard var` scope without referencing
    the unwrapped binding cannot fall through to later uses of that binding.
    Inner-loop `break` / `continue` only exit the loop, not an outer unwrap, so
    unfreezing inside an inner loop requires an unconditional `return`.
    """
    active = getattr(self, "_active_unwrap_freezes", [])
    temporarily_unfrozen = []
    if (
      active and isinstance(block, BlockNode) and self._block_terminates(block)
    ):
      always_returns = self._block_always_returns(block)
      for entry in active:
        unwrap_scope, var_name, freeze_entry, freeze_loop_depth = entry
        exits_unwrap_scope = always_returns or (
          self.loop_depth == freeze_loop_depth
        )
        if (
          exits_unwrap_scope
          and freeze_entry in unwrap_scope.frozen_lvalues
          and not self._ast_references_ident(block, var_name)
        ):
          unwrap_scope.frozen_lvalues.remove(freeze_entry)
          temporarily_unfrozen.append((unwrap_scope, freeze_entry))
    try:
      self.visit(block)
    finally:
      for unwrap_scope, freeze_entry in temporarily_unfrozen:
        if freeze_entry not in unwrap_scope.frozen_lvalues:
          unwrap_scope.frozen_lvalues.append(freeze_entry)

  def _block_terminates(self, block: BlockNode) -> bool:
    for stmt in getattr(block, "statements", []):
      if self._statement_terminates(stmt):
        return True
    return False

  def _ast_captures_ident_in_lambda(self, ast_node: Any, name: str) -> bool:
    """Returns True if any LambdaNode within *ast_node* captures *name*."""
    if ast_node is None:
      return False
    if isinstance(ast_node, list):
      return any(
        self._ast_captures_ident_in_lambda(item, name) for item in ast_node
      )
    if isinstance(ast_node, LambdaNode):
      param_names = {p.name for p in getattr(ast_node, "parameters", [])}
      if name not in param_names and self._ast_references_ident(
        ast_node.body, name
      ):
        return True
      return False
    if isinstance(ast_node, ASTNode):
      for val in ast_node.__dict__.values():
        if isinstance(
          val, (ASTNode, list)
        ) and self._ast_captures_ident_in_lambda(val, name):
          return True
    return False

  def _resolve_container_get_unwrap(
    self, expr: ASTNode
  ) -> Optional[Tuple[Tuple[str, List[str]], ASTNode, ASTNode, bool]]:
    """Resolves `container.get(key)` on a Map or Array lvalue."""
    if not (
      isinstance(expr, CallNode)
      and isinstance(expr.callee, MemberAccessNode)
      and expr.callee.member == "get"
      and not expr.callee.is_optional
      and len(expr.arguments) == 1
    ):
      return None
    recv = expr.callee.receiver
    recv_t = self.node_types.get(recv)
    if not isinstance(recv_t, (MapType, ArrayType)):
      return None
    recv_res = ArenaChecker.get_lvalue_path(self.symbol_table, recv)
    if not recv_res:
      return None
    arg = expr.arguments[0]
    key_expr = arg.expr if hasattr(arg, "expr") else arg
    return (recv_res, recv, key_expr, isinstance(recv_t, ArrayType))

  def _register_unwrap_binding_freeze(
    self, binding: HeaderBindingNode, freeze_label: str
  ) -> Optional[Tuple[str, Tuple[str, List[str], str]]]:
    """Validates and registers a mutable optional-unwrap freeze on an lvalue."""
    if not (binding.is_unwrap and binding.is_mutable):
      return None
    b_res = ArenaChecker.get_lvalue_path(self.symbol_table, binding.expr)
    container_info = None
    target_lvalue_node = binding.expr
    if not b_res:
      container_info = self._resolve_container_get_unwrap(binding.expr)
      if container_info:
        b_res = container_info[0]
        target_lvalue_node = container_info[1]
    if not b_res:
      self.error(
        "Mutable optional unwrap ('if var' / 'guard var') binds an in-place "
        "reference and requires a mutable lvalue. Use 'if let' / 'guard let' "
        "for non-lvalue temporaries.",
        node=binding.expr,
      )
      return None
    if self.has_shared_ref_base(target_lvalue_node):
      self.error(
        "Mutable optional unwrap ('if var' / 'guard var') cannot borrow "
        "through deeply immutable 'SharedRef'.",
        node=binding.expr,
      )
      return None
    root_sym = self.symbol_table.lookup(b_res[0])
    if isinstance(root_sym, VariableSymbol) and not root_sym.is_mutable:
      self.error(
        f"Mutable optional unwrap ('if var' / 'guard var') requires a mutable "
        f"source lvalue, but '{b_res[0]}' is immutable.",
        node=binding.expr,
      )
      return None
    immut = self._find_immutable_field_in_chain(target_lvalue_node)
    if immut is not None:
      field_name, struct_name = immut
      self.error(
        f"Mutable optional unwrap ('if var' / 'guard var') cannot borrow "
        f"through constant field '{field_name}' of '{struct_name}'.",
        node=binding.expr,
      )
      return None
    if container_info:
      _, recv, key_expr, is_array = container_info
      binding._writeback_container = (recv, key_expr, is_array)
    freeze_entry = (b_res[0], b_res[1], freeze_label)
    self.symbol_table.current_scope.frozen_lvalues.append(freeze_entry)
    return (binding.let_name, freeze_entry)

  def _visit_stmts_with_unwrap_nll(
    self,
    stmts: List[ASTNode],
    initial_freezes: Optional[
      List[Tuple[str, Tuple[str, List[str], str]]]
    ] = None,
    freeze_scope: Any = None,
  ) -> None:
    """Visits statements with non-lexical lifetime unfreezing for `if var` and
    `guard var`.
    """
    active_scope = freeze_scope or self.symbol_table.current_scope
    if not hasattr(self, "_active_unwrap_freezes"):
      self._active_unwrap_freezes = []
    pushed_count = 0
    tracked: List[Tuple[str, Tuple[str, List[str], str], int]] = []

    def register_freezes(
      freezes: List[Tuple[str, Tuple[str, List[str], str]]], start_idx: int
    ) -> None:
      nonlocal pushed_count
      for var_name, freeze_entry in freezes:
        last_idx = -1
        captured_in_lambda = False
        for s_idx in range(start_idx, len(stmts)):
          if self._ast_captures_ident_in_lambda(stmts[s_idx], var_name):
            captured_in_lambda = True
            last_idx = len(stmts)
            break
          if self._ast_references_ident(stmts[s_idx], var_name):
            last_idx = s_idx
        if last_idx == -1:
          if freeze_entry in active_scope.frozen_lvalues:
            active_scope.frozen_lvalues.remove(freeze_entry)
        else:
          self._active_unwrap_freezes.append(
            (active_scope, var_name, freeze_entry, self.loop_depth)
          )
          pushed_count += 1
          tracked.append((var_name, freeze_entry, last_idx))
          if captured_in_lambda:
            # Keep freeze alive through end of block; closure may run later.
            pass

    if initial_freezes:
      register_freezes(initial_freezes, 0)

    try:
      for s_idx, stmt in enumerate(stmts):
        prev_pending = getattr(self, "_pending_guard_unwrap_freezes", None)
        self._pending_guard_unwrap_freezes = []
        try:
          self.visit(stmt)
          new_guard_freezes = self._pending_guard_unwrap_freezes
        finally:
          self._pending_guard_unwrap_freezes = prev_pending

        if new_guard_freezes:
          register_freezes(new_guard_freezes, s_idx + 1)

        for _var_name, freeze_entry, last_idx in tracked:
          if last_idx == s_idx and freeze_entry in active_scope.frozen_lvalues:
            active_scope.frozen_lvalues.remove(freeze_entry)
      for s_idx, stmt in enumerate(stmts):
        if isinstance(stmt, GuardStmtNode):
          check_guard_contains_access(self, stmt, stmts[s_idx + 1 :])
    finally:
      if pushed_count > 0:
        del self._active_unwrap_freezes[
          len(self._active_unwrap_freezes) - pushed_count :
        ]

  def visit_GuardStmtNode(self, node: GuardStmtNode) -> Type:
    """Type-checks `guard` statements and promotes unwrapped bindings to outer
    scope.
    """
    outer_scope = self.symbol_table.current_scope
    pre_clause_symbols = dict(outer_scope.symbols)
    guard_freezes: List[Tuple[str, Tuple[str, List[str], str]]] = []
    for clause in node.clauses:
      if clause.binding:
        unwrap_entry = self._bind_header_binding(
          clause.binding,
          node,
          "active 'guard var' unwrap",
          "Cannot unwrap non-optional type '{expr_t}' in guard clause.",
        )
        if unwrap_entry:
          guard_freezes.append(unwrap_entry)
      elif clause.condition:
        cond_t = self.visit(clause.condition)
        if cond_t != PrimitiveType("bool"):
          self.error(f"Guard condition must be of type 'bool', got '{cond_t}'.")

    post_clause_symbols = dict(outer_scope.symbols)

    # Temporarily release freezes and hide newly bound guard vars while checking
    # `else`.
    if guard_freezes:
      for _, freeze_entry in guard_freezes:
        if freeze_entry in outer_scope.frozen_lvalues:
          outer_scope.frozen_lvalues.remove(freeze_entry)

    pre_else_moved = set(self.moved_symbols)
    pre_else_uninit = set(self.uninitialized_symbols)
    pre_else_init_fields = set(self.initialized_fields)
    outer_scope.symbols = pre_clause_symbols
    try:
      self.symbol_table.enter_scope()
      try:
        self.visit(node.else_block)
      finally:
        self.symbol_table.exit_scope()
    finally:
      outer_scope.symbols = post_clause_symbols

    if self._block_terminates(node.else_block):
      self._restore_moved_symbols(pre_else_moved)
      self.uninitialized_symbols = pre_else_uninit
      self.initialized_fields = pre_else_init_fields
    else:
      self.error(
        "Guard else block must terminate control flow (via return, break, or "
        "continue)."
      )

    if guard_freezes:
      for _, freeze_entry in guard_freezes:
        outer_scope.frozen_lvalues.append(freeze_entry)
      pending = getattr(self, "_pending_guard_unwrap_freezes", None)
      if pending is not None:
        pending.extend(guard_freezes)

    return PrimitiveType("none")
