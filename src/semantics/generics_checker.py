"""Generics substitution and monomorphization helper module for Sapphire.

Decouples generic AST type parameter substitution and mangling from the
monolithic TypeChecker.
"""

import copy
from typing import Any, Dict, List
from src.parser.ast import ASTNode, BasicTypeNode, ImplBlockNode, TypeNode
from src.semantics.symbol_table import (
    Type,
    OptionalType,
    ArrayType,
    MapType,
    FunctionType,
    FunctionSymbol,
    StructType,
    StructSymbol,
    StructField,
    StructMethod,
)


class GenericsChecker:
  """Helper class for generic AST substitutions and type mangling."""

  @staticmethod
  def substitute_ast(node: Any, param_map: Dict[str, TypeNode]) -> Any:
    """Recursively replaces generic parameter identifiers with concrete TypeNodes in an AST snippet."""
    if node is None:
      return None
    if isinstance(node, BasicTypeNode):
      if node.name in param_map:
        return copy.deepcopy(param_map[node.name])
      if node.type_args:
        new_args = [GenericsChecker.substitute_ast(t, param_map) for t in node.type_args]
        new_node = copy.deepcopy(node)
        new_node.type_args = new_args
        return new_node
      return copy.deepcopy(node)
    if isinstance(node, list):
      return [GenericsChecker.substitute_ast(item, param_map) for item in node]
    if isinstance(node, ASTNode):
      new_node = copy.copy(node)
      for k, v in node.__dict__.items():
        if isinstance(v, (ASTNode, list)):
          setattr(new_node, k, GenericsChecker.substitute_ast(v, param_map))
        else:
          setattr(new_node, k, v)
      return new_node
    return copy.deepcopy(node)

  @staticmethod
  def mangle_type_name(type_obj: Type) -> str:
    """Recursively converts a semantic Type into a clean, valid identifier string component."""
    if isinstance(type_obj, OptionalType):
      return f"Opt_{GenericsChecker.mangle_type_name(type_obj.base_type)}"
    elif isinstance(type_obj, ArrayType):
      return f"Arr_{GenericsChecker.mangle_type_name(type_obj.element_type)}"
    elif isinstance(type_obj, MapType):
      return f"Map_{GenericsChecker.mangle_type_name(type_obj.key_type)}_{GenericsChecker.mangle_type_name(type_obj.value_type)}"
    elif isinstance(type_obj, FunctionType):
      p_str = "_".join(GenericsChecker.mangle_type_name(t) for t in type_obj.param_types)
      r_str = "_".join(GenericsChecker.mangle_type_name(t) for t in type_obj.return_types)
      return f"Fn_{p_str}_to_{r_str}"
    else:
      raw = str(type_obj)
      clean = "".join(c if c.isalnum() else "_" for c in raw)
      clean = "_".join(filter(None, clean.split("_")))
      return clean or "type"

  @staticmethod
  def monomorphize_struct(
      checker: Any,
      generic_struct_type: StructType,
      type_arg_nodes: List[TypeNode],
      resolved_type_args: List[Type],
  ) -> StructType:
    """Monomorphizes a generic struct template for a specific set of concrete type arguments."""
    arg_names = [GenericsChecker.mangle_type_name(t) for t in resolved_type_args]
    mangled_name = f"{generic_struct_type.name}__{'_'.join(arg_names)}"
    existing = checker.symbol_table.lookup_type(mangled_name)
    if existing and isinstance(existing, StructType):
      return existing

    if not generic_struct_type.ast_decl:  # pragma: no cover
      return generic_struct_type

    param_map = dict(zip(generic_struct_type.type_params, type_arg_nodes))
    cloned_decl = GenericsChecker.substitute_ast(generic_struct_type.ast_decl, param_map)
    cloned_decl.name = mangled_name
    cloned_decl.type_params = []

    mono_struct_type = StructType(mangled_name, parent_names=cloned_decl.parent_names, is_prototype=cloned_decl.is_prototype)
    root_scope = checker.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    root_scope.define_type(mangled_name, mono_struct_type)
    root_scope.define(mangled_name, StructSymbol(mangled_name, mono_struct_type))

    # Resolve fields for monomorphized struct
    for f in cloned_decl.fields:
      ftype = checker._resolve_field_type(f, mono_struct_type.name)
      has_default = f.default_expr is not None or checker._has_implicit_default_value(ftype)
      mono_struct_type.fields[f.name] = StructField(
          f.name, ftype, f.is_mutable, has_default=has_default, has_explicit_default=f.default_expr is not None
      )

    # Instantiate generic impl blocks matching generic_struct_type.name
    if hasattr(checker, "program") and checker.program:
      for decl in checker.program.declarations:
        if isinstance(decl, ImplBlockNode) and decl.struct_name == generic_struct_type.name:
          cloned_impl = GenericsChecker.substitute_ast(decl, param_map)
          cloned_impl.struct_name = mangled_name
          cloned_impl.type_params = []
          cloned_impl.struct_type_args = []
          cloned_impl.trait_type_args = []
          for member in cloned_impl.members:
            func_decl = member.func_decl
            p_types = [checker._resolve_type_node(p.param_type) for p in func_decl.parameters]
            ret_t = checker._resolve_return_types(func_decl)
            num_defaults = sum(1 for p in func_decl.parameters if getattr(p, "default_expr", None) is not None)
            sig = FunctionType(p_types, ret_t, [p.is_mutable for p in func_decl.parameters], [p.name for p in func_decl.parameters], num_defaults=num_defaults)
            mono_struct_type.methods[func_decl.name] = StructMethod(func_decl.name, sig, member.modifier)
          checker.program.declarations.append(cloned_impl)

      checker.program.declarations.append(cloned_decl)

    return mono_struct_type

  @staticmethod
  def monomorphize_function(
      checker: Any,
      func_sym: FunctionSymbol,
      type_arg_nodes: List[TypeNode],
      resolved_type_args: List[Type],
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete type arguments."""
    arg_names = [GenericsChecker.mangle_type_name(t) for t in resolved_type_args]
    mangled_name = f"{func_sym.name}__{'_'.join(arg_names)}"
    existing = checker.symbol_table.lookup(mangled_name)
    if existing and isinstance(existing, FunctionSymbol):
      return mangled_name

    if not func_sym.ast_decl:  # pragma: no cover
      return func_sym.name

    param_map = dict(zip(func_sym.type_params, type_arg_nodes))
    cloned_func = GenericsChecker.substitute_ast(func_sym.ast_decl, param_map)
    cloned_func.name = mangled_name
    cloned_func.type_params = []

    p_types = [checker._resolve_type_node(p.param_type) for p in cloned_func.parameters]
    ret_t = checker._resolve_return_types(cloned_func)
    num_defaults = sum(1 for p in cloned_func.parameters if getattr(p, "default_expr", None) is not None)
    mono_func_type = FunctionType(
        p_types,
        ret_t,
        [p.is_mutable for p in cloned_func.parameters],
        [p.name for p in cloned_func.parameters],
        num_defaults=num_defaults,
    )
    mono_func_sym = FunctionSymbol(mangled_name, mono_func_type, ast_decl=cloned_func)
    root_scope = checker.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    root_scope.define(mangled_name, mono_func_sym)

    if hasattr(checker, "program") and checker.program:
      checker.program.declarations.append(cloned_func)

    saved_func = checker.current_function
    # Type check the body of the monomorphized function
    checker.visit_FuncDeclNode(cloned_func)
    checker.current_function = saved_func
    return mangled_name
