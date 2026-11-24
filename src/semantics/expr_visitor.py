"""Expression, literal, and initializer AST visitor methods for TypeChecker."""

from typing import TYPE_CHECKING

from src.parser.ast import (
  ArrayLiteralNode,
  ASTNode,
  BinaryOpNode,
  BlockNode,
  CallNode,
  CastExprNode,
  CloneNode,
  ExprStmtNode,
  IdentifierNode,
  IndexExprNode,
  InterpolatedStringNode,
  LambdaNode,
  LiteralNode,
  MapLiteralNode,
  MemberAccessNode,
  MoveNode,
  ReturnNode,
  StructInitializerNode,
  TernaryExprNode,
  UnaryOpNode,
  VarDeclNode,
)
from src.semantics.arena_checker import ArenaChecker
from src.semantics.symbol_table import (
  ArenaType,
  ArrayType,
  EnumType,
  FunctionSymbol,
  FunctionType,
  InferredType,
  MapType,
  NoneType,
  OptionalType,
  PrimitiveType,
  RefType,
  SharedRefType,
  StringType,
  StructType,
  Type,
  VariableSymbol,
)

if TYPE_CHECKING:
  from src.semantics.type_checker import TypeChecker as _TypeCheckerBase
else:
  _TypeCheckerBase = object


class ExprVisitorMixin(_TypeCheckerBase):
  """Provides AST visitor methods for expressions, literals, and initializers.
  """

  def visit_LiteralNode(self, node: LiteralNode) -> Type:
    if node.lit_type == "int":
      return PrimitiveType("int")
    if node.lit_type == "float":
      return PrimitiveType("float")
    if node.lit_type == "bool":
      return PrimitiveType("bool")
    if node.lit_type == "string":
      return StringType()
    return NoneType()

  def visit_InterpolatedStringNode(self, node: InterpolatedStringNode) -> Type:
    for part in node.parts:
      t = self.visit(part)
      if isinstance(t, StructType):
        self.error(
          f"Cannot interpolate struct type '{t.name}' directly into string."
          " Call a string conversion method explicitly."
        )
    return StringType()

  def visit_IdentifierNode(self, node: IdentifierNode) -> Type:
    sym = self.symbol_table.lookup(node.name)
    if not sym:
      type_sym = self.symbol_table.lookup_type(node.name)
      if type_sym:
        return type_sym
      matching_mods = self._find_imported_modules_with_prefix(node.name)
      if len(matching_mods) == 1:
        mod = matching_mods[0]
        self.error(
          f"Undefined identifier '{node.name}'. Module '{mod.module_path}' "
          f"was imported as '{mod.name}'. Did you mean '{mod.name}'?",
          node=node,
        )
      elif len(matching_mods) > 1:
        names = ", ".join(f"'{m.name}'" for m in matching_mods)
        self.error(
          f"Undefined identifier '{node.name}'. Modules under '{node.name}' "
          f"are imported by their module name directly (e.g. {names}).",
          node=node,
        )
      else:
        self.error(f"Undefined identifier '{node.name}'.", node=node)
      return PrimitiveType("none")
    if isinstance(sym, VariableSymbol):
      if sym in self.uninitialized_symbols:
        self.error(f"Use of uninitialized variable '{node.name}'.", node=node)
      if sym in self.moved_symbols:
        self.error(f"Use of moved variable '{node.name}'.", node=node)
      ArenaChecker.check_use_validity(
        self.symbol_table, sym, lambda msg: self.error(msg, node=node)
      )
    return sym.symbol_type

  def _is_orderable_pair(self, left: Type, right: Type) -> bool:
    """Returns True if *left* and *right* support ordering operators (<, <=, >,
    >=).
    """
    if isinstance(left, InferredType) or isinstance(right, InferredType):
      return True
    if (
      isinstance(left, PrimitiveType)
      and left.name in ("int", "float")
      and isinstance(right, PrimitiveType)
      and right.name in ("int", "float")
    ):
      return True
    if isinstance(left, StringType) and isinstance(right, StringType):
      return True
    if (
      isinstance(left, EnumType)
      and isinstance(right, EnumType)
      and left == right
    ):
      return True
    return False

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> Type:
    left = self.visit(node.left)
    right = self.visit(node.right)

    # Coalescing operator
    if node.op == "??":
      if not isinstance(left, OptionalType):
        self.error(
          f"Left operand of '??' must be an optional type, got '{left}'."
        )
        return left
      base_type = left.base_type
      if isinstance(right, NoneType) or (
        isinstance(right, PrimitiveType) and right.name == "none"
      ):
        return left
      if isinstance(right, OptionalType):
        widened = self._widen_types(base_type, right.base_type)
        if widened is None:
          self.error(
            f"Fallback type '{right}' is not compatible with the optional's "
            f"base type '{base_type}'."
          )
          return left
        return OptionalType(widened)
      if (
        isinstance(base_type, PrimitiveType)
        and base_type.name == "int"
        and isinstance(right, PrimitiveType)
        and right.name == "float"
      ):
        self.error(
          f"Fallback type '{right}' is not compatible with the optional's "
          f"base type '{base_type}'."
        )
        return base_type
      widened = self._widen_types(base_type, right)
      if widened is None:
        self.error(
          f"Fallback type '{right}' is not compatible with the optional's "
          f"base type '{base_type}'."
        )
        return base_type
      return widened

    # Boolean operators
    if node.op in ("&&", "||"):
      if left != PrimitiveType("bool") or right != PrimitiveType("bool"):
        self.error(f"Operator '{node.op}' requires boolean operands.")
      return PrimitiveType("bool")

    # Comparison operators
    if node.op in ("==", "!="):
      # Sapphire allows comparing compatible types
      if not left.is_compatible(right) and not right.is_compatible(left):
        self.error(
          f"Cannot compare type '{left}' with type '{right}' using '{node.op}'."
        )
      return PrimitiveType("bool")

    if node.op in ("<", "<=", ">", ">="):
      if not self._is_orderable_pair(left, right):
        self.error(
          f"Cannot compare type '{left}' with type '{right}' using '{node.op}'."
        )
      return PrimitiveType("bool")

    # Arithmetic operators
    if node.op in ("+", "-", "*", "/", "%"):
      if node.op == "+" and (
        isinstance(left, StringType) or isinstance(right, StringType)
      ):
        node.is_string_concat = True
        return StringType()
      # Supports int and float operations; InferredType is a permitted
      # placeholder during lambda body analysis — treat it as numeric.
      is_numeric_left = (
        isinstance(left, PrimitiveType) and left.name in ("int", "float")
      ) or isinstance(left, InferredType)
      is_numeric_right = (
        isinstance(right, PrimitiveType) and right.name in ("int", "float")
      ) or isinstance(right, InferredType)
      if not (is_numeric_left and is_numeric_right):
        self.error(f"Arithmetic operator '{node.op}' requires numeric types.")
        return PrimitiveType("none")

      # If one side is a concrete float, propagate float; otherwise int.
      left_is_float = isinstance(left, PrimitiveType) and left.name == "float"
      right_is_float = (
        isinstance(right, PrimitiveType) and right.name == "float"
      )
      if left_is_float or right_is_float:
        return PrimitiveType("float")
      return PrimitiveType("int")

    return PrimitiveType("none")

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> Type:
    # Enforce mandatory parentheses on nested ternary expressions
    for branch_node in (node.condition, node.true_expr, node.false_expr):
      if isinstance(branch_node, TernaryExprNode) and not getattr(
        branch_node, "is_parenthesized", False
      ):
        self.error(
          "Nested ternary expressions must be explicitly enclosed in "
          "parentheses."
        )

    old_expected = self.expected_type
    self.expected_type = None
    try:
      cond_type = self.visit(node.condition)
    finally:
      self.expected_type = old_expected
    if cond_type != PrimitiveType("bool"):
      self.error(
        f"Ternary condition must be of type 'bool', got '{cond_type}'."
      )

    pre_branch_moved = set(self.moved_symbols)
    true_type = self.visit(node.true_expr)
    true_moved = set(self.moved_symbols)
    self._restore_moved_symbols(pre_branch_moved)
    false_type = self.visit(node.false_expr)
    false_moved = set(self.moved_symbols)
    self._restore_moved_symbols(true_moved | false_moved)

    widened = self._widen_types(true_type, false_type)
    if widened is not None:
      return widened

    self.error(
      f"Incompatible types in ternary branches: '{true_type}' and "
      f"'{false_type}'."
    )
    return true_type

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> Type:
    expr_type = self.visit(node.expr)
    if node.op in ("-", "+"):
      if isinstance(expr_type, PrimitiveType) and expr_type.name in (
        "int",
        "float",
      ):
        return expr_type
      self.error(
        f"Unary operator '{node.op}' requires a numeric type, got "
        f"'{expr_type}'."
      )
      return expr_type
    elif node.op == "!":
      if isinstance(expr_type, PrimitiveType) and expr_type.name == "bool":
        return expr_type
      self.error(
        f"Unary operator '!' requires a boolean type, got '{expr_type}'."
      )
      return PrimitiveType("bool")
    return PrimitiveType("none")

  def visit_CastExprNode(self, node: CastExprNode) -> Type:
    expr_type = self.visit(node.expr)
    target_type = self._resolve_type_node(node.target_type)

    if expr_type.is_compatible(target_type):
      return target_type

    is_expr_num = isinstance(expr_type, PrimitiveType) and expr_type.name in (
      "int",
      "float",
      "bool",
    )
    is_target_num = isinstance(
      target_type, PrimitiveType
    ) and target_type.name in ("int", "float", "bool")
    if is_expr_num and is_target_num:
      return target_type

    if isinstance(expr_type, EnumType) and (
      isinstance(target_type, StringType)
      or (isinstance(target_type, PrimitiveType) and target_type.name == "int")
    ):
      return target_type

    if isinstance(expr_type, StringType):
      if isinstance(target_type, PrimitiveType) and target_type.name in (
        "int",
        "float",
        "bool",
      ):
        self.error(
          f"Cannot cast 'String' to '{target_type.name}' using 'as'. Use "
          f"'.to_{target_type.name}()' instance method instead."
        )
        return target_type

    if isinstance(expr_type, StructType) and isinstance(
      target_type, StructType
    ):
      self.error(
        f"Cannot cast struct '{expr_type}' to '{target_type}'.",
        node=node,
        code="E_NO_STRUCT_UPCAST",
        hint=(
          "Struct up-casting is prohibited in Sapphire. Define a "
          "behavioral 'trait' implemented by both structs for polymorphism."
        ),
      )
      return target_type

    self.error(f"Cannot cast type '{expr_type}' to '{target_type}'.", node=node)
    return target_type

  def visit_CloneNode(self, node: CloneNode) -> Type:
    expr_type = self.visit(node.expr)
    if not isinstance(expr_type, StructType):
      self.error("Clone expression target must be a struct instance.")
      return PrimitiveType("none")

    # Verify struct is a prototype struct (or inherits from one)
    def check_proto(st: StructType, visited: set[str]) -> bool:
      if st.name in visited:
        return False
      visited.add(st.name)
      if st.is_prototype:
        return True
      for p_name in st.parent_names:
        parent = self.symbol_table.lookup_type(p_name)
        if isinstance(parent, StructType) and check_proto(parent, visited):
          return True
      return False

    is_proto = check_proto(expr_type, set())

    if not is_proto:
      self.error(
        f"Cannot clone instance of non-proto struct '{expr_type.name}'. "
        "Struct must be declared using the 'proto' keyword."
      )

    # Validate explicit arena target
    if node.arena_expr:
      arena_type = self.visit(node.arena_expr)
      if not isinstance(arena_type, ArenaType):
        self.error("Explicit arena target must be an instance of Arena.")
      else:
        ArenaChecker.validate_cross_arena_clone(
          self.symbol_table,
          node,
          lambda msg: self.error(msg, node=node),
          checker=self,
        )
        if (
          self.is_in_init
          and isinstance(node.arena_expr, MemberAccessNode)
          and isinstance(node.arena_expr.receiver, IdentifierNode)
          and node.arena_expr.receiver.name == "self"
        ):
          self._init_used_arena_fields.add(node.arena_expr.member)

    # Mark the struct type as cloned
    expr_type.is_cloned = True

    # If immediate shadow block is defined, check statements
    if node.initializer_block:
      self.symbol_table.enter_scope()
      old_clone_init = self.is_in_clone_init
      self.is_in_clone_init = True
      # Define self inside block as mutable
      clone_self_sym = VariableSymbol("self", expr_type, is_mutable=True)
      clone_self_deps = list(
        ArenaChecker.collect_arena_deps(self.symbol_table, node.expr, self)
      )
      if node.arena_expr:
        resolved_arena = ArenaChecker._resolve_arena_target(
          self.symbol_table, node.arena_expr
        )
        if resolved_arena:
          dep_rec = (resolved_arena[0], resolved_arena[2])
          if dep_rec not in clone_self_deps:
            clone_self_deps.append(dep_rec)
      clone_self_sym.arena_dep_records = clone_self_deps
      clone_self_sym.arena_dependency = (
        clone_self_deps[0][0] if clone_self_deps else None
      )
      self.symbol_table.define("self", clone_self_sym)
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.is_in_clone_init = old_clone_init
      self.symbol_table.exit_scope()

    return expr_type

  def visit_MoveNode(self, node: MoveNode) -> Type:
    sym = self.symbol_table.lookup(node.name)
    if not sym:
      self.error(f"Cannot move undefined variable '{node.name}'.", node=node)
      return PrimitiveType("none")
    if not isinstance(sym, VariableSymbol):
      self.error(f"Cannot move non-variable symbol '{node.name}'.", node=node)
      return sym.symbol_type
    reason = self.get_frozen_lvalue_reason(node.name, [])
    if reason:
      self.error(
        f"Cannot move variable '{node.name}' while it is frozen ({reason}).",
        node=node,
      )
      return sym.symbol_type
    if getattr(sym, "is_parameter", False):
      self.error(
        f"Cannot move out of borrowed parameter '{node.name}'.", node=node
      )
      return sym.symbol_type
    if getattr(sym, "is_borrowed_unwrap", False):
      self.error(
        f"Cannot move out of borrowed unwrap binding '{node.name}'.", node=node
      )
      return sym.symbol_type
    if (
      self.current_function is not None
      and sym.scope_defined is not None
      and sym.scope_defined.parent is None
    ):
      self.error(
        f"Cannot move out of module-level global variable '{node.name}'.",
        node=node,
      )
      return sym.symbol_type
    if (
      isinstance(self.current_function, FunctionSymbol)
      and self.current_function.name == "<lambda>"
      and sym.scope_defined is not None
      and not ArenaChecker.is_descendant_scope(
        sym.scope_defined, self.current_function_scope
      )
    ):
      self.error(
        f"Cannot move captured outer variable '{node.name}' inside a closure.",
        node=node,
      )
      return sym.symbol_type
    if sym in self.uninitialized_symbols:
      self.error(f"Use of uninitialized variable '{node.name}'.", node=node)
      return sym.symbol_type
    if sym in self.moved_symbols:
      self.error(f"Use of moved variable '{node.name}'.", node=node)
      return sym.symbol_type

    sym.is_moved = True
    if isinstance(sym.symbol_type, ArenaType):
      sym.arena_generation += 1
    self.moved_symbols.add(sym)
    return sym.symbol_type

  def _infer_lambda_param_type(
    self, param_name: str, body: "ASTNode"
  ) -> Type | None:
    """Infer the type of a lambda parameter from its usage in *body*.

    Performs a lightweight structural scan of the body AST — not a full
    type-check pass — to determine the most specific type for *param_name*
    based on how it is used.  Returns a ``PrimitiveType`` if a clear
    constraint is found, or ``None`` if the usage is unconstrained.

    This is called only when neither an explicit annotation nor an enclosing
    ``expected_type`` FunctionType is available.
    """
    ARITHMETIC_OPS = {"+", "-", "*", "/", "%"}

    def references_param(node: "ASTNode") -> bool:
      return isinstance(node, IdentifierNode) and node.name == param_name

    def scan(node: "ASTNode") -> Type | None:
      if node is None:
        return None

      if isinstance(node, BinaryOpNode):
        left_is_param = references_param(node.left)
        right_is_param = references_param(node.right)

        if node.op in ARITHMETIC_OPS and (left_is_param or right_is_param):
          # The other operand tells us whether this is float or int.
          other = node.right if left_is_param else node.left
          if isinstance(other, LiteralNode) and other.lit_type == "float":
            return PrimitiveType("float")
          return PrimitiveType("int")

        if node.op in ("==", "!=", "<", "<=", ">", ">=") and (
          left_is_param or right_is_param
        ):
          # Comparison with a numeric literal → param is numeric
          other = node.right if left_is_param else node.left
          if isinstance(other, LiteralNode):
            if other.lit_type == "float":
              return PrimitiveType("float")
            if other.lit_type == "int":
              return PrimitiveType("int")
            if other.lit_type == "string":
              return StringType()
          return None

        if node.op in ("&&", "||") and (left_is_param or right_is_param):
          return PrimitiveType("bool")

        # Recurse into both sides
        return scan(node.left) or scan(node.right)

      if isinstance(node, UnaryOpNode):
        if node.op in ("-", "+") and references_param(node.expr):
          return PrimitiveType("int")
        return scan(node.expr)

      if isinstance(node, BlockNode):
        for stmt in node.statements or []:
          result = scan(stmt)
          if result is not None:
            return result
        return None

      if isinstance(node, ReturnNode):
        return scan(node.expr) if node.expr else None

      if isinstance(node, VarDeclNode):
        for expr in node.exprs or []:
          result = scan(expr)
          if result is not None:
            return result
        return None

      if isinstance(node, ExprStmtNode):
        return scan(node.expr)

      if isinstance(node, CallNode):
        for arg in node.arguments or []:
          result = scan(arg.expr)
          if result is not None:
            return result
        return None

      if isinstance(node, TernaryExprNode):
        return (
          scan(node.condition) or scan(node.true_expr) or scan(node.false_expr)
        )

      return None

    return scan(body)

  def visit_LambdaNode(self, node: LambdaNode) -> Type:
    if self.is_in_del and self._ast_references_self(node.body):
      self.error(
        "Cannot capture 'self' in a closure inside destructor '__del__'.",
        node=node,
      )
    self.symbol_table.enter_scope()
    pre_lambda_moved = set(self.moved_symbols)
    pre_lambda_uninit = set(self.uninitialized_symbols)

    expected_func = self.expected_type
    from src.semantics.symbol_table import OptionalType

    if isinstance(expected_func, OptionalType):
      expected_func = expected_func.base_type

    seen_param_names: set[str] = set()
    param_types = []
    for idx, p in enumerate(node.parameters):
      if p.name in seen_param_names:
        self.error(f"Duplicate parameter name '{p.name}' in lambda.", node=node)
      seen_param_names.add(p.name)
      if p.param_type:
        ptype = self._resolve_type_node(p.param_type)
      elif (
        expected_func
        and isinstance(expected_func, FunctionType)
        and idx < len(expected_func.param_types)
      ):
        ptype = expected_func.param_types[idx]
      else:
        # No annotation and no expected type: infer from usage in the body.
        # Fall back to InferredType (compatible with all ops) when the usage
        # is ambiguous so that no false errors are emitted.
        inferred = self._infer_lambda_param_type(p.name, node.body)
        ptype = inferred if inferred is not None else InferredType()
      self.symbol_table.define(
        p.name,
        VariableSymbol(p.name, ptype, is_mutable=False, is_parameter=True),
      )
      param_types.append(ptype)

    old_func = self.current_function
    old_func_scope = self.current_function_scope
    old_expected = self.expected_type
    declared_ret = (
      self._resolve_type_node(node.return_type) if node.return_type else None
    )
    expected_ret = declared_ret
    if expected_ret is None and isinstance(expected_func, FunctionType):
      cand_ret = expected_func.return_type
      if not isinstance(cand_ret, (InferredType, NoneType)) and not (
        isinstance(cand_ret, PrimitiveType)
        and cand_ret.name in ("none", "void")
      ):
        expected_ret = cand_ret

    lambda_sym = FunctionSymbol("<lambda>", None)
    lambda_sym.return_types = [expected_ret] if expected_ret else []
    self.current_function = lambda_sym
    self.current_function_scope = self.symbol_table.current_scope
    self.expected_type = (
      None if isinstance(node.body, BlockNode) else expected_ret
    )

    try:
      body_type = self.visit(node.body)
    finally:
      self.expected_type = old_expected
      self.current_function = old_func
      self.current_function_scope = old_func_scope

    # Resolve any InferredType placeholders: if the body produced a concrete
    # return type, use it to back-fill params that remained unconstrained.
    resolved_param_types: list[Type] = []
    for p, pt in zip(node.parameters, param_types, strict=False):
      if isinstance(pt, InferredType):
        if not isinstance(body_type, (NoneType, InferredType)) and not (
          isinstance(body_type, PrimitiveType) and body_type.name == "none"
        ):
          resolved_param_types.append(body_type)
        else:
          self.error(
            f"Cannot infer type for lambda parameter '{p.name}'; "
            "add an explicit type annotation.",
            node=node,
          )
          resolved_param_types.append(PrimitiveType("none"))
      else:
        resolved_param_types.append(pt)

    # Lambda expression implicit return
    ret_type = (
      body_type
      if not isinstance(node.body, BlockNode)
      else (expected_ret or PrimitiveType("none"))
    )
    if node.return_type:
      ret_type = self._resolve_type_node(node.return_type)

    self._restore_moved_symbols(pre_lambda_moved)
    self.uninitialized_symbols = pre_lambda_uninit
    self.symbol_table.exit_scope()
    node.stack_borrow_symbols = self._scan_lambda_stack_borrows(node)
    mut_caps, read_caps = self._scan_lambda_capture_modes(node)
    node.closure_mutated_captures = mut_caps
    node.closure_read_captures = read_caps
    return FunctionType(
      resolved_param_types,
      ret_type,
      param_names=[p.name for p in node.parameters],
    )

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> Type:
    expected_arr = (
      self.expected_type if isinstance(self.expected_type, ArrayType) else None
    )
    if not node.elements:
      if expected_arr is not None:
        if expected_arr.is_fixed_size and expected_arr.size != 0:
          self.error(
            f"Fixed-size array '[{expected_arr.element_type}; "
            f"{expected_arr.size}]' requires exactly {expected_arr.size} "
            "element(s), got 0.",
            node=node,
          )
        return ArrayType(
          expected_arr.element_type,
          size=0,
          is_fixed_size=expected_arr.is_fixed_size,
        )
      return ArrayType(NoneType(), size=0)

    old_expected = self.expected_type
    elem_types: list[Type] = []
    try:
      for e in node.elements:
        self.expected_type = (
          expected_arr.element_type if expected_arr is not None else None
        )
        elem_types.append(self.visit(e))
    finally:
      self.expected_type = old_expected

    for elem_node, etype in zip(node.elements, elem_types, strict=False):
      self._check_value_ownership_transfer(elem_node, etype, node=elem_node)
    if expected_arr is not None:
      target_elem = expected_arr.element_type
      for etype in elem_types:
        if not etype.is_compatible(target_elem):
          self.error(
            f"Array element of type '{etype}' is not compatible with expected "
            f"element type '{target_elem}'."
          )
          break
      if expected_arr.is_fixed_size:
        if len(node.elements) != expected_arr.size:
          self.error(
            f"Fixed-size array '[{target_elem}; {expected_arr.size}]' "
            f"requires exactly {expected_arr.size} element(s), "
            f"got {len(node.elements)}.",
            node=node,
          )
        return ArrayType(
          target_elem, size=len(node.elements), is_fixed_size=True
        )
      return ArrayType(
        target_elem, size=len(node.elements), is_fixed_size=False
      )

    inferred_elem = elem_types[0]
    for etype in elem_types[1:]:
      widened = self._widen_types(inferred_elem, etype)
      if widened is None:
        self.error("Inconsistent element types in array literal.")
        break
      inferred_elem = widened
    return ArrayType(
      inferred_elem, size=len(node.elements), is_fixed_size=False
    )

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> Type:
    expected_map = (
      self.expected_type if isinstance(self.expected_type, MapType) else None
    )
    if not node.entries:
      if expected_map is not None:
        return MapType(expected_map.key_type, expected_map.value_type)
      return MapType(NoneType(), NoneType())

    def is_valid_key_type(ktype: Type) -> bool:
      return (
        isinstance(ktype, StringType)
        or (isinstance(ktype, PrimitiveType) and ktype.name == "int")
        or isinstance(ktype, EnumType)
      )

    old_expected = self.expected_type
    key_types: list[Type] = []
    val_types: list[Type] = []
    try:
      for entry in node.entries:
        self.expected_type = (
          expected_map.key_type if expected_map is not None else None
        )
        key_types.append(self.visit(entry.key))
        self.expected_type = (
          expected_map.value_type if expected_map is not None else None
        )
        val_types.append(self.visit(entry.value))
    finally:
      self.expected_type = old_expected

    for entry, ktype, vtype in zip(
      node.entries, key_types, val_types, strict=False
    ):
      self._check_value_ownership_transfer(entry.key, ktype, node=entry.key)
      self._check_value_ownership_transfer(entry.value, vtype, node=entry.value)
      if not is_valid_key_type(ktype):
        self.error("Map key must be a string, int, or enum.")

    if expected_map is not None:
      for ktype, vtype in zip(key_types, val_types, strict=False):
        if not ktype.is_compatible(expected_map.key_type):
          self.error("Inconsistent key types in map literal.")
        if not vtype.is_compatible(expected_map.value_type):
          self.error("Inconsistent value types in map literal.")
      return MapType(expected_map.key_type, expected_map.value_type)

    inferred_key = key_types[0]
    inferred_val = val_types[0]
    for ktype, vtype in zip(key_types[1:], val_types[1:], strict=False):
      widened_k = self._widen_types(inferred_key, ktype)
      if widened_k is None:
        self.error("Inconsistent key types in map literal.")
      else:
        inferred_key = widened_k

      widened_v = self._widen_types(inferred_val, vtype)
      if widened_v is None:
        self.error("Inconsistent value types in map literal.")
      else:
        inferred_val = widened_v

    return MapType(inferred_key, inferred_val)

  def _get_const_int_value(self, expr: ASTNode) -> int | None:
    if isinstance(expr, LiteralNode) and expr.lit_type == "int":
      return int(expr.value)
    if (
      isinstance(expr, UnaryOpNode)
      and expr.op == "-"
      and isinstance(expr.expr, LiteralNode)
      and expr.expr.lit_type == "int"
    ):
      return -int(expr.expr.value)
    return None

  def _check_array_bounds(
    self, node: IndexExprNode, array_type: ArrayType
  ) -> None:
    const_idx = self._get_const_int_value(node.index)
    if const_idx is not None:
      size = array_type.size
      if size is not None:
        if const_idx >= size or const_idx < -size:
          self.error(
            f"Array index out of bounds: index {const_idx} is out of bounds "
            f"for array of size {size}.",
            node=node,
          )

  def _check_map_literal_key(self, node: IndexExprNode) -> None:
    if isinstance(node.array, MapLiteralNode) and isinstance(
      node.index, LiteralNode
    ):
      key_val = str(node.index.value)
      for entry in node.array.entries:
        if (
          isinstance(entry.key, LiteralNode) and str(entry.key.value) == key_val
        ):
          return
      self.error(f"Key '{key_val}' not found in map literal.")

  def visit_IndexExprNode(self, node: IndexExprNode) -> Type:
    if isinstance(node.array, MoveNode):
      self.error(
        f"Cannot index into moved variable '{node.array.name}'.", node=node
      )
      return PrimitiveType("none")
    container_type = self.visit(node.array)
    if isinstance(container_type, (RefType, SharedRefType)):
      container_type = container_type.inner_type
    index_type = self.visit(node.index)

    if isinstance(container_type, ArrayType):
      if index_type != PrimitiveType("int"):
        self.error("Array index must be an 'int'.")
      const_idx = self._get_const_int_value(node.index)
      if const_idx is not None:
        self._check_array_bounds(node, container_type)
      return container_type.element_type
    elif isinstance(container_type, MapType):
      if not index_type.is_compatible(container_type.key_type):
        self.error(
          f"Map index type '{index_type}' is not compatible with key type "
          f"'{container_type.key_type}'."
        )
      if isinstance(node.array, MapLiteralNode):
        self._check_map_literal_key(node)
      return container_type.value_type
    else:
      self.error("Cannot index non-array type.", node=node)
      return PrimitiveType("none")

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> Type:
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      self.error(f"Cannot instantiate undefined struct '{node.struct_name}'.")
      return PrimitiveType("none")

    raw_name = node.struct_name

    if struct_type.type_params:
      if node.type_args:
        resolved_type_args = [
          self._resolve_type_node(t) for t in node.type_args
        ]
        struct_type = self._monomorphize_struct(
          struct_type, node.type_args, resolved_type_args
        )
        node.struct_name = struct_type.name
      else:
        self.error(
          f"Generic struct '{node.struct_name}' requires explicit type "
          "arguments."
        )
        return PrimitiveType("none")

    def _struct_has_init(st: StructType) -> bool:
      if "__init__" in st.methods:
        return True
      if st.parent_names:
        for p_name in st.parent_names:
          p_type = self.symbol_table.lookup_type(p_name)
          if isinstance(p_type, StructType) and _struct_has_init(p_type):
            return True
      return False

    if _struct_has_init(struct_type):
      self.error(
        f"Cannot use literal initializer for struct '{raw_name}' because it "
        "defines an '__init__' constructor. Use constructor call syntax "
        f"'{raw_name}(...)' instead."
      )
      return struct_type

    # Validate explicit arena target
    if struct_type.is_prototype and not node.arena_expr:
      self.error(
        f"Proto instantiation of '{node.struct_name}' requires an explicit "
        "arena via 'in <arena>'."
      )
    if node.arena_expr:
      arena_type = self.visit(node.arena_expr)
      if not isinstance(arena_type, ArenaType):
        self.error("Explicit arena target must be an instance of Arena.")
      else:
        ArenaChecker.validate_arena_mutability(
          self.symbol_table,
          node.arena_expr,
          lambda msg: self.error(msg, node=node),
          checker=self,
        )
        if (
          self.is_in_init
          and isinstance(node.arena_expr, MemberAccessNode)
          and isinstance(node.arena_expr.receiver, IdentifierNode)
          and node.arena_expr.receiver.name == "self"
        ):
          self._init_used_arena_fields.add(node.arena_expr.member)

    initialized = set()
    for field_arg in node.fields:
      field_name = field_arg.name
      if not field_name:
        self.error(
          "Positional arguments are not allowed in struct initializer of "
          f"'{node.struct_name}'. Use named initializers instead."
        )
        continue

      if field_name not in struct_type.fields:
        self.error(f"Struct '{node.struct_name}' has no field '{field_name}'.")
        continue

      if field_name in initialized:
        self.error(
          f"Field '{field_name}' is initialized multiple times in struct "
          "initializer."
        )
        continue

      expected_type = struct_type.fields[field_name].field_type
      old_expected = self.expected_type
      self.expected_type = expected_type
      try:
        expr_type = self.visit(field_arg.expr)
      finally:
        self.expected_type = old_expected
      self._check_value_ownership_transfer(
        field_arg.expr, expr_type, node=field_arg.expr
      )

      if not expr_type.is_compatible(expected_type):
        self.error(
          f"Field '{field_name}' in struct '{node.struct_name}' initializer "
          f"has type '{expr_type}', but expected '{expected_type}'."
        )

      initialized.add(field_name)

    # Verify all non-optional and non-default fields are initialized
    for f_name, f_obj in struct_type.fields.items():
      if (
        f_name not in initialized
        and not isinstance(f_obj.field_type, OptionalType)
        and not f_obj.has_default
      ):
        self.error(
          f"Struct initializer for '{node.struct_name}' is missing required "
          f"field '{f_name}'."
        )

    return struct_type
