"""Semantic analyzer and type checker implementation for Sapphire.

This module walks the Sapphire AST, constructs symbol tables, performs type
checking and type inference, and validates all semantic constraints of the
Sapphire language.
"""

import copy
from typing import Any, Dict, List, Optional

try:
  from parser.ast import *
  from semantics.symbol_table import (
      SymbolTable,
      Type,
      PrimitiveType,
      OptionalType,
      FunctionType,
      MultiReturnType,
      StructField,
      StructMethod,
      StructType,
      TraitType,
      EnumType,
      NoneType,
      ArrayType,
      MapType,
      ArenaType,
      ModuleType,
      GenericTypeParameter,
      VariableSymbol,
      FunctionSymbol,
      StructSymbol,
      TraitSymbol,
      EnumSymbol,
      ModuleSymbol,
  )
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.ast import *
  from src.semantics.symbol_table import (
      SymbolTable,
      Type,
      PrimitiveType,
      OptionalType,
      FunctionType,
      MultiReturnType,
      StructField,
      StructMethod,
      StructType,
      TraitType,
      EnumType,
      NoneType,
      ArrayType,
      MapType,
      ArenaType,
      ModuleType,
      GenericTypeParameter,
      VariableSymbol,
      FunctionSymbol,
      StructSymbol,
      TraitSymbol,
      EnumSymbol,
      ModuleSymbol,
  )



class SemanticError(Exception):
  """Exception raised for semantic or compile-time type errors."""
  pass


class TypeChecker:
  """Walks the AST to perform type-checking and semantic validation."""

  def __init__(self, source_file_path: Optional[str] = None):
    self.symbol_table = SymbolTable()
    self.errors: List[str] = []
    self.source_file_path: Optional[str] = source_file_path
    self.current_function: Optional[FunctionType] = None
    self.current_struct: Optional[StructType] = None
    self.is_in_init: bool = False
    self.is_in_clone_init: bool = False
    self.initialized_fields: set = set()
    self.expected_type: Optional[Type] = None
    self.current_function_scope = None
    self._match_stack: List[List[Type]] = []

  def _get_arena_dependency(self, node: ASTNode) -> Optional[str]:
    if isinstance(node, IdentifierNode):
      symbol = self.symbol_table.lookup(node.name)
      if isinstance(symbol, VariableSymbol):
        return symbol.arena_dependency
    elif isinstance(node, StructInitializerNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
    elif isinstance(node, CloneNode):
      if node.arena_expr and isinstance(node.arena_expr, IdentifierNode):
        return node.arena_expr.name
      else:
        return self._get_arena_dependency(node.expr)
    return None

  def _is_descendant_scope(self, child: Optional[object], parent: Optional[object]) -> bool:
    curr = child
    while curr:
      if curr == parent:
        return True
      curr = curr.parent
    return False

  def _get_target_symbol(self, target: ASTNode) -> Optional[VariableSymbol]:
    if isinstance(target, IdentifierNode):
      sym = self.symbol_table.lookup(target.name)
      if isinstance(sym, VariableSymbol):
        return sym
    elif isinstance(target, MemberAccessNode):
      return self._get_target_symbol(target.receiver)
    return None

  def error(self, message: str) -> None:
    """Logs a semantic error."""
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
    """Recursively replaces generic parameter identifiers with concrete TypeNodes in an AST snippet."""
    if node is None:
      return None
    if isinstance(node, BasicTypeNode):
      if node.name in param_map:
        return copy.deepcopy(param_map[node.name])
      if node.type_args:
        new_args = [self._substitute_ast(t, param_map) for t in node.type_args]
        new_node = copy.deepcopy(node)
        new_node.type_args = new_args
        return new_node
      return copy.deepcopy(node)
    if isinstance(node, list):
      return [self._substitute_ast(item, param_map) for item in node]
    if isinstance(node, ASTNode):
      new_node = copy.copy(node)
      for k, v in node.__dict__.items():
        if isinstance(v, (ASTNode, list)):
          setattr(new_node, k, self._substitute_ast(v, param_map))
        else:
          setattr(new_node, k, v)
      return new_node
    return copy.deepcopy(node)

  def _monomorphize_struct(
      self, generic_struct_type: StructType, type_arg_nodes: List[TypeNode], resolved_type_args: List[Type]
  ) -> StructType:
    """Monomorphizes a generic struct template for a specific set of concrete type arguments."""
    arg_names = [str(t) for t in resolved_type_args]
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

    mono_struct_type = StructType(mangled_name, cloned_decl.parent_name, cloned_decl.is_prototype)
    self.symbol_table.define_type(mangled_name, mono_struct_type)
    self.symbol_table.define(mangled_name, StructSymbol(mangled_name, mono_struct_type))

    # Resolve fields for monomorphized struct
    for f in cloned_decl.fields:
      ftype = self._resolve_type_node(f.field_type)
      mono_struct_type.fields[f.name] = StructField(f.name, ftype, f.is_mutable, f.default_expr is not None)

    # Instantiate generic impl blocks matching generic_struct_type.name
    if hasattr(self, "program") and self.program:
      for decl in self.program.declarations:
        if isinstance(decl, ImplBlockNode) and decl.struct_name == generic_struct_type.name:
          cloned_impl = self._substitute_ast(decl, param_map)
          cloned_impl.struct_name = mangled_name
          cloned_impl.type_params = []
          for member in cloned_impl.members:
            func_decl = member.func_decl
            p_types = [self._resolve_type_node(p.param_type) for p in func_decl.parameters]
            ret_t = self._resolve_return_types(func_decl)
            sig = FunctionType(p_types, ret_t, [p.is_mutable for p in func_decl.parameters], [p.name for p in func_decl.parameters])
            mono_struct_type.methods[func_decl.name] = StructMethod(func_decl.name, sig, member.modifier)
          self.program.declarations.append(cloned_impl)

      self.program.declarations.append(cloned_decl)

    return mono_struct_type

  def _monomorphize_function(
      self, func_sym: FunctionSymbol, type_arg_nodes: List[TypeNode], resolved_type_args: List[Type]
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete type arguments."""
    arg_names = [str(t) for t in resolved_type_args]
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
    sig = FunctionType(p_types, ret_t, [p.is_mutable for p in cloned_func.parameters], [p.name for p in cloned_func.parameters])
    mono_func_sym = FunctionSymbol(mangled_name, sig, ast_decl=cloned_func)
    self.symbol_table.define(mangled_name, mono_func_sym)

    if hasattr(self, "program") and self.program:
      self.program.declarations.append(cloned_func)

    # Type check the body of the monomorphized function
    self.visit_FuncDeclNode(cloned_func)
    return mangled_name

  def _declare_imports(self, program: ProgramNode) -> None:
    """Pre-pass to register imported module symbols."""
    import os
    for imp in getattr(program, "imports", []):
      module_name = imp.alias if imp.alias else imp.path.split(".")[-1]
      existing = self.symbol_table.lookup_current_scope(module_name)
      if not existing or not isinstance(existing, ModuleSymbol):
        mod_sym = ModuleSymbol(module_name, imp.path)
        self.symbol_table.define(module_name, mod_sym)
        self.symbol_table.define_type(module_name, ModuleType(imp.path))
      else:
        mod_sym = existing

      # Resolve imported module file path on disk
      possible_paths = [
          imp.path.replace(".", "/") + ".sp",
          os.path.join(os.getcwd(), imp.path.replace(".", "/") + ".sp"),
      ]
      if getattr(self, "source_file_path", None):
        base_dir = os.path.dirname(self.source_file_path)
        possible_paths.insert(0, os.path.join(base_dir, imp.path.replace(".", "/") + ".sp"))

      target_file = None
      for p in possible_paths:
        if os.path.exists(p):
          target_file = p
          break

      if target_file:
        try:
          with open(target_file, "r", encoding="utf-8") as f:
            sub_code = f.read()
          try:
            from parser.gen.SapphireLexer import SapphireLexer
            from parser.gen.SapphireParser import SapphireParser
            from parser.ast_builder import ASTBuilder
          except ImportError:  # pragma: no cover
            from src.parser.gen.SapphireLexer import SapphireLexer
            from src.parser.gen.SapphireParser import SapphireParser
            from src.parser.ast_builder import ASTBuilder
          from antlr4 import InputStream, CommonTokenStream

          sub_lexer = SapphireLexer(InputStream(sub_code))
          sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
          sub_ast = ASTBuilder().visit(sub_parser.program())
          sub_checker = TypeChecker(source_file_path=target_file)
          try:
            sub_checker.check(sub_ast)
          except Exception:
            pass

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
                exp = sub_checker.symbol_table.lookup(spec.symbol) or sub_checker.symbol_table.lookup_type(spec.symbol)
                if exp:
                  mod_sym.exports[export_name] = exp
          else:
            for name, sym in sub_checker.symbol_table.current_scope.symbols.items():
              mod_sym.exports[name] = sym
            for name, t in sub_checker.symbol_table.current_scope.types.items():
              if name not in ("int", "float", "bool", "String", "none", "Arena"):
                mod_sym.exports[name] = t
        except Exception:
          pass

  def _declare_globals(self, program: ProgramNode) -> None:
    """Pre-pass to register types and global function symbols in the symbol table."""
    for decl in program.declarations:
      if isinstance(decl, StructDeclNode):
        if self.symbol_table.lookup_current_scope(decl.name):
          self.error(f"Redefinition of identifier '{decl.name}'.")
          continue
        struct_type = StructType(decl.name, decl.parent_name, decl.is_prototype, type_params=decl.type_params, ast_decl=decl)
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
          fn_type = FunctionType(
              p_types,
              ret_t,
              p_mutabilities,
              param_names=param_names,
              has_self=has_self,
              extern_name=extern_name,
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
        signature = FunctionType(
            param_types,
            ret_type,
            param_mutabilities,
            param_names=[p.name for p in decl.parameters],
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

    def process_struct(node: StructDeclNode):
      if node.name in processed:
        return

      struct_type = self.symbol_table.lookup_type(node.name)
      if not isinstance(struct_type, StructType):
        return

      if node.parent_name:
        parent_type = self.symbol_table.lookup_type(node.parent_name)
        if not parent_type:
          self.error(f"Parent struct '{node.parent_name}' not found for '{node.name}'.")
        elif not isinstance(parent_type, StructType):
          self.error(f"Parent '{node.parent_name}' of '{node.name}' is not a struct type.")
        else:
          parent_node = next((s for s in structs_to_process if s.name == node.parent_name), None)
          if parent_node:
            process_struct(parent_node)
          for field_name, field_obj in parent_type.fields.items():
            struct_type.fields[field_name] = field_obj

      for f in node.fields:
        ftype = self._resolve_type_node(f.field_type)
        if f.name in struct_type.fields:
          self.error(f"Field '{f.name}' in struct '{node.name}' shadows inherited parent field.")
        struct_type.fields[f.name] = StructField(f.name, ftype, f.is_mutable, f.default_expr is not None)

      processed.add(node.name)

    for s in structs_to_process:
      process_struct(s)

  def _register_impl_signatures(self, program: ProgramNode) -> None:
    """Pre-pass to register methods defined inside impl blocks onto struct types."""
    for decl in program.declarations:
      if isinstance(decl, ImplBlockNode):
        if decl.type_params:
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
          signature = FunctionType(
              param_types,
              ret_type,
              param_mutabilities,
              param_names=[p.name for p in func_decl.parameters],
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
    if node.type_params:
      return
    struct_type = self.symbol_table.lookup_type(node.struct_name)
    if not struct_type or not isinstance(struct_type, StructType):
      return

    self.current_struct = struct_type

    # If implementing a trait, verify contract is fully satisfied
    if node.trait_name:
      trait_type = self.symbol_table.lookup_type(node.trait_name)
      if isinstance(trait_type, TraitType):
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
    ret_type = self._resolve_type_node(func_decl.return_type) if func_decl.return_type else PrimitiveType("none")
    self.current_function = FunctionType(
        resolved_params,
        ret_type,
        param_mutabilities,
        param_names=[p.name for p in func_decl.parameters],
    )

    # Visit body
    self.visit(func_decl.body)

    # Verify constructor initializes all non-optional fields
    if func_decl.name == "__init__" and struct_type:
      for f_name, f_obj in struct_type.fields.items():
        if (f_name not in self.initialized_fields 
            and not isinstance(f_obj.field_type, OptionalType)
            and not f_obj.has_default):
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
    self.current_function = FunctionType(resolved_params, ret_types, param_mutabilities)

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
        v_type = self._resolve_type_node(val_type_node) if val_type_node else PrimitiveType("none")
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
      self.error(f"Cannot unpack {len(rhs_types)} value(s) into {len(node.names)} variable(s).")
      return

    for i, (name, val_type_node, expr_type) in enumerate(zip(node.names, node.val_types, rhs_types)):
      if val_type_node:
        val_type = self._resolve_type_node(val_type_node)
        if not expr_type.is_compatible(val_type):
          self.error(f"Cannot assign expression of type '{expr_type}' to variable '{name}' of type '{val_type}'.")
        var_type = val_type
        if isinstance(var_type, ArrayType) and isinstance(expr_type, ArrayType) and expr_type.size is not None and var_type.size is None:
          var_type = ArrayType(var_type.element_type, size=expr_type.size)
      else:
        if isinstance(expr_type, NoneType):
          self.error(f"Cannot infer type of '{name}' from 'none' alone. Specify an optional type annotation.")
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
      self.error(f"Cannot assign {len(rhs_types)} value(s) to {len(target_types)} target(s).")
      return

    for i, (target, target_type, expr_type) in enumerate(zip(node.targets, target_types, rhs_types)):
      if not expr_type.is_compatible(target_type):
        self.error(f"Cannot assign type '{expr_type}' to target of type '{target_type}'.")

      expr_node = node.exprs[0] if len(node.exprs) == 1 else node.exprs[i]
      arena_name = self._get_arena_dependency(expr_node)
      if arena_name:
        target_sym = self._get_target_symbol(target)
        if target_sym:
          target_sym.arena_dependency = arena_name
          arena_sym = self.symbol_table.lookup(arena_name)
          if arena_sym and arena_sym.scope_defined and target_sym.scope_defined:
            if self._is_descendant_scope(arena_sym.scope_defined, target_sym.scope_defined) and arena_sym.scope_defined != target_sym.scope_defined:
              self.error(f"Variable '{target_sym.name}' in outer scope cannot hold a reference to an object allocated in nested arena '{arena_name}'.")

      if self.is_in_init and isinstance(target, MemberAccessNode):
        if isinstance(target.receiver, IdentifierNode) and target.receiver.name == "self":
          self.initialized_fields.add(target.member)

  def _check_lvalue(self, node: ASTNode) -> Type:
    """Helper to check if AST node is a mutable lvalue and returns its resolved type."""
    if isinstance(node, IdentifierNode):
      sym = self.symbol_table.lookup(node.name)
      if not sym:
        self.error(f"Undefined identifier '{node.name}'.")
        return PrimitiveType("none")
      if not isinstance(sym, VariableSymbol):
        self.error(f"Identifier '{node.name}' is not a mutable variable.")
        return sym.symbol_type
      if not sym.is_mutable and sym.name != "self":
        self.error(f"Cannot assign to constant variable '{node.name}'.")
      return sym.symbol_type

    if isinstance(node, MemberAccessNode):
      receiver_type = self.visit(node.receiver)
      # Unwrap optional if chained
      if node.is_optional and isinstance(receiver_type, OptionalType):
        receiver_type = receiver_type.base_type

      if not isinstance(receiver_type, StructType):
        self.error("Property access target is not a struct.")
        return PrimitiveType("none")

      # Field access
      field = receiver_type.fields.get(node.member)
      if not field:
        self.error(f"Struct '{receiver_type.name}' has no field '{node.member}'.")
        return PrimitiveType("none")

      # Check field mutability or constructor exemption
      # Inside __init__ or clone blocks, self fields are always assignable (even if immutable let fields)
      is_self = isinstance(node.receiver, IdentifierNode) and node.receiver.name == "self"
      if not field.is_mutable:
        if not ((self.is_in_init or self.is_in_clone_init) and is_self):
          self.error(f"Cannot assign to constant field '{node.member}' of '{receiver_type.name}'.")

      # Verify self constness
      if is_self:
        self_sym = self.symbol_table.lookup("self")
        if self_sym and not self_sym.is_mutable:
          self.error(f"Cannot mutate field '{node.member}' within a constant method.")

      return field.field_type

    if isinstance(node, IndexExprNode):
      array_type = self.visit(node.array)
      if not isinstance(array_type, ArrayType):
        self.error("Cannot index non-array type.")
        return PrimitiveType("none")

      # Enforce that array target is a mutable variable
      if isinstance(node.array, IdentifierNode):
        sym = self.symbol_table.lookup(node.array.name)
        if sym and not sym.is_mutable:
          self.error(f"Cannot assign to index of constant array '{sym.name}'.")

      index_type = self.visit(node.index)
      if index_type != PrimitiveType("int"):
        self.error("Array index must be of type 'int'.")

      self._check_array_bounds(node, array_type)

      return array_type.element_type

    self.error("Invalid assignment target (not an lvalue).")
    return PrimitiveType("none")

  def visit_ExprStmtNode(self, node: ExprStmtNode) -> None:
    self.visit(node.expr)

  def visit_ReturnNode(self, node: ReturnNode) -> None:
    if not self.current_function:
      self.error("Return statement outside function context.")
      return

    expected_ret_types = self.current_function.return_types
    actual_ret_types = [self.visit(e) for e in node.expressions] if node.expressions else []

    if len(actual_ret_types) != len(expected_ret_types):
      if len(expected_ret_types) == 0:
        self.error(f"Function with no return type cannot return {len(actual_ret_types)} values.")
      else:
        self.error(f"Function expected {len(expected_ret_types)} return value(s), but return statement provided {len(actual_ret_types)} value(s).")
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
    expr_type = self.visit(node.expr)
    self._match_stack[-1].append(expr_type)

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
          has_ellipsis = True
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

  def visit_ForNode(self, node: ForNode) -> None:
    iter_type = self.visit(node.iterable)
    if not isinstance(iter_type, ArrayType):
      self.error("For-in loop source must be an array type.")
      elem_type = PrimitiveType("none")
    else:
      elem_type = iter_type.element_type

    self.symbol_table.enter_scope()
    self.symbol_table.define(node.loop_var, VariableSymbol(node.loop_var, elem_type, node.is_mutable))
    self.visit(node.block)
    self.symbol_table.exit_scope()

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
      return PrimitiveType("string")
    return NoneType()

  def visit_IdentifierNode(self, node: IdentifierNode) -> Type:
    sym = self.symbol_table.lookup(node.name)
    if not sym:
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
      if node.op == "+" and ((isinstance(left, PrimitiveType) and left.name in ("String", "string")) or (isinstance(right, PrimitiveType) and right.name in ("String", "string"))):
        node.is_string_concat = True
        return PrimitiveType("string")
      # Supports int and float operations
      is_numeric_left = isinstance(left, PrimitiveType) and left.name in ("int", "float")
      is_numeric_right = isinstance(right, PrimitiveType) and right.name in ("int", "float")
      if not (is_numeric_left and is_numeric_right):
        self.error(f"Arithmetic operator '{node.op}' requires numeric types.")
        return PrimitiveType("none")

      # Common type rules
      if left.name == "float" or right.name == "float":
        return PrimitiveType("float")
      return PrimitiveType("int")

    return PrimitiveType("none")

  def visit_UnaryOpNode(self, node: UnaryOpNode) -> Type:
    expr_type = self.visit(node.expr)
    if node.op == "!":
      if expr_type != PrimitiveType("bool"):
        self.error("Logical NOT operator requires a boolean expression.")
      return PrimitiveType("bool")
    if node.op in ("-", "+"):
      is_numeric = isinstance(expr_type, PrimitiveType) and expr_type.name in ("int", "float")
      if not is_numeric:
        self.error(f"Numeric operator '{node.op}' requires a numeric expression.")
      return expr_type
    return PrimitiveType("none")

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
      return type_obj.name not in ("int", "float", "bool")
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
        method = receiver_type.methods.get(node.callee.member)
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
    if getattr(signature, "has_self", False) and isinstance(callee_node, MemberAccessNode):
      expected_param_types = signature.param_types[1:]

    for idx, arg in enumerate(arguments):
      # Pass expected parameter type for lambda type inference
      old_expected = self.expected_type
      if idx < len(expected_param_types):
        self.expected_type = expected_param_types[idx]
      else:
        self.expected_type = None

      arg_type = self.visit(arg.expr)
      self.expected_type = old_expected

      # Check positional constraints (since this is basic subset)
      if idx < len(expected_param_types):
        param_type = expected_param_types[idx]
        if not arg_type.is_compatible(param_type):
          self.error(f"Argument type mismatch at position {idx+1}. Expected '{param_type}', got '{arg_type}'.")

      else:
        # Extra parameter
        if not is_constructor:
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

    if isinstance(receiver_type, ModuleType):
      if isinstance(node.receiver, IdentifierNode):
        mod_sym = self.symbol_table.lookup(node.receiver.name)
        if isinstance(mod_sym, ModuleSymbol):
          exp_sym = mod_sym.lookup_export(node.member)
          if exp_sym:
            return exp_sym.symbol_type if hasattr(exp_sym, "symbol_type") else exp_sym
      return PrimitiveType("none")

    if isinstance(receiver_type, EnumType):
      if node.member in receiver_type.variants:
        return receiver_type
      self.error(f"Enum '{receiver_type.name}' has no member '{node.member}'.")
      return PrimitiveType("none")

    if isinstance(receiver_type, TraitType):
      method = receiver_type.methods.get(node.member)
      if method:
        if getattr(method, "extern_name", None):
          node.target_name = method.extern_name
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
    method = receiver_type.methods.get(node.member)
    if method:
      return method.method_type

    self.error(f"Struct '{receiver_type.name}' has no member '{node.member}'.")
    return PrimitiveType("none")

  def visit_CloneNode(self, node: CloneNode) -> Type:
    expr_type = self.visit(node.expr)
    if not isinstance(expr_type, StructType):
      self.error("Clone expression target must be a struct instance.")
      return PrimitiveType("none")

    # Verify struct is a prototype struct (or inherits from one)
    is_proto = False
    curr = expr_type
    while curr:
      if curr.is_prototype:
        is_proto = True
        break
      if curr.parent_name:
        parent = self.symbol_table.lookup_type(curr.parent_name)
        if isinstance(parent, StructType):
          curr = parent
        else:
          break
      else:
        break

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

  def visit_LambdaNode(self, node: LambdaNode) -> Type:
    self.symbol_table.enter_scope()

    expected_func = self.expected_type
    try:
      from semantics.symbol_table import OptionalType
    except ImportError:  # pragma: no cover
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
        ptype = PrimitiveType("none")
      self.symbol_table.define(p.name, VariableSymbol(p.name, ptype, is_mutable=False))
      param_types.append(ptype)

    body_type = self.visit(node.body)

    # Lambda expression implicit return
    ret_type = body_type if not isinstance(node.body, BlockNode) else PrimitiveType("none")
    if node.return_type:
      ret_type = self._resolve_type_node(node.return_type)
    elif (
        expected_func
        and isinstance(expected_func, FunctionType)
    ):
      ret_type = expected_func.return_type

    self.symbol_table.exit_scope()
    return FunctionType(param_types, ret_type)

  def visit_ArrayLiteralNode(self, node: ArrayLiteralNode) -> Type:
    if not node.elements:
      return ArrayType(NoneType(), size=0)

    elem_types = [self.visit(e) for e in node.elements]
    first_type = elem_types[0]
    for etype in elem_types[1:]:
      if not etype.is_compatible(first_type) and not first_type.is_compatible(etype):
        self.error("Inconsistent element types in array literal.")
        break
    return ArrayType(first_type, size=len(node.elements))

  def visit_MapLiteralNode(self, node: MapLiteralNode) -> Type:
    if not node.entries:
      return MapType(NoneType(), NoneType())

    first_key_type = self.visit(node.entries[0].key)
    first_val_type = self.visit(node.entries[0].value)

    def is_valid_key_type(ktype: Type) -> bool:
      return (
          (isinstance(ktype, PrimitiveType) and ktype.name in ("string", "int"))
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
      self._check_array_bounds(node, container_type)
      return container_type.element_type
    elif isinstance(container_type, MapType):
      if not index_type.is_compatible(container_type.key_type) and not container_type.key_type.is_compatible(index_type):
        self.error(f"Map index type '{index_type}' is not compatible with key type '{container_type.key_type}'.")
      self._check_map_literal_key(node)
      return container_type.value_type
    else:
      self.error("Cannot index non-array type.")
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
