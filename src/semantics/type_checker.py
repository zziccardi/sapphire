"""Semantic analyzer and type checker implementation for Sapphire.

This module walks the Sapphire AST, constructs symbol tables, performs type
checking and type inference, and validates all semantic constraints of the
Sapphire language.
"""

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

from src.semantics.type_resolver import TypeResolverMixin
from src.semantics.decl_visitor import DeclVisitorMixin
from src.semantics.stmt_visitor import StmtVisitorMixin
from src.semantics.call_visitor import CallVisitorMixin
from src.semantics.expr_visitor import ExprVisitorMixin


class TypeChecker(
    DeclVisitorMixin,
    StmtVisitorMixin,
    CallVisitorMixin,
    ExprVisitorMixin,
    TypeResolverMixin,
):
  """Walks the AST to perform type-checking and semantic validation."""

  def __init__(self, source_file_path: Optional[str] = None, source_content: Optional[Any] = None):
    self.symbol_table = SymbolTable()
    self.context = SemanticContext(symbol_table=self.symbol_table)
    self.node_types: Dict[ASTNode, Type] = self.context.node_types
    self.errors: List[str] = []
    self.source_file_path: Optional[str] = source_file_path
    self.source_content: Optional[Any] = source_content
    self.current_function: Optional[FunctionType] = None
    self.current_struct: Optional[StructType] = None
    self.is_in_init: bool = False
    self.is_in_del: bool = False
    self.is_in_clone_init: bool = False
    self.initialized_fields: set = set()
    self.expected_type: Optional[Type] = None
    self.current_function_scope = None
    self._match_stack: List[List[Type]] = []
    self.loop_depth: int = 0
    self.moved_symbols: Set[VariableSymbol] = set()
    self._branch_depth: int = 0
    self._init_assigned_arena_fields: Set[str] = set()
    self._init_used_arena_fields: Set[str] = set()
    self._temporary_frozen_lvalues: List[Tuple[str, List[str], str]] = []

  def get_frozen_lvalue_reason(
      self, root: str, path: List[str]
  ) -> Optional[str]:
    """Returns freeze reason if lvalue path overlaps with a frozen lvalue."""
    scope = self.symbol_table.current_scope
    all_frozen = list(self._temporary_frozen_lvalues)
    while scope is not None:
      all_frozen.extend(getattr(scope, "frozen_lvalues", []))
      scope = scope.parent
    for f_root, f_path, reason in all_frozen:
      if f_root == root:
        if f_path[:len(path)] == path or path[:len(f_path)] == f_path:
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
      if (
          isinstance(node_t, OptionalType)
          and isinstance(node_t.base_type, SharedRefType)
      ):
        return True
      if isinstance(curr, MemberAccessNode):
        curr = curr.receiver
      elif isinstance(curr, IndexExprNode):
        curr = curr.array
      else:
        break
    return False

  def _get_target_symbol(self, target: ASTNode) -> Optional[VariableSymbol]:
    if isinstance(target, IdentifierNode):
      sym = self.symbol_table.lookup(target.name)
      if isinstance(sym, VariableSymbol):
        return sym
    elif isinstance(target, MemberAccessNode):
      return self._get_target_symbol(target.receiver)
    return None

  def _ast_references_self(self, ast_node: Any) -> bool:
    """Returns True if *ast_node* contains an IdentifierNode('self')."""
    if ast_node is None:
      return False
    if isinstance(ast_node, IdentifierNode) and ast_node.name == "self":
      return True
    if isinstance(ast_node, list):
      return any(self._ast_references_self(item) for item in ast_node)
    if isinstance(ast_node, ASTNode):
      for val in ast_node.__dict__.values():
        if isinstance(val, (ASTNode, list)) and self._ast_references_self(val):
          return True
    return False

  def _check_value_ownership_transfer(
      self,
      expr_node: Optional[ASTNode],
      expr_type: Type,
      node: Optional[ASTNode] = None,
  ) -> None:
    """Enforces explicit 'move' on move-only lvalues and '.share()'/'move' on SharedRef lvalues."""
    if expr_node is None:
      return
    diag_node = node or expr_node

    if self.is_in_del and isinstance(expr_node, IdentifierNode) and expr_node.name == "self":
      self.error("Cannot allow 'self' to escape from destructor '__del__'.", node=diag_node)
      return

    if isinstance(expr_node, TernaryExprNode):
      self._check_value_ownership_transfer(expr_node.true_expr, expr_type, node=diag_node)
      self._check_value_ownership_transfer(expr_node.false_expr, expr_type, node=diag_node)
      return

    if isinstance(expr_node, BinaryOpNode) and expr_node.op == "??":
      self._check_value_ownership_transfer(expr_node.left, expr_type, node=diag_node)
      self._check_value_ownership_transfer(expr_node.right, expr_type, node=diag_node)
      return

    if expr_type.is_move_only_type(self.symbol_table):
      if isinstance(expr_node, IdentifierNode) and not isinstance(expr_node, MoveNode):
        self.error(
            f"Cannot copy move-only type '{expr_type}'; use explicit 'move {expr_node.name}' to transfer ownership.",
            node=diag_node,
        )
      elif isinstance(expr_node, (MemberAccessNode, IndexExprNode)):
        self.error(
            f"Cannot copy or partially move move-only type '{expr_type}' out of a field or collection index.",
            node=diag_node,
        )
    elif expr_type.is_shared_ref_lvalue_type():
      if isinstance(expr_node, IdentifierNode) and not isinstance(expr_node, MoveNode):
        self.error(
            f"Cannot implicitly copy 'SharedRef' variable '{expr_node.name}'; "
            f"call '{expr_node.name}.share()' or use 'move {expr_node.name}'.",
            node=diag_node,
        )
      elif isinstance(expr_node, (MemberAccessNode, IndexExprNode)):
        self.error(
            "Cannot implicitly copy 'SharedRef' from a field or collection index; call '.share()' explicitly.",
            node=diag_node,
        )

  def _check_return_ownership_transfer(
      self,
      ret_expr: Optional[ASTNode],
      ret_type: Type,
      node: Optional[ASTNode] = None,
  ) -> None:
    """Validates ownership transfer on return expressions (allowing local RVO)."""
    if ret_expr is None:
      return
    diag_node = node or ret_expr
    if isinstance(ret_expr, TernaryExprNode):
      self._check_return_ownership_transfer(ret_expr.true_expr, ret_type, node=diag_node)
      self._check_return_ownership_transfer(ret_expr.false_expr, ret_type, node=diag_node)
      return
    if isinstance(ret_expr, BinaryOpNode) and ret_expr.op == "??":
      self._check_return_ownership_transfer(ret_expr.left, ret_type, node=diag_node)
      self._check_return_ownership_transfer(ret_expr.right, ret_type, node=diag_node)
      return
    if isinstance(ret_expr, IdentifierNode) and not isinstance(ret_expr, MoveNode):
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
            f"Cannot return borrowed or global move-only value '{ret_expr.name}' of type '{ret_type}'.",
            node=diag_node,
        )
      elif ret_type.is_shared_ref_lvalue_type():
        self.error(
            f"Cannot implicitly copy 'SharedRef' variable '{ret_expr.name}' on return; "
            f"call '{ret_expr.name}.share()'.",
            node=diag_node,
        )
      return
    self._check_value_ownership_transfer(ret_expr, ret_type, node=diag_node)

  def error(self, message: str, node: Optional[ASTNode] = None) -> None:
    """Logs a semantic error."""
    line = getattr(node, "start_line", None) if node else None
    column = getattr(node, "start_column", None) if node else None
    length = getattr(node, "length", None) if node else None

    if line or self.source_file_path or self.source_content:
      diag = format_diagnostic(
          error_type="Semantic Error",
          message=message,
          file_path=self.source_file_path,
          line=line,
          column=column,
          length=length,
          source_content=self.source_content,
      )
      self.errors.append(diag)
    else:
      self.errors.append(message)

  def check(self, program: ProgramNode) -> None:
    """Executes semantic analysis on the program."""
    self.program = program
    # Pass 0: Declare imported modules
    self._declare_imports(program)

    # Pass 1: Declare global symbols (Structs, Traits, Functions)
    self._declare_globals(program)

    # Pass 2: Copy inheritance layouts and resolve struct fields
    self._resolve_struct_layouts(program)

    # Pass 3: Register impl block method signatures
    self._register_impl_signatures(program)

    # Pass 3.5: Pre-analyze module-level var globals and call graph accesses
    self._analyze_global_accesses(program)

    # Pass 4: Type-check top-level statements, functions, and structs
    self.visit_ProgramNode(program)

    if self.errors:
      raise SemanticError("\n".join(self.errors))

  def _substitute_ast(self, node: Any, param_map: Dict[str, TypeNode]) -> Any:
    return GenericsChecker.substitute_ast(node, param_map)

  def _mangle_type_name(self, type_obj: Type) -> str:
    return GenericsChecker.mangle_type_name(type_obj)

  def _monomorphize_struct(
      self, generic_struct_type: StructType, type_arg_nodes: List[TypeNode], resolved_type_args: List[Type]
  ) -> StructType:
    """Monomorphizes a generic struct template for a specific set of concrete type arguments."""
    return GenericsChecker.monomorphize_struct(self, generic_struct_type, type_arg_nodes, resolved_type_args)

  def _monomorphize_function(
      self, func_sym: FunctionSymbol, type_arg_nodes: List[TypeNode], resolved_type_args: List[Type]
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete type arguments."""
    return GenericsChecker.monomorphize_function(self, func_sym, type_arg_nodes, resolved_type_args)

  def _declare_imports(self, program: ProgramNode) -> None:
    """Pre-pass to register imported module symbols."""
    DeclarationPass.declare_imports(self, program)

  def _validate_parameter_defaults(self, parameters: List[ParameterNode]) -> None:
    """Validates that parameters without default values do not follow parameters with default values."""
    DeclarationPass.validate_parameter_defaults(self, parameters)

  def _declare_globals(self, program: ProgramNode) -> None:
    """Pass 1: Collect struct, enum, and function declarations into global scope."""
    DeclarationPass.declare_globals(self, program)

  def _resolve_struct_layouts(self, program: ProgramNode) -> None:
    """Pre-pass to resolve static inheritance field copying and layout sizing."""
    StructLayoutPass.resolve_struct_layouts(self, program)

  def visit(self, node: ASTNode) -> Any:
    """Visit a node by dynamically calling its corresponding visit method."""
    method_name = f"visit_{node.__class__.__name__}"
    visitor = getattr(self, method_name, self.generic_visit)
    res = visitor(node)
    if res is not None and isinstance(res, Type):
      self.context.record_type(node, res)
    if isinstance(node, ExprNode) and isinstance(res, Type):
      node.inferred_type = res
    return res

  def generic_visit(self, node: ASTNode) -> Any:
    """Default fallback when no specific visitor method is defined."""
    raise NotImplementedError(f"No visit_{node.__class__.__name__} method defined.")

  # ==========================================
  # Visitor Methods
  # ==========================================

