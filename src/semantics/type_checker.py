"""Semantic analyzer and type checker implementation for Sapphire.

This module walks the Sapphire AST, constructs symbol tables, performs type
checking and type inference, and validates all semantic constraints of the
Sapphire language.
"""

from typing import Any

from src.common.diagnostics import Diagnostic, format_diagnostic
from src.common.errors import SemanticError
from src.parser.ast import (
  ASTNode,
  BinaryOpNode,
  ExprNode,
  IdentifierNode,
  IndexExprNode,
  MemberAccessNode,
  MoveNode,
  ParameterNode,
  ProgramNode,
  TernaryExprNode,
  TypeNode,
)
from src.semantics.call_visitor import CallVisitorMixin
from src.semantics.decl_visitor import DeclVisitorMixin
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.expr_visitor import ExprVisitorMixin
from src.semantics.generics_checker import GenericsChecker
from src.semantics.semantic_context import SemanticContext
from src.semantics.stmt_visitor import StmtVisitorMixin
from src.semantics.struct_layout_pass import StructLayoutPass
from src.semantics.symbol_table import (
  ArrayType,
  FunctionSymbol,
  FunctionType,
  InferredType,
  MapType,
  NoneType,
  OptionalType,
  PrimitiveType,
  RefType,
  SharedRefType,
  StructType,
  SymbolTable,
  Type,
  VariableSymbol,
)
from src.semantics.type_resolver import TypeResolverMixin


class TypeChecker(
  DeclVisitorMixin,
  StmtVisitorMixin,
  CallVisitorMixin,
  ExprVisitorMixin,
  TypeResolverMixin,
):
  """Walks the AST to perform type-checking and semantic validation."""

  def __init__(
    self,
    source_file_path: str | None = None,
    source_content: Any | None = None,
  ):
    self.symbol_table = SymbolTable()
    self.context = SemanticContext(symbol_table=self.symbol_table)
    self.node_types: dict[ASTNode, Type] = self.context.node_types
    self.errors: list[str] = []
    self.warnings: list[str] = []
    self.diagnostics: list[Diagnostic] = self.context.diagnostics
    self.source_file_path: str | None = source_file_path
    self.source_content: Any | None = source_content
    self.current_function: FunctionType | None = None
    self.current_struct: StructType | None = None
    self.is_in_init: bool = False
    self.is_in_del: bool = False
    self.is_in_clone_init: bool = False
    self.initialized_fields: set = set()
    self.expected_type: Type | None = None
    self.current_function_scope = None
    self._match_stack: list[list[Type]] = []
    self.loop_depth: int = 0
    self.moved_symbols: set[VariableSymbol] = set()
    self.uninitialized_symbols: set[VariableSymbol] = set()
    self._mono_depth: int = 0
    self._branch_depth: int = 0
    self._init_assigned_arena_fields: set[str] = set()
    self._init_used_arena_fields: set[str] = set()
    self._temporary_frozen_lvalues: list[tuple[str, list[str], str]] = []
    self._loop_context_stack: list[tuple[set[VariableSymbol], Any]] = []
    self._checked_import_results: dict[
      str, tuple[dict[str, Any], list[str], dict[str, tuple[int, int]], bool]
    ] = {}
    self._active_import_stack: set[str] = set()
    self._reported_import_errors: set[str] = set()
    self._resolved_dep_stats: dict[str, tuple[int, int]] = {}
    self._current_node: ASTNode | None = None

  @property
  def temporary_frozen_lvalues(self) -> list[tuple[str, list[str], str]]:
    """Public accessor for temporary frozen lvalues used by helper passes."""
    return self._temporary_frozen_lvalues

  def find_immutable_field_in_chain(self, expr: ASTNode) -> Any:
    """Public wrapper for `_find_immutable_field_in_chain`."""
    return self._find_immutable_field_in_chain(expr)

  def check_value_ownership_transfer(
    self,
    expr_node: ASTNode,
    expr_type: Type,
    node: ASTNode | None = None,
  ) -> None:
    """Public wrapper for `_check_value_ownership_transfer`."""
    self._check_value_ownership_transfer(expr_node, expr_type, node=node)

  def resolve_type_node(self, type_node: Any) -> Type:
    """Public wrapper for `_resolve_type_node`."""
    return self._resolve_type_node(type_node)

  def resolve_return_types(self, decl: Any) -> Type:
    """Public wrapper for `_resolve_return_types`."""
    return self._resolve_return_types(decl)

  def get_lvalue_path(
    self, node: ASTNode
  ) -> tuple[str, list[str]] | None:
    """Public wrapper for `_get_lvalue_path`."""
    return self._get_lvalue_path(node)

  def is_reference_type(self, type_obj: Type) -> bool:
    """Public wrapper for `_is_reference_type`."""
    return self._is_reference_type(type_obj)

  def _restore_moved_symbols(self, target_moved: set[VariableSymbol]) -> None:
    """Restores `moved_symbols` to *target_moved* and keeps `sym.is_moved`
    synced.
    """
    for sym in self.moved_symbols - target_moved:
      sym.is_moved = False
    for sym in target_moved - self.moved_symbols:
      sym.is_moved = True
    self.moved_symbols = set(target_moved)

  def _widen_types(self, t1: Type, t2: Type) -> Type | None:
    """Returns the common widened type for *t1* and *t2*, or None if
    incompatible.
    """
    if isinstance(t1, InferredType):
      return t2
    if isinstance(t2, InferredType):
      return t1
    if t1 == t2:
      return t1
    is_t1_none = isinstance(t1, NoneType) or (
      isinstance(t1, PrimitiveType) and t1.name == "none"
    )
    is_t2_none = isinstance(t2, NoneType) or (
      isinstance(t2, PrimitiveType) and t2.name == "none"
    )
    if is_t1_none and is_t2_none:
      return NoneType()
    if is_t1_none:
      return t2 if isinstance(t2, OptionalType) else OptionalType(t2)
    if is_t2_none:
      return t1 if isinstance(t1, OptionalType) else OptionalType(t1)
    if isinstance(t1, OptionalType) and isinstance(t2, OptionalType):
      inner = self._widen_types(t1.base_type, t2.base_type)
      return OptionalType(inner) if inner is not None else None
    if isinstance(t1, OptionalType):
      inner = self._widen_types(t1.base_type, t2)
      return OptionalType(inner) if inner is not None else None
    if isinstance(t2, OptionalType):
      inner = self._widen_types(t1, t2.base_type)
      return OptionalType(inner) if inner is not None else None
    if isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveType):
      if {t1.name, t2.name} == {"int", "float"}:
        return PrimitiveType("float")
    if isinstance(t1, ArrayType) and isinstance(t2, ArrayType):
      if isinstance(t1.element_type, NoneType):
        return ArrayType(t2.element_type, is_fixed_size=False)
      if isinstance(t2.element_type, NoneType):
        return ArrayType(t1.element_type, is_fixed_size=False)
      elem = self._widen_types(t1.element_type, t2.element_type)
      if elem is not None:
        return ArrayType(elem, is_fixed_size=False)
    if isinstance(t1, MapType) and isinstance(t2, MapType):
      if isinstance(t1.key_type, NoneType) and isinstance(
        t1.value_type, NoneType
      ):
        return t2
      if isinstance(t2.key_type, NoneType) and isinstance(
        t2.value_type, NoneType
      ):
        return t1
      k = self._widen_types(t1.key_type, t2.key_type)
      v = self._widen_types(t1.value_type, t2.value_type)
      if k is not None and v is not None:
        return MapType(k, v)
    if t1.is_compatible(t2) and not t2.is_compatible(t1):
      return t2
    if t2.is_compatible(t1):
      return t1
    if t1.is_compatible(t2):
      return t2
    return None

  def _find_immutable_field_in_chain(
    self,
    node: ASTNode,
    skip_outermost: bool = False,
  ) -> tuple[str, str] | None:
    """Walks an lvalue chain and returns `(field_name, struct_name)` for any
    `let`
    field.
    """
    curr: Any = node
    first = True
    while curr is not None:
      if isinstance(curr, MemberAccessNode):
        if not (first and skip_outermost):
          recv_type = self.node_types.get(curr.receiver)
          if isinstance(recv_type, OptionalType):
            recv_type = recv_type.base_type
          if isinstance(recv_type, RefType):
            recv_type = recv_type.inner_type
          if isinstance(recv_type, StructType):
            field = recv_type.fields.get(curr.member)
            if field and not field.is_mutable:
              return (curr.member, recv_type.name)
        curr = curr.receiver
      elif isinstance(curr, IndexExprNode):
        curr = curr.array
      else:
        break
      first = False
    return None

  def get_frozen_lvalue_reason(
    self, root: str, path: list[str]
  ) -> str | None:
    """Returns freeze reason if lvalue path overlaps with a frozen lvalue."""
    scope = self.symbol_table.current_scope
    all_frozen = list(self._temporary_frozen_lvalues)
    while scope is not None:
      all_frozen.extend(getattr(scope, "frozen_lvalues", []))
      scope = scope.parent
    for f_root, f_path, reason in all_frozen:
      if f_root == root:
        if f_path[: len(path)] == path or path[: len(f_path)] == f_path:
          return reason
    return None

  def has_shared_ref_base(self, node: ASTNode) -> bool:
    """Returns True if *node* or any base in its chain is a SharedRef."""
    curr = node
    while curr is not None:
      node_t = self.node_types.get(curr)
      if node_t is None and isinstance(curr, IdentifierNode):
        sym = self.symbol_table.lookup(curr.name)
        if isinstance(sym, VariableSymbol):
          node_t = sym.symbol_type
      if isinstance(node_t, SharedRefType):
        return True
      if isinstance(node_t, OptionalType) and isinstance(
        node_t.base_type, SharedRefType
      ):
        return True
      if isinstance(curr, MemberAccessNode):
        curr = curr.receiver
      elif isinstance(curr, IndexExprNode):
        curr = curr.array
      else:
        break
    return False

  def _get_target_symbol(self, target: ASTNode) -> VariableSymbol | None:
    if isinstance(target, IdentifierNode):
      sym = self.symbol_table.lookup(target.name)
      if isinstance(sym, VariableSymbol):
        return sym
    elif isinstance(target, MemberAccessNode):
      return self._get_target_symbol(target.receiver)
    return None

  def _ast_references_ident(self, ast_node: Any, name: str) -> bool:
    """Returns True if *ast_node* contains an IdentifierNode with *name*."""
    if ast_node is None:
      return False
    if isinstance(ast_node, IdentifierNode) and ast_node.name == name:
      return True
    if isinstance(ast_node, list):
      return any(self._ast_references_ident(item, name) for item in ast_node)
    if isinstance(ast_node, ASTNode):
      for val in ast_node.__dict__.values():
        if isinstance(val, (ASTNode, list)) and self._ast_references_ident(
          val, name
        ):
          return True
    return False

  def _ast_references_self(self, ast_node: Any) -> bool:
    """Returns True if *ast_node* contains an IdentifierNode('self')."""
    return self._ast_references_ident(ast_node, "self")

  def _check_value_ownership_transfer(
    self,
    expr_node: ASTNode | None,
    expr_type: Type,
    node: ASTNode | None = None,
  ) -> None:
    """Enforces explicit 'move' on move-only lvalues and '.share()'/'move' on
    SharedRef lvalues.
    """
    if expr_node is None:
      return
    diag_node = node or expr_node

    if (
      self.is_in_del
      and isinstance(expr_node, IdentifierNode)
      and expr_node.name == "self"
    ):
      self.error(
        "Cannot allow 'self' to escape from destructor '__del__'.",
        node=diag_node,
      )
      return

    if isinstance(expr_node, TernaryExprNode):
      self._check_value_ownership_transfer(
        expr_node.true_expr, expr_type, node=diag_node
      )
      self._check_value_ownership_transfer(
        expr_node.false_expr, expr_type, node=diag_node
      )
      return

    if isinstance(expr_node, BinaryOpNode) and expr_node.op == "??":
      self._check_value_ownership_transfer(
        expr_node.left, expr_type, node=diag_node
      )
      self._check_value_ownership_transfer(
        expr_node.right, expr_type, node=diag_node
      )
      return

    if expr_type.is_move_only_type(self.symbol_table):
      if isinstance(expr_node, IdentifierNode) and not isinstance(
        expr_node, MoveNode
      ):
        self.error(
          f"Cannot copy move-only type '{expr_type}'; use explicit 'move "
          f"{expr_node.name}' to transfer ownership.",
          node=diag_node,
        )
      elif isinstance(expr_node, (MemberAccessNode, IndexExprNode)):
        self.error(
          f"Cannot copy or partially move move-only type '{expr_type}' out of "
          "a field or collection index.",
          node=diag_node,
        )
    elif expr_type.is_shared_ref_lvalue_type():
      if isinstance(expr_node, IdentifierNode) and not isinstance(
        expr_node, MoveNode
      ):
        self.error(
          f"Cannot implicitly copy 'SharedRef' variable '{expr_node.name}'; "
          f"call '{expr_node.name}.share()' or use 'move {expr_node.name}'.",
          node=diag_node,
        )
      elif isinstance(expr_node, (MemberAccessNode, IndexExprNode)):
        self.error(
          "Cannot implicitly copy 'SharedRef' from a field or collection "
          "index; call '.share()' explicitly.",
          node=diag_node,
        )

  def _check_return_ownership_transfer(
    self,
    ret_expr: ASTNode | None,
    ret_type: Type,
    node: ASTNode | None = None,
  ) -> None:
    """Validates ownership transfer on return expressions (allowing local RVO).
    """
    if ret_expr is None:
      return
    diag_node = node or ret_expr
    if isinstance(ret_expr, TernaryExprNode):
      self._check_return_ownership_transfer(
        ret_expr.true_expr, ret_type, node=diag_node
      )
      self._check_return_ownership_transfer(
        ret_expr.false_expr, ret_type, node=diag_node
      )
      return
    if isinstance(ret_expr, BinaryOpNode) and ret_expr.op == "??":
      self._check_return_ownership_transfer(
        ret_expr.left, ret_type, node=diag_node
      )
      self._check_return_ownership_transfer(
        ret_expr.right, ret_type, node=diag_node
      )
      return
    if isinstance(ret_expr, IdentifierNode) and not isinstance(
      ret_expr, MoveNode
    ):
      sym = self.symbol_table.lookup(ret_expr.name)
      is_non_owned = (
        ret_expr.name == "self"
        or getattr(sym, "is_parameter", False)
        or getattr(sym, "is_borrowed_unwrap", False)
        or (
          isinstance(sym, VariableSymbol)
          and sym.scope_defined is not None
          and sym.scope_defined.parent is None
        )
      )
      if not is_non_owned:
        return
      if ret_type.is_move_only_type(self.symbol_table):
        self.error(
          f"Cannot return borrowed or global move-only value "
          f"'{ret_expr.name}' of type '{ret_type}'.",
          node=diag_node,
        )
      elif ret_type.is_shared_ref_lvalue_type():
        self.error(
          f"Cannot implicitly copy 'SharedRef' variable '{ret_expr.name}' on "
          "return; "
          f"call '{ret_expr.name}.share()'.",
          node=diag_node,
        )
      return
    self._check_value_ownership_transfer(ret_expr, ret_type, node=diag_node)

  def _infer_diagnostic_metadata(
    self, message: str
  ) -> tuple[str | None, str | None]:
    """Infers default error code and fix-it hint for known error patterns."""
    if (
      "cannot escape to" in message
      or "Cannot return closure" in message
      or "Cannot return coroutine" in message
      or "capturing local stack borrow" in message
    ):
      return (
        "E_BORROW_ESCAPE",
        "Escaping closures and stored coroutines cannot borrow local "
        "non-primitives or 'var' bindings. Pass a behavioral 'trait' "
        "adapter or yield data instead of borrowing 'var' state.",
      )
    return None, None

  def _make_diagnostic(
    self,
    severity: str,
    message: str,
    node: ASTNode | None = None,
    hint: str | None = None,
    code: str | None = None,
  ) -> Diagnostic:
    """Constructs a structured Diagnostic for an error or warning."""
    diag_node = (
      node if node is not None else getattr(self, "_current_node", None)
    )
    line = getattr(diag_node, "start_line", None) if diag_node else None
    column = getattr(diag_node, "start_column", None) if diag_node else None
    length = getattr(diag_node, "length", None) if diag_node else None
    if hint is None and code is None and severity == "error":
      code, hint = self._infer_diagnostic_metadata(message)
    return Diagnostic(
      severity=severity,
      message=message,
      file_path=self.source_file_path,
      line=line,
      column=column,
      length=length,
      hint=hint,
      code=code,
    )

  def _format_diagnostic_entry(
    self,
    error_type: str,
    message: str,
    node: ASTNode | None = None,
    hint: str | None = None,
  ) -> str:
    """Formats a diagnostic string for an error or warning."""
    diag_node = (
      node if node is not None else getattr(self, "_current_node", None)
    )
    line = getattr(diag_node, "start_line", None) if diag_node else None
    column = getattr(diag_node, "start_column", None) if diag_node else None
    length = getattr(diag_node, "length", None) if diag_node else None

    if line or self.source_file_path or self.source_content:
      return format_diagnostic(
        error_type=error_type,
        message=message,
        file_path=self.source_file_path,
        line=line,
        column=column,
        length=length,
        source_content=self.source_content,
        hint=hint,
      )
    if hint:
      return f"{message}\n  Hint: {hint}"
    return message

  def error(
    self,
    message: str,
    node: ASTNode | None = None,
    hint: str | None = None,
    code: str | None = None,
  ) -> None:
    """Logs a semantic error."""
    diag = self._make_diagnostic(
      "error", message, node=node, hint=hint, code=code
    )
    self.diagnostics.append(diag)
    self.errors.append(
      self._format_diagnostic_entry(
        "Semantic Error", message, node, hint=diag.hint
      )
    )

  def warning(
    self,
    message: str,
    node: ASTNode | None = None,
    hint: str | None = None,
    code: str | None = None,
  ) -> None:
    """Logs a non-fatal semantic warning."""
    diag = self._make_diagnostic(
      "warning", message, node=node, hint=hint, code=code
    )
    self.diagnostics.append(diag)
    self.warnings.append(
      self._format_diagnostic_entry("Warning", message, node, hint=diag.hint)
    )

  def check(self, program: ProgramNode) -> None:
    """Executes semantic analysis on the program."""
    self.program = program
    # Pass 0: Declare imported modules
    self._declare_imports(program)

    # Pass 1: Declare global symbols (Structs, Traits, Functions)
    self._declare_globals(program)

    # Pass 2: Register impl block method signatures
    self._register_impl_signatures(program)

    # Pass 3: Resolve struct layouts and module-level let constants in source
    # order
    self._resolve_struct_layouts(program)

    # Pass 3.5: Pre-analyze module-level var globals and call graph accesses
    self._analyze_global_accesses(program)
    self._analyze_method_self_fields(program)

    # Pass 4: Type-check top-level statements, functions, and structs
    self.visit_ProgramNode(program)

    if self.errors:
      raise SemanticError("\n".join(self.errors))

  def _substitute_ast(self, node: Any, param_map: dict[str, TypeNode]) -> Any:
    return GenericsChecker.substitute_ast(node, param_map)

  def _mangle_type_name(self, type_obj: Type) -> str:
    return GenericsChecker.mangle_type_name(type_obj)

  def _monomorphize_struct(
    self,
    generic_struct_type: StructType,
    type_arg_nodes: list[TypeNode],
    resolved_type_args: list[Type],
  ) -> StructType:
    """Monomorphizes a generic struct template for a specific set of concrete
    type
    arguments.
    """
    return GenericsChecker.monomorphize_struct(
      self, generic_struct_type, type_arg_nodes, resolved_type_args
    )

  def _monomorphize_function(
    self,
    func_sym: FunctionSymbol,
    type_arg_nodes: list[TypeNode],
    resolved_type_args: list[Type],
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete
    type arguments.
    """
    return GenericsChecker.monomorphize_function(
      self, func_sym, type_arg_nodes, resolved_type_args
    )

  def _declare_imports(self, program: ProgramNode) -> None:
    """Pre-pass to register imported module symbols."""
    DeclarationPass.declare_imports(self, program)

  def _validate_parameter_defaults(
    self, parameters: list[ParameterNode]
  ) -> None:
    """Validates that parameters without default values do not follow parameters
    with default values.
    """
    DeclarationPass.validate_parameter_defaults(self, parameters)

  def _declare_globals(self, program: ProgramNode) -> None:
    """Pass 1: Collect struct, enum, and function declarations into global
    scope.
    """
    DeclarationPass.declare_globals(self, program)

  def _resolve_struct_layouts(self, program: ProgramNode) -> None:
    """Pre-pass to resolve static inheritance field copying and layout sizing.
    """
    StructLayoutPass.resolve_struct_layouts(self, program)

  def visit(self, node: ASTNode) -> Any:
    """Visit a node by dynamically calling its corresponding visit method."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    prev_node = self._current_node
    self._current_node = node
    try:
      res = visitor(node)
    finally:
      self._current_node = prev_node
    if res is not None and isinstance(res, Type):
      self.context.record_type(node, res)
    if isinstance(node, ExprNode) and isinstance(res, Type):
      node.inferred_type = res
    return res

  def generic_visit(self, node: ASTNode) -> Any:
    """Default fallback when no specific visitor method is defined."""
    raise NotImplementedError(
      f"No visit_{node.__class__.__name__} method defined."
    )

  # ==========================================
  # Visitor Methods
  # ==========================================
