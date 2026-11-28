"""Struct layout and inheritance resolution pass for Sapphire semantic analyzer.

Handles Pass 2: resolves static struct inheritance, copies parent fields,
detects circular inheritance, and validates shadowing or duplicate field
layouts.
"""

from collections.abc import Iterator
from typing import Any

from sapphire.parser.ast import ProgramNode, StructDeclNode, VarDeclNode
from sapphire.semantics.const_eval import is_constant_expression
from sapphire.semantics.symbol_table import (
  ArenaType,
  ArrayType,
  MapType,
  OptionalType,
  StructField,
  StructType,
  Type,
)


class StructLayoutPass:
  """Resolves static composition and field layouts for inherited structs."""

  @staticmethod
  def _iter_inline_structs(ftype: Type) -> Iterator[StructType]:
    """Yields non-proto StructTypes stored inline within *ftype*."""
    if isinstance(ftype, OptionalType):
      yield from StructLayoutPass._iter_inline_structs(ftype.base_type)
    elif isinstance(ftype, ArrayType) and ftype.is_fixed_size:
      yield from StructLayoutPass._iter_inline_structs(ftype.element_type)
    elif isinstance(ftype, StructType) and not ftype.is_prototype:
      yield ftype

  @staticmethod
  def check_unboxed_recursion(checker: Any, struct_types: list[Any]) -> None:
    """Rejects direct or mutual unboxed recursion across non-proto structs."""
    reported_cycles: set[frozenset] = getattr(
      checker, "_reported_recursive_struct_cycles", None
    )
    if reported_cycles is None:
      reported_cycles = set()
      checker._reported_recursive_struct_cycles = reported_cycles

    fully_checked: set[str] = set()

    def dfs(st: StructType, path: list[str]) -> None:
      for field_name, field_obj in st.fields.items():
        for target_st in StructLayoutPass._iter_inline_structs(
          field_obj.field_type
        ):
          if target_st.name in path:
            idx = path.index(target_st.name)
            cycle_key = frozenset(path[idx:])
            if cycle_key not in reported_cycles:
              reported_cycles.add(cycle_key)
              checker.error(
                f"Recursive struct '{target_st.name}' has infinite inline "
                f"size via field '{field_name}'; "
                f"use 'Ref<{target_st.name}>', 'SharedRef<{target_st.name}>', "
                f"dynamic '[{target_st.name}]', "
                f"or 'proto' in an Arena."
              )
          elif target_st.name not in fully_checked:
            dfs(target_st, path + [target_st.name])

    for st in struct_types:
      if (
        isinstance(st, StructType)
        and not st.is_prototype
        and st.name not in fully_checked
      ):
        dfs(st, [st.name])
        fully_checked.add(st.name)

  @staticmethod
  def resolve_struct_layouts(checker: Any, program: ProgramNode) -> None:
    """Resolves struct layouts and module-level let constants in source order.
    """
    structs_to_process = [
      d
      for d in program.declarations
      if isinstance(d, StructDeclNode)
      and not d.type_params
      and not getattr(d, "is_monomorphized", False)
    ]
    processed = set()
    visiting = set()

    def process_struct(node: StructDeclNode):
      if node.name in processed:
        return
      if node.name in visiting:
        checker.error(
          f"Circular inheritance detected involving struct '{node.name}'."
        )
        return
      visiting.add(node.name)

      struct_type = checker.symbol_table.lookup_type(node.name)
      if not isinstance(struct_type, StructType):
        visiting.remove(node.name)
        return

      if node.parent_names:
        struct_type.parent_types = []
        for parent_name in node.parent_names:
          parent_type = checker.symbol_table.lookup_type(parent_name)
          if not parent_type:
            checker.error(
              f"Parent struct '{parent_name}' not found for '{node.name}'."
            )
          elif not isinstance(parent_type, StructType):
            checker.error(
              f"Parent '{parent_name}' of '{node.name}' is not a struct type."
            )
          else:
            if parent_type not in struct_type.parent_types:
              struct_type.parent_types.append(parent_type)
            parent_node = next(
              (s for s in structs_to_process if s.name == parent_name), None
            )
            if parent_node:
              process_struct(parent_node)
            for field_name, field_obj in parent_type.fields.items():
              if field_name in struct_type.fields:
                checker.error(
                  f"Duplicate field '{field_name}' in struct '{node.name}' "
                  "inherited from multiple parents."
                )
              else:
                struct_type.fields[field_name] = field_obj

      for f in node.fields:
        if getattr(f, "is_static", False):
          if f.is_mutable:
            checker.error(
              f"Static field '{f.name}' in struct '{node.name}' must be "
              "immutable ('static let'); 'static var' is not permitted.",
              node=f,
            )
            continue
          if f.default_expr is None:
            checker.error(
              f"Static field '{f.name}' in struct '{node.name}' requires a "
              "compile-time constant initializer.",
              node=f,
            )
            continue
          is_const, const_err = is_constant_expression(
            f.default_expr, checker.symbol_table
          )
          if not is_const:
            checker.error(
              const_err
              or f"Static field '{f.name}' in struct '{node.name}' must be "
              "initialized with a compile-time constant expression.",
              node=f,
            )
          ftype = checker._resolve_field_type(f, node.name)
          if (
            f.name in struct_type.static_fields
            or f.name in struct_type.fields
          ):
            checker.error(
              f"Duplicate field '{f.name}' in struct '{node.name}'.",
              node=f,
            )
          struct_type.static_fields[f.name] = StructField(
            f.name,
            ftype,
            False,
            has_default=True,
            has_explicit_default=True,
            is_static=True,
          )
          continue

        ftype = checker._resolve_field_type(f, node.name)
        if f.name in struct_type.fields:
          checker.error(
            f"Field '{f.name}' in struct '{node.name}' shadows inherited "
            "parent field."
          )
        elif f.name in struct_type.static_fields:
          checker.error(
            f"Duplicate field '{f.name}' in struct '{node.name}'.",
            node=f,
          )
        has_default = (
          f.default_expr is not None
          or checker._has_implicit_default_value(ftype)
        )
        struct_type.fields[f.name] = StructField(
          f.name,
          ftype,
          f.is_mutable,
          has_default=has_default,
          has_explicit_default=f.default_expr is not None,
        )

      node._canonical_fields = [
        (
          f_name,
          isinstance(f_obj.field_type, OptionalType)
          and f_obj.has_explicit_default,
        )
        for f_name, f_obj in struct_type.fields.items()
      ]
      visiting.remove(node.name)
      processed.add(node.name)

    prechecked_restores: list[tuple[str, Any]] = []
    for decl in program.declarations:
      if (
        isinstance(decl, StructDeclNode)
        and not decl.type_params
        and not getattr(decl, "is_monomorphized", False)
      ):
        process_struct(decl)
      elif (
        isinstance(decl, VarDeclNode)
        and not decl.is_mutable
        and not any(
          a.name == "extern" for a in getattr(decl, "annotations", [])
        )
      ):
        prior_map = {
          name: checker.symbol_table.lookup_current_scope(name)
          for name in decl.names
        }
        checker.visit(decl)
        decl._prechecked_module_const = True
        decl._prechecked_symbols = {
          name: checker.symbol_table.lookup_current_scope(name)
          for name in decl.names
        }
        for name, prior_sym in prior_map.items():
          prechecked_restores.append((name, prior_sym))

    # Restore top-level scope bindings so Pass 4 enforces lexical source order
    # while re-exposing each pre-checked let constant at its declaration point.
    for name, prior_sym in reversed(prechecked_restores):
      if prior_sym is None:
        checker.symbol_table.current_scope.symbols.pop(name, None)
      else:
        checker.symbol_table.current_scope.symbols[name] = prior_sym

    resolved_types = [
      checker.symbol_table.lookup_type(s.name) for s in structs_to_process
    ]
    StructLayoutPass.check_unboxed_recursion(checker, resolved_types)
    StructLayoutPass.check_arena_field_ordering(checker, resolved_types)

  @staticmethod
  def _type_contains_proto(t: Type, seen: set[str] | None = None) -> bool:
    """Returns True if `t` is a proto type or contains one inline."""
    if isinstance(t, OptionalType):
      return StructLayoutPass._type_contains_proto(t.base_type, seen)
    if isinstance(t, ArrayType):
      return StructLayoutPass._type_contains_proto(t.element_type, seen)
    if isinstance(t, MapType):
      return StructLayoutPass._type_contains_proto(
        t.key_type, seen
      ) or StructLayoutPass._type_contains_proto(t.value_type, seen)
    if isinstance(t, StructType):
      if t.is_prototype:
        return True
      seen_set = set() if seen is None else seen
      if t.name in seen_set:
        return False
      seen_set.add(t.name)
      try:
        return any(
          StructLayoutPass._type_contains_proto(f.field_type, seen_set)
          for f in t.fields.values()
        )
      finally:
        seen_set.remove(t.name)
    return False

  @staticmethod
  def _type_contains_arena(t: Type, seen: set[str] | None = None) -> bool:
    """Returns True if `t` is an Arena or inline struct owning an Arena."""
    if isinstance(t, ArenaType):
      return True
    if isinstance(t, OptionalType):
      return StructLayoutPass._type_contains_arena(t.base_type, seen)
    if isinstance(t, ArrayType):
      return StructLayoutPass._type_contains_arena(t.element_type, seen)
    if isinstance(t, MapType):
      return StructLayoutPass._type_contains_arena(
        t.key_type, seen
      ) or StructLayoutPass._type_contains_arena(t.value_type, seen)
    if isinstance(t, StructType) and not t.is_prototype:
      seen_set = set() if seen is None else seen
      if t.name in seen_set:
        return False
      seen_set.add(t.name)
      try:
        return any(
          StructLayoutPass._type_contains_arena(f.field_type, seen_set)
          for f in t.fields.values()
        )
      finally:
        seen_set.remove(t.name)
    return False

  @staticmethod
  def check_arena_field_ordering(checker: Any, struct_types: list[Any]) -> None:
    """Enforces that Arena fields precede proto-referencing fields."""
    for st in struct_types:
      if not isinstance(st, StructType):
        continue
      first_proto_field: str | None = None
      for field_name, field in st.fields.items():
        if StructLayoutPass._type_contains_arena(field.field_type):
          if first_proto_field is not None:
            checker.error(
              f"In struct '{st.name}', Arena field '{field_name}' must be "
              f"declared before prototype-referencing field "
              f"'{first_proto_field}' to ensure safe LIFO teardown."
            )
        elif (
          first_proto_field is None
          and StructLayoutPass._type_contains_proto(field.field_type)
        ):
          first_proto_field = field_name
