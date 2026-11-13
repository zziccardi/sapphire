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


class TypeChecker:
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

  def _resolve_field_type(self, f: StructFieldNode, struct_name: str) -> Type:
    """Resolves struct field type from explicit annotation or infers it from default expression."""
    if f.field_type:
      ftype = self._resolve_type_node(f.field_type)
      if f.default_expr:
        expr_type = self.visit(f.default_expr)
        if not expr_type.is_compatible(ftype):
          self.error(
              f"Default expression of type '{expr_type}' is not compatible with field '{f.name}' of type '{ftype}'.",
              node=f,
          )
      return ftype
    elif f.default_expr:
      ftype = self.visit(f.default_expr)
      if isinstance(ftype, NoneType):
        self.error(
            f"Cannot infer type of struct field '{f.name}' from 'none' alone. Specify an explicit type annotation.",
            node=f,
        )
        return PrimitiveType("none")
      return ftype
    else:
      self.error(
          f"Struct field '{f.name}' in struct '{struct_name}' requires an explicit type annotation or a default value.",
          node=f,
      )
      return PrimitiveType("none")

  def _has_implicit_default_value(self, ftype: Type) -> bool:
    if isinstance(ftype, OptionalType):
      return True
    if isinstance(ftype, PrimitiveType) and ftype.name in ("int", "float", "bool"):
      return True
    return False

  def _get_impl_type_params(self, decl: ImplBlockNode) -> List[str]:
    type_params = list(decl.type_params) if decl.type_params else []
    builtin_type_names = {
        "int", "float", "String", "bool", "none", "void",
        "Array", "Map", "Coroutine", "Ref", "SharedRef", "WeakRef", "Arena", "Range",
    }
    for arg in getattr(decl, "trait_type_args", []) + getattr(decl, "struct_type_args", []):
      if isinstance(arg, BasicTypeNode) and arg.name not in builtin_type_names:
        if "." not in arg.name and self.symbol_table.lookup_type(arg.name) is None:
          if arg.name not in type_params:
            type_params.append(arg.name)
    decl.type_params = type_params
    return type_params

  def _substitute_type_params(self, t: Type, type_map: Dict[str, Type]) -> Type:
    if isinstance(t, GenericTypeParameter) and t.name in type_map:
      return type_map[t.name]
    if isinstance(t, OptionalType):
      return OptionalType(self._substitute_type_params(t.base_type, type_map))
    if isinstance(t, ArrayType):
      return ArrayType(self._substitute_type_params(t.element_type, type_map), size=t.size)
    if isinstance(t, MapType):
      return MapType(
          self._substitute_type_params(t.key_type, type_map),
          self._substitute_type_params(t.value_type, type_map),
      )
    if isinstance(t, MultiReturnType):
      return MultiReturnType([self._substitute_type_params(sub, type_map) for sub in t.types])
    if isinstance(t, FunctionType):
      return FunctionType(
          [self._substitute_type_params(p, type_map) for p in t.param_types],
          self._substitute_type_params(t.return_type, type_map),
          param_mutabilities=t.param_mutabilities,
          param_names=t.param_names,
          has_self=t.has_self,
          num_defaults=t.num_defaults,
      )
    return t

  def _register_impl_signatures(self, program: ProgramNode) -> None:
    """Pre-pass to register methods defined inside impl blocks onto struct types."""
    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
        for member in decl.members:
          self._validate_parameter_defaults(member.func_decl.parameters)
        if self._get_impl_type_params(decl):
          continue
        struct_type = self.symbol_table.lookup_type(decl.struct_name)
        if not struct_type or not isinstance(struct_type, StructType):
          self.error(f"Cannot implement members for undefined struct '{decl.struct_name}'.")
          continue

        # If implementing a trait
        trait_type = None
        if decl.trait_name:
          trait_type = self.symbol_table.lookup_type(decl.trait_name)
          if not trait_type or not isinstance(trait_type, TraitType):
            self.error(f"Cannot implement undefined trait '{decl.trait_name}'.")
            continue
          struct_type.implemented_traits.add(trait_type.name)

        for member in decl.members:
          if trait_type and member.func_decl.name in trait_type.methods:
            trait_method = trait_type.methods[member.func_decl.name]
            if getattr(trait_method.ast_decl, "modifier", None) == "static":
              member.modifier = "static"
          func_decl = member.func_decl
          # Resolve parameters
          param_types = []
          param_mutabilities = []
          for p in func_decl.parameters:
            if p.name == "self" and p.param_type is None:
              ptype = trait_type if trait_type else struct_type
            else:
              ptype = self._resolve_type_node(p.param_type)
            param_types.append(ptype)
            param_mutabilities.append(p.is_mutable)
          ret_type = self._resolve_return_types(func_decl)
          num_defaults = sum(1 for p in func_decl.parameters if getattr(p, "default_expr", None) is not None)
          signature = FunctionType(
              param_types,
              ret_type,
              param_mutabilities,
              param_names=[p.name for p in func_decl.parameters],
              num_defaults=num_defaults,
          )

          method = StructMethod(func_decl.name, signature, member.modifier)

          # Validate __del__ destructor
          if func_decl.name == "__del__":
            if member.modifier == "static":
              self.error("Destructor '__del__' cannot be static.")
            if len(func_decl.parameters) > 0:
              self.error("Destructor '__del__' must take 0 parameters; 'self' is implicitly available.")
            is_void = (len(ret_type) == 1 and (ret_type[0].name in ("none", "void") or (isinstance(ret_type[0], PrimitiveType) and ret_type[0].name in ("none", "void"))))
            if not is_void:
              self.error("Destructor '__del__' must return void.")

          # Check for duplicate definitions
          if func_decl.name in struct_type.methods:
            self.error(f"Method '{func_decl.name}' redefined in struct '{decl.struct_name}'.")
          struct_type.methods[func_decl.name] = method

          # Register on trait if needed
          if trait_type:
            pass

    # Propagate nominal trait implementations to child structs
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode) and decl.parent_names:
        child_type = self.symbol_table.lookup_type(decl.name)
        if isinstance(child_type, StructType):
          visited = set()
          stack = list(decl.parent_names)
          while stack:
            p_name = stack.pop()
            if p_name in visited:
              continue
            visited.add(p_name)
            p_type = self.symbol_table.lookup_type(p_name)
            if isinstance(p_type, StructType):
              child_type.implemented_traits.update(p_type.implemented_traits)
              stack.extend(p_type.parent_names)

  def _resolve_return_types(self, node: Any) -> List[Type]:
    if isinstance(node, FunctionTypeNode):
      return [self._resolve_type_node(t) for t in node.return_types]
    if hasattr(node, "return_types") and node.return_types:
      return [self._resolve_type_node(t) for t in node.return_types]
    elif hasattr(node, "return_type") and node.return_type:
      return [self._resolve_type_node(node.return_type)]
    else:
      return [PrimitiveType("none")]

  def _resolve_type_node(self, node: Optional[TypeNode]) -> Type:
    """Helper to map an AST TypeNode into a semantic Type object."""
    res = self._do_resolve_type_node(node)
    if node and res:
      self.context.record_type(node, res)
    return res

  def _do_resolve_type_node(self, node: Optional[TypeNode]) -> Type:
    if not node:
      return PrimitiveType("none")
    if isinstance(node, BasicTypeNode):
      if node.name == "Array" and node.type_args:
        return ArrayType(self._resolve_type_node(node.type_args[0]))
      if node.name == "Map" and len(node.type_args) >= 2:
        return MapType(self._resolve_type_node(node.type_args[0]), self._resolve_type_node(node.type_args[1]))
      if node.name == "Coroutine":
        if node.type_args:
          return CoroutineType(self._resolve_type_node(node.type_args[0]))
        return CoroutineType(NoneType())
      if node.name == "Ref":
        if node.type_args:
          return RefType(self._resolve_type_node(node.type_args[0]))
        return RefType(NoneType())
      if node.name == "SharedRef":
        if node.type_args:
          return SharedRefType(self._resolve_type_node(node.type_args[0]))
        return SharedRefType(NoneType())
      if node.name == "WeakRef":
        if node.type_args:
          return WeakRefType(self._resolve_type_node(node.type_args[0]))
        return WeakRefType(NoneType())
      if "." in node.name:
        parts = node.name.split(".")
        mod_sym = self.symbol_table.lookup(parts[0])
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(parts[1])
          if exp_sym:
            return exp_sym.symbol_type if hasattr(exp_sym, "symbol_type") else exp_sym
          self.error(f"Module '{parts[0]}' does not export type '{parts[1]}'.", node=node)
          return PrimitiveType("none")
      resolved = self.symbol_table.lookup_type(node.name)
      if isinstance(resolved, GenericTypeParameter):
        return resolved
      if not resolved:
        self.error(f"Undefined type '{node.name}'.", node=node)
        return PrimitiveType("none")
      if node.type_args and isinstance(resolved, StructType) and resolved.type_params:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        if not any(isinstance(t, GenericTypeParameter) for t in resolved_type_args):
          return self._monomorphize_struct(resolved, node.type_args, resolved_type_args)
      return resolved
    if isinstance(node, OptionalTypeNode):
      return OptionalType(self._resolve_type_node(node.base_type))
    if isinstance(node, ArrayTypeNode):
      elem_type = self._resolve_type_node(node.element_type)
      if node.size is not None:
        return ArrayType(elem_type, size=node.size, is_fixed_size=True)
      return ArrayType(elem_type)
    if isinstance(node, MapTypeNode):
      return MapType(self._resolve_type_node(node.key_type), self._resolve_type_node(node.val_type))
    if isinstance(node, FunctionTypeNode):
      param_types = [self._resolve_type_node(t) for t in node.param_types]
      ret_types = self._resolve_return_types(node)
      return FunctionType(param_types, ret_types)
    return PrimitiveType("none")

  # ==========================================
  # Visitor Dispatcher
  # ==========================================

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

  def _analyze_global_accesses(self, program: ProgramNode) -> None:
    """Pre-analyzes module-level mutable var globals and call graph accesses."""
    self.module_var_globals: Set[str] = set()
    self.exported_symbols: Set[str] = set()
    for decl in program.declarations:
      if (
          isinstance(decl, VarDeclNode)
          and decl.is_mutable
          and not getattr(decl, "is_extern", False)
      ):
        for name in decl.names:
          self.module_var_globals.add(name)
    if getattr(program, "export_block", None):
      for spec in program.export_block.specifiers:
        self.exported_symbols.add(spec.symbol)
    self.exported_var_globals = (
        self.module_var_globals & self.exported_symbols
    )

    self.func_direct_globals: Dict[str, Set[str]] = {}
    self.func_direct_calls: Dict[str, Set[str]] = {}
    self.func_has_dynamic: Set[str] = set()

    for decl in program.declarations:
      if isinstance(decl, FuncDeclNode):
        self._scan_func_global_accesses(decl.name, decl)
      elif isinstance(decl, ImplBlockNode):
        for member in decl.members:
          fdecl = getattr(member, "func_decl", member)
          if isinstance(fdecl, FuncDeclNode):
            func_id = f"{decl.struct_name}.{fdecl.name}"
            self._scan_func_global_accesses(
                func_id, fdecl, struct_name=decl.struct_name
            )

    self.func_transitive_globals = {
        k: set(v) for k, v in self.func_direct_globals.items()
    }
    self.func_transitive_dynamic = set(self.func_has_dynamic)
    changed = True
    while changed:
      changed = False
      for f_id, called_set in self.func_direct_calls.items():
        for callee in called_set:
          matching = [
              k
              for k in self.func_direct_globals
              if k == callee or k.endswith(f".{callee}")
          ]
          for m in matching:
            before_len = len(self.func_transitive_globals[f_id])
            self.func_transitive_globals[f_id].update(
                self.func_transitive_globals[m]
            )
            if len(self.func_transitive_globals[f_id]) > before_len:
              changed = True
            if (
                m in self.func_transitive_dynamic
                and f_id not in self.func_transitive_dynamic
            ):
              self.func_transitive_dynamic.add(f_id)
              changed = True

  def _scan_func_global_accesses(
      self,
      func_id: str,
      decl: FuncDeclNode,
      struct_name: Optional[str] = None,
  ) -> None:
    direct_globals: Set[str] = set()
    direct_calls: Set[str] = set()
    local_names: Set[str] = {p.name for p in decl.parameters}
    if struct_name:
      local_names.add("self")

    def walk(node: Any) -> None:
      if node is None:
        return
      if isinstance(node, list):
        for item in node:
          walk(item)
        return
      if isinstance(node, VarDeclNode):
        expr_list = getattr(node, "exprs", None) or (
            [node.expr] if getattr(node, "expr", None) else []
        )
        for e in expr_list:
          walk(e)
        for n in node.names:
          local_names.add(n)
        return
      if isinstance(node, LambdaNode):
        saved = set(local_names)
        for p in node.parameters:
          local_names.add(p.name)
        walk(node.body)
        local_names.clear()
        local_names.update(saved)
        return
      if isinstance(node, IdentifierNode):
        if (
            node.name in self.module_var_globals
            and node.name not in local_names
        ):
          direct_globals.add(node.name)
        return
      if isinstance(node, CallNode):
        if isinstance(node.callee, IdentifierNode):
          direct_calls.add(node.callee.name)
        elif isinstance(node.callee, MemberAccessNode):
          if (
              isinstance(node.callee.receiver, IdentifierNode)
              and node.callee.receiver.name == "self"
              and struct_name
          ):
            direct_calls.add(f"{struct_name}.{node.callee.member}")
          else:
            direct_calls.add(node.callee.member)
        else:
          self.func_has_dynamic.add(func_id)
        for arg in node.arguments:
          walk(arg.expr)
        return
      if isinstance(node, ASTNode):
        for v in node.__dict__.values():
          if isinstance(v, (ASTNode, list)):
            walk(v)

    walk(decl.body)
    self.func_direct_globals[func_id] = direct_globals
    self.func_direct_calls[func_id] = direct_calls

  def _scan_lambda_stack_borrows(self, lambda_node: LambdaNode) -> Set[str]:
    """Finds enclosing local stack non-primitive or var bindings in lambda."""
    local_names: Set[str] = {p.name for p in lambda_node.parameters}
    borrows: Set[str] = set()

    def walk(node: Any) -> None:
      if node is None:
        return
      if isinstance(node, list):
        for item in node:
          walk(item)
        return
      if isinstance(node, VarDeclNode):
        expr_list = getattr(node, "exprs", None) or (
            [node.expr] if getattr(node, "expr", None) else []
        )
        for e in expr_list:
          walk(e)
        for n in node.names:
          local_names.add(n)
        return
      if isinstance(node, LambdaNode):
        saved = set(local_names)
        for p in node.parameters:
          local_names.add(p.name)
        walk(node.body)
        local_names.clear()
        local_names.update(saved)
        return
      if isinstance(node, (IdentifierNode, MoveNode)):
        if node.name not in local_names:
          sym = self.symbol_table.lookup(node.name)
          if isinstance(sym, VariableSymbol):
            if (
                sym.scope_defined is not None
                and sym.scope_defined.parent is not None
            ):
              is_ref = ArenaChecker.is_reference_type(sym.symbol_type)
              is_plain_stack = (
                  is_ref
                  and not sym.arena_dep_records
                  and not isinstance(
                      sym.symbol_type, (SharedRefType, RefType)
                  )
              )
              if (
                  sym.is_mutable
                  or is_plain_stack
                  or sym.stack_borrow_symbols
              ):
                borrows.add(sym.name)
                borrows.update(sym.stack_borrow_symbols)
        return
      if isinstance(node, ASTNode):
        for v in node.__dict__.values():
          if isinstance(v, (ASTNode, list)):
            walk(v)

    walk(lambda_node.body)
    return borrows

  def visit_ProgramNode(self, node: ProgramNode) -> None:
    for imp in getattr(node, "imports", []):
      self.visit(imp)
    for decl in node.declarations:
      if not isinstance(
          decl,
          (
              StructDeclNode,
              EnumDeclNode,
              TraitDeclNode,
              VarDeclNode,
              FuncDeclNode,
              ImplBlockNode,
          ),
      ):
        self.error(
            "Executable statements are not permitted at module scope. All "
            "executable logic must reside inside 'func main()' or a function.",
            node=decl,
        )
      else:
        self.visit(decl)
    if getattr(node, "export_block", None):
      self.visit(node.export_block)

  def visit_ImportStmtNode(self, node: ImportStmtNode) -> None:
    pass

  def visit_ExportStmtNode(self, node: ExportStmtNode) -> None:
    for spec in node.specifiers:
      if spec.module_prefix:
        mod_sym = self.symbol_table.lookup(spec.module_prefix)
        if not mod_sym or not isinstance(mod_sym, ModuleSymbol):
          self.error(f"Module '{spec.module_prefix}' is not imported.", node=spec)
        elif spec.symbol not in mod_sym.exports:
          self.error(f"Module '{spec.module_prefix}' does not export symbol '{spec.symbol}'.", node=spec)
      else:
        sym = self.symbol_table.lookup(spec.symbol)
        type_sym = self.symbol_table.lookup_type(spec.symbol)
        if not sym and not type_sym:
          self.error(f"Exported symbol '{spec.symbol}' is not defined in module.", node=spec)
        elif isinstance(sym, VariableSymbol) and sym.is_mutable and not getattr(sym, "is_extern", False):
          self.error(
              f"Cannot export mutable module-level variable '{spec.symbol}'. "
              "Module-level mutable state cannot be exported.",
              node=spec,
          )

  def visit_StructDeclNode(self, node: StructDeclNode) -> None:
    # Fields already verified in pre-pass
    pass

  def visit_EnumDeclNode(self, node: EnumDeclNode) -> None:
    # Members already verified in pre-pass
    pass

  def visit_ImplBlockNode(self, node: ImplBlockNode) -> None:
    if self._get_impl_type_params(node):
      return
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      return

    self.current_struct = struct_type

    # If implementing a trait, verify contract is fully satisfied
    if node.trait_name:
      trait_type = self.symbol_table.lookup_type(node.trait_name)
      if isinstance(trait_type, TraitType):
        is_test_case = trait_type is self.symbol_table.testcase_trait or node.trait_name.endswith(".TestCase")
        if is_test_case:
          # Inject TestCase assertion methods onto struct methods if not defined explicitly
          for trait_m_name, trait_sig in trait_type.methods.items():
            if trait_m_name not in struct_type.methods:
              struct_type.methods[trait_m_name] = StructMethod(trait_m_name, trait_sig, None)
        else:
          trait_type_map: Dict[str, Type] = {}
          if trait_type.type_params and getattr(node, "trait_type_args", None):
            resolved_args = [self._resolve_type_node(t) for t in node.trait_type_args]
            trait_type_map = dict(zip(trait_type.type_params, resolved_args))
          for trait_method_name, trait_sig in trait_type.methods.items():
            expected_sig = (
                self._substitute_type_params(trait_sig, trait_type_map)
                if trait_type_map
                else trait_sig
            )
            if trait_method_name not in struct_type.methods:
              self.error(
                  f"Struct '{node.struct_name}' does not implement trait method "
                  f"'{trait_method_name}' of '{node.trait_name}'."
              )
            else:
              impl_sig = struct_type.methods[trait_method_name].method_type
              if impl_sig != expected_sig:
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"has signature {impl_sig}, but trait '{node.trait_name}' "
                    f"requires {expected_sig}."
                )
      else:
        self.error(f"Trait '{node.trait_name}' is not defined.")

    # Check each method implementation
    for member in node.members:
      self.visit(member)

    self.current_struct = None

  def _expr_references_self(self, expr: ASTNode) -> bool:
    if not expr:
      return False
    if isinstance(expr, IdentifierNode) and expr.name == "self":
      return True
    if isinstance(expr, MemberAccessNode):
      return self._expr_references_self(expr.receiver)
    if isinstance(expr, CallNode):
      if self._expr_references_self(expr.callee):
        return True
      for a in expr.arguments:
        if self._expr_references_self(a.expr):
          return True
    if isinstance(expr, BinaryOpNode):
      return self._expr_references_self(expr.left) or self._expr_references_self(expr.right)
    if isinstance(expr, UnaryOpNode):
      return self._expr_references_self(expr.expr)
    if isinstance(expr, TernaryExprNode):
      return (self._expr_references_self(expr.condition) or
              self._expr_references_self(expr.true_expr) or
              self._expr_references_self(expr.false_expr))
    return False

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func_decl = node.func_decl
    struct_type = self.current_struct

    # Enter scope of method
    self.symbol_table.enter_scope()
    old_moved_symbols = set(self.moved_symbols)
    self.moved_symbols = set()

    # Define parameters in scope before evaluating base initializers
    for p in func_decl.parameters:
      if p.name == "self":
        continue
      ptype = self._resolve_type_node(p.param_type)
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))

    # Reject base initializers on non-init methods
    if func_decl.base_initializers and func_decl.name != "__init__":
      self.error("Base initializers are only permitted on constructor '__init__'.", node=func_decl)

    # Setup constructor / destructor checking
    old_in_init = self.is_in_init
    old_in_del = self.is_in_del
    old_fields = self.initialized_fields
    old_init_assigned_arenas = self._init_assigned_arena_fields
    old_init_used_arenas = self._init_used_arena_fields
    self._init_assigned_arena_fields = set()
    self._init_used_arena_fields = set()
    parents_initialized = set()

    if func_decl.name == "__del__":
      self.is_in_del = True

    if func_decl.name == "__init__":
      self.is_in_init = True
      self.initialized_fields = set()

      if func_decl.base_initializers:
        if not struct_type or not struct_type.parent_names:
          self.error(f"Struct '{struct_type.name if struct_type else 'unknown'}' has no parent structs to initialize.", node=func_decl)
        else:
          for base_init in func_decl.base_initializers:
            parent_name = base_init.callee.name
            if parent_name not in struct_type.parent_names:
              self.error(f"'{parent_name}' is not a parent of struct '{struct_type.name}'.", node=base_init)
              continue
            if parent_name in parents_initialized:
              self.error(f"Duplicate initialization of parent struct '{parent_name}'.", node=base_init)
              continue
            parents_initialized.add(parent_name)

            has_self_ref = False
            for arg in base_init.arguments:
              if self._expr_references_self(arg.expr):
                self.error("References to 'self' are not allowed in base initializer arguments.", node=arg)
                has_self_ref = True

            parent_type = self.symbol_table.lookup_type(parent_name)
            if isinstance(parent_type, StructType):
              init_method = parent_type.methods.get("__init__")
              if init_method:
                if not has_self_ref:
                  self._check_arguments(base_init.arguments, init_method.method_type, is_constructor=True)
              elif base_init.arguments:
                self.error(f"Parent struct '{parent_name}' does not define an '__init__' constructor.", node=base_init)

              # Mark parent fields as initialized
              for f_name in parent_type.fields:
                self.initialized_fields.add(f_name)

      # Enforce all parents with __init__ are initialized
      if struct_type and struct_type.parent_names:
        for p_name in struct_type.parent_names:
          p_type = self.symbol_table.lookup_type(p_name)
          if isinstance(p_type, StructType) and "__init__" in p_type.methods:
            if p_name not in parents_initialized:
              self.error(f"Constructor '__init__' of struct '{struct_type.name}' must initialize parent struct '{p_name}'.", node=func_decl)

    # Define 'self' unless it is a static method
    if node.modifier != "static":
      is_mutable = (node.modifier == "var") or (func_decl.name in ("__init__", "__del__"))
      self.symbol_table.define("self", VariableSymbol("self", struct_type, is_mutable))

    # Save function signature context
    resolved_params = [self._resolve_type_node(p.param_type) for p in func_decl.parameters]
    param_mutabilities = [p.is_mutable for p in func_decl.parameters]
    ret_types = self._resolve_return_types(func_decl)
    num_defaults = sum(1 for p in func_decl.parameters if getattr(p, "default_expr", None) is not None)
    self.current_function = FunctionType(
        resolved_params,
        ret_types,
        param_mutabilities,
        param_names=[p.name for p in func_decl.parameters],
        num_defaults=num_defaults,
    )

    # Visit body
    self.visit(func_decl.body)

    # Verify constructor initializes all non-optional fields
    if func_decl.name == "__init__" and struct_type:
      for f_name, f_obj in struct_type.fields.items():
        if (f_name not in self.initialized_fields
            and not isinstance(f_obj.field_type, OptionalType)
            and not f_obj.has_explicit_default):
          self.error(f"Constructor '__init__' failed to initialize non-optional field '{f_name}'.")

    # Restore constructor / destructor contexts
    self.is_in_init = old_in_init
    self.is_in_del = old_in_del
    self.initialized_fields = old_fields
    self._init_assigned_arena_fields = old_init_assigned_arenas
    self._init_used_arena_fields = old_init_used_arenas
    self.current_function = None
    self.moved_symbols = old_moved_symbols

    self.symbol_table.exit_scope()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    if hasattr(node, "annotations") and node.annotations:
      DeclarationPass.validate_annotations(self, node.annotations, node=node)
    if node.base_initializers:
      self.error("Base initializers are only permitted on constructor '__init__'.", node=node)
    if node.type_params:
      return
    # Register parameters and check body
    self.symbol_table.enter_scope()
    old_moved_symbols = set(self.moved_symbols)
    self.moved_symbols = set()
    old_function_scope = self.current_function_scope
    self.current_function_scope = self.symbol_table.current_scope

    for p in node.parameters:
      ptype = self._resolve_type_node(p.param_type)
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))

    resolved_params = [self._resolve_type_node(p.param_type) for p in node.parameters]
    param_mutabilities = [p.is_mutable for p in node.parameters]
    ret_types = self._resolve_return_types(node)
    num_defaults = sum(1 for p in node.parameters if getattr(p, "default_expr", None) is not None)
    self.current_function = FunctionType(
        resolved_params,
        ret_types,
        param_mutabilities,
        param_names=[p.name for p in node.parameters],
        num_defaults=num_defaults,
    )

    self.visit(node.body)

    self.current_function = None
    self.current_function_scope = old_function_scope
    self.moved_symbols = old_moved_symbols
    self.symbol_table.exit_scope()

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.symbol_table.enter_scope()
    for stmt in node.statements:
      self.visit(stmt)
    cur_scope = self.symbol_table.current_scope
    self.moved_symbols = {s for s in self.moved_symbols if s.scope_defined != cur_scope}
    self.symbol_table.exit_scope()

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
      self.error(f"Undefined identifier '{node.name}'.", node=node)
      return PrimitiveType("none")
    if isinstance(sym, VariableSymbol):
      if sym in self.moved_symbols:
        self.error(f"Use of moved variable '{node.name}'.", node=node)
      ArenaChecker.check_use_validity(
          self.symbol_table, sym, lambda msg: self.error(msg, node=node)
      )
    return sym.symbol_type

  def visit_BinaryOpNode(self, node: BinaryOpNode) -> Type:
    left = self.visit(node.left)
    right = self.visit(node.right)

    # Coalescing operator
    if node.op == "??":
      if not isinstance(left, OptionalType):
        self.error(f"Left operand of '??' must be an optional type, got '{left}'.")
        return left
      base_type = left.base_type
      if not right.is_compatible(base_type) and not base_type.is_compatible(right):
        self.error(f"Fallback type '{right}' is not compatible with the optional's base type '{base_type}'.")
      return base_type

    # Boolean operators
    if node.op in ("&&", "||"):
      if left != PrimitiveType("bool") or right != PrimitiveType("bool"):
        self.error(f"Operator '{node.op}' requires boolean operands.")
      return PrimitiveType("bool")

    # Comparison operators
    if node.op in ("==", "!=", "<", "<=", ">", ">="):
      # Sapphire allows comparing compatible types
      if not left.is_compatible(right) and not right.is_compatible(left):
        self.error(f"Cannot compare type '{left}' with type '{right}' using '{node.op}'.")
      return PrimitiveType("bool")

    # Arithmetic operators
    if node.op in ("+", "-", "*", "/", "%"):
      if node.op == "+" and (isinstance(left, StringType) or isinstance(right, StringType)):
        node.is_string_concat = True
        return StringType()
      # Supports int and float operations; InferredType is a permitted
      # placeholder during lambda body analysis — treat it as numeric.
      is_numeric_left = (isinstance(left, PrimitiveType) and left.name in ("int", "float")) or isinstance(left, InferredType)
      is_numeric_right = (isinstance(right, PrimitiveType) and right.name in ("int", "float")) or isinstance(right, InferredType)
      if not (is_numeric_left and is_numeric_right):
        self.error(f"Arithmetic operator '{node.op}' requires numeric types.")
        return PrimitiveType("none")

      # If one side is a concrete float, propagate float; otherwise int.
      left_is_float = isinstance(left, PrimitiveType) and left.name == "float"
      right_is_float = isinstance(right, PrimitiveType) and right.name == "float"
      if left_is_float or right_is_float:
        return PrimitiveType("float")
      return PrimitiveType("int")

    return PrimitiveType("none")

  def visit_TernaryExprNode(self, node: TernaryExprNode) -> Type:
    # Enforce mandatory parentheses on nested ternary expressions
    for branch_node in (node.condition, node.true_expr, node.false_expr):
      if isinstance(branch_node, TernaryExprNode) and not getattr(branch_node, "is_parenthesized", False):
        self.error("Nested ternary expressions must be explicitly enclosed in parentheses.")

    cond_type = self.visit(node.condition)
    if cond_type != PrimitiveType("bool"):
      self.error(f"Ternary condition must be of type 'bool', got '{cond_type}'.")

    true_type = self.visit(node.true_expr)
    false_type = self.visit(node.false_expr)

    # Check type compatibility between true and false branches
    if isinstance(true_type, NoneType) and isinstance(false_type, NoneType):
      return NoneType()
    if isinstance(true_type, NoneType):
      return OptionalType(false_type) if not isinstance(false_type, OptionalType) else false_type
    if isinstance(false_type, NoneType):
      return OptionalType(true_type) if not isinstance(true_type, OptionalType) else true_type

    if true_type.is_compatible(false_type):
      if isinstance(true_type, PrimitiveType) and true_type.name == "int" and isinstance(false_type, PrimitiveType) and false_type.name == "float":
        return PrimitiveType("float")
      return false_type if not false_type.is_compatible(true_type) else true_type
    elif false_type.is_compatible(true_type):
      if isinstance(false_type, PrimitiveType) and false_type.name == "int" and isinstance(true_type, PrimitiveType) and true_type.name == "float":
        return PrimitiveType("float")
      return true_type

    self.error(f"Incompatible types in ternary branches: '{true_type}' and '{false_type}'.")
    return true_type

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> Type:
    expr_type = self.visit(node.expr)
    if node.op in ("-", "+"):
      if isinstance(expr_type, PrimitiveType) and expr_type.name in ("int", "float"):
        return expr_type
      self.error(f"Unary operator '{node.op}' requires a numeric type, got '{expr_type}'.")
      return expr_type
    elif node.op == "!":
      if isinstance(expr_type, PrimitiveType) and expr_type.name == "bool":
        return expr_type
      self.error(f"Unary operator '!' requires a boolean type, got '{expr_type}'.")
      return PrimitiveType("bool")
    return PrimitiveType("none")

  def visit_CastExprNode(self, node: CastExprNode) -> Type:
    expr_type = self.visit(node.expr)
    target_type = self._resolve_type_node(node.target_type)

    if expr_type.is_compatible(target_type):
      return target_type

    is_expr_num = isinstance(expr_type, PrimitiveType) and expr_type.name in ("int", "float", "bool")
    is_target_num = isinstance(target_type, PrimitiveType) and target_type.name in ("int", "float", "bool")
    if is_expr_num and is_target_num:
      return target_type

    if isinstance(expr_type, EnumType) and (isinstance(target_type, StringType) or (isinstance(target_type, PrimitiveType) and target_type.name == "int")):
      return target_type

    if isinstance(expr_type, StringType):
      if isinstance(target_type, PrimitiveType) and target_type.name in ("int", "float", "bool"):
        self.error(f"Cannot cast 'String' to '{target_type.name}' using 'as'. Use '.to_{target_type.name}()' instance method instead.")
        return target_type

    self.error(f"Cannot cast type '{expr_type}' to '{target_type}'.")
    return target_type

  def _get_lvalue_path(self, node: ASTNode) -> Optional[tuple[str, List[str]]]:
    """Resolves an AST node to its root variable name and field path if it is an lvalue."""
    return ArenaChecker.get_lvalue_path(self.symbol_table, node)

  def _is_reference_type(self, type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    return ArenaChecker.is_reference_type(type_obj)

  def _check_aliasing(self, node: CallNode, signature: FunctionType, is_constructor: bool) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    ArenaChecker.check_aliasing(self, node, signature, is_constructor)

  def visit_CallNode(self, node: CallNode) -> Type:
    # Generic function resolution & monomorphization
    sym = None
    mod_sym = None
    if isinstance(node.callee, IdentifierNode):
      sym = self.symbol_table.lookup(node.callee.name)
    elif isinstance(node.callee, MemberAccessNode) and isinstance(node.callee.receiver, IdentifierNode):
      mod_sym = self.symbol_table.lookup(node.callee.receiver.name)
      if isinstance(mod_sym, ModuleSymbol):
        sym = mod_sym.lookup_export(node.callee.member)

    if sym and isinstance(sym, FunctionSymbol) and sym.type_params:
      if node.type_args:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        mangled_name = self._monomorphize_function(sym, node.type_args, resolved_type_args)
        if isinstance(node.callee, IdentifierNode):
          node.callee.name = mangled_name
        else:
          node.callee.member = mangled_name
        if mod_sym:
          mono_sym = self.symbol_table.lookup(mangled_name)
          if mono_sym:
            mod_sym.exports[mangled_name] = mono_sym
      else:
        inferred_map = {}
        for idx, arg in enumerate(node.arguments):
          if idx < len(sym.symbol_type.param_types):
            param_t = sym.symbol_type.param_types[idx]
            arg_t = self.visit(arg.expr)
            if isinstance(param_t, GenericTypeParameter):
              inferred_map[param_t.name] = arg_t

        type_arg_nodes = []
        resolved_type_args = []
        for p_name in sym.type_params:
          inf_t = inferred_map.get(p_name, PrimitiveType("int"))
          resolved_type_args.append(inf_t)
          type_arg_nodes.append(BasicTypeNode(str(inf_t)))
        mangled_name = self._monomorphize_function(sym, type_arg_nodes, resolved_type_args)
        if isinstance(node.callee, IdentifierNode):
          node.callee.name = mangled_name
        else:
          node.callee.member = mangled_name
        if mod_sym:
          mono_sym = self.symbol_table.lookup(mangled_name)
          if mono_sym:
            mod_sym.exports[mangled_name] = mono_sym

    # 1. Resolve callee
    callee_type = self.visit(node.callee)

    if getattr(node.callee, "is_string_from", False):
      if len(node.arguments) != 1:
        self.error("String.from() requires exactly 1 argument.")
        return StringType()
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = (
          isinstance(arg_t, StringType)
          or (isinstance(arg_t, PrimitiveType) and arg_t.name in ("int", "float", "bool"))
          or isinstance(arg_t, EnumType)
      )
      if not is_valid:
        self.error(f"Cannot convert type '{arg_t}' to String using String.from().")
      return StringType()

    if getattr(node.callee, "is_enum_from", False):
      enum_t = getattr(node.callee, "enum_type", PrimitiveType("none"))
      if len(node.arguments) != 1:
        self.error(f"{getattr(enum_t, 'name', 'Enum')}.from() requires exactly 1 argument.")
        return OptionalType(enum_t)
      arg_t = self.visit(node.arguments[0].expr)
      is_valid = (
          isinstance(arg_t, StringType)
          or (isinstance(arg_t, PrimitiveType) and arg_t.name == "int")
      )
      if not is_valid:
        self.error(f"Cannot convert type '{arg_t}' to Enum '{getattr(enum_t, 'name', 'Enum')}' using .from(). Requires int or String.")
      return OptionalType(enum_t)

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_array_method", False):
      res = CollectionChecker.check_array_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_map_method", False):
      res = CollectionChecker.check_map_method_call(self, node)
      if res is not None:
        return res

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "Ref":
      if node.arena_expr:
        self.error("Ref() allocations cannot specify an 'in <arena>' clause.", node=node)
      if len(node.arguments) != 1:
        self.error(f"Ref() constructor expects 1 argument, got {len(node.arguments)}.", node=node)
        return RefType(PrimitiveType("none"))
      arg_expr = node.arguments[0].expr
      arg_type = self.visit(arg_expr)
      self._check_value_ownership_transfer(arg_expr, arg_type, node=node)
      ArenaChecker.validate_heap_box_escape(
          self.symbol_table, "Ref", arg_expr,
          lambda msg: self.error(msg, node=node), checker=self
      )
      node.is_ref_constructor = True
      if node.type_args:
        expected_inner = self._resolve_type_node(node.type_args[0])
        if ArenaChecker.type_can_hold_arena_ref(expected_inner, is_box_check=True):
          self.error(
              f"Cannot store arena-referencing type '{expected_inner}' inside 'Ref'.",
              node=node,
          )
        if not arg_type.is_compatible(expected_inner):
          self.error(f"Ref<{expected_inner}> expected argument of type '{expected_inner}', got '{arg_type}'.", node=node)
        return RefType(expected_inner)
      return RefType(arg_type)

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "SharedRef":
      if node.arena_expr:
        self.error("SharedRef() allocations cannot specify an 'in <arena>' clause.", node=node)
      if len(node.arguments) != 1:
        self.error(f"SharedRef() constructor expects 1 argument, got {len(node.arguments)}.", node=node)
        return SharedRefType(PrimitiveType("none"))
      arg_expr = node.arguments[0].expr
      arg_type = self.visit(arg_expr)
      self._check_value_ownership_transfer(arg_expr, arg_type, node=node)
      ArenaChecker.validate_heap_box_escape(
          self.symbol_table, "SharedRef", arg_expr,
          lambda msg: self.error(msg, node=node), checker=self
      )
      node.is_shared_ref_constructor = True
      if isinstance(arg_type, RefType):
        inner_t = arg_type.inner_type
      else:
        inner_t = arg_type
      if node.type_args:
        expected_inner = self._resolve_type_node(node.type_args[0])
        if ArenaChecker.type_can_hold_arena_ref(expected_inner, is_box_check=True):
          self.error(
              f"Cannot store arena-referencing type '{expected_inner}' inside 'SharedRef'.",
              node=node,
          )
        if not inner_t.is_compatible(expected_inner):
          self.error(f"SharedRef<{expected_inner}> expected argument of type '{expected_inner}', got '{inner_t}'.", node=node)
        return SharedRefType(expected_inner)
      return SharedRefType(inner_t)

    if isinstance(node.callee, IdentifierNode) and node.callee.name == "WeakRef":
      self.error("WeakRef cannot be constructed directly; use 'shared_ref.downgrade()'.", node=node)
      return WeakRefType(PrimitiveType("none"))

    signature = None
    is_constructor = False

    # Constructor resolution
    if isinstance(callee_type, StructType):
      if callee_type.type_params:
        if node.type_args:
          resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
          callee_type = self._monomorphize_struct(callee_type, node.type_args, resolved_type_args)
          if isinstance(node.callee, IdentifierNode):
            node.callee.name = callee_type.name
        else:
          self.error(f"Generic struct '{callee_type.name}' requires explicit type arguments.")
          return callee_type

      is_constructor = True
      # Look up constructor
      init_method = callee_type.methods.get("__init__")
      if not init_method:
        self.error(f"Struct '{callee_type.name}' has no '__init__' constructor defined.")
        return callee_type
      signature = init_method.method_type
      # Match arguments
      self._check_arguments(node.arguments, signature, is_constructor=True)
      if callee_type.is_prototype and not node.arena_expr:
        self.error(f"Proto constructor call for '{callee_type.name}' requires an explicit arena via 'in <arena>'.")
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
    else:
      # Standard function/method resolution
      if not isinstance(callee_type, FunctionType):
        self.error("Target is not callable.")
        return PrimitiveType("none")
      if node.arena_expr:
        self.error("The 'in <arena>' clause can only be used on struct/proto instantiations and clone expressions.")
      signature = callee_type
      self._check_arguments(node.arguments, signature, callee_node=node.callee)

    # Perform borrow checking / aliasing rules
    if signature:
      self._check_aliasing(node, signature, is_constructor)
      ArenaChecker.check_call_var_sink_escape(self, node, signature, is_constructor)

    # Check module-level var global reentrancy
    callee_id = None
    is_known_func = False
    if isinstance(node.callee, IdentifierNode):
      callee_id = node.callee.name
      callee_sym = self.symbol_table.lookup(callee_id)
      if isinstance(callee_sym, FunctionSymbol):
        is_known_func = True
    elif isinstance(node.callee, MemberAccessNode):
      recv_t = self.node_types.get(node.callee.receiver)
      if isinstance(recv_t, StructType):
        callee_id = f"{recv_t.name}.{node.callee.member}"
      else:
        callee_id = node.callee.member
      is_known_func = True

    callee_transitive = getattr(self, "func_transitive_globals", {})
    callee_dynamic = getattr(self, "func_transitive_dynamic", set())
    matching_keys = [
        k for k in callee_transitive
        if k == callee_id or k.endswith(f".{callee_id}")
    ] if callee_id else []

    for arg in node.arguments:
      arg_path = ArenaChecker.get_lvalue_path(self.symbol_table, arg.expr)
      if arg_path:
        root, _ = arg_path
        if root in getattr(self, "module_var_globals", set()):
          root_sym = self.symbol_table.lookup(root)
          if (
              isinstance(root_sym, VariableSymbol)
              and ArenaChecker.is_reference_type(root_sym.symbol_type)
          ):
            if root in getattr(self, "exported_var_globals", set()):
              self.error(
                  f"Cannot pass exported mutable global '{root}' by reference.",
                  node=node,
              )
            elif (
                not is_known_func
                or any(k in callee_dynamic for k in matching_keys)
            ):
              self.error(
                  f"Cannot pass mutable global '{root}' by reference to "
                  "dynamic or higher-order callee.",
                  node=node,
              )
            elif any(
                root in callee_transitive.get(k, set()) for k in matching_keys
            ):
              self.error(
                  f"Cannot pass mutable global '{root}' by reference: callee "
                  f"accesses '{root}' in its call graph (reentrant global "
                  "aliasing hazard).",
                  node=node,
              )

    if isinstance(node.callee, MemberAccessNode):
      recv_path = ArenaChecker.get_lvalue_path(
          self.symbol_table, node.callee.receiver
      )
      if recv_path:
        root, _ = recv_path
        if root in getattr(self, "module_var_globals", set()):
          root_sym = self.symbol_table.lookup(root)
          if (
              isinstance(root_sym, VariableSymbol)
              and ArenaChecker.is_reference_type(root_sym.symbol_type)
          ):
            if any(
                root in callee_transitive.get(k, set()) for k in matching_keys
            ):
              self.error(
                  f"Cannot invoke method '{node.callee.member}' on mutable "
                  f"global '{root}': method accesses '{root}' in its call "
                  "graph (reentrant global aliasing hazard).",
                  node=node,
              )

    if is_constructor:
      return callee_type
    ret_type = signature.return_type
    if isinstance(node.callee, MemberAccessNode) and node.callee.is_optional:
      if not isinstance(ret_type, OptionalType):
        ret_type = OptionalType(ret_type)

    if isinstance(ret_type, CoroutineType):
      coro_borrows: Set[str] = set()
      if isinstance(node.callee, MemberAccessNode):
        r_path = ArenaChecker.get_lvalue_path(
            self.symbol_table, node.callee.receiver
        )
        if r_path:
          root, _ = r_path
          r_sym = self.symbol_table.lookup(root)
          if (
              isinstance(r_sym, VariableSymbol)
              and r_sym.scope_defined is not None
              and r_sym.scope_defined.parent is not None
          ):
            coro_borrows.add(r_sym.name)
            coro_borrows.update(r_sym.stack_borrow_symbols)
        coro_borrows.update(
            ArenaChecker.collect_stack_borrow_symbols(
                self.symbol_table, node.callee.receiver, self
            )
        )
      for arg in node.arguments:
        a_path = ArenaChecker.get_lvalue_path(self.symbol_table, arg.expr)
        if a_path:
          root, _ = a_path
          a_sym = self.symbol_table.lookup(root)
          if (
              isinstance(a_sym, VariableSymbol)
              and a_sym.scope_defined is not None
              and a_sym.scope_defined.parent is not None
              and (
                  ArenaChecker.is_reference_type(a_sym.symbol_type)
                  or a_sym.is_mutable
              )
          ):
            coro_borrows.add(a_sym.name)
            coro_borrows.update(a_sym.stack_borrow_symbols)
        coro_borrows.update(
            ArenaChecker.collect_stack_borrow_symbols(
                self.symbol_table, arg.expr, self
            )
        )
      node.stack_borrow_symbols = coro_borrows

    return ret_type

  def _check_arguments(self, arguments: List[ArgumentNode], signature: FunctionType, is_constructor: bool = False, callee_node: Optional[ASTNode] = None) -> None:
    """Helper to match argument lists against signatures (including parameter modes)."""
    expected_param_types = signature.param_types
    expected_param_names = signature.param_names or []
    if getattr(signature, "has_self", False) and isinstance(callee_node, MemberAccessNode):
      expected_param_types = signature.param_types[1:]
      expected_param_names = signature.param_names[1:] if signature.param_names else []

    num_defaults = getattr(signature, "num_defaults", 0)
    min_required = max(0, len(expected_param_types) - num_defaults)
    if len(arguments) < min_required:
      self.error(f"Not enough arguments passed to call. Expected at least {min_required}, got {len(arguments)}.")
      return

    for idx, arg in enumerate(arguments):
      # Pass expected parameter type for lambda type inference
      old_expected = self.expected_type
      param_idx = idx
      if arg.name and expected_param_names and arg.name in expected_param_names:
        param_idx = expected_param_names.index(arg.name)

      if param_idx < len(expected_param_types):
        self.expected_type = expected_param_types[param_idx]
      else:
        self.expected_type = None

      arg_type = self.visit(arg.expr)
      self.expected_type = old_expected

      if self.is_in_del and isinstance(arg.expr, IdentifierNode) and arg.expr.name == "self":
        self.error(
            "Cannot pass 'self' as an argument from destructor '__del__'; 'self' cannot escape destruction.",
            node=arg.expr,
        )

      is_test_assert = getattr(signature, "is_testing_assertion", False)
      if param_idx < len(expected_param_types):
        param_type = expected_param_types[param_idx]
        param_is_var = False
        param_mutabilities = getattr(signature, "param_mutabilities", None)
        if param_mutabilities:
          mut_idx = param_idx
          if getattr(signature, "has_self", False) and isinstance(callee_node, MemberAccessNode):
            mut_idx = param_idx + 1
          if mut_idx < len(param_mutabilities):
            param_is_var = param_mutabilities[mut_idx]

        effective_arg_type = arg_type
        # Auto-borrowing
        if isinstance(arg_type, RefType) and not isinstance(param_type, RefType):
          effective_arg_type = arg_type.inner_type
          arg.is_auto_borrow = True
        elif isinstance(arg_type, SharedRefType) and not isinstance(param_type, SharedRefType):
          if param_is_var:
            self.error(f"Cannot pass 'SharedRef<{arg_type.inner_type}>' as mutable 'var' parameter; shared references are read-only borrows.")
          else:
            effective_arg_type = arg_type.inner_type
            arg.is_auto_borrow = True

        # Explicit move check when passing to RefType parameter
        if isinstance(param_type, RefType):
          if isinstance(arg.expr, IdentifierNode) and not isinstance(arg.expr, MoveNode):
            self.error(f"Cannot pass move-only type '{arg_type}' by value; use explicit 'move {arg.expr.name}' to transfer ownership.")
          elif isinstance(arg.expr, (MemberAccessNode, IndexExprNode)):
            self.error(f"Cannot copy or partially move move-only type '{arg_type}' out of a field or collection index.")

        if not is_test_assert and not effective_arg_type.is_compatible(param_type):
          self.error(f"Argument type mismatch at position {idx+1}. Expected '{param_type}', got '{arg_type}'.")
      else:
        # Extra parameter
        if not is_constructor and not is_test_assert:
          self.error("Too many arguments passed to call.")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> Type:
    if isinstance(node.receiver, MoveNode):
      self.error(f"Cannot access member '{node.member}' on moved variable '{node.receiver.name}'.", node=node)
      return PrimitiveType("none")
    receiver_type = self.visit(node.receiver)

    # Optional chaining check
    if node.is_optional:
      if not isinstance(receiver_type, OptionalType):
        self.error("Optional chaining '?.' requires an optional receiver.")
        return PrimitiveType("none")
      receiver_type = receiver_type.base_type
    else:
      if isinstance(receiver_type, OptionalType):
        self.error("Must use optional chaining '?.' to access properties on an optional receiver.")
        return PrimitiveType("none")

    if isinstance(receiver_type, StringType):
      if node.member == "from":
        node.is_string_from = True
        return FunctionType([StringType()], StringType())
      method = STRING_METHODS.get(node.member)
      if method:
        node.is_string_method = True
        return method
      self.error(f"String has no method '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, ArrayType):
      return CollectionChecker.resolve_array_member(self, node, receiver_type)

    if isinstance(receiver_type, MapType):
      return CollectionChecker.resolve_map_member(self, node, receiver_type)

    if isinstance(receiver_type, CoroutineType):
      if node.member in COROUTINE_METHODS:
        node.is_coroutine_method = True
        node.coroutine_method = node.member
        node.coroutine_receiver_type = receiver_type
        y_type = receiver_type.yield_type
        if node.member == "step":
          ret_t = NoneType() if isinstance(y_type, NoneType) else OptionalType(y_type)
          return FunctionType([receiver_type], ret_t, param_names=["self"], has_self=True)
        elif node.member == "is_done":
          return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
        elif node.member == "reset":
          return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
      self.error(f"Coroutine has no method '{node.member}'.")
      return PrimitiveType("none")

    assertion_names = (
        "assert_true", "assert_false", "assert_eq", "assert_ne",
        "assert_almost_eq", "assert_none", "assert_not_none",
        "expect_true", "expect_false", "expect_eq", "expect_ne",
        "expect_almost_eq", "expect_none", "expect_not_none"
    )
    if node.member in assertion_names:
      fn_t = FunctionType([], PrimitiveType("none"))
      fn_t.is_testing_assertion = True
      return fn_t

    if isinstance(receiver_type, ModuleType):
      if isinstance(node.receiver, IdentifierNode):
        mod_sym = self.symbol_table.lookup(node.receiver.name)
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(node.member)
          if exp_sym:
            return exp_sym.symbol_type if hasattr(exp_sym, "symbol_type") else exp_sym
      return PrimitiveType("none")

    if isinstance(receiver_type, EnumType):
      if node.member == "from":
        node.is_enum_from = True
        node.enum_type = receiver_type
        return FunctionType([StringType()], OptionalType(receiver_type))
      if node.member in receiver_type.variants:
        return receiver_type
      self.error(f"Enum '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, TraitType):
      method = receiver_type.methods.get(node.member)
      if method:
        if getattr(method, "extern_name", None):
          node.target_name = method.extern_name
        is_static = getattr(method.ast_decl, "modifier", None) == "static"
        node.is_static_method = is_static
        node.is_instance_method = not is_static
        return method
      self.error(f"Trait '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, SharedRefType):
      if node.member == "share":
        node.is_shared_ref_share = True
        node.is_instance_method = True
        return FunctionType([receiver_type], receiver_type, param_names=["self"], has_self=True)
      elif node.member == "downgrade":
        node.is_shared_ref_downgrade = True
        node.is_instance_method = True
        return FunctionType([receiver_type], WeakRefType(receiver_type.inner_type), param_names=["self"], has_self=True)
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, RefType):
      receiver_type = receiver_type.inner_type
      node.is_auto_deref = True
    elif isinstance(receiver_type, WeakRefType):
      if node.member == "upgrade":
        node.is_weak_ref_upgrade = True
        node.is_instance_method = True
        return FunctionType([receiver_type], OptionalType(SharedRefType(receiver_type.inner_type)), param_names=["self"], has_self=True)
      self.error(f"WeakRef has no member '{node.member}'; call '.upgrade()' to access the underlying value.", node=node)
      return PrimitiveType("none")

    if isinstance(receiver_type, ArrayType):
      return CollectionChecker.resolve_array_member(self, node, receiver_type)

    if isinstance(receiver_type, MapType):
      return CollectionChecker.resolve_map_member(self, node, receiver_type)

    if not isinstance(receiver_type, StructType):
      self.error("Member access receiver is not a struct or trait.")
      return PrimitiveType("none")

    # Special member __proto__
    if node.member == "__proto__":
      if not receiver_type.is_prototype:
        self.error(
            f"Cannot access '__proto__' on standard struct '{receiver_type.name}'; '__proto__' is only available on 'proto' instances.",
            node=node,
        )
        return PrimitiveType("none")
      return OptionalType(receiver_type)

    # Special member __del__
    if node.member == "__del__":
      self.error("Destructor '__del__' cannot be manually invoked.")
      return PrimitiveType("none")

    # Resolve field
    field = receiver_type.fields.get(node.member)
    if field:
      # If optional chained, result type is optional
      if node.is_optional:
        return OptionalType(field.field_type)
      return field.field_type

    # Resolve method
    method = receiver_type.get_method(node.member, self.symbol_table)
    if method:
      node.is_static_method = (method.modifier == "static")
      node.is_instance_method = (method.modifier != "static")
      return method.method_type

    self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
    return PrimitiveType("none")

  def visit_CloneNode(self, node: CloneNode) -> Type:
    expr_type = self.visit(node.expr)
    if not isinstance(expr_type, StructType):
      self.error("Clone expression target must be a struct instance.")
      return PrimitiveType("none")

    # Verify struct is a prototype struct (or inherits from one)
    def check_proto(st: StructType, visited: Set[str]) -> bool:
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
      self.error(f"Cannot clone instance of non-proto struct '{expr_type.name}'. Struct must be declared using the 'proto' keyword.")

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
      clone_self_deps = ArenaChecker.collect_arena_deps(
          self.symbol_table, node.expr, self
      )
      clone_self_sym.arena_dep_records = list(clone_self_deps)
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
      self.error(f"Cannot move out of borrowed parameter '{node.name}'.", node=node)
      return sym.symbol_type
    if getattr(sym, "is_borrowed_unwrap", False):
      self.error(f"Cannot move out of borrowed unwrap binding '{node.name}'.", node=node)
      return sym.symbol_type
    if self.current_function is not None and sym.scope_defined is not None and sym.scope_defined.parent is None:
      self.error(f"Cannot move out of module-level global variable '{node.name}'.", node=node)
      return sym.symbol_type
    if sym in self.moved_symbols:
      self.error(f"Use of moved variable '{node.name}'.", node=node)
      return sym.symbol_type

    sym.is_moved = True
    if isinstance(sym.symbol_type, ArenaType):
      sym.arena_generation += 1
    self.moved_symbols.add(sym)
    return sym.symbol_type

  def _infer_lambda_param_type(self, param_name: str, body: "ASTNode") -> Optional[Type]:
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

    def scan(node: "ASTNode") -> Optional[Type]:
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

        if node.op in ("==", "!=", "<", "<=", ">", ">=") and (left_is_param or right_is_param):
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
        for stmt in (node.statements or []):
          result = scan(stmt)
          if result is not None:
            return result
        return None

      if isinstance(node, ReturnNode):
        return scan(node.expr) if node.expr else None

      if isinstance(node, VarDeclNode):
        for expr in (node.exprs or []):
          result = scan(expr)
          if result is not None:
            return result
        return None

      if isinstance(node, ExprStmtNode):
        return scan(node.expr)

      if isinstance(node, CallNode):
        for arg in (node.arguments or []):
          result = scan(arg.expr)
          if result is not None:
            return result
        return None

      if isinstance(node, TernaryExprNode):
        return scan(node.condition) or scan(node.true_expr) or scan(node.false_expr)

      return None

    return scan(body)

  def visit_LambdaNode(self, node: LambdaNode) -> Type:
    if self.is_in_del and self._ast_references_self(node.body):
      self.error("Cannot capture 'self' in a closure inside destructor '__del__'.", node=node)
    self.symbol_table.enter_scope()
    old_moved_symbols = set(self.moved_symbols)
    self.moved_symbols = set()

    expected_func = self.expected_type
    from src.semantics.symbol_table import OptionalType

    if isinstance(expected_func, OptionalType):
      expected_func = expected_func.base_type

    param_types = []
    for idx, p in enumerate(node.parameters):
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
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, is_mutable=False))
      param_types.append(ptype)

    old_func = self.current_function
    old_func_scope = self.current_function_scope
    declared_ret = self._resolve_type_node(node.return_type) if node.return_type else None
    from src.semantics.symbol_table import FunctionSymbol
    lambda_sym = FunctionSymbol("<lambda>", None)
    lambda_sym.return_types = [declared_ret] if declared_ret else []
    self.current_function = lambda_sym
    self.current_function_scope = self.symbol_table.current_scope

    try:
      body_type = self.visit(node.body)
    finally:
      self.current_function = old_func
      self.current_function_scope = old_func_scope

    # Resolve any InferredType placeholders: if the body produced a concrete
    # return type, use it to back-fill params that remained unconstrained.
    resolved_param_types = [
        body_type if isinstance(pt, InferredType) and not isinstance(body_type, (NoneType, InferredType))
        else (PrimitiveType("none") if isinstance(pt, InferredType) else pt)
        for pt in param_types
    ]

    # Lambda expression implicit return
    ret_type = body_type if not isinstance(node.body, BlockNode) else PrimitiveType("none")
    if node.return_type:
      ret_type = self._resolve_type_node(node.return_type)

    self.moved_symbols = old_moved_symbols
    self.symbol_table.exit_scope()
    node.stack_borrow_symbols = self._scan_lambda_stack_borrows(node)
    return FunctionType(resolved_param_types, ret_type)

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> Type:
    if not node.elements:
      if isinstance(self.expected_type, ArrayType):
        if self.expected_type.is_fixed_size and self.expected_type.size != 0:
          self.error(f"Fixed-size array '[{self.expected_type.element_type}; {self.expected_type.size}]' requires exactly {self.expected_type.size} element(s), got 0.", node=node)
        return ArrayType(self.expected_type.element_type, size=0, is_fixed_size=self.expected_type.is_fixed_size)
      return ArrayType(NoneType(), size=0)

    elem_types = [self.visit(e) for e in node.elements]
    for elem_node, etype in zip(node.elements, elem_types):
      self._check_value_ownership_transfer(elem_node, etype, node=elem_node)
    if isinstance(self.expected_type, ArrayType):
      target_elem = self.expected_type.element_type
      for etype in elem_types:
        if not etype.is_compatible(target_elem):
          self.error(f"Array element of type '{etype}' is not compatible with expected element type '{target_elem}'.")
          break
      if self.expected_type.is_fixed_size:
        if len(node.elements) != self.expected_type.size:
          self.error(f"Fixed-size array '[{target_elem}; {self.expected_type.size}]' requires exactly {self.expected_type.size} element(s), got {len(node.elements)}.", node=node)
        return ArrayType(target_elem, size=len(node.elements), is_fixed_size=True)
      return ArrayType(target_elem, size=len(node.elements), is_fixed_size=False)

    first_type = elem_types[0]
    for etype in elem_types[1:]:
      if not etype.is_compatible(first_type) and not first_type.is_compatible(etype):
        self.error("Inconsistent element types in array literal.")
        break
    return ArrayType(first_type, size=len(node.elements), is_fixed_size=False)

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> Type:
    if not node.entries:
      if isinstance(self.expected_type, MapType):
        return MapType(self.expected_type.key_type, self.expected_type.value_type)
      return MapType(NoneType(), NoneType())

    first_key_type = self.visit(node.entries[0].key)
    first_val_type = self.visit(node.entries[0].value)
    self._check_value_ownership_transfer(node.entries[0].key, first_key_type, node=node.entries[0].key)
    self._check_value_ownership_transfer(node.entries[0].value, first_val_type, node=node.entries[0].value)

    def is_valid_key_type(ktype: Type) -> bool:
      return (
          isinstance(ktype, StringType)
          or (isinstance(ktype, PrimitiveType) and ktype.name == "int")
          or isinstance(ktype, EnumType)
      )

    if not is_valid_key_type(first_key_type):
      self.error("Map key must be a string, int, or enum.")

    for entry in node.entries[1:]:
      ktype = self.visit(entry.key)
      vtype = self.visit(entry.value)
      self._check_value_ownership_transfer(entry.key, ktype, node=entry.key)
      self._check_value_ownership_transfer(entry.value, vtype, node=entry.value)

      if not is_valid_key_type(ktype):
        self.error("Map key must be a string, int, or enum.")

      if not ktype.is_compatible(first_key_type) and not first_key_type.is_compatible(ktype):
        self.error("Inconsistent key types in map literal.")

      if not vtype.is_compatible(first_val_type) and not first_val_type.is_compatible(vtype):
        self.error("Inconsistent value types in map literal.")

    return MapType(first_key_type, first_val_type)

  def _get_const_int_value(self, expr: ASTNode) -> Optional[int]:
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

  def _check_array_bounds(self, node: IndexExprNode, array_type: ArrayType) -> None:
    const_idx = self._get_const_int_value(node.index)
    if const_idx is not None:
      size = array_type.size
      if size is not None:
        if const_idx >= size or const_idx < -size:
          self.error(f"Array index out of bounds: index {const_idx} is out of bounds for array of size {size}.", node=node)

  def _check_map_literal_key(self, node: IndexExprNode) -> None:
    if isinstance(node.array, MapLiteralNode) and isinstance(node.index, LiteralNode):
      key_val = str(node.index.value)
      for entry in node.array.entries:
        if isinstance(entry.key, LiteralNode) and str(entry.key.value) == key_val:
          return
      self.error(f"Key '{key_val}' not found in map literal.")

  def visit_IndexExprNode(self, node: IndexExprNode) -> Type:
    if isinstance(node.array, MoveNode):
      self.error(f"Cannot index into moved variable '{node.array.name}'.", node=node)
      return PrimitiveType("none")
    container_type = self.visit(node.array)
    index_type = self.visit(node.index)

    if isinstance(container_type, ArrayType):
      if index_type != PrimitiveType("int"):
        self.error("Array index must be an 'int'.")
      const_idx = self._get_const_int_value(node.index)
      if const_idx is not None:
        self._check_array_bounds(node, container_type)
      return container_type.element_type
    elif isinstance(container_type, MapType):
      if not index_type.is_compatible(container_type.key_type) and not container_type.key_type.is_compatible(index_type):
        self.error(f"Map index type '{index_type}' is not compatible with key type '{container_type.key_type}'.")
      if isinstance(node.array, MapLiteralNode):
        self._check_map_literal_key(node)
      return container_type.value_type
    else:
      self.error("Cannot index non-array type.")
      return PrimitiveType("none")

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

  def visit_StructInitializerNode(self, node: StructInitializerNode) -> Type:
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      self.error(f"Cannot instantiate undefined struct '{node.struct_name}'.")
      return PrimitiveType("none")

    raw_name = node.struct_name

    if struct_type.type_params:
      if node.type_args:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        struct_type = self._monomorphize_struct(struct_type, node.type_args, resolved_type_args)
        node.struct_name = struct_type.name
      else:
        self.error(f"Generic struct '{node.struct_name}' requires explicit type arguments.")
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
          f"Cannot use literal initializer for struct '{raw_name}' because it defines an '__init__' constructor. Use constructor call syntax '{raw_name}(...)' instead."
      )
      return struct_type

    # Validate explicit arena target
    if struct_type.is_prototype and not node.arena_expr:
      self.error(f"Proto instantiation of '{node.struct_name}' requires an explicit arena via 'in <arena>'.")
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
        self.error(f"Positional arguments are not allowed in struct initializer of '{node.struct_name}'. Use named initializers instead.")
        continue

      if field_name not in struct_type.fields:
        self.error(f"Struct '{node.struct_name}' has no field '{field_name}'.")
        continue

      if field_name in initialized:
        self.error(f"Field '{field_name}' is initialized multiple times in struct initializer.")
        continue

      expected_type = struct_type.fields[field_name].field_type
      old_expected = self.expected_type
      self.expected_type = expected_type
      try:
        expr_type = self.visit(field_arg.expr)
      finally:
        self.expected_type = old_expected
      self._check_value_ownership_transfer(field_arg.expr, expr_type, node=field_arg.expr)

      if not expr_type.is_compatible(expected_type):
        self.error(
            f"Field '{field_name}' in struct '{node.struct_name}' initializer "
            f"has type '{expr_type}', but expected '{expected_type}'."
        )

      initialized.add(field_name)

    # Verify all non-optional and non-default fields are initialized
    for f_name, f_obj in struct_type.fields.items():
      if (f_name not in initialized
          and not isinstance(f_obj.field_type, OptionalType)
          and not f_obj.has_default):
        self.error(f"Struct initializer for '{node.struct_name}' is missing required field '{f_name}'.")

    return struct_type
