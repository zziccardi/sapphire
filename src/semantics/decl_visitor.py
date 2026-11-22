"""Declaration and block AST visitor methods for TypeChecker."""

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


class DeclVisitorMixin:
  """Provides AST visitor methods for top-level declarations and blocks."""

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
        if isinstance(decl, VarDeclNode) and getattr(
            decl, "_prechecked_module_const", False
        ):
          for name, sym in getattr(decl, "_prechecked_symbols", {}).items():
            if sym is not None:
              self.symbol_table.define(name, sym)
          continue
        if getattr(decl, "_already_type_checked", False):
          continue
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

  def _check_no_explicit_self(
      self, parameters: List[ParameterNode], node: ASTNode
  ) -> None:
    """Rejects explicit 'self' parameters in functions, methods, and traits."""
    for p in parameters:
      if p.name == "self":
        self.error(
            "Explicit 'self' parameter is not permitted; 'self' is always "
            "implicit in methods and traits.",
            node=node,
        )
        return

  def _check_duplicate_params(
      self, parameters: List[ParameterNode], node: ASTNode
  ) -> None:
    """Rejects duplicate parameter names in function, method, and trait signatures."""
    seen: Set[str] = set()
    for p in parameters:
      if p.name in seen:
        self.error(
            f"Duplicate parameter name '{p.name}'.",
            node=node,
        )
      seen.add(p.name)

  def visit_ImplBlockNode(self, node: ImplBlockNode) -> None:
    for member in node.members:
      self._check_no_explicit_self(member.func_decl.parameters, member.func_decl)
    if self._get_impl_type_params(node):
      return
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      return

    self.current_struct = struct_type
    self._current_impl_trait = None

    # If implementing a trait, verify contract is fully satisfied
    if node.trait_name:
      trait_type = self.symbol_table.lookup_type(node.trait_name)
      if isinstance(trait_type, TraitType):
        self._current_impl_trait = trait_type
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
              impl_method = struct_type.methods[trait_method_name]
              impl_sig = impl_method.method_type
              if impl_sig != expected_sig:
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"has signature {impl_sig}, but trait '{node.trait_name}' "
                    f"requires {expected_sig}."
                )
              trait_mod = getattr(trait_sig.ast_decl, "modifier", None)
              impl_mod = impl_method.modifier
              if trait_mod is None and impl_mod == "var":
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"is declared 'var', but trait '{node.trait_name}' requires "
                    "an immutable method."
                )
              elif trait_mod != "static" and impl_mod == "static":
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"is declared 'static', but trait '{node.trait_name}' requires "
                    "an instance method."
                )
              elif trait_mod == "static" and impl_mod == "var":
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"is declared 'var', but trait '{node.trait_name}' requires "
                    "a 'static' method."
                )
      else:
        self.error(f"Trait '{node.trait_name}' is not defined.")

    # Check each method implementation
    for member in node.members:
      self.visit(member)

    self._current_impl_trait = None
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

  def _check_parameter_defaults(
      self,
      parameters: List[ParameterNode],
      resolved_types: List[Type],
  ) -> None:
    """Type-checks parameter default expressions against declared parameter types."""
    for p, ptype in zip(parameters, resolved_types):
      if p.name == "self" or getattr(p, "default_expr", None) is None:
        continue
      old_expected = self.expected_type
      self.expected_type = ptype
      try:
        expr_type = self.visit(p.default_expr)
      finally:
        self.expected_type = old_expected
      if not expr_type.is_compatible(ptype):
        self.error(
            f"Default expression of type '{expr_type}' is not compatible "
            f"with parameter '{p.name}' of type '{ptype}'.",
            node=p,
        )

  def _check_missing_return(
      self,
      func_decl: FuncDeclNode,
      func_type: FunctionType,
  ) -> None:
    """Verifies that non-void, non-coroutine, non-extern functions return on all paths."""
    if getattr(func_decl, "body", None) is None:
      return
    if any(
        a.name == "extern" for a in getattr(func_decl, "annotations", [])
    ):
      return
    ret_types = func_type.return_types
    if not ret_types:
      return
    if any(isinstance(t, CoroutineType) for t in ret_types):
      return
    if not self._block_always_returns(func_decl.body):
      ret_desc = (
          str(ret_types[0])
          if len(ret_types) == 1
          else f"({', '.join(str(t) for t in ret_types)})"
      )
      self.error(
          f"Function '{func_decl.name}' with return type '{ret_desc}' does not "
          "return a value on all code paths.",
          node=func_decl,
      )

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func_decl = node.func_decl
    struct_type = self.current_struct
    self._check_duplicate_params(func_decl.parameters, func_decl)

    # Enter scope of method
    self.symbol_table.enter_scope()
    old_moved_symbols = set(self.moved_symbols)
    old_uninit_symbols = set(self.uninitialized_symbols)
    self._restore_moved_symbols(set())
    self.uninitialized_symbols = set()
    old_function_scope = self.current_function_scope
    self.current_function_scope = self.symbol_table.current_scope
    old_current_function = self.current_function

    resolved_params = [
        (
            struct_type
            if p.name == "self" and p.param_type is None
            else self._resolve_type_node(p.param_type)
        )
        for p in func_decl.parameters
    ]
    self._check_parameter_defaults(func_decl.parameters, resolved_params)

    # Define parameters in scope before evaluating base initializers
    for p, ptype in zip(func_decl.parameters, resolved_params):
      if p.name == "self":
        continue
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))
    self._on_parameters_defined(func_decl.parameters, resolved_params)

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
                  self._check_arguments(
                      base_init.arguments,
                      init_method.method_type,
                      is_constructor=True,
                      call_node=base_init,
                  )
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
    param_mutabilities = [p.is_mutable for p in func_decl.parameters]
    ret_types = self._resolve_return_types(func_decl)
    num_defaults = sum(1 for p in func_decl.parameters if getattr(p, "default_expr", None) is not None)
    param_defaults = [getattr(p, "default_expr", None) for p in func_decl.parameters]
    self.current_function = FunctionType(
        resolved_params,
        ret_types,
        param_mutabilities,
        param_names=[p.name for p in func_decl.parameters],
        num_defaults=num_defaults,
        param_defaults=param_defaults,
        ast_decl=func_decl,
    )

    # Visit body
    self.visit(func_decl.body)
    self._check_missing_return(func_decl, self.current_function)

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
    self.current_function = old_current_function
    self.current_function_scope = old_function_scope
    self._restore_moved_symbols(old_moved_symbols)
    self.uninitialized_symbols = old_uninit_symbols

    self.symbol_table.exit_scope()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    for member in node.members:
      self._check_no_explicit_self(member.parameters, member)
      self._check_duplicate_params(member.parameters, member)
    if node.type_params:
      return
    trait_type = self.symbol_table.lookup_type(node.name)
    if not isinstance(trait_type, TraitType):
      return
    for member in node.members:
      fn_type = trait_type.methods.get(member.name)
      if fn_type is not None:
        self._check_parameter_defaults(member.parameters, fn_type.param_types)

  def _on_parameters_defined(
      self, parameters: list, resolved_params: list
  ) -> None:
    """Optional hook invoked inside a function/method scope after parameters are defined."""
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    self._check_no_explicit_self(node.parameters, node)
    self._check_duplicate_params(node.parameters, node)
    if hasattr(node, "annotations") and node.annotations:
      DeclarationPass.validate_annotations(self, node.annotations, node=node)
    if node.base_initializers:
      self.error("Base initializers are only permitted on constructor '__init__'.", node=node)
    if node.type_params:
      return
    # Register parameters and check body
    self.symbol_table.enter_scope()
    old_moved_symbols = set(self.moved_symbols)
    old_uninit_symbols = set(self.uninitialized_symbols)
    self._restore_moved_symbols(set())
    self.uninitialized_symbols = set()
    old_function_scope = self.current_function_scope
    self.current_function_scope = self.symbol_table.current_scope
    old_current_function = self.current_function

    resolved_params = [self._resolve_type_node(p.param_type) for p in node.parameters]
    self._check_parameter_defaults(node.parameters, resolved_params)

    for p, ptype in zip(node.parameters, resolved_params):
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))
    self._on_parameters_defined(node.parameters, resolved_params)

    param_mutabilities = [p.is_mutable for p in node.parameters]
    ret_types = self._resolve_return_types(node)
    num_defaults = sum(1 for p in node.parameters if getattr(p, "default_expr", None) is not None)
    param_defaults = [getattr(p, "default_expr", None) for p in node.parameters]
    self.current_function = FunctionType(
        resolved_params,
        ret_types,
        param_mutabilities,
        param_names=[p.name for p in node.parameters],
        num_defaults=num_defaults,
        param_defaults=param_defaults,
        ast_decl=node,
    )

    self.visit(node.body)
    self._check_missing_return(node, self.current_function)

    self.current_function = old_current_function
    self.current_function_scope = old_function_scope
    self._restore_moved_symbols(old_moved_symbols)
    self.uninitialized_symbols = old_uninit_symbols
    self.symbol_table.exit_scope()

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.symbol_table.enter_scope()
    try:
      self._visit_stmts_with_unwrap_nll(node.statements)
    finally:
      cur_scope = self.symbol_table.current_scope
      self.moved_symbols = {s for s in self.moved_symbols if s.scope_defined != cur_scope}
      self.uninitialized_symbols = {
          s for s in self.uninitialized_symbols if s.scope_defined != cur_scope
      }
      self.symbol_table.exit_scope()

