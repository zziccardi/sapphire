"""Statement and control-flow AST visitor methods for TypeChecker."""

from typing import Any, Dict, List, Optional, Set

from src.parser.ast import *
from src.semantics.symbol_table import (
    SymbolTable,
    Type,
    PrimitiveType,
    StringType,
    OptionalType,
    FunctionType,
    MultiReturnType,
    StructMethod,
    StructType,
    TraitType,
    EnumType,
    NoneType,
    InferredType,
    ArrayType,
    MapType,
    ArenaType,
    RangeType,
    ModuleType,
    GenericTypeParameter,
    VariableSymbol,
    FunctionSymbol,
    EnumSymbol,
    ModuleSymbol,
    CoroutineType,
    RefType,
    SharedRefType,
    WeakRefType,
    COROUTINE_METHODS,
    STRING_METHODS,
)
from src.cli.diagnostics import format_diagnostic
from src.common.errors import SemanticError
from src.semantics.arena_checker import ArenaChecker
from src.semantics.collection_checker import CollectionChecker
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.generics_checker import GenericsChecker
from src.semantics.semantic_context import SemanticContext
from src.semantics.struct_layout_pass import StructLayoutPass


class StmtVisitorMixin:
  """Provides AST visitor methods for statements and control flow."""

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if hasattr(node, "annotations") and node.annotations:
      DeclarationPass.validate_annotations(self, node.annotations, node=node)
    if any(a.name == "extern" for a in node.annotations):
      return

    # 1. Namespace validation
    for name in node.names:
      existing = self.symbol_table.lookup_current_scope(name)
      if existing and not getattr(existing, "_from_declare_globals", False):
        self.error(f"Identifier '{name}' is already defined in this scope.")
        return

    # 2. Evaluate expressions and resolve RHS types
    if not node.exprs:
      for name, val_type_node in zip(node.names, node.val_types):
        if not val_type_node:
          self.error(f"Variable '{name}' requires an explicit type annotation or an initial value.", node=node)
          v_type = PrimitiveType("none")
        else:
          v_type = self._resolve_type_node(val_type_node)
        sym = VariableSymbol(name, v_type, node.is_mutable)
        self.symbol_table.define(name, sym)
      return

    # Check compile-time constant expressions for module-level variables
    if self.current_function is None:
      from src.semantics.const_eval import is_constant_expression
      for i, name in enumerate(node.names):
        expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
        is_const, err_reason = is_constant_expression(expr_node, self.symbol_table)
        if not is_const:
          self.error(
              f"Module-level variable '{name}' must be initialized with a "
              f"compile-time constant expression. {err_reason}",
              node=node,
          )

    # Set expected_type for type inference (e.g. lambdas)
    old_expected = self.expected_type
    if len(node.names) == 1 and node.val_types[0]:
      self.expected_type = self._resolve_type_node(node.val_types[0])

    rhs_types: List[Type] = []
    if len(node.exprs) == 1:
      single_type = self.visit(node.exprs[0])
      if isinstance(single_type, MultiReturnType):
        rhs_types = single_type.types
      else:
        rhs_types = [single_type]
    else:
      rhs_types = [self.visit(e) for e in node.exprs]

    self.expected_type = old_expected

    if len(rhs_types) != len(node.names):
      self.error(f"Cannot unpack {len(rhs_types)} value(s) into {len(node.names)} variable(s).", node=node)
      return

    for i, (name, val_type_node, expr_type) in enumerate(zip(node.names, node.val_types, rhs_types)):
      if val_type_node:
        val_type = self._resolve_type_node(val_type_node)
        if not expr_type.is_compatible(val_type):
          self.error(f"Cannot assign expression of type '{expr_type}' to variable '{name}' of type '{val_type}'.", node=node)
        var_type = val_type
        if isinstance(var_type, ArrayType) and isinstance(expr_type, ArrayType) and expr_type.size is not None and var_type.size is None:
          var_type = ArrayType(var_type.element_type, size=expr_type.size, is_fixed_size=False)
      else:
        if isinstance(expr_type, NoneType):
          self.error(f"Cannot infer type of '{name}' from 'none' alone. Specify an optional type annotation.", node=node)
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

  def visit_AssignmentNode(self, node: AssignmentNode) -> None:
    target_types = [self._check_lvalue(t) for t in node.targets]

    rhs_types: List[Type] = []
    if len(node.exprs) == 1:
      single_type = self.visit(node.exprs[0])
      if isinstance(single_type, MultiReturnType):
        rhs_types = single_type.types
      else:
        rhs_types = [single_type]
    else:
      rhs_types = [self.visit(e) for e in node.exprs]

    if len(rhs_types) != len(target_types):
      self.error(f"Cannot assign {len(rhs_types)} value(s) to {len(target_types)} target(s).", node=node)
      return

    for i, (target, target_type, expr_type) in enumerate(zip(node.targets, target_types, rhs_types)):
      if not expr_type.is_compatible(target_type):
        self.error(f"Cannot assign type '{expr_type}' to target of type '{target_type}'.", node=node)

      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      self._check_value_ownership_transfer(expr_node, expr_type, node=node)
      if isinstance(target, IdentifierNode):
        target_sym = self._get_target_symbol(target)
        if target_sym:
          if isinstance(expr_node, CloneNode):
            src_id = ArenaChecker.get_root_identifier(expr_node.expr)
            if src_id:
              src_sym = self.symbol_table.lookup(src_id.name)
              if isinstance(src_sym, VariableSymbol):
                target_sym.proto_ancestors = (
                    {src_sym.name} | set(src_sym.proto_ancestors)
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
                f"initial '__init__' assignment.",
                node=node,
            )
          elif target.member in self._init_assigned_arena_fields:
            self.error(
                f"Cannot reassign Arena field 'self.{target.member}' inside "
                f"'__init__' after initial assignment.",
                node=node,
            )
          elif target.member in self._init_used_arena_fields:
            self.error(
                f"Cannot assign Arena field 'self.{target.member}' after "
                f"allocating into it.",
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
        if isinstance(target.receiver, IdentifierNode) and target.receiver.name == "self":
          self.initialized_fields.add(target.member)

      if isinstance(target, IdentifierNode):
        target_sym = self.symbol_table.lookup(target.name)
        if isinstance(target_sym, VariableSymbol):
          target_sym.is_moved = False
          self.moved_symbols.discard(target_sym)

  def _check_lvalue(self, node: ASTNode) -> Type:
    """Helper to check if AST node is a mutable lvalue and returns its resolved type."""
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
        )

    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if not sym:
        self.error(f"Undefined identifier '{node.name}'.", node=node)
        return PrimitiveType("none")
      if not isinstance(sym, VariableSymbol):
        self.error(f"Identifier '{node.name}' is not a mutable variable.", node=node)
        return sym.symbol_type
      if not sym.is_mutable and sym.name != "self":
        self.error(f"Cannot assign to constant variable '{node.name}'.", node=node)
      return sym.symbol_type

    if isinstance(node, MemberAccessNode):
      if isinstance(node.receiver, MoveNode):
        self.error(f"Cannot access member '{node.member}' on moved variable '{node.receiver.name}'.", node=node)
        return PrimitiveType("none")

      receiver_type = self.visit(node.receiver)
      # Unwrap optional if chained
      if node.is_optional and isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type

      if isinstance(receiver_type, RefType):
        receiver_type = receiver_type.inner_type

      if not isinstance(receiver_type, StructType):
        self.error("Property access target is not a struct.", node=node)
        return PrimitiveType("none")

      # Field access
      field = receiver_type.fields.get(node.member)
      if not field:
        self.error(f"Struct '{receiver_type.name}' has no field '{node.member}'.", node=node)
        return PrimitiveType("none")

      # Encapsulation check for invariant-enforcing structs (with __init__)
      if getattr(receiver_type, "is_imported", False) and "__init__" in receiver_type.methods:
        is_same_module = False
        if getattr(receiver_type, "defining_module", None) and self.source_file_path:
          import os
          if os.path.abspath(receiver_type.defining_module) == os.path.abspath(self.source_file_path):
            is_same_module = True
        if not is_same_module:
          self.error(
              f"Cannot mutate field '{node.member}' of encapsulated struct '{receiver_type.name}' outside its defining module; mutate via methods instead.",
              node=node,
          )
          return field.field_type

      # Check field mutability or constructor exemption
      # Inside __init__ or clone blocks, self fields are always assignable (even if immutable let fields)
      is_self = isinstance(node.receiver, IdentifierNode) and node.receiver.name == "self"
      if not field.is_mutable:
        if not ((self.is_in_init or self.is_in_clone_init) and is_self):
          self.error(f"Cannot assign to constant field '{node.member}' of '{receiver_type.name}'.", node=node)

      # Verify self mutability
      if is_self:
        self_sym = self.symbol_table.lookup("self")
        if self_sym and not self_sym.is_mutable:
          self.error(
              f"Cannot mutate field '{node.member}' within an immutable method. "
              f"Declare the method with 'var func' to allow mutation of 'self'.",
              node=node,
          )

      # Verify root receiver binding mutability (let vs var)
      curr = node.receiver
      while isinstance(curr, MemberAccessNode):
        curr = curr.receiver
      if isinstance(curr, IdentifierNode) and curr.name != "self":
        root_sym = self.symbol_table.lookup(curr.name)
        if isinstance(root_sym, VariableSymbol) and not root_sym.is_mutable:
          kind = (
              "Ref "
              if isinstance(root_sym.symbol_type, RefType)
              else "struct "
          )
          self.error(
              f"Cannot mutate field '{node.member}' of constant {kind}"
              f"variable '{curr.name}'.",
              node=node,
          )

      return field.field_type

    if isinstance(node, IndexExprNode):
      array_type = self.visit(node.array)
      if isinstance(array_type, RefType):
        array_type = array_type.inner_type
      if not isinstance(array_type, ArrayType):
        self.error("Cannot index non-array type.", node=node)
        return PrimitiveType("none")

      # Enforce that array target is a mutable variable
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

      self._check_array_bounds(node, array_type)

      return array_type.element_type

    self.error("Invalid assignment target (not an lvalue).", node=node)
    return PrimitiveType("none")

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    if not self.current_function:
      self.error("Return statement outside function context.", node=node)
      return

    expected_ret_types = self.current_function.return_types
    if expected_ret_types and any(isinstance(t, CoroutineType) for t in expected_ret_types):
      if node.expressions:
        self.error("Cannot return a value from a coroutine; use 'yield' or bare 'return;'.", node=node)
      return

    actual_ret_types = []
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
        self.error(f"Function with no return type cannot return {len(actual_ret_types)} values.", node=node)
      else:
        self.error(f"Function expected {len(expected_ret_types)} return value(s), but return statement provided {len(actual_ret_types)} value(s).", node=node)
      return

    for idx, (act, exp) in enumerate(zip(actual_ret_types, expected_ret_types)):
      if not act.is_compatible(exp):
        self.error(f"Cannot return value of type '{act}' for return value #{idx + 1} (expected '{exp}').")
      ret_expr_node = (
          node.expressions[0] if len(node.expressions) == 1 else node.expressions[idx]
      )
      self._check_return_ownership_transfer(ret_expr_node, act, node=node)

    # Check return escaping arena reference and stack borrows
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
      self.error("Yield statement outside coroutine or match context.", node=node)
      return

    expected_ret_types = self.current_function.return_types
    coro_type = next((t for t in expected_ret_types if isinstance(t, CoroutineType)), None)
    if not coro_type:
      ret_desc = expected_ret_types[0] if expected_ret_types else "void"
      self.error(f"Cannot yield in a function with return type '{ret_desc}' (expected Coroutine).", node=node)
      return

    node.is_coroutine_yield = True
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
        self.error(f"Cannot yield {len(actual_types)} values in Coroutine<void>; use bare 'yield;'.", node=node)
      elif len(actual_types) == 1:
        act = actual_types[0]
        if not isinstance(act, NoneType) and not (isinstance(act, PrimitiveType) and act.name in ("none", "void")):
          self.error(f"Cannot yield value of type '{act}' in Coroutine<void>; use bare 'yield;'.", node=node)
    else:
      if not actual_types:
        self.error(f"Must yield a value of type '{expected_yield}' in Coroutine<{expected_yield}>.", node=node)
      elif len(actual_types) == 1:
        act = actual_types[0]
        if not act.is_compatible(expected_yield):
          self.error(f"Cannot yield value of type '{act}' in Coroutine<{expected_yield}> (expected '{expected_yield}').", node=node)
      else:
        self.error(f"Cannot yield multiple values in Coroutine<{expected_yield}>.", node=node)

  def visit_MatchExprNode(self, node: MatchExprNode) -> Type:
    subject_type = self.visit(node.subject)
    is_stmt = getattr(node, "is_statement", False)

    seen_enum_variants = set()
    seen_bool_true = False
    seen_bool_false = False
    seen_optional_none = False
    seen_optional_some = False
    has_ellipsis = False
    has_unyielded_block = False

    case_types: List[Type] = []
    pre_match_moved = set(self.moved_symbols)
    union_moved: Set[VariableSymbol] = set(pre_match_moved)

    for case in node.cases:
      self.moved_symbols = set(pre_match_moved)
      if isinstance(case.pattern, EllipsisPatternNode):
        has_ellipsis = True
      elif isinstance(subject_type, EnumType):
        if isinstance(case.pattern, MemberAccessNode):
          pat_type = self.visit(case.pattern)
          if isinstance(pat_type, EnumType) and pat_type.name == subject_type.name:
            seen_enum_variants.add(case.pattern.member)
          else:
            self.error(f"Pattern '{case.pattern}' is not a valid variant of enum '{subject_type.name}'.")
        elif isinstance(case.pattern, IdentifierNode):
          if case.pattern.name in subject_type.variants:
            seen_enum_variants.add(case.pattern.name)
          else:
            sym = self.symbol_table.lookup(case.pattern.name)
            if isinstance(sym, EnumSymbol) and sym.name == subject_type.name:
              pass
            else:
              self.error(f"Undefined identifier '{case.pattern.name}'.")
        else:
          pat_type = self.visit(case.pattern)
          if not (isinstance(pat_type, EnumType) and pat_type.name == subject_type.name):
            self.error(f"Pattern '{case.pattern}' is not a valid variant of enum '{subject_type.name}'.")
      elif isinstance(subject_type, PrimitiveType) and subject_type.name == "bool":
        pat_type = self.visit(case.pattern)
        if isinstance(case.pattern, LiteralNode) and case.pattern.lit_type == "bool":
          if case.pattern.value is True or case.pattern.value == "true":
            seen_bool_true = True
          elif case.pattern.value is False or case.pattern.value == "false":
            seen_bool_false = True
        else:
          self.error("Bool match pattern must be 'true' or 'false'.")
      elif isinstance(subject_type, OptionalType):
        pat_type = self.visit(case.pattern)
        if isinstance(pat_type, NoneType) or (isinstance(pat_type, PrimitiveType) and pat_type.name == "none"):
          seen_optional_none = True
        elif pat_type.is_compatible(subject_type.base_type) or subject_type.base_type.is_compatible(pat_type):
          seen_optional_some = True
        else:
          self.error(f"Pattern type '{pat_type}' is incompatible with optional inner type '{subject_type.base_type}'.")
      else:
        pat_type = self.visit(case.pattern)  # pragma: no cover
        if not pat_type.is_compatible(subject_type) and not subject_type.is_compatible(pat_type):  # pragma: no cover
          self.error(f"Pattern type '{pat_type}' is incompatible with subject type '{subject_type}'.")  # pragma: no cover
        seen_optional_some = True  # pragma: no cover

      if is_stmt:
        self.visit(case.body)
        case_types.append(NoneType())
      else:
        self._match_stack.append([])
        if isinstance(case.body, BlockNode):
          self.visit(case.body)
          yields = self._match_stack.pop()
          if yields:
            first_yield = yields[0]
            for y in yields[1:]:
              if not y.is_compatible(first_yield):
                self.error(f"Incompatible yield types in match case: '{first_yield}' and '{y}'.")
            case_types.append(first_yield)
          else:
            case_types.append(NoneType())
            has_unyielded_block = True
        else:
          self._match_stack.pop()
          expr_type = self.visit(case.body)
          self._check_value_ownership_transfer(case.body, expr_type, node=case.body)
          case_types.append(expr_type)
      union_moved |= self.moved_symbols

    if node.cases:
      self.moved_symbols = union_moved

    if not has_ellipsis:
      if isinstance(subject_type, EnumType):
        all_variants = set(subject_type.variants.keys())
        missing = all_variants - seen_enum_variants
        if missing:
          self.error(f"Match expression for enum '{subject_type.name}' is not exhaustive. Missing case: '{next(iter(missing))}'.")
      elif isinstance(subject_type, PrimitiveType) and subject_type.name == "bool":
        if not (seen_bool_true and seen_bool_false):
          self.error("Match expression for bool is not exhaustive.")
      elif isinstance(subject_type, OptionalType):
        if not (seen_optional_none and (seen_optional_some or has_ellipsis)):
          self.error(f"Match expression for optional '{subject_type}' is not exhaustive.")

    if is_stmt:
      return PrimitiveType("none")

    non_none_types = [
        t for t in case_types
        if not (isinstance(t, NoneType) or (isinstance(t, PrimitiveType) and t.name == "none"))
    ]
    if not non_none_types:
      return PrimitiveType("none")

    if has_unyielded_block:
      self.error("Match case block in value-producing match expression must explicitly yield a value.")

    first_type = non_none_types[0]
    for t in non_none_types[1:]:
      if not t.is_compatible(first_type) and not first_type.is_compatible(t):
        self.error(f"Incompatible return types in match branches: '{first_type}' and '{t}'.")

    has_none = any(
        isinstance(t, NoneType) or (isinstance(t, PrimitiveType) and t.name == "none")
        for t in case_types
    )
    if has_none or len(non_none_types) < len(case_types):
      return OptionalType(first_type)
    return first_type

  def visit_IfNode(self, node: IfNode) -> None:
    if node.bindings:
      self.symbol_table.enter_scope()
      has_unwrap = False
      for binding in node.bindings:
        expr_type = self.visit(binding.expr)
        is_borrowed_unwrap = False
        if binding.is_unwrap:
          has_unwrap = True
          if not isinstance(expr_type, OptionalType):
            self.error("Expression in optional unwrapping must resolve to an optional type.", node=binding.expr)
            unwrapped_type = expr_type
          else:
            unwrapped_type = expr_type.base_type
          if isinstance(binding.expr, (IdentifierNode, MemberAccessNode, IndexExprNode)) and not isinstance(binding.expr, MoveNode):
            is_borrowed_unwrap = True
        else:
          unwrapped_type = expr_type
          self._check_value_ownership_transfer(binding.expr, expr_type, node=binding.expr)

        let_names = getattr(binding, "let_names", [binding.let_name])
        self.node_types[binding] = unwrapped_type
        if len(let_names) > 1:
          elem_t = unwrapped_type.element_type if isinstance(unwrapped_type, ArrayType) else unwrapped_type
          for name in let_names:
            sym = VariableSymbol(name, elem_t, is_mutable=binding.is_mutable)
            sym.is_borrowed_unwrap = is_borrowed_unwrap
            sym.ast_decl = binding
            self.symbol_table.define(name, sym)
            ArenaChecker.validate_arena_escape(
                self.symbol_table,
                sym,
                binding.expr,
                lambda msg: self.error(msg, node=node),
                checker=self,
            )
        else:
          sym = VariableSymbol(binding.let_name, unwrapped_type, is_mutable=binding.is_mutable)
          sym.is_borrowed_unwrap = is_borrowed_unwrap
          sym.ast_decl = binding
          self.symbol_table.define(binding.let_name, sym)
          ArenaChecker.validate_arena_escape(
              self.symbol_table,
              sym,
              binding.expr,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )

        if binding.is_unwrap and binding.is_mutable:
          b_res = ArenaChecker.get_lvalue_path(self.symbol_table, binding.expr)
          if b_res:
            self.symbol_table.current_scope.frozen_lvalues.append(
                (b_res[0], b_res[1], "active 'if var' unwrap")
            )

      if node.condition:
        cond_type = self.visit(node.condition)
        if cond_type != PrimitiveType("bool"):
          c_node = node.condition if (hasattr(node.condition, "start_line") and isinstance(node.condition.start_line, int)) else None
          self.error("If condition must resolve to 'bool'.", node=c_node)
      else:
        if not has_unwrap:
          self.error("Init-statement in 'if' must be followed by a condition unless using optional unwrapping '?='.")

      pre_branch_moved = set(self.moved_symbols)
      self._branch_depth += 1
      try:
        self.visit(node.then_block)
        then_moved = set(self.moved_symbols)

        if node.else_block:
          saved_frozen = list(self.symbol_table.current_scope.frozen_lvalues)
          self.symbol_table.current_scope.frozen_lvalues = [
              f for f in saved_frozen if f[2] != "active 'if var' unwrap"
          ]
          self.moved_symbols = set(pre_branch_moved)
          self.visit(node.else_block)
          else_moved = set(self.moved_symbols)
          self.moved_symbols = then_moved | else_moved
          self.symbol_table.current_scope.frozen_lvalues = saved_frozen
        else:
          self.moved_symbols = then_moved
      finally:
        self._branch_depth -= 1

      self.symbol_table.exit_scope()
    else:
      cond_type = self.visit(node.condition)
      if cond_type != PrimitiveType("bool"):
        c_node = node.condition if (hasattr(node.condition, "start_line") and isinstance(node.condition.start_line, int)) else None
        self.error("If condition must resolve to 'bool'.", node=c_node)

      pre_branch_moved = set(self.moved_symbols)
      self._branch_depth += 1
      try:
        self.visit(node.then_block)
        then_moved = set(self.moved_symbols)

        if node.else_block:
          saved_frozen = list(self.symbol_table.current_scope.frozen_lvalues)
          self.symbol_table.current_scope.frozen_lvalues = [
              f for f in saved_frozen if f[2] != "active 'if var' unwrap"
          ]
          self.moved_symbols = set(pre_branch_moved)
          self.visit(node.else_block)
          else_moved = set(self.moved_symbols)
          self.moved_symbols = then_moved | else_moved
          self.symbol_table.current_scope.frozen_lvalues = saved_frozen
        else:
          self.moved_symbols = then_moved
      finally:
        self._branch_depth -= 1

  def visit_WhileNode(self, node: WhileNode) -> None:
    self.loop_depth += 1
    self._branch_depth += 1
    pre_loop_moved = set(self.moved_symbols)
    try:
      cond_type = self.visit(node.condition)
      if cond_type != PrimitiveType("bool"):
        self.error("While condition must resolve to 'bool'.")
      self.visit(node.block)

      for sym in self.moved_symbols - pre_loop_moved:
        self.error(
            f"Cannot move variable '{sym.name}' inside a loop without re-assigning it before the next iteration.",
            node=node,
        )
    finally:
      self._branch_depth -= 1
      self.loop_depth -= 1

  def visit_ForNode(self, node: ForNode) -> None:
    self.loop_depth += 1
    self._branch_depth += 1
    pre_loop_moved = set(self.moved_symbols)
    try:
      iter_type = self.visit(node.iterable)
      self.symbol_table.enter_scope()
      iter_res = ArenaChecker.get_lvalue_path(self.symbol_table, node.iterable)
      if iter_res:
        self.symbol_table.current_scope.frozen_lvalues.append(
            (iter_res[0], iter_res[1], "for-in loop iteration")
        )

      if isinstance(iter_type, ArrayType):
        if node.key_var is not None:
          self.error("Cannot iterate over an array with key-value syntax; use a single loop variable.")
        elem_type = iter_type.element_type
        self.node_types[node] = elem_type
        val_sym = VariableSymbol(node.val_var, elem_type, node.is_mutable)
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
          self.error("Cannot iterate over a range with key-value syntax; use a single loop variable.")
        self.node_types[node] = PrimitiveType("int")
        self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, PrimitiveType("int"), node.is_mutable))
      elif isinstance(iter_type, MapType):
        self.node_types[node] = iter_type.value_type
        if node.key_var is None:
          self.error("Map iteration requires key and value loop variables: 'for key, val in map'.")
          val_sym = VariableSymbol(node.val_var, iter_type.value_type, node.is_mutable)
          self.symbol_table.define(node.val_var, val_sym)
          ArenaChecker.validate_arena_escape(
              self.symbol_table,
              val_sym,
              node.iterable,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )
        else:
          key_sym = VariableSymbol(node.key_var, iter_type.key_type, node.is_mutable)
          val_sym = VariableSymbol(node.val_var, iter_type.value_type, node.is_mutable)
          self.symbol_table.define(node.key_var, key_sym)
          self.symbol_table.define(node.val_var, val_sym)
          ArenaChecker.validate_arena_escape(
              self.symbol_table,
              key_sym,
              node.iterable,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )
          ArenaChecker.validate_arena_escape(
              self.symbol_table,
              val_sym,
              node.iterable,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )
      else:
        self.error("For-in loop source must be an array, map, or range type.")
        self.node_types[node] = PrimitiveType("none")
        if node.key_var is not None:
          self.symbol_table.define(node.key_var, VariableSymbol(node.key_var, PrimitiveType("none"), node.is_mutable))
        self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, PrimitiveType("none"), node.is_mutable))

      self.visit(node.block)
      self.symbol_table.exit_scope()

      for sym in self.moved_symbols - pre_loop_moved:
        self.error(
            f"Cannot move variable '{sym.name}' inside a loop without re-assigning it before the next iteration.",
            node=node,
        )
    finally:
      self._branch_depth -= 1
      self.loop_depth -= 1

  def visit_BreakNode(self, node: BreakNode) -> None:
    if self.loop_depth <= 0:
      self.error("'break' statement outside of loop.")

  def visit_ContinueNode(self, node: ContinueNode) -> None:
    if self.loop_depth <= 0:
      self.error("'continue' statement outside of loop.")

  # ==========================================
  # Expressions Visitor
  # ==========================================

  def _statement_terminates(self, stmt: ASTNode) -> bool:
    if isinstance(stmt, (ReturnNode, BreakNode, ContinueNode)):
      return True
    if isinstance(stmt, IfNode):
      if stmt.then_block and stmt.else_block:
        then_term = self._block_terminates(stmt.then_block)
        else_term = self._statement_terminates(stmt.else_block) if isinstance(stmt.else_block, ASTNode) else self._block_terminates(stmt.else_block)
        return then_term and else_term
    if isinstance(stmt, BlockNode):
      return self._block_terminates(stmt)
    return False

  def _block_terminates(self, block: BlockNode) -> bool:
    for stmt in getattr(block, "statements", []):
      if self._statement_terminates(stmt):
        return True
    return False

  def visit_GuardStmtNode(self, node: GuardStmtNode) -> Type:
    for clause in node.clauses:
      if clause.binding:
        binding = clause.binding
        expr_t = self.visit(binding.expr)
        is_borrowed_unwrap = False
        if binding.is_unwrap:
          if not isinstance(expr_t, OptionalType):
            self.error(f"Cannot unwrap non-optional type '{expr_t}' in guard clause.")
            base_t = expr_t
          else:
            base_t = expr_t.base_type
          if isinstance(binding.expr, (IdentifierNode, MemberAccessNode, IndexExprNode)) and not isinstance(binding.expr, MoveNode):
            is_borrowed_unwrap = True
        else:
          base_t = expr_t
          self._check_value_ownership_transfer(binding.expr, expr_t, node=binding.expr)

        let_names = getattr(binding, "let_names", [binding.let_name])
        self.node_types[binding] = base_t
        if len(let_names) > 1:
          elem_t = base_t.element_type if isinstance(base_t, ArrayType) else base_t
          for name in let_names:
            sym = VariableSymbol(name, elem_t, is_mutable=binding.is_mutable)
            sym.is_borrowed_unwrap = is_borrowed_unwrap
            sym.ast_decl = binding
            self.symbol_table.define(name, sym)
            ArenaChecker.validate_arena_escape(
                self.symbol_table,
                sym,
                binding.expr,
                lambda msg: self.error(msg, node=node),
                checker=self,
            )
        else:
          name = binding.let_name
          sym = VariableSymbol(name, base_t, is_mutable=binding.is_mutable)
          sym.is_borrowed_unwrap = is_borrowed_unwrap
          sym.ast_decl = binding
          self.symbol_table.define(name, sym)
          ArenaChecker.validate_arena_escape(
              self.symbol_table,
              sym,
              binding.expr,
              lambda msg: self.error(msg, node=node),
              checker=self,
          )

        if binding.is_unwrap and binding.is_mutable:
          b_res = ArenaChecker.get_lvalue_path(self.symbol_table, binding.expr)
          if b_res:
            self.symbol_table.current_scope.frozen_lvalues.append(
                (b_res[0], b_res[1], "active 'guard var' unwrap")
            )
      elif clause.condition:
        cond_t = self.visit(clause.condition)
        if cond_t != PrimitiveType("bool"):
          self.error(f"Guard condition must be of type 'bool', got '{cond_t}'.")

    self.symbol_table.enter_scope()
    self.visit(node.else_block)
    self.symbol_table.exit_scope()

    if not self._block_terminates(node.else_block):
      self.error("Guard else block must terminate control flow (via return, break, or continue).")

    return PrimitiveType("none")

