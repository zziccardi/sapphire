"""Generics substitution and monomorphization helper module for Sapphire.

Decouples generic AST type parameter substitution and mangling from the
monolithic TypeChecker.
"""

import copy
from typing import Any

from src.parser.ast import ASTNode, BasicTypeNode, ImplBlockNode, TypeNode
from src.semantics.symbol_table import (
  ArrayType,
  FunctionSymbol,
  FunctionType,
  MapType,
  NoneType,
  OptionalType,
  PrimitiveType,
  StructField,
  StructMethod,
  StructSymbol,
  StructType,
  TraitType,
  Type,
)

MAX_MONO_DEPTH = 32


class GenericsChecker:
  """Helper class for generic AST substitutions and type mangling."""

  @staticmethod
  def substitute_ast(node: Any, param_map: dict[str, TypeNode]) -> Any:
    """Recursively replaces generic parameter identifiers with concrete
    TypeNodes
    in an AST snippet.
    """
    if node is None:
      return None
    if isinstance(node, BasicTypeNode):
      if node.name in param_map:
        return copy.deepcopy(param_map[node.name])
      if node.type_args:
        new_args = [
          GenericsChecker.substitute_ast(t, param_map) for t in node.type_args
        ]
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
    """Recursively converts a semantic Type into a clean, valid identifier
    string
    component.
    """
    if isinstance(type_obj, OptionalType):
      return f"Opt_{GenericsChecker.mangle_type_name(type_obj.base_type)}"
    elif isinstance(type_obj, ArrayType):
      if type_obj.is_fixed_size and type_obj.size is not None:
        elem_m = GenericsChecker.mangle_type_name(type_obj.element_type)
        return f"FixedArr_{type_obj.size}_{elem_m}"
      return f"Arr_{GenericsChecker.mangle_type_name(type_obj.element_type)}"
    elif isinstance(type_obj, MapType):
      key_m = GenericsChecker.mangle_type_name(type_obj.key_type)
      val_m = GenericsChecker.mangle_type_name(type_obj.value_type)
      return f"Map_{key_m}_{val_m}"
    elif isinstance(type_obj, FunctionType):
      p_str = "_".join(
        GenericsChecker.mangle_type_name(t) for t in type_obj.param_types
      )
      r_str = (
        "_".join(
          GenericsChecker.mangle_type_name(t) for t in type_obj.return_types
        )
        or "void"
      )
      return f"Fn_{p_str}_to_{r_str}"
    else:
      raw = str(type_obj)
      clean = "".join(c if c.isalnum() else "_" for c in raw)
      clean = "_".join(filter(None, clean.split("_")))
      return clean or "type"

  @staticmethod
  def _build_impl_param_map(
    decl: ImplBlockNode,
    generic_struct_type: StructType,
    type_arg_nodes: list[TypeNode],
  ) -> dict[str, TypeNode]:
    """Builds a substitution map keyed by the impl block's own type parameters.
    """
    impl_map = dict(
      zip(generic_struct_type.type_params, type_arg_nodes, strict=False)
    )
    struct_args = getattr(decl, "struct_type_args", None) or []
    if len(struct_args) == len(type_arg_nodes):
      for s_arg, t_node in zip(struct_args, type_arg_nodes, strict=False):
        if isinstance(s_arg, BasicTypeNode) and not s_arg.type_args:
          impl_map[s_arg.name] = t_node
    elif getattr(decl, "type_params", None) and len(decl.type_params) == len(
      type_arg_nodes
    ):
      for tp_name, t_node in zip(
        decl.type_params, type_arg_nodes, strict=False
      ):
        impl_map[tp_name] = t_node
    return impl_map

  @staticmethod
  def _is_void_return(ret_t: list[Type]) -> bool:
    return len(ret_t) == 0 or (
      len(ret_t) == 1
      and (
        isinstance(ret_t[0], NoneType)
        or (
          isinstance(ret_t[0], PrimitiveType)
          and ret_t[0].name in ("none", "void")
        )
      )
    )

  @staticmethod
  def monomorphize_struct(
    checker: Any,
    generic_struct_type: StructType,
    type_arg_nodes: list[TypeNode],
    resolved_type_args: list[Type],
  ) -> StructType:
    """Monomorphizes a generic struct template for a specific set of concrete
    type
    arguments.
    """
    if len(resolved_type_args) != len(generic_struct_type.type_params):
      checker.error(
        f"Generic struct '{generic_struct_type.name}' expects "
        f"{len(generic_struct_type.type_params)} type argument(s), got "
        f"{len(resolved_type_args)}."
      )
      return generic_struct_type

    arg_names = [
      GenericsChecker.mangle_type_name(t) for t in resolved_type_args
    ]
    mangled_name = f"{generic_struct_type.name}__{'_'.join(arg_names)}"
    existing = checker.symbol_table.lookup_type(mangled_name)
    if existing and isinstance(existing, StructType):
      return existing

    mono_depth = getattr(checker, "_mono_depth", 0)
    if mono_depth >= MAX_MONO_DEPTH:
      checker.error(
        f"Maximum generic monomorphization recursion depth ({MAX_MONO_DEPTH}) "
        f"exceeded while instantiating '{mangled_name}'."
      )
      return generic_struct_type

    if not generic_struct_type.ast_decl:  # pragma: no cover
      return generic_struct_type

    param_map = dict(
      zip(generic_struct_type.type_params, type_arg_nodes, strict=False)
    )
    cloned_decl = GenericsChecker.substitute_ast(
      generic_struct_type.ast_decl, param_map
    )
    cloned_decl.name = mangled_name
    cloned_decl.type_params = []
    cloned_decl.is_monomorphized = True

    mono_struct_type = StructType(
      mangled_name,
      parent_names=cloned_decl.parent_names,
      is_prototype=cloned_decl.is_prototype,
      defining_module=generic_struct_type.defining_module,
    )
    root_scope = checker.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent
    root_scope.define_type(mangled_name, mono_struct_type)
    root_scope.define(
      mangled_name, StructSymbol(mangled_name, mono_struct_type)
    )

    old_mono = getattr(checker, "_in_monomorphization", False)
    checker._in_monomorphization = True
    checker._mono_depth = mono_depth + 1
    try:
      # Resolve fields for monomorphized struct
      for f in cloned_decl.fields:
        ftype = checker._resolve_field_type(f, mono_struct_type.name)
        has_default = (
          f.default_expr is not None
          or checker._has_implicit_default_value(ftype)
        )
        mono_struct_type.fields[f.name] = StructField(
          f.name,
          ftype,
          f.is_mutable,
          has_default=has_default,
          has_explicit_default=f.default_expr is not None,
        )

      from src.semantics.struct_layout_pass import StructLayoutPass

      StructLayoutPass.check_unboxed_recursion(checker, [mono_struct_type])
      StructLayoutPass.check_arena_field_ordering(checker, [mono_struct_type])

      # Instantiate generic impl blocks matching generic_struct_type.name
      if hasattr(checker, "program") and checker.program:
        for decl in list(checker.program.declarations):
          if (
            isinstance(decl, ImplBlockNode)
            and decl.struct_name == generic_struct_type.name
          ):
            impl_param_map = GenericsChecker._build_impl_param_map(
              decl, generic_struct_type, type_arg_nodes
            )
            cloned_impl = GenericsChecker.substitute_ast(decl, impl_param_map)
            cloned_impl.struct_name = mangled_name
            cloned_impl.type_params = []
            cloned_impl.struct_type_args = []
            cloned_impl.is_monomorphized = True

            trait_type = None
            if cloned_impl.trait_name:
              trait_type = checker.symbol_table.lookup_type(
                cloned_impl.trait_name
              )
              if isinstance(trait_type, TraitType):
                mono_struct_type.implemented_traits.add(trait_type.name)
                mono_struct_type.implemented_trait_types[trait_type.name] = (
                  trait_type
                )
                trait_type.add_implementor(mono_struct_type)
              else:
                checker.error(
                  "Cannot implement undefined trait "
                  f"'{cloned_impl.trait_name}'."
                )

            for member in cloned_impl.members:
              if trait_type and member.func_decl.name in trait_type.methods:
                trait_method = trait_type.methods[member.func_decl.name]
                if (
                  member.modifier is None
                  and getattr(trait_method.ast_decl, "modifier", None)
                  == "static"
                ):
                  member.modifier = "static"
              func_decl = member.func_decl
              p_types = [
                checker._resolve_type_node(p.param_type)
                for p in func_decl.parameters
              ]
              ret_t = checker._resolve_return_types(func_decl)
              num_defaults = sum(
                1
                for p in func_decl.parameters
                if getattr(p, "default_expr", None) is not None
              )
              param_defaults = [
                getattr(p, "default_expr", None) for p in func_decl.parameters
              ]
              sig = FunctionType(
                p_types,
                ret_t,
                [p.is_mutable for p in func_decl.parameters],
                [p.name for p in func_decl.parameters],
                num_defaults=num_defaults,
                param_defaults=param_defaults,
                ast_decl=func_decl,
              )

              if func_decl.name == "__del__":
                if member.modifier == "static":
                  checker.error("Destructor '__del__' cannot be static.")
                if len(func_decl.parameters) > 0:
                  checker.error(
                    "Destructor '__del__' must take 0 parameters; 'self' is "
                    "implicitly available."
                  )
                if not GenericsChecker._is_void_return(ret_t):
                  checker.error("Destructor '__del__' must return void.")
              elif func_decl.name == "__init__":
                if member.modifier == "static":
                  checker.error("Constructor '__init__' cannot be static.")
                if not GenericsChecker._is_void_return(ret_t):
                  checker.error("Constructor '__init__' must return void.")

              if func_decl.name in mono_struct_type.methods:
                checker.error(
                  f"Method '{func_decl.name}' redefined in struct "
                  f"'{generic_struct_type.name}'."
                )
              mono_struct_type.methods[func_decl.name] = StructMethod(
                func_decl.name, sig, member.modifier
              )
            checker.program.declarations.append(cloned_impl)

        checker.program.declarations.append(cloned_decl)
    finally:
      checker._mono_depth = mono_depth
      checker._in_monomorphization = old_mono

    return mono_struct_type

  @staticmethod
  def monomorphize_function(
    checker: Any,
    func_sym: FunctionSymbol,
    type_arg_nodes: list[TypeNode],
    resolved_type_args: list[Type],
  ) -> str:
    """Monomorphizes a generic function template for a specific set of concrete
    type arguments.
    """
    if len(resolved_type_args) != len(func_sym.type_params):
      checker.error(
        f"Generic function '{func_sym.name}' expects "
        f"{len(func_sym.type_params)} type argument(s), got "
        f"{len(resolved_type_args)}."
      )
      return func_sym.name

    arg_names = [
      GenericsChecker.mangle_type_name(t) for t in resolved_type_args
    ]
    mangled_name = f"{func_sym.name}__{'_'.join(arg_names)}"
    existing = checker.symbol_table.lookup(mangled_name)
    if existing and isinstance(existing, FunctionSymbol):
      return mangled_name

    mono_depth = getattr(checker, "_mono_depth", 0)
    if mono_depth >= MAX_MONO_DEPTH:
      checker.error(
        f"Maximum generic monomorphization recursion depth ({MAX_MONO_DEPTH}) "
        f"exceeded while instantiating '{mangled_name}'."
      )
      return func_sym.name

    if not func_sym.ast_decl:  # pragma: no cover
      return func_sym.name

    param_map = dict(zip(func_sym.type_params, type_arg_nodes, strict=False))
    cloned_func = GenericsChecker.substitute_ast(func_sym.ast_decl, param_map)
    cloned_func.name = mangled_name
    cloned_func.type_params = []
    cloned_func.is_monomorphized = True

    root_scope = checker.symbol_table.current_scope
    while root_scope.parent:
      root_scope = root_scope.parent

    old_mono = getattr(checker, "_in_monomorphization", False)
    saved_scope = checker.symbol_table.current_scope
    saved_frozen = list(getattr(checker, "_temporary_frozen_lvalues", []))
    saved_loop_depth = getattr(checker, "loop_depth", 0)
    saved_branch_depth = getattr(checker, "_branch_depth", 0)
    saved_func = checker.current_function
    saved_func_scope = checker.current_function_scope
    saved_struct = checker.current_struct
    saved_expected = checker.expected_type
    saved_in_init = checker.is_in_init
    saved_in_del = checker.is_in_del
    saved_moved = set(checker.moved_symbols)
    saved_uninit = set(getattr(checker, "uninitialized_symbols", set()))

    checker._in_monomorphization = True
    checker._mono_depth = mono_depth + 1
    checker.symbol_table.current_scope = root_scope
    checker._temporary_frozen_lvalues = []
    checker.loop_depth = 0
    checker._branch_depth = 0
    checker.current_function = None
    checker.current_function_scope = None
    checker.current_struct = None
    checker.expected_type = None
    checker.is_in_init = False
    checker.is_in_del = False
    checker._restore_moved_symbols(set())
    checker.uninitialized_symbols = set()

    try:
      p_types = [
        checker._resolve_type_node(p.param_type) for p in cloned_func.parameters
      ]
      ret_t = checker._resolve_return_types(cloned_func)
      num_defaults = sum(
        1
        for p in cloned_func.parameters
        if getattr(p, "default_expr", None) is not None
      )
      param_defaults = [
        getattr(p, "default_expr", None) for p in cloned_func.parameters
      ]
      mono_func_type = FunctionType(
        p_types,
        ret_t,
        [p.is_mutable for p in cloned_func.parameters],
        [p.name for p in cloned_func.parameters],
        num_defaults=num_defaults,
        param_defaults=param_defaults,
        ast_decl=cloned_func,
      )
      mono_func_sym = FunctionSymbol(
        mangled_name, mono_func_type, ast_decl=cloned_func
      )
      root_scope.define(mangled_name, mono_func_sym)

      cloned_func._already_type_checked = True
      if hasattr(checker, "program") and checker.program:
        checker.program.declarations.append(cloned_func)

      # Type check the body of the monomorphized function in clean root scope
      checker.visit_FuncDeclNode(cloned_func)
    finally:
      checker.symbol_table.current_scope = saved_scope
      checker._temporary_frozen_lvalues = saved_frozen
      checker.loop_depth = saved_loop_depth
      checker._branch_depth = saved_branch_depth
      checker.current_function = saved_func
      checker.current_function_scope = saved_func_scope
      checker.current_struct = saved_struct
      checker.expected_type = saved_expected
      checker.is_in_init = saved_in_init
      checker.is_in_del = saved_in_del
      checker._restore_moved_symbols(saved_moved)
      checker.uninitialized_symbols = saved_uninit
      checker._mono_depth = mono_depth
      checker._in_monomorphization = old_mono
    return mangled_name
