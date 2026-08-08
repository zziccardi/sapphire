"""Semantic analyzer and type checker implementation for Sapphire.

This module walks the Sapphire AST, constructs symbol tables, performs type
checking and type inference, and validates all semantic constraints of the
Sapphire language.
"""

import copy
from typing import Any, Dict, List, Optional

from src.parser.ast import *
from src.semantics.symbol_table import (
    SymbolTable,
    Type,
    PrimitiveType,
    StringType,
    OptionalType,
    FunctionType,
    MultiReturnType,
    StructField,
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
    StructSymbol,
    TraitSymbol,
    EnumSymbol,
    ModuleSymbol,
    STRING_METHODS,
    ARRAY_METHODS,
    MAP_METHODS,
)
from src.cli.diagnostics import format_diagnostic
from src.common.errors import SapphireError, SapphireTypeError, SemanticError
from src.semantics.arena_checker import ArenaChecker
from src.semantics.generics_checker import GenericsChecker


class TypeChecker:
  """Walks the AST to perform type-checking and semantic validation."""

  def __init__(self, source_file_path: Optional[str] = None, source_content: Optional[Any] = None):
    self.symbol_table = SymbolTable()
    self.errors: List[str] = []
    self.source_file_path: Optional[str] = source_file_path
    self.source_content: Optional[Any] = source_content
    self.current_function: Optional[FunctionType] = None
    self.current_struct: Optional[StructType] = None
    self.is_in_init: bool = False
    self.is_in_clone_init: bool = False
    self.initialized_fields: set = set()
    self.expected_type: Optional[Type] = None
    self.current_function_scope = None
    self._match_stack: List[List[Type]] = []
    self.loop_depth: int = 0

  def _get_arena_dependency(self, node: ASTNode) -> Optional[str]:
    return ArenaChecker.get_arena_dependency(self.symbol_table, node)

  def _is_descendant_scope(self, child: Optional[object], parent: Optional[object]) -> bool:
    return ArenaChecker.is_descendant_scope(child, parent)


  def _get_target_symbol(self, target: ASTNode) -> Optional[VariableSymbol]:
    if isinstance(target, IdentifierNode):
      sym = self.symbol_table.lookup(target.name)
      if isinstance(sym, VariableSymbol):
        return sym
    elif isinstance(target, MemberAccessNode):
      return self._get_target_symbol(target.receiver)
    return None

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
    arg_names = [self._mangle_type_name(t) for t in resolved_type_args]
    mangled_name = f"{generic_struct_type.name}__{'_'.join(arg_names)}"
    existing = self.symbol_table.lookup_type(mangled_name)
    if existing and isinstance(existing, StructType):
      return existing

    if not generic_struct_type.ast_decl:  # pragma: no cover
      return generic_struct_type

    param_map = dict(zip(generic_struct_type.type_params, type_arg_nodes))
    cloned_decl = self._substitute_ast(generic_struct_type.ast_decl, param_map)
    cloned_decl.name = mangled_name
    cloned_decl.type_params = []

    mono_struct_type = StructType(mangled_name, parent_names=cloned_decl.parent_names, is_prototype=cloned_decl.is_prototype)
    root_scope = self.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    root_scope.define_type(mangled_name, mono_struct_type)
    root_scope.define(mangled_name, StructSymbol(mangled_name, mono_struct_type))

    # Resolve fields for monomorphized struct
    for f in cloned_decl.fields:
      ftype = self._resolve_field_type(f, mono_struct_type.name)
      has_default = f.default_expr is not None or self._has_implicit_default_value(ftype)
      mono_struct_type.fields[f.name] = StructField(
          f.name, ftype, f.is_mutable, has_default=has_default, has_explicit_default=f.default_expr is not None
      )

    # Instantiate generic impl blocks matching generic_struct_type.name
    if hasattr(self, "program") and self.program:
      for decl in self.program.declarations:
        if isinstance(decl, ImplBlockNode) and decl.struct_name == generic_struct_type.name:
          cloned_impl = self._substitute_ast(decl, param_map)
          cloned_impl.struct_name = mangled_name
          cloned_impl.type_params = []
          cloned_impl.struct_type_args = []
          cloned_impl.trait_type_args = []
          for member in cloned_impl.members:
            func_decl = member.func_decl
            p_types = [self._resolve_type_node(p.param_type) for p in func_decl.parameters]
            ret_t = self._resolve_return_types(func_decl)
            num_defaults = sum(1 for p in func_decl.parameters if getattr(p, "default_expr", None) is not None)
            sig = FunctionType(p_types, ret_t, [p.is_mutable for p in func_decl.parameters], [p.name for p in func_decl.parameters], num_defaults=num_defaults)
            mono_struct_type.methods[func_decl.name] = StructMethod(func_decl.name, sig, member.modifier)
          self.program.declarations.append(cloned_impl)

      self.program.declarations.append(cloned_decl)

    return mono_struct_type

  def _monomorphize_function(
      self, func_sym: FunctionSymbol, type_arg_nodes: List[TypeNode], resolved_type_args: List[Type]
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete type arguments."""
    arg_names = [self._mangle_type_name(t) for t in resolved_type_args]
    mangled_name = f"{func_sym.name}__{'_'.join(arg_names)}"
    existing = self.symbol_table.lookup(mangled_name)
    if existing and isinstance(existing, FunctionSymbol):
      return mangled_name

    if not func_sym.ast_decl:  # pragma: no cover
      return func_sym.name

    param_map = dict(zip(func_sym.type_params, type_arg_nodes))
    cloned_func = self._substitute_ast(func_sym.ast_decl, param_map)
    cloned_func.name = mangled_name
    cloned_func.type_params = []

    p_types = [self._resolve_type_node(p.param_type) for p in cloned_func.parameters]
    ret_t = self._resolve_return_types(cloned_func)
    mono_func_type = FunctionType(
        p_types,
        ret_t,
        [p.is_mutable for p in cloned_func.parameters],
        [p.name for p in cloned_func.parameters],
    )
    mono_func_sym = FunctionSymbol(mangled_name, mono_func_type, ast_decl=cloned_func)
    root_scope = self.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    root_scope.define(mangled_name, mono_func_sym)

    if hasattr(self, "program") and self.program:
      self.program.declarations.append(cloned_func)

    # Type check the body of the monomorphized function
    self.visit_FuncDeclNode(cloned_func)
    return mangled_name

  def _declare_imports(self, program: ProgramNode) -> None:
    """Pre-pass to register imported module symbols."""
    import os
    from src.semantics.module_resolver import resolve_module_path

    for imp in getattr(program, "imports", []):
      module_name = imp.alias if imp.alias else imp.path.split(".")[-1]
      existing = self.symbol_table.lookup_current_scope(module_name)
      is_predefined = existing is not None and isinstance(existing, ModuleSymbol)
      if not is_predefined:
        mod_sym = ModuleSymbol(module_name, imp.path)
        self.symbol_table.define(module_name, mod_sym)
        self.symbol_table.define_type(module_name, ModuleType(imp.path))
      else:
        mod_sym = existing

      if imp.path == "std.testing" or imp.path.startswith("std.testing"):
        mod_sym.exports["TestCase"] = self.symbol_table.testcase_trait

      # Resolve imported module file path on disk
      target_file = resolve_module_path(imp.path, source_file_path=getattr(self, "source_file_path", None))

      is_builtin = (imp.path == "std.testing" or imp.path.startswith("std.testing"))
      if not target_file and not is_builtin and not is_predefined:
        self.error(f"Cannot resolve imported module '{imp.path}'. Module file not found.", node=imp)

      if target_file:
          try:
            with open(target_file, "r", encoding="utf-8") as f:
              sub_code = f.read()
            from src.parser.gen.SapphireLexer import SapphireLexer
            from src.parser.gen.SapphireParser import SapphireParser
            from src.parser.ast_builder import ASTBuilder

            from antlr4 import InputStream, CommonTokenStream

            try:
              sub_lexer = SapphireLexer(InputStream(sub_code))
              sub_lexer.removeErrorListeners()
              sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
              sub_parser.removeErrorListeners()
              sub_ast = ASTBuilder().visit(sub_parser.program())
              mod_file_path = os.path.abspath(target_file)
              from pygls.uris import from_fs_path
              mod_file_uri = from_fs_path(mod_file_path)
              def _mark_file_uri(node):
                if isinstance(node, ASTNode):
                  node.file_uri = mod_file_uri
                  for v in node.__dict__.values():
                    if isinstance(v, list):
                      for item in v:
                        if isinstance(item, ASTNode):
                          _mark_file_uri(item)
                    elif isinstance(v, ASTNode):
                      _mark_file_uri(v)
              if sub_ast:
                _mark_file_uri(sub_ast)

              sub_checker = TypeChecker(source_file_path=target_file)
              try:
                sub_checker.check(sub_ast)
              except Exception:
                pass

              mod_sym.file_path = os.path.abspath(target_file)
              # Populate mod_sym exports from sub_checker
              if getattr(sub_ast, "export_block", None):
                for spec in sub_ast.export_block.specifiers:
                  export_name = spec.alias or spec.symbol
                  if spec.module_prefix:
                    prefix_sym = sub_checker.symbol_table.lookup(spec.module_prefix)
                    if isinstance(prefix_sym, ModuleSymbol):
                      exp = prefix_sym.lookup_export(spec.symbol)
                      if exp:
                        mod_sym.exports[export_name] = exp
                  else:
                    exp = sub_checker.symbol_table.lookup_type(spec.symbol) or sub_checker.symbol_table.lookup(spec.symbol)
                    if exp:
                      mod_sym.exports[export_name] = exp
              else:
                sub_root = sub_checker.symbol_table.current_scope
                while sub_root.parent:
                  sub_root = sub_root.parent
                for name, sym in sub_root.symbols.items():
                  mod_sym.exports[name] = sym
                for name, t in sub_root.types.items():
                  if name not in ("int", "float", "bool", "String", "none", "Arena"):
                    mod_sym.exports[name] = t
              if is_builtin:
                mod_sym.exports["TestCase"] = self.symbol_table.testcase_trait
            except Exception:  # pragma: no cover
              pass
          except Exception:  # pragma: no cover
            pass

  def _declare_globals(self, program: ProgramNode) -> None:
    """Pre-pass to register types and global function symbols in the symbol table."""
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        struct_type = StructType(decl.name, parent_names=decl.parent_names, is_prototype=decl.is_prototype, type_params=decl.type_params, ast_decl=decl)
        self.symbol_table.define_type(decl.name, struct_type)
        self.symbol_table.define(decl.name, StructSymbol(decl.name, struct_type))

      elif isinstance(decl, EnumDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        current_val: Union[int, str] = 0
        is_string_enum = any(isinstance(m.value, str) for m in decl.members)
        variants: Dict[str, Union[int, str]] = {}
        seen_members = set()
        for member in decl.members:
          if member.name in seen_members:
            self.error(f"Duplicate member '{member.name}' in enum '{decl.name}'.")
            continue
          seen_members.add(member.name)
          if member.value is not None:
            current_val = member.value
          elif is_string_enum and isinstance(current_val, str):
            current_val = member.name
          variants[member.name] = current_val
          if isinstance(current_val, int):
            current_val += 1
        enum_type = EnumType(decl.name, variants)
        enum_type.ast_decl = decl
        self.symbol_table.define_type(decl.name, enum_type)
        self.symbol_table.define(decl.name, EnumSymbol(decl.name, enum_type))

      elif isinstance(decl, TraitDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        trait_type = TraitType(decl.name, type_params=decl.type_params, ast_decl=decl)
        # Populate trait method signatures
        if decl.type_params:
          self.symbol_table.enter_scope()
          for tp in decl.type_params:
            self.symbol_table.define_type(tp, GenericTypeParameter(tp))
        for member in decl.members:
          p_types = []
          for p in member.parameters:
            if p.name == "self" and p.param_type is None:
              p_types.append(trait_type)
            else:
              p_types.append(self._resolve_type_node(p.param_type))
          ret_t = self._resolve_return_types(member)
          p_mutabilities = [p.is_mutable for p in member.parameters]
          param_names = [p.name for p in member.parameters]
          has_self = bool(param_names) and param_names[0] == "self"
          extern_name = None
          for ann in getattr(member, "annotations", []):
            if ann.name == "export" and ann.arg:
              extern_name = ann.arg
              break
          num_defaults = sum(1 for p in member.parameters if getattr(p, "default_expr", None) is not None)
          param_defaults = [getattr(p, "default_expr", None) for p in member.parameters]
          fn_type = FunctionType(
              p_types,
              ret_t,
              p_mutabilities,
              param_names=param_names,
              has_self=has_self,
              extern_name=extern_name,
              num_defaults=num_defaults,
              param_defaults=param_defaults,
              ast_decl=member,
          )
          trait_type.methods[member.name] = fn_type
        if decl.type_params:
          self.symbol_table.exit_scope()
        self.symbol_table.define_type(decl.name, trait_type)
        self.symbol_table.define(decl.name, TraitSymbol(decl.name, trait_type))

      elif isinstance(decl, FuncDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        if decl.type_params:
          self.symbol_table.enter_scope()
          for tp in decl.type_params:
            self.symbol_table.define_type(tp, GenericTypeParameter(tp))
        param_types = []
        param_mutabilities = []
        for p in decl.parameters:
          ptype = self._resolve_type_node(p.param_type)
          param_types.append(ptype)
          param_mutabilities.append(p.is_mutable)
        ret_type = self._resolve_return_types(decl)
        if decl.type_params:
          self.symbol_table.exit_scope()
        num_defaults = sum(1 for p in decl.parameters if getattr(p, "default_expr", None) is not None)
        param_defaults = [getattr(p, "default_expr", None) for p in decl.parameters]
        signature = FunctionType(
            param_types,
            ret_type,
            param_mutabilities,
            param_names=[p.name for p in decl.parameters],
            num_defaults=num_defaults,
            param_defaults=param_defaults,
        )
        self.symbol_table.define(decl.name, FunctionSymbol(decl.name, signature, type_params=decl.type_params, ast_decl=decl))

      elif isinstance(decl, VarDeclNode):
        if any(a.name == "extern" for a in decl.annotations):
          if decl.exprs:
            self.error("An '@extern' variable declaration cannot have an initializer expression.")
          for name, val_type_node in zip(decl.names, decl.val_types):
            if self.symbol_table.lookup_current_scope(name):
              self.error(f"Redefinition of identifier '{name}'.")
              continue
            if not val_type_node:
              self.error(f"An '@extern' variable declaration for '{name}' requires an explicit type annotation.")
              var_type = PrimitiveType("none")
            else:
              var_type = self._resolve_type_node(val_type_node)
            self.symbol_table.define(name, VariableSymbol(name, var_type, decl.is_mutable))

  def _resolve_struct_layouts(self, program: ProgramNode) -> None:
    """Pre-pass to resolve static inheritance field copying and layout sizing."""
    structs_to_process = [d for d in program.declarations if isinstance(d, StructDeclNode) and not d.type_params]
    processed = set()

    visiting = set()

    def process_struct(node: StructDeclNode):
      if node.name in processed:
        return
      if node.name in visiting:
        self.error(f"Circular inheritance detected involving struct '{node.name}'.")
        return
      visiting.add(node.name)

      struct_type = self.symbol_table.lookup_type(node.name)
      if not isinstance(struct_type, StructType):
        visiting.remove(node.name)
        return

      if node.parent_names:
        for parent_name in node.parent_names:
          parent_type = self.symbol_table.lookup_type(parent_name)
          if not parent_type:
            self.error(f"Parent struct '{parent_name}' not found for '{node.name}'.")
          elif not isinstance(parent_type, StructType):
            self.error(f"Parent '{parent_name}' of '{node.name}' is not a struct type.")
          else:
            parent_node = next((s for s in structs_to_process if s.name == parent_name), None)
            if parent_node:
              process_struct(parent_node)
            for field_name, field_obj in parent_type.fields.items():
              if field_name in struct_type.fields:
                self.error(f"Duplicate field '{field_name}' in struct '{node.name}' inherited from multiple parents.")
              else:
                struct_type.fields[field_name] = field_obj

      for f in node.fields:
        ftype = self._resolve_field_type(f, node.name)
        if f.name in struct_type.fields:
          self.error(f"Field '{f.name}' in struct '{node.name}' shadows inherited parent field.")
        has_default = f.default_expr is not None or self._has_implicit_default_value(ftype)
        struct_type.fields[f.name] = StructField(
            f.name, ftype, f.is_mutable, has_default=has_default, has_explicit_default=f.default_expr is not None
        )

      visiting.remove(node.name)
      processed.add(node.name)

    for s in structs_to_process:
      process_struct(s)

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
    return list(decl.type_params) if decl.type_params else []

  def _register_impl_signatures(self, program: ProgramNode) -> None:
    """Pre-pass to register methods defined inside impl blocks onto struct types."""
    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
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
          func_decl = member.func_decl
          # Resolve parameters
          param_types = []
          param_mutabilities = []
          for p in func_decl.parameters:
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

          # Check for duplicate definitions
          if func_decl.name in struct_type.methods:
            self.error(f"Method '{func_decl.name}' redefined in struct '{decl.struct_name}'.")
          struct_type.methods[func_decl.name] = method

          # Register on trait if needed
          if trait_type:
            pass

  def _resolve_return_types(self, node: Any) -> List[Type]:
    if hasattr(node, "return_types") and node.return_types:
      return [self._resolve_type_node(t) for t in node.return_types]
    elif hasattr(node, "return_type") and node.return_type:
      return [self._resolve_type_node(node.return_type)]
    else:
      return [PrimitiveType("none")]

  def _resolve_type_node(self, node: Optional[TypeNode]) -> Type:
    """Helper to map an AST TypeNode into a semantic Type object."""
    if not node:
      return PrimitiveType("none")
    if isinstance(node, BasicTypeNode):
      if node.name == "Array" and node.type_args:
        return ArrayType(self._resolve_type_node(node.type_args[0]))
      if node.name == "Map" and len(node.type_args) >= 2:
        return MapType(self._resolve_type_node(node.type_args[0]), self._resolve_type_node(node.type_args[1]))
      if "." in node.name:
        parts = node.name.split(".")
        mod_sym = self.symbol_table.lookup(parts[0])
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(parts[1])
          if exp_sym:
            return exp_sym.symbol_type if hasattr(exp_sym, "symbol_type") else exp_sym
          return EnumType(parts[1]) if ("Mode" in parts[1] or "Code" in parts[1]) else StructType(parts[1])
      resolved = self.symbol_table.lookup_type(node.name)
      if isinstance(resolved, GenericTypeParameter):
        return resolved
      if not resolved:
        self.error(f"Undefined type '{node.name}'.")
        return PrimitiveType("none")
      if node.type_args and isinstance(resolved, StructType) and resolved.type_params:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        if not any(isinstance(t, GenericTypeParameter) for t in resolved_type_args):
          return self._monomorphize_struct(resolved, node.type_args, resolved_type_args)
      return resolved
    if isinstance(node, OptionalTypeNode):
      return OptionalType(self._resolve_type_node(node.base_type))
    if isinstance(node, ArrayTypeNode):
      return ArrayType(self._resolve_type_node(node.element_type))
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
    if isinstance(node, ExprNode) and isinstance(res, Type):
      node.inferred_type = res
    return res

  def generic_visit(self, node: ASTNode) -> Any:
    """Default fallback when no specific visitor method is defined."""
    raise NotImplementedError(f"No visit_{node.__class__.__name__} method defined.")

  # ==========================================
  # Visitor Methods
  # ==========================================

  def visit_ProgramNode(self, node: ProgramNode) -> None:
    for imp in getattr(node, "imports", []):
      self.visit(imp)
    for decl in node.declarations:
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
          self.error(f"Module '{spec.module_prefix}' is not imported.")
        elif mod_sym.exports and spec.symbol not in mod_sym.exports:
          self.error(f"Module '{spec.module_prefix}' does not export symbol '{spec.symbol}'.")
      else:
        sym = self.symbol_table.lookup(spec.symbol)
        type_sym = self.symbol_table.lookup_type(spec.symbol)
        if not sym and not type_sym:
          self.error(f"Exported symbol '{spec.symbol}' is not defined in module.")

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
          for trait_method_name, trait_sig in trait_type.methods.items():
            if trait_method_name not in struct_type.methods:
              self.error(
                  f"Struct '{node.struct_name}' does not implement trait method "
                  f"'{trait_method_name}' of '{node.trait_name}'."
              )
            else:
              impl_sig = struct_type.methods[trait_method_name].method_type
              if impl_sig != trait_sig:
                self.error(
                    f"Method '{trait_method_name}' in struct '{node.struct_name}' "
                    f"has signature {impl_sig}, but trait '{node.trait_name}' "
                    f"requires {trait_sig}."
                )
      else:
        self.error(f"Trait '{node.trait_name}' is not defined.")

    # Check each method implementation
    for member in node.members:
      self.visit(member)

    self.current_struct = None

  def visit_ImplMemberNode(self, node: ImplMemberNode) -> None:
    func_decl = node.func_decl
    struct_type = self.current_struct

    # Enter scope of method
    self.symbol_table.enter_scope()

    # Define 'self' unless it is a static method
    if node.modifier != "static":
      # If const method, self is immutable. Else mutable
      is_mutable = node.modifier != "const"
      self.symbol_table.define("self", VariableSymbol("self", struct_type, is_mutable))

    # Setup constructor checking
    old_in_init = self.is_in_init
    old_fields = self.initialized_fields
    if func_decl.name == "__init__":
      self.is_in_init = True
      self.initialized_fields = set()

    # Define parameters in scope
    for p in func_decl.parameters:
      ptype = self._resolve_type_node(p.param_type)
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, p.is_mutable, is_parameter=True))

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

    # Restore constructor contexts
    self.is_in_init = old_in_init
    self.initialized_fields = old_fields
    self.current_function = None

    self.symbol_table.exit_scope()

  def visit_TraitDeclNode(self, node: TraitDeclNode) -> None:
    pass

  def visit_FuncDeclNode(self, node: FuncDeclNode) -> None:
    if node.type_params:
      return
    # Register parameters and check body
    self.symbol_table.enter_scope()
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
    self.symbol_table.exit_scope()

  def visit_BlockNode(self, node: BlockNode) -> None:
    self.symbol_table.enter_scope()
    for stmt in node.statements:
      self.visit(stmt)
    self.symbol_table.exit_scope()

  def visit_VarDeclNode(self, node: VarDeclNode) -> None:
    if any(a.name == "extern" for a in node.annotations):
      return

    # 1. Namespace validation
    for name in node.names:
      if self.symbol_table.lookup_current_scope(name):
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
          var_type = ArrayType(var_type.element_type, size=expr_type.size)
      else:
        if isinstance(expr_type, NoneType):
          self.error(f"Cannot infer type of '{name}' from 'none' alone. Specify an optional type annotation.", node=node)
          var_type = OptionalType(PrimitiveType("none"))
        else:
          var_type = expr_type

      sym = VariableSymbol(name, var_type, node.is_mutable)
      self.symbol_table.define(name, sym)

      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      arena_name = self._get_arena_dependency(expr_node)
      if arena_name:
        sym.arena_dependency = arena_name
        arena_sym = self.symbol_table.lookup(arena_name)
        if arena_sym and arena_sym.scope_defined and sym.scope_defined:
          if self._is_descendant_scope(arena_sym.scope_defined, sym.scope_defined) and arena_sym.scope_defined != sym.scope_defined:
            self.error(f"Variable '{name}' in outer scope cannot hold a reference to an object allocated in nested arena '{arena_name}'.")

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
      arena_name = self._get_arena_dependency(expr_node)
      if arena_name:
        target_sym = self._get_target_symbol(target)
        if target_sym:
          target_sym.arena_dependency = arena_name
          arena_sym = self.symbol_table.lookup(arena_name)
          if arena_sym and arena_sym.scope_defined and target_sym.scope_defined:
            if self._is_descendant_scope(arena_sym.scope_defined, target_sym.scope_defined) and arena_sym.scope_defined != target_sym.scope_defined:
              self.error(f"Variable '{target_sym.name}' in outer scope cannot hold a reference to an object allocated in nested arena '{arena_name}'.", node=node)

      if self.is_in_init and isinstance(target, MemberAccessNode):
        if isinstance(target.receiver, IdentifierNode) and target.receiver.name == "self":
          self.initialized_fields.add(target.member)

  def _check_lvalue(self, node: ASTNode) -> Type:
    """Helper to check if AST node is a mutable lvalue and returns its resolved type."""
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
      receiver_type = self.visit(node.receiver)
      # Unwrap optional if chained
      if node.is_optional and isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type

      if not isinstance(receiver_type, StructType):
        self.error("Property access target is not a struct.", node=node)
        return PrimitiveType("none")

      # Field access
      field = receiver_type.fields.get(node.member)
      if not field:
        self.error(f"Struct '{receiver_type.name}' has no field '{node.member}'.", node=node)
        return PrimitiveType("none")

      # Check field mutability or constructor exemption
      # Inside __init__ or clone blocks, self fields are always assignable (even if immutable let fields)
      is_self = isinstance(node.receiver, IdentifierNode) and node.receiver.name == "self"
      if not field.is_mutable:
        if not ((self.is_in_init or self.is_in_clone_init) and is_self):
          self.error(f"Cannot assign to constant field '{node.member}' of '{receiver_type.name}'.", node=node)

      # Verify self constness
      if is_self:
        self_sym = self.symbol_table.lookup("self")
        if self_sym and not self_sym.is_mutable:
          self.error(f"Cannot mutate field '{node.member}' within a constant method.", node=node)

      return field.field_type

    if isinstance(node, IndexExprNode):
      array_type = self.visit(node.array)
      if not isinstance(array_type, ArrayType):
        self.error("Cannot index non-array type.", node=node)
        return PrimitiveType("none")

      # Enforce that array target is a mutable variable
      if isinstance(node.array, IdentifierNode):
        sym = self.symbol_table.lookup(node.array.name)
        if sym and not sym.is_mutable:
          self.error(f"Cannot assign to index of constant array '{sym.name}'.", node=node)

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

    # Check return escaping arena reference
    if node.expr:
      arena_name = self._get_arena_dependency(node.expr)
      if arena_name:
        arena_sym = self.symbol_table.lookup(arena_name)
        if arena_sym and arena_sym.scope_defined and self.current_function_scope:
          if self._is_descendant_scope(arena_sym.scope_defined, self.current_function_scope):
            self.error(f"Cannot return a reference to an object allocated in local arena '{arena_name}'.")

  def visit_YieldNode(self, node: YieldNode) -> None:
    if not self._match_stack:
      self.error("Yield statement outside match context.")  # pragma: no cover
      return  # pragma: no cover
    if getattr(node, "expressions", None):
      actual_types = [self.visit(e) for e in node.expressions]
    elif getattr(node, "expr", None):  # pragma: no cover
      actual_types = [self.visit(node.expr)]  # pragma: no cover
    else:
      actual_types = []

    if len(actual_types) == 1:
      self._match_stack[-1].append(actual_types[0])
    elif len(actual_types) > 1:
      self._match_stack[-1].append(MultiReturnType(actual_types))
    else:
      self._match_stack[-1].append(PrimitiveType("none"))

  def visit_MatchExprNode(self, node: MatchExprNode) -> Type:
    subject_type = self.visit(node.subject)

    seen_enum_variants = set()
    seen_bool_true = False
    seen_bool_false = False
    seen_optional_none = False
    seen_optional_some = False
    has_ellipsis = False

    case_types: List[Type] = []

    for case in node.cases:
      if isinstance(case.pattern, EllipsisPatternNode):
        has_ellipsis = True
      elif isinstance(case.pattern, IdentifierNode):
        sym = self.symbol_table.lookup(case.pattern.name)
        if isinstance(sym, EnumSymbol) and isinstance(subject_type, EnumType) and sym.name == subject_type.name:
          pass
        else:
          self.error(f"Undefined identifier '{case.pattern.name}'.")
      elif isinstance(case.pattern, MemberAccessNode):
        pat_type = self.visit(case.pattern)
        if isinstance(subject_type, EnumType) and isinstance(pat_type, EnumType):
          seen_enum_variants.add(case.pattern.member)
        elif not pat_type.is_compatible(subject_type) and not subject_type.is_compatible(pat_type):
          self.error(f"Pattern type '{pat_type}' is incompatible with subject type '{subject_type}'.")
      elif isinstance(case.pattern, LiteralNode):
        if case.pattern.lit_type == "none":
          seen_optional_none = True
        elif case.pattern.lit_type == "bool":
          if case.pattern.value is True:
            seen_bool_true = True
          elif case.pattern.value is False:
            seen_bool_false = True
        pat_type = self.visit(case.pattern)
        if not pat_type.is_compatible(subject_type) and not subject_type.is_compatible(pat_type):
          self.error(f"Pattern type '{pat_type}' is incompatible with subject type '{subject_type}'.")
      else:
        pat_type = self.visit(case.pattern)  # pragma: no cover
        if not pat_type.is_compatible(subject_type) and not subject_type.is_compatible(pat_type):  # pragma: no cover
          self.error(f"Pattern type '{pat_type}' is incompatible with subject type '{subject_type}'.")  # pragma: no cover
        seen_optional_some = True  # pragma: no cover

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
      else:
        self._match_stack.pop()
        expr_type = self.visit(case.body)
        case_types.append(expr_type)

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

    non_none_types = [t for t in case_types if not isinstance(t, NoneType)]
    if not non_none_types:
      return NoneType()

    first_type = non_none_types[0]
    for t in non_none_types[1:]:
      if not t.is_compatible(first_type) and not first_type.is_compatible(t):
        self.error(f"Incompatible return types in match branches: '{first_type}' and '{t}'.")

    has_none = any(isinstance(t, NoneType) for t in case_types)
    if has_none or len(non_none_types) < len(case_types):
      return OptionalType(first_type)
    return first_type

  def visit_IfNode(self, node: IfNode) -> None:
    if node.init_binding:
      self.symbol_table.enter_scope()
      expr_type = self.visit(node.init_binding.expr)
      if node.init_binding.is_unwrap:
        if not isinstance(expr_type, OptionalType):
          self.error("Expression in optional unwrapping must resolve to an optional type.")
          unwrapped_type = expr_type
        else:
          unwrapped_type = expr_type.base_type
      else:
        unwrapped_type = expr_type

      self.symbol_table.define(
          node.init_binding.let_name,
          VariableSymbol(node.init_binding.let_name, unwrapped_type, is_mutable=node.init_binding.is_mutable)
      )

      if node.condition:
        cond_type = self.visit(node.condition)
        if cond_type != PrimitiveType("bool"):
          self.error("If condition must resolve to 'bool'.")
      else:
        if not node.init_binding.is_unwrap:
          self.error("Init-statement in 'if' must be followed by a condition unless using optional unwrapping '?='.")

      self.visit(node.then_block)
      self.symbol_table.exit_scope()
    else:
      cond_type = self.visit(node.condition)
      if cond_type != PrimitiveType("bool"):
        self.error("If condition must resolve to 'bool'.")
      self.visit(node.then_block)

    if node.else_block:
      self.visit(node.else_block)

  def visit_WhileNode(self, node: WhileNode) -> None:
    self.loop_depth += 1
    try:
      if node.init_binding:
        self.symbol_table.enter_scope()
        expr_type = self.visit(node.init_binding.expr)
        if node.init_binding.is_unwrap:
          if not isinstance(expr_type, OptionalType):
            self.error("Expression in optional unwrapping must resolve to an optional type.")
            unwrapped_type = expr_type
          else:
            unwrapped_type = expr_type.base_type
        else:
          unwrapped_type = expr_type

        self.symbol_table.define(
            node.init_binding.let_name,
            VariableSymbol(node.init_binding.let_name, unwrapped_type, is_mutable=node.init_binding.is_mutable)
        )

        if node.condition:
          cond_type = self.visit(node.condition)
          if cond_type != PrimitiveType("bool"):
            self.error("While condition must resolve to 'bool'.")
        else:
          if not node.init_binding.is_unwrap:
            self.error("Init-statement in 'while' must be followed by a condition unless using optional unwrapping '?='.")

        self.visit(node.block)
        self.symbol_table.exit_scope()
      else:
        cond_type = self.visit(node.condition)
        if cond_type != PrimitiveType("bool"):
          self.error("While condition must resolve to 'bool'.")
        self.visit(node.block)
    finally:
      self.loop_depth -= 1

  def visit_ForNode(self, node: ForNode) -> None:
    self.loop_depth += 1
    try:
      iter_type = self.visit(node.iterable)
      self.symbol_table.enter_scope()

      if isinstance(iter_type, ArrayType):
        if node.key_var is not None:
          self.error("Cannot iterate over an array with key-value syntax; use a single loop variable.")
        elem_type = iter_type.element_type
        self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, elem_type, node.is_mutable))
      elif isinstance(iter_type, RangeType):
        if node.key_var is not None:
          self.error("Cannot iterate over a range with key-value syntax; use a single loop variable.")
        self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, PrimitiveType("int"), node.is_mutable))
      elif isinstance(iter_type, MapType):
        if node.key_var is None:
          self.error("Map iteration requires key and value loop variables: 'for key, val in map'.")
          self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, iter_type.value_type, node.is_mutable))
        else:
          self.symbol_table.define(node.key_var, VariableSymbol(node.key_var, iter_type.key_type, node.is_mutable))
          self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, iter_type.value_type, node.is_mutable))
      else:
        self.error("For-in loop source must be an array, map, or range type.")
        if node.key_var is not None:
          self.symbol_table.define(node.key_var, VariableSymbol(node.key_var, PrimitiveType("none"), node.is_mutable))
        self.symbol_table.define(node.val_var, VariableSymbol(node.val_var, PrimitiveType("none"), node.is_mutable))

      self.visit(node.block)
      self.symbol_table.exit_scope()
    finally:
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
      self.error(f"Undefined identifier '{node.name}'.")
      return PrimitiveType("none")
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
    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if isinstance(sym, VariableSymbol):
        return (node.name, [])
    elif isinstance(node, MemberAccessNode):
      res = self._get_lvalue_path(node.receiver)
      if res is not None:
        root, path = res
        return (root, path + [node.member])
    elif isinstance(node, IndexExprNode):
      res = self._get_lvalue_path(node.array)
      if res is not None:
        root, path = res
        return (root, path + ["[]"])
    return None

  def _is_reference_type(self, type_obj: Type) -> bool:
    """Returns True if the type is passed by reference (non-primitive)."""
    if isinstance(type_obj, OptionalType):
      return self._is_reference_type(type_obj.base_type)
    if isinstance(type_obj, PrimitiveType):
      return False
    if isinstance(type_obj, NoneType):
      return False
    return True

  def _check_aliasing(self, node: CallNode, signature: FunctionType, is_constructor: bool) -> None:
    """Verifies that non-primitive arguments do not conflict due to mutability aliasing."""
    borrows = []  # List of (root, path, is_mutable)

    # 1. Check implicit self receiver for non-static method calls
    if not is_constructor and isinstance(node.callee, MemberAccessNode):
      receiver_node = node.callee.receiver
      receiver_type = self.visit(receiver_node)
      if isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type
      if isinstance(receiver_type, StructType):
        method = receiver_type.get_method(node.callee.member, self.symbol_table)
        if method and method.modifier != "static":
          # Receiver is implicitly passed.
          # It is mutably borrowed if method is not const.
          is_mutable = (method.modifier != "const")
          res = self._get_lvalue_path(receiver_node)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))

    # 2. Check explicit arguments
    for idx, arg in enumerate(node.arguments):
      if idx < len(signature.param_types):
        param_type = signature.param_types[idx]
        is_mutable = signature.param_mutabilities[idx]
        if self._is_reference_type(param_type):
          res = self._get_lvalue_path(arg.expr)
          if res:
            root, path = res
            borrows.append((root, path, is_mutable))

    # 3. Check for conflicts among all borrows
    for i in range(len(borrows)):
      for j in range(i + 1, len(borrows)):
        r1, p1, m1 = borrows[i]
        r2, p2, m2 = borrows[j]
        if r1 == r2:
          # Check if paths overlap (one is prefix of another)
          overlap = p1[:len(p2)] == p2 or p2[:len(p1)] == p1
          if overlap:
            # Conflict if at least one is mutable
            if m1 or m2:
              self.error(
                  f"Aliasing conflict: variable '{r1}' (or a sub-field) "
                  f"is mutably borrowed and cannot be borrowed again in the same call."
              )

  def visit_CallNode(self, node: CallNode) -> Type:
    # Generic function resolution & monomorphization
    if isinstance(node.callee, IdentifierNode):
      sym = self.symbol_table.lookup(node.callee.name)
      if isinstance(sym, FunctionSymbol) and sym.type_params:
        if node.type_args:
          resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
          mangled_name = self._monomorphize_function(sym, node.type_args, resolved_type_args)
          node.callee.name = mangled_name
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
          node.callee.name = mangled_name

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
      method = node.callee.array_method
      receiver_type = node.callee.array_receiver_type
      elem_type = receiver_type.element_type

      if method == "size":
        if node.arguments:
          self.error(".size() takes no arguments.")
        return PrimitiveType("int")

      elif method == "empty":
        if node.arguments:
          self.error(".empty() takes no arguments.")
        return PrimitiveType("bool")

      elif method == "map":
        fn_arg = None
        in_place_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "fn":
            fn_arg = arg
          elif arg.name == "in_place":
            in_place_arg = arg
          elif idx == 0 and not arg.name:
            fn_arg = arg
          elif idx == 1 and not arg.name:
            in_place_arg = arg

        if not fn_arg:
          self.error(".map() requires at least 1 argument (fn).")
          return ArrayType(elem_type, size=receiver_type.size)

        old_expected = self.expected_type
        self.expected_type = FunctionType([elem_type], InferredType())
        fn_type = self.visit(fn_arg.expr)
        self.expected_type = old_expected

        ret_elem_type = PrimitiveType("none")
        if isinstance(fn_type, FunctionType):
          ret_elem_type = fn_type.return_type
          if fn_type.param_types and not elem_type.is_compatible(fn_type.param_types[0]):
            self.error(f"Closure parameter type mismatch in .map(). Expected '{elem_type}', got '{fn_type.param_types[0]}'.")

        is_in_place = False
        if in_place_arg:
          in_p_type = self.visit(in_place_arg.expr)
          if not in_p_type.is_compatible(PrimitiveType("bool")):
            self.error(f"'in_place' parameter in .map() must be 'bool', got '{in_p_type}'.")
          if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
            is_in_place = True

        if is_in_place:
          receiver = node.callee.receiver
          if isinstance(receiver, IdentifierNode):
            sym = self.symbol_table.lookup(receiver.name)
            if isinstance(sym, VariableSymbol) and not sym.is_mutable:
              self.error(f"Cannot invoke in-place transformation '.map()' on constant variable '{receiver.name}'.")
          if isinstance(fn_type, FunctionType) and not ret_elem_type.is_compatible(elem_type):
            self.error(f"In-place mapping requires closure return type to match element type '{elem_type}', got '{ret_elem_type}'.")
          return ArrayType(elem_type, size=receiver_type.size)

        if receiver_type.size is not None:
          return ArrayType(ret_elem_type, size=receiver_type.size)
        return ArrayType(ret_elem_type)

      elif method == "filter":
        fn_arg = None
        in_place_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "fn":
            fn_arg = arg
          elif arg.name == "in_place":
            in_place_arg = arg
          elif idx == 0 and not arg.name:
            fn_arg = arg
          elif idx == 1 and not arg.name:
            in_place_arg = arg

        if not fn_arg:
          self.error(".filter() requires at least 1 argument (fn).")
          return ArrayType(elem_type)

        old_expected = self.expected_type
        self.expected_type = FunctionType([elem_type], PrimitiveType("bool"))
        fn_type = self.visit(fn_arg.expr)
        self.expected_type = old_expected

        if isinstance(fn_type, FunctionType):
          if fn_type.param_types and not elem_type.is_compatible(fn_type.param_types[0]):
            self.error(f"Closure parameter type mismatch in .filter(). Expected '{elem_type}', got '{fn_type.param_types[0]}'.")
          if not fn_type.return_type.is_compatible(PrimitiveType("bool")):
            self.error(f".filter() predicate closure must return 'bool', got '{fn_type.return_type}'.")

        is_in_place = False
        if in_place_arg:
          in_p_type = self.visit(in_place_arg.expr)
          if not in_p_type.is_compatible(PrimitiveType("bool")):
            self.error(f"'in_place' parameter in .filter() must be 'bool', got '{in_p_type}'.")
          if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
            is_in_place = True

        if is_in_place:
          if receiver_type.is_fixed_size:
            self.error(f"Cannot invoke in-place '.filter()' on fixed-size array '{receiver_type}'.")
          receiver = node.callee.receiver
          if isinstance(receiver, IdentifierNode):
            sym = self.symbol_table.lookup(receiver.name)
            if isinstance(sym, VariableSymbol) and not sym.is_mutable:
              self.error(f"Cannot invoke in-place transformation '.filter()' on constant variable '{receiver.name}'.")

        return ArrayType(elem_type)

      elif method == "reduce":
        initial_arg = None
        fn_arg = None
        reverse_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "initial":
            initial_arg = arg
          elif arg.name == "fn":
            fn_arg = arg
          elif arg.name == "reverse":
            reverse_arg = arg
          elif idx == 0 and not arg.name:
            initial_arg = arg
          elif idx == 1 and not arg.name:
            fn_arg = arg
          elif idx == 2 and not arg.name:
            reverse_arg = arg

        if not initial_arg or not fn_arg:
          self.error(".reduce() requires mandatory 'initial' and 'fn' arguments.")
          return elem_type

        acc_type = self.visit(initial_arg.expr)

        old_expected = self.expected_type
        self.expected_type = FunctionType([acc_type, elem_type], acc_type)
        fn_type = self.visit(fn_arg.expr)
        self.expected_type = old_expected

        if isinstance(fn_type, FunctionType):
          if len(fn_type.param_types) >= 2:
            if not acc_type.is_compatible(fn_type.param_types[0]):
              self.error(f"Closure accumulator parameter mismatch in .reduce(). Expected '{acc_type}', got '{fn_type.param_types[0]}'.")
            if not elem_type.is_compatible(fn_type.param_types[1]):
              self.error(f"Closure item parameter mismatch in .reduce(). Expected '{elem_type}', got '{fn_type.param_types[1]}'.")
          if not fn_type.return_type.is_compatible(acc_type):
            self.error(f"Closure return type in .reduce() must match initial value type '{acc_type}', got '{fn_type.return_type}'.")

        if reverse_arg:
          rev_type = self.visit(reverse_arg.expr)
          if not rev_type.is_compatible(PrimitiveType("bool")):
            self.error(f"'reverse' parameter in .reduce() must be 'bool', got '{rev_type}'.")

        return acc_type

      elif method in ("push", "pop", "insert", "remove", "clear"):
        if receiver_type.is_fixed_size:
          self.error(f"Cannot invoke mutating method '{method}' on fixed-size array '{receiver_type}'.")
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = self.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            self.error(f"Cannot invoke mutating method '{method}' on constant variable '{receiver.name}'.")

        if method == "push":
          if len(node.arguments) != 1:
            self.error(".push() requires exactly 1 argument (element).")
            return elem_type
          arg_t = self.visit(node.arguments[0].expr)
          if not arg_t.is_compatible(elem_type):
            self.error(f"Argument type mismatch in .push(). Expected '{elem_type}', got '{arg_t}'.")
          return elem_type

        elif method == "pop":
          if node.arguments:
            self.error(".pop() takes no arguments.")
          return OptionalType(elem_type)

        elif method == "insert":
          index_arg = None
          element_arg = None
          for idx, arg in enumerate(node.arguments):
            if arg.name == "index":
              index_arg = arg
            elif arg.name == "element":
              element_arg = arg
            elif idx == 0 and not arg.name:
              index_arg = arg
            elif idx == 1 and not arg.name:
              element_arg = arg

          if not index_arg or not element_arg:
            self.error(".insert() requires mandatory 'index' and 'element' arguments.")
            return elem_type

          idx_t = self.visit(index_arg.expr)
          if not idx_t.is_compatible(PrimitiveType("int")):
            self.error(f"Argument 'index' in .insert() must be 'int', got '{idx_t}'.")
          elem_t = self.visit(element_arg.expr)
          if not elem_t.is_compatible(elem_type):
            self.error(f"Argument type mismatch in .insert(). Expected '{elem_type}', got '{elem_t}'.")
          return elem_type

        elif method == "remove":
          if len(node.arguments) != 1:
            self.error(".remove() requires exactly 1 argument (index).")
            return OptionalType(elem_type)
          idx_t = self.visit(node.arguments[0].expr)
          if not idx_t.is_compatible(PrimitiveType("int")):
            self.error(f"Argument 'index' in .remove() must be 'int', got '{idx_t}'.")
          return OptionalType(elem_type)

        elif method == "clear":
          if node.arguments:
            self.error(".clear() takes no arguments.")
          return PrimitiveType("none")

      elif method == "contains":
        if len(node.arguments) != 1:
          self.error(".contains() requires exactly 1 argument (element).")
          return PrimitiveType("bool")
        arg_t = self.visit(node.arguments[0].expr)
        if not arg_t.is_compatible(elem_type):
          self.error(f"Argument type mismatch in .contains(). Expected '{elem_type}', got '{arg_t}'.")
        return PrimitiveType("bool")

      elif method == "reverse":
        in_place_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "in_place":
            in_place_arg = arg
          elif idx == 0 and not arg.name:
            in_place_arg = arg

        if len(node.arguments) > 1:
          self.error(".reverse() takes at most 1 argument (in_place).")

        is_in_place = False
        if in_place_arg:
          in_p_type = self.visit(in_place_arg.expr)
          if not in_p_type.is_compatible(PrimitiveType("bool")):
            self.error(f"'in_place' parameter in .reverse() must be 'bool', got '{in_p_type}'.")
          if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
            is_in_place = True

        if is_in_place:
          receiver = node.callee.receiver
          if isinstance(receiver, IdentifierNode):
            sym = self.symbol_table.lookup(receiver.name)
            if isinstance(sym, VariableSymbol) and not sym.is_mutable:
              self.error(f"Cannot invoke in-place transformation '.reverse()' on constant variable '{receiver.name}'.")

        return ArrayType(elem_type, size=receiver_type.size)

      elif method == "sort":
        by_arg = None
        reverse_arg = None
        in_place_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "by":
            by_arg = arg
          elif arg.name == "reverse":
            reverse_arg = arg
          elif arg.name == "in_place":
            in_place_arg = arg
          elif idx == 0 and not arg.name:
            by_arg = arg
          elif idx == 1 and not arg.name:
            reverse_arg = arg
          elif idx == 2 and not arg.name:
            in_place_arg = arg

        if by_arg:
          old_expected = self.expected_type
          self.expected_type = FunctionType([elem_type, elem_type], PrimitiveType("int"))
          by_type = self.visit(by_arg.expr)
          self.expected_type = old_expected
          if isinstance(by_type, FunctionType):
            if not by_type.return_type.is_compatible(PrimitiveType("int")):
              self.error(f"Comparator closure in .sort() must return 'int', got '{by_type.return_type}'.")
        if reverse_arg:
          rev_t = self.visit(reverse_arg.expr)
          if not rev_t.is_compatible(PrimitiveType("bool")):
            self.error(f"'reverse' parameter in .sort() must be 'bool', got '{rev_t}'.")

        is_in_place = False
        if in_place_arg:
          in_p_type = self.visit(in_place_arg.expr)
          if not in_p_type.is_compatible(PrimitiveType("bool")):
            self.error(f"'in_place' parameter in .sort() must be 'bool', got '{in_p_type}'.")
          if isinstance(in_place_arg.expr, LiteralNode) and in_place_arg.expr.value is True:
            is_in_place = True

        if is_in_place:
          receiver = node.callee.receiver
          if isinstance(receiver, IdentifierNode):
            sym = self.symbol_table.lookup(receiver.name)
            if isinstance(sym, VariableSymbol) and not sym.is_mutable:
              self.error(f"Cannot invoke in-place transformation '.sort()' on constant variable '{receiver.name}'.")

        return ArrayType(elem_type, size=receiver_type.size)

      elif method == "join":
        if len(node.arguments) > 1:
          self.error(".join() takes at most 1 argument (sep).")
        elif len(node.arguments) == 1:
          sep_t = self.visit(node.arguments[0].expr)
          if not sep_t.is_compatible(StringType()):
            self.error(f"Delimiter 'sep' in .join() must be 'String', got '{sep_t}'.")
        return StringType()

    if isinstance(node.callee, MemberAccessNode) and getattr(node.callee, "is_map_method", False):
      method = node.callee.map_method
      receiver_type = node.callee.map_receiver_type
      k_type = receiver_type.key_type
      v_type = receiver_type.value_type

      if method in ("insert", "remove", "clear"):
        receiver = node.callee.receiver
        if isinstance(receiver, IdentifierNode):
          sym = self.symbol_table.lookup(receiver.name)
          if isinstance(sym, VariableSymbol) and not sym.is_mutable:
            self.error(f"Cannot invoke mutating method '{method}' on constant variable '{receiver.name}'.")

      if method == "size":
        if node.arguments:
          self.error(".size() takes no arguments.")
        return PrimitiveType("int")

      elif method == "empty":
        if node.arguments:
          self.error(".empty() takes no arguments.")
        return PrimitiveType("bool")

      elif method == "contains":
        if len(node.arguments) != 1:
          self.error(".contains() requires exactly 1 argument (key).")
          return PrimitiveType("bool")
        key_arg_type = self.visit(node.arguments[0].expr)
        if not key_arg_type.is_compatible(k_type):
          self.error(f"Argument type mismatch in .contains(). Expected '{k_type}', got '{key_arg_type}'.")
        return PrimitiveType("bool")

      elif method == "keys":
        if node.arguments:
          self.error(".keys() takes no arguments.")
        return ArrayType(k_type)

      elif method == "values":
        if node.arguments:
          self.error(".values() takes no arguments.")
        return ArrayType(v_type)

      elif method == "insert":
        key_arg = None
        val_arg = None
        for idx, arg in enumerate(node.arguments):
          if arg.name == "key":
            key_arg = arg
          elif arg.name == "value":
            val_arg = arg
          elif idx == 0 and not arg.name:
            key_arg = arg
          elif idx == 1 and not arg.name:
            val_arg = arg

        if not key_arg or not val_arg:
          self.error(".insert() requires mandatory 'key' and 'value' arguments.")
          return v_type

        k_arg_type = self.visit(key_arg.expr)
        if not k_arg_type.is_compatible(k_type):
          self.error(f"Argument 'key' in .insert() must be '{k_type}', got '{k_arg_type}'.")

        v_arg_type = self.visit(val_arg.expr)
        if not v_arg_type.is_compatible(v_type):
          self.error(f"Argument 'value' in .insert() must be '{v_type}', got '{v_arg_type}'.")

        return v_type

      elif method == "remove":
        if len(node.arguments) != 1:
          self.error(".remove() requires exactly 1 argument (key).")
          return OptionalType(v_type)
        k_arg_type = self.visit(node.arguments[0].expr)
        if not k_arg_type.is_compatible(k_type):
          self.error(f"Argument 'key' in .remove() must be '{k_type}', got '{k_arg_type}'.")
        return OptionalType(v_type)

      elif method == "clear":
        if node.arguments:
          self.error(".clear() takes no arguments.")
        return PrimitiveType("none")

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
    else:
      # Standard function/method resolution
      if not isinstance(callee_type, FunctionType):
        self.error("Target is not callable.")
        return PrimitiveType("none")
      signature = callee_type
      self._check_arguments(node.arguments, signature, callee_node=node.callee)

    # Perform borrow checking / aliasing rules
    if signature:
      self._check_aliasing(node, signature, is_constructor)

    if is_constructor:
      return callee_type
    return signature.return_type

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

      is_test_assert = getattr(signature, "is_testing_assertion", False)
      if param_idx < len(expected_param_types):
        param_type = expected_param_types[param_idx]
        if not is_test_assert and not arg_type.is_compatible(param_type):
          self.error(f"Argument type mismatch at position {idx+1}. Expected '{param_type}', got '{arg_type}'.")
      else:
        # Extra parameter
        if not is_constructor and not is_test_assert:
          self.error("Too many arguments passed to call.")

  def visit_MemberAccessNode(self, node: MemberAccessNode) -> Type:
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
      if node.member in ARRAY_METHODS:
        node.is_array_method = True
        node.array_method = node.member
        node.array_receiver_type = receiver_type
        elem_t = receiver_type.element_type
        if node.member == "size":
          return FunctionType([receiver_type], PrimitiveType("int"), param_names=["self"], has_self=True)
        elif node.member == "empty":
          return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
        elif node.member == "map":
          return FunctionType([receiver_type, FunctionType([elem_t], InferredType()), PrimitiveType("bool")], ArrayType(InferredType(), size=receiver_type.size), param_names=["self", "fn", "in_place"], has_self=True, num_defaults=1)
        elif node.member == "filter":
          return FunctionType([receiver_type, FunctionType([elem_t], PrimitiveType("bool")), PrimitiveType("bool")], ArrayType(elem_t), param_names=["self", "fn", "in_place"], has_self=True, num_defaults=1)
        elif node.member == "reduce":
          return FunctionType([receiver_type, InferredType(), FunctionType([InferredType(), elem_t], InferredType()), PrimitiveType("bool")], InferredType(), param_names=["self", "initial", "fn", "reverse"], has_self=True, num_defaults=1)
        elif node.member == "contains":
          return FunctionType([receiver_type, elem_t], PrimitiveType("bool"), param_names=["self", "element"], has_self=True)
        elif node.member == "reverse":
          return FunctionType([receiver_type, PrimitiveType("bool")], ArrayType(elem_t, size=receiver_type.size), param_names=["self", "in_place"], has_self=True, num_defaults=1)
        elif node.member == "sort":
          return FunctionType([receiver_type, OptionalType(FunctionType([elem_t, elem_t], PrimitiveType("int"))), PrimitiveType("bool"), PrimitiveType("bool")], ArrayType(elem_t, size=receiver_type.size), param_names=["self", "by", "reverse", "in_place"], has_self=True, num_defaults=3)
        elif node.member == "join":
          return FunctionType([receiver_type, OptionalType(StringType())], StringType(), param_names=["self", "sep"], has_self=True, num_defaults=1)
        elif node.member == "push":
          return FunctionType([receiver_type, elem_t], elem_t, param_names=["self", "element"], has_self=True)
        elif node.member == "pop":
          return FunctionType([receiver_type], OptionalType(elem_t), param_names=["self"], has_self=True)
        elif node.member == "insert":
          return FunctionType([receiver_type, PrimitiveType("int"), elem_t], elem_t, param_names=["self", "index", "element"], has_self=True)
        elif node.member == "remove":
          return FunctionType([receiver_type, PrimitiveType("int")], OptionalType(elem_t), param_names=["self", "index"], has_self=True)
        elif node.member == "clear":
          return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
      self.error(f"Array has no method '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, MapType):
      if node.member in MAP_METHODS:
        node.is_map_method = True
        node.map_method = node.member
        node.map_receiver_type = receiver_type
        k_type = receiver_type.key_type
        v_type = receiver_type.value_type
        if node.member == "size":
          return FunctionType([receiver_type], PrimitiveType("int"), param_names=["self"], has_self=True)
        elif node.member == "empty":
          return FunctionType([receiver_type], PrimitiveType("bool"), param_names=["self"], has_self=True)
        elif node.member == "contains":
          return FunctionType([receiver_type, k_type], PrimitiveType("bool"), param_names=["self", "key"], has_self=True)
        elif node.member == "keys":
          return FunctionType([receiver_type], ArrayType(k_type), param_names=["self"], has_self=True)
        elif node.member == "values":
          return FunctionType([receiver_type], ArrayType(v_type), param_names=["self"], has_self=True)
        elif node.member == "insert":
          return FunctionType([receiver_type, k_type, v_type], v_type, param_names=["self", "key", "value"], has_self=True)
        elif node.member == "remove":
          return FunctionType([receiver_type, k_type], OptionalType(v_type), param_names=["self", "key"], has_self=True)
        elif node.member == "clear":
          return FunctionType([receiver_type], PrimitiveType("none"), param_names=["self"], has_self=True)
      self.error(f"Map has no method '{node.member}'.")
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
        node.is_instance_method = method.has_self
        node.is_static_method = not method.has_self
        return method
      self.error(f"Trait '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if not isinstance(receiver_type, StructType):
      self.error("Member access receiver is not a struct or trait.")
      return PrimitiveType("none")

    # Special member __proto__
    if node.member == "__proto__":
      # returns optional of same struct type
      return OptionalType(receiver_type)

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

    # Mark the struct type as cloned
    expr_type.is_cloned = True

    # If immediate shadow block is defined, check statements
    if node.initializer_block:
      self.symbol_table.enter_scope()
      old_clone_init = self.is_in_clone_init
      self.is_in_clone_init = True
      # Define self inside block as mutable
      self.symbol_table.define("self", VariableSymbol("self", expr_type, is_mutable=True))
      for stmt in node.initializer_block:
        self.visit(stmt)
      self.is_in_clone_init = old_clone_init
      self.symbol_table.exit_scope()

    return expr_type

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
    self.symbol_table.enter_scope()

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

    body_type = self.visit(node.body)

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

    self.symbol_table.exit_scope()
    return FunctionType(resolved_param_types, ret_type)

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> Type:
    if not node.elements:
      if isinstance(self.expected_type, ArrayType):
        return ArrayType(self.expected_type.element_type, size=0)
      return ArrayType(NoneType(), size=0)

    elem_types = [self.visit(e) for e in node.elements]
    if isinstance(self.expected_type, ArrayType):
      target_elem = self.expected_type.element_type
      for etype in elem_types:
        if not etype.is_compatible(target_elem):
          self.error(f"Array element of type '{etype}' is not compatible with expected element type '{target_elem}'.")
          break
      return ArrayType(target_elem, size=len(node.elements))

    first_type = elem_types[0]
    for etype in elem_types[1:]:
      if not etype.is_compatible(first_type) and not first_type.is_compatible(etype):
        self.error("Inconsistent element types in array literal.")
        break
    return ArrayType(first_type, size=len(node.elements))

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> Type:
    if not node.entries:
      if isinstance(self.expected_type, MapType):
        return MapType(self.expected_type.key_type, self.expected_type.value_type)
      return MapType(NoneType(), NoneType())

    first_key_type = self.visit(node.entries[0].key)
    first_val_type = self.visit(node.entries[0].value)

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
      if const_idx < 0:
        self.error(f"Array index out of bounds: negative index '{const_idx}' is not allowed.")
      elif size is not None and const_idx >= size:
        self.error(f"Array index out of bounds: index {const_idx} is out of bounds for array of size {size}.")

  def _check_map_literal_key(self, node: IndexExprNode) -> None:
    if isinstance(node.array, MapLiteralNode) and isinstance(node.index, LiteralNode):
      key_val = str(node.index.value)
      for entry in node.array.entries:
        if isinstance(entry.key, LiteralNode) and str(entry.key.value) == key_val:
          return
      self.error(f"Key '{key_val}' not found in map literal.")

  def visit_IndexExprNode(self, node: IndexExprNode) -> Type:
    container_type = self.visit(node.array)
    index_type = self.visit(node.index)

    if isinstance(container_type, ArrayType):
      if index_type != PrimitiveType("int"):
        self.error("Array index must be an 'int'.")
      const_idx = self._get_const_int_value(node.index)
      if const_idx is not None:
        self._check_array_bounds(node, container_type)
        return container_type.element_type
      else:
        return OptionalType(container_type.element_type)
    elif isinstance(container_type, MapType):
      if not index_type.is_compatible(container_type.key_type) and not container_type.key_type.is_compatible(index_type):
        self.error(f"Map index type '{index_type}' is not compatible with key type '{container_type.key_type}'.")
      if isinstance(node.array, MapLiteralNode):
        self._check_map_literal_key(node)
      is_const_key = isinstance(node.index, (LiteralNode, MemberAccessNode))
      if is_const_key:
        return container_type.value_type
      else:
        return OptionalType(container_type.value_type)
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
        if binding.is_unwrap:
          if not isinstance(expr_t, OptionalType):
            self.error(f"Cannot unwrap non-optional type '{expr_t}' in guard clause.")
            base_t = expr_t
          else:
            base_t = expr_t.base_type
        else:
          base_t = expr_t

        let_names = getattr(binding, "let_names", [binding.let_name])
        if len(let_names) > 1:
          elem_t = base_t.element_type if isinstance(base_t, ArrayType) else base_t
          for name in let_names:
            self.symbol_table.define(name, VariableSymbol(name, elem_t, is_mutable=binding.is_mutable))
        else:
          name = binding.let_name
          self.symbol_table.define(name, VariableSymbol(name, base_t, is_mutable=binding.is_mutable))
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

    if struct_type.type_params:
      if node.type_args:
        resolved_type_args = [self._resolve_type_node(t) for t in node.type_args]
        struct_type = self._monomorphize_struct(struct_type, node.type_args, resolved_type_args)
        node.struct_name = struct_type.name
      else:
        self.error(f"Generic struct '{node.struct_name}' requires explicit type arguments.")
        return PrimitiveType("none")

    # Validate explicit arena target
    if node.arena_expr:
      arena_type = self.visit(node.arena_expr)
      if not isinstance(arena_type, ArenaType):
        self.error("Explicit arena target must be an instance of Arena.")

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
