"""Type resolution and pre-pass global/lambda analysis for TypeChecker."""

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


class TypeResolverMixin:
  """Provides type-node resolution and global/lambda static analysis helpers."""

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

