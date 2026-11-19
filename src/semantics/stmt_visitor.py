"""Statement AST visitor methods for TypeChecker."""

import os
from typing import Any, List, Optional

from src.parser.ast import (
    ASTNode,
    AssignmentNode,
    CloneNode,
    ExprStmtNode,
    IdentifierNode,
    IndexExprNode,
    MemberAccessNode,
    MoveNode,
    ReturnNode,
    VarDeclNode,
    YieldNode,
)
from src.semantics.arena_checker import ArenaChecker
from src.semantics.control_flow_visitor import ControlFlowVisitorMixin
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.symbol_table import (
    ArenaType,
    ArrayType,
    CoroutineType,
    MapType,
    MultiReturnType,
    NoneType,
    OptionalType,
    PrimitiveType,
    RefType,
    StructType,
    Type,
    VariableSymbol,
)


class StmtVisitorMixin(ControlFlowVisitorMixin):
  """Provides AST visitor methods for declarations, assignments, returns, and control flow."""

  def _define_uninitialized_vars(self, node: VarDeclNode) -> None:
    """Defines uninitialized variable declarations with explicit type annotations."""
    for name, val_type_node in zip(node.names, node.val_types):
      if not val_type_node:
        self.error(
            f"Variable '{name}' requires an explicit type annotation or an initial value.",
            node=node,
        )
        v_type: Type = PrimitiveType("none")
      else:
        v_type = self._resolve_type_node(val_type_node)
      sym = VariableSymbol(name, v_type, node.is_mutable)
      self.symbol_table.define(name, sym)

  def _check_module_level_const_init(self, node: VarDeclNode) -> None:
    """Enforces compile-time constant initializers for module-level bindings."""
    from src.semantics.const_eval import is_constant_expression

    for i, name in enumerate(node.names):
      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      is_const, err_reason = is_constant_expression(
          expr_node, self.symbol_table
      )
      if not is_const:
        self.error(
            f"Module-level variable '{name}' must be initialized with a "
            f"compile-time constant expression. {err_reason}",
            node=node,
        )

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    """Type-checks `let` and `var` declarations (including multi-value unpacking)."""
    if hasattr(node, "annotations") and node.annotations:
      DeclarationPass.validate_annotations(self, node.annotations, node=node)
    if any(a.name == "extern" for a in node.annotations):
      return

    for name in node.names:
      existing = self.symbol_table.lookup_current_scope(name)
      if existing and not getattr(existing, "_from_declare_globals", False):
        self.error(f"Identifier '{name}' is already defined in this scope.")
        return

    if not node.exprs:
      self._define_uninitialized_vars(node)
      return

    if self.current_function is None:
      self._check_module_level_const_init(node)

    # Propagate expected_type for single-variable lambda/literal inference.
    old_expected = self.expected_type
    if len(node.names) == 1 and node.val_types[0]:
      self.expected_type = self._resolve_type_node(node.val_types[0])

    if len(node.exprs) == 1:
      single_type = self.visit(node.exprs[0])
      rhs_types = (
          single_type.types
          if isinstance(single_type, MultiReturnType)
          else [single_type]
      )
    else:
      rhs_types = [self.visit(e) for e in node.exprs]

    self.expected_type = old_expected

    if len(rhs_types) != len(node.names):
      self.error(
          f"Cannot unpack {len(rhs_types)} value(s) into {len(node.names)} variable(s).",
          node=node,
      )
      return

    for i, (name, val_type_node, expr_type) in enumerate(
        zip(node.names, node.val_types, rhs_types)
    ):
      if val_type_node:
        val_type = self._resolve_type_node(val_type_node)
        if not expr_type.is_compatible(val_type):
          self.error(
              f"Cannot assign expression of type '{expr_type}' to variable '{name}' of type '{val_type}'.",
              node=node,
          )
        var_type = val_type
        if (
            isinstance(var_type, ArrayType)
            and isinstance(expr_type, ArrayType)
            and expr_type.size is not None
            and var_type.size is None
        ):
          var_type = ArrayType(
              var_type.element_type, size=expr_type.size, is_fixed_size=False
          )
      else:
        if isinstance(expr_type, NoneType):
          self.error(
              f"Cannot infer type of '{name}' from 'none' alone. Specify an optional type annotation.",
              node=node,
          )
          var_type = OptionalType(PrimitiveType("none"))
        else:
          var_type = expr_type

      sym = VariableSymbol(name, var_type, node.is_mutable)
      if self.current_function is None and not node.is_mutable:
        sym.is_constant_expr = True
      self.symbol_table.define(name, sym)

      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      if isinstance(expr_node, CloneNode):
        src_id = ArenaChecker.get_root_identifier(expr_node.expr)
        if src_id:
          src_sym = self.symbol_table.lookup(src_id.name)
          if isinstance(src_sym, VariableSymbol):
            sym.proto_ancestors.add(src_sym.name)
            sym.proto_ancestors.update(src_sym.proto_ancestors)
      self._check_value_ownership_transfer(expr_node, expr_type, node=node)
      ArenaChecker.validate_arena_escape(
          self.symbol_table,
          sym,
          expr_node,
          lambda msg: self.error(msg, node=node),
          checker=self,
      )
      ArenaChecker.validate_stack_borrow_escape(
          self.symbol_table,
          sym,
          expr_node,
          lambda msg: self.error(msg, node=node),
          checker=self,
      )

  def _update_assignment_target(
      self,
      target: ASTNode,
      target_type: Type,
      expr_node: ASTNode,
      node: AssignmentNode,
  ) -> None:
    """Updates prototype ancestry, arena escape/generation, and container mutation state."""
    if isinstance(target, IdentifierNode):
      target_sym = self._get_target_symbol(target)
      if target_sym:
        if isinstance(expr_node, CloneNode):
          src_id = ArenaChecker.get_root_identifier(expr_node.expr)
          if src_id:
            src_sym = self.symbol_table.lookup(src_id.name)
            if isinstance(src_sym, VariableSymbol):
              target_sym.proto_ancestors = {src_sym.name} | set(
                  src_sym.proto_ancestors
              )
        else:
          target_sym.proto_ancestors.clear()
        ArenaChecker.validate_arena_escape(
            self.symbol_table,
            target_sym,
            expr_node,
            lambda msg: self.error(msg, node=node),
            checker=self,
        )
        ArenaChecker.validate_stack_borrow_escape(
            self.symbol_table,
            target_sym,
            expr_node,
            lambda msg: self.error(msg, node=node),
            checker=self,
        )
        # Reassigning an Arena bumps its generation, invalidating prior local deps.
        if isinstance(target_sym.symbol_type, ArenaType):
          target_sym.arena_generation += 1
          target_sym.is_moved = False
    elif isinstance(target, MemberAccessNode):
      if isinstance(target_type, ArenaType):
        is_self_target = (
            isinstance(target.receiver, IdentifierNode)
            and target.receiver.name == "self"
        )
        recv_struct = self.node_types.get(target.receiver)
        field_obj = (
            recv_struct.fields.get(target.member)
            if isinstance(recv_struct, StructType)
            else None
        )
        has_default = bool(field_obj and field_obj.has_explicit_default)
        if not (self.is_in_init and is_self_target) or has_default:
          self.error(
              f"Cannot reassign Arena field '{target.member}' outside "
              "initial '__init__' assignment.",
              node=node,
          )
        elif target.member in self._init_assigned_arena_fields:
          self.error(
              f"Cannot reassign Arena field 'self.{target.member}' inside "
              "'__init__' after initial assignment.",
              node=node,
          )
        elif target.member in self._init_used_arena_fields:
          self.error(
              f"Cannot assign Arena field 'self.{target.member}' after "
              "allocating into it.",
              node=node,
          )
        else:
          self._init_assigned_arena_fields.add(target.member)
      ArenaChecker.validate_container_mutation(
          self, target.receiver, [expr_node], error_node=node
      )
    elif isinstance(target, IndexExprNode):
      ArenaChecker.validate_container_mutation(
          self, target.array, [expr_node], error_node=node
      )

    if self.is_in_init and isinstance(target, MemberAccessNode):
      if (
          isinstance(target.receiver, IdentifierNode)
          and target.receiver.name == "self"
      ):
        self.initialized_fields.add(target.member)

    if isinstance(target, IdentifierNode):
      target_sym = self.symbol_table.lookup(target.name)
      if isinstance(target_sym, VariableSymbol):
        # Re-initializing a previously moved `var` makes it live again.
        target_sym.is_moved = False
        self.moved_symbols.discard(target_sym)

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    """Type-checks single and multi-target assignments."""
    target_types = [self._check_lvalue(t) for t in node.targets]

    if len(node.exprs) == 1:
      single_type = self.visit(node.exprs[0])
      rhs_types = (
          single_type.types
          if isinstance(single_type, MultiReturnType)
          else [single_type]
      )
    else:
      rhs_types = [self.visit(e) for e in node.exprs]

    if len(rhs_types) != len(target_types):
      self.error(
          f"Cannot assign {len(rhs_types)} value(s) to {len(target_types)} target(s).",
          node=node,
      )
      return

    for i, (target, target_type, expr_type) in enumerate(
        zip(node.targets, target_types, rhs_types)
    ):
      if not expr_type.is_compatible(target_type):
        self.error(
            f"Cannot assign type '{expr_type}' to target of type '{target_type}'.",
            node=node,
        )
      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      self._check_value_ownership_transfer(expr_node, expr_type, node=node)
      self._update_assignment_target(target, target_type, expr_node, node)

  def _check_member_lvalue(self, node: MemberAccessNode) -> Type:
    """Validates mutability and encapsulation for a struct field lvalue."""
    if isinstance(node.receiver, MoveNode):
      self.error(
          f"Cannot access member '{node.member}' on moved variable '{node.receiver.name}'.",
          node=node,
      )
      return PrimitiveType("none")

    receiver_type = self.visit(node.receiver)
    if node.is_optional and isinstance(receiver_type, OptionalType):
      receiver_type = receiver_type.base_type
    if isinstance(receiver_type, RefType):
      receiver_type = receiver_type.inner_type

    if not isinstance(receiver_type, StructType):
      self.error("Property access target is not a struct.", node=node)
      return PrimitiveType("none")

    field = receiver_type.fields.get(node.member)
    if not field:
      self.error(
          f"Struct '{receiver_type.name}' has no field '{node.member}'.",
          node=node,
      )
      return PrimitiveType("none")

    # Imported structs with `__init__` enforce encapsulation outside their module.
    if (
        getattr(receiver_type, "is_imported", False)
        and "__init__" in receiver_type.methods
    ):
      is_same_module = False
      if (
          getattr(receiver_type, "defining_module", None)
          and self.source_file_path
      ):
        if os.path.abspath(receiver_type.defining_module) == os.path.abspath(
            self.source_file_path
        ):
          is_same_module = True
      if not is_same_module:
        self.error(
            f"Cannot mutate field '{node.member}' of encapsulated struct '{receiver_type.name}' outside its defining module; mutate via methods instead.",
            node=node,
            code="E_ENCAPSULATED_FIELD_MUTATION",
            hint=(
                "Structs with '__init__' lock fields from external mutation. "
                "Add a 'var func' mutator method or omit '__init__' and use "
                "a plain data struct with a factory function."
            ),
        )
        return field.field_type

    # Inside `__init__` or `clone` blocks, `self` fields are assignable even if `let`.
    is_self = (
        isinstance(node.receiver, IdentifierNode)
        and node.receiver.name == "self"
    )
    if not field.is_mutable:
      if not ((self.is_in_init or self.is_in_clone_init) and is_self):
        self.error(
            f"Cannot assign to constant field '{node.member}' of '{receiver_type.name}'.",
            node=node,
        )

    if is_self:
      self_sym = self.symbol_table.lookup("self")
      if self_sym and not self_sym.is_mutable:
        self.error(
            f"Cannot mutate field '{node.member}' within an immutable method. "
            "Declare the method with 'var func' to allow mutation of 'self'.",
            node=node,
        )

    curr = node.receiver
    while isinstance(curr, MemberAccessNode):
      curr = curr.receiver
    if isinstance(curr, IdentifierNode) and curr.name != "self":
      root_sym = self.symbol_table.lookup(curr.name)
      if isinstance(root_sym, VariableSymbol) and not root_sym.is_mutable:
        kind = (
            "Ref " if isinstance(root_sym.symbol_type, RefType) else "struct "
        )
        self.error(
            f"Cannot mutate field '{node.member}' of constant {kind}"
            f"variable '{curr.name}'.",
            node=node,
        )

    return field.field_type

  def _check_index_lvalue(self, node: IndexExprNode) -> Type:
    """Validates mutability and index types for an Array or Map subscript lvalue."""
    container_type = self.visit(node.array)
    if isinstance(container_type, RefType):
      container_type = container_type.inner_type

    if isinstance(container_type, ArrayType):
      if isinstance(node.array, IdentifierNode):
        sym = self.symbol_table.lookup(node.array.name)
        if sym and not sym.is_mutable:
          kind = "Ref " if isinstance(sym.symbol_type, RefType) else "array "
          self.error(
              f"Cannot assign to index of constant {kind}'{sym.name}'.",
              node=node,
          )
      index_type = self.visit(node.index)
      if index_type != PrimitiveType("int"):
        self.error("Array index must be of type 'int'.", node=node)
      self._check_array_bounds(node, container_type)
      return container_type.element_type

    if isinstance(container_type, MapType):
      if isinstance(node.array, IdentifierNode):
        sym = self.symbol_table.lookup(node.array.name)
        if sym and not sym.is_mutable:
          kind = "Ref " if isinstance(sym.symbol_type, RefType) else "map "
          self.error(
              f"Cannot assign to key of constant {kind}'{sym.name}'.",
              node=node,
          )
      index_type = self.visit(node.index)
      if (
          not index_type.is_compatible(container_type.key_type)
          and not container_type.key_type.is_compatible(index_type)
      ):
        self.error(
            f"Map index type '{index_type}' is not compatible with key type "
            f"'{container_type.key_type}'.",
            node=node.index,
        )
      return container_type.value_type

    self.error("Cannot index non-array type.", node=node)
    return PrimitiveType("none")

  def _check_lvalue(self, node: ASTNode) -> Type:
    """Checks that an AST node is a mutable lvalue and returns its resolved type."""
    if self.has_shared_ref_base(node):
      self.error(
          "Cannot mutate through deeply immutable 'SharedRef'.", node=node
      )
      return PrimitiveType("none")

    res = ArenaChecker.get_lvalue_path(self.symbol_table, node)
    if res:
      root_name, field_path = res
      reason = self.get_frozen_lvalue_reason(root_name, field_path)
      if reason:
        self.error(
            f"Cannot mutate or reassign '{root_name}' while it is frozen "
            f"({reason}).",
            node=node,
            code="E_FROZEN_LVALUE",
            hint=(
                "Capture any needed state before the last use of the "
                "unwrapped/iterated binding, or mutate after the unwrap/loop "
                "block ends."
            ),
        )

    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if not sym:
        self.error(f"Undefined identifier '{node.name}'.", node=node)
        return PrimitiveType("none")
      if not isinstance(sym, VariableSymbol):
        self.error(
            f"Identifier '{node.name}' is not a mutable variable.", node=node
        )
        return sym.symbol_type
      if not sym.is_mutable and sym.name != "self":
        self.error(
            f"Cannot assign to constant variable '{node.name}'.", node=node
        )
      return sym.symbol_type

    if isinstance(node, MemberAccessNode):
      return self._check_member_lvalue(node)

    if isinstance(node, IndexExprNode):
      return self._check_index_lvalue(node)

    self.error("Invalid assignment target (not an lvalue).", node=node)
    return PrimitiveType("none")

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    """Type-checks `return` statements, ownership transfers, and escape rules."""
    if not self.current_function:
      self.error("Return statement outside function context.", node=node)
      return

    expected_ret_types = self.current_function.return_types
    if expected_ret_types and any(
        isinstance(t, CoroutineType) for t in expected_ret_types
    ):
      if node.expressions:
        self.error(
            "Cannot return a value from a coroutine; use 'yield' or bare 'return;'.",
            node=node,
        )
      return

    actual_ret_types: List[Type] = []
    if node.expressions:
      if len(node.expressions) == 1:
        single_type = self.visit(node.expressions[0])
        if isinstance(single_type, MultiReturnType):
          actual_ret_types = single_type.types
        else:
          actual_ret_types = [single_type]
      else:
        actual_ret_types = [self.visit(e) for e in node.expressions]

    if len(actual_ret_types) != len(expected_ret_types):
      if len(expected_ret_types) == 0:
        self.error(
            f"Function with no return type cannot return {len(actual_ret_types)} values.",
            node=node,
        )
      else:
        self.error(
            f"Function expected {len(expected_ret_types)} return value(s), but return statement provided {len(actual_ret_types)} value(s).",
            node=node,
        )
      return

    for idx, (act, exp) in enumerate(zip(actual_ret_types, expected_ret_types)):
      if not act.is_compatible(exp):
        self.error(
            f"Cannot return value of type '{act}' for return value #{idx + 1} (expected '{exp}')."
        )
      ret_expr_node = (
          node.expressions[0]
          if len(node.expressions) == 1
          else node.expressions[idx]
      )
      self._check_return_ownership_transfer(ret_expr_node, act, node=node)

    for ret_expr in node.expressions:
      ArenaChecker.validate_return_escape(
          self.symbol_table,
          self.current_function_scope,
          ret_expr,
          lambda msg, n: self.error(msg, node=n),
          checker=self,
      )
      ArenaChecker.validate_stack_borrow_return_escape(
          self.symbol_table,
          self.current_function_scope,
          ret_expr,
          lambda msg, n: self.error(msg, node=n),
          checker=self,
      )

  def visit_YieldNode(self, node: YieldNode) -> None:
    """Type-checks `yield` inside `match` blocks or `Coroutine<T>` functions."""
    if self._match_stack:
      expr_nodes = getattr(node, "expressions", None) or (
          [node.expr] if getattr(node, "expr", None) else []
      )
      actual_types = [self.visit(e) for e in expr_nodes]
      for e_node, a_type in zip(expr_nodes, actual_types):
        self._check_value_ownership_transfer(e_node, a_type, node=node)

      if len(actual_types) == 1:
        self._match_stack[-1].append(actual_types[0])
      elif len(actual_types) > 1:
        self._match_stack[-1].append(MultiReturnType(actual_types))
      else:
        self._match_stack[-1].append(PrimitiveType("none"))
      return

    if not self.current_function:
      self.error(
          "Yield statement outside coroutine or match context.", node=node
      )
      return

    expected_ret_types = self.current_function.return_types
    coro_type = next(
        (t for t in expected_ret_types if isinstance(t, CoroutineType)), None
    )
    if not coro_type:
      ret_desc = expected_ret_types[0] if expected_ret_types else "void"
      self.error(
          f"Cannot yield in a function with return type '{ret_desc}' (expected Coroutine).",
          node=node,
      )
      return

    node.is_coroutine_yield = True
    # Move-only RAII bindings cannot remain live across a coroutine suspension.
    curr_scope = self.symbol_table.current_scope
    while curr_scope is not None:
      for sym in curr_scope.symbols.values():
        if (
            isinstance(sym, VariableSymbol)
            and not sym.is_moved
            and sym not in self.moved_symbols
        ):
          if sym.symbol_type and sym.symbol_type.is_move_only_type(
              self.symbol_table
          ):
            self.error(
                f"Variable '{sym.name}' of move-only RAII type "
                f"'{sym.symbol_type}' cannot remain live across 'yield'.",
                node=node,
            )
      if curr_scope is self.current_function_scope:
        break
      curr_scope = curr_scope.parent

    expected_yield = coro_type.yield_type
    expr_nodes = getattr(node, "expressions", None) or (
        [node.expr] if getattr(node, "expr", None) else []
    )
    actual_types = [self.visit(e) for e in expr_nodes]
    for e_node, a_type in zip(expr_nodes, actual_types):
      self._check_value_ownership_transfer(e_node, a_type, node=node)

    if isinstance(expected_yield, NoneType):
      if len(actual_types) > 1:
        self.error(
            f"Cannot yield {len(actual_types)} values in Coroutine<void>; use bare 'yield;'.",
            node=node,
        )
      elif len(actual_types) == 1:
        act = actual_types[0]
        if not isinstance(act, NoneType) and not (
            isinstance(act, PrimitiveType) and act.name in ("none", "void")
        ):
          self.error(
              f"Cannot yield value of type '{act}' in Coroutine<void>; use bare 'yield;'.",
              node=node,
          )
    else:
      if not actual_types:
        self.error(
            f"Must yield a value of type '{expected_yield}' in Coroutine<{expected_yield}>.",
            node=node,
        )
      elif len(actual_types) == 1:
        act = actual_types[0]
        if not act.is_compatible(expected_yield):
          self.error(
              f"Cannot yield value of type '{act}' in Coroutine<{expected_yield}> (expected '{expected_yield}').",
              node=node,
          )
      else:
        self.error(
            f"Cannot yield multiple values in Coroutine<{expected_yield}>.",
            node=node,
        )
