"""Struct layout and inheritance resolution pass for Sapphire semantic analyzer.

Handles Pass 2: resolves static struct inheritance, copies parent fields,
detects circular inheritance, and validates shadowing or duplicate field layouts.
"""

from typing import Any, Iterator, List, Set
from src.parser.ast import ProgramNode, StructDeclNode
from src.semantics.symbol_table import ArrayType, OptionalType, StructField, StructType, Type


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
  def check_unboxed_recursion(checker: Any, struct_types: List[Any]) -> None:
    """Rejects direct or mutual unboxed recursion across non-proto structs."""
    reported_cycles: Set[frozenset] = getattr(
        checker, "_reported_recursive_struct_cycles", None
    )
    if reported_cycles is None:
      reported_cycles = set()
      checker._reported_recursive_struct_cycles = reported_cycles

    fully_checked: Set[str] = set()

    def dfs(st: StructType, path: List[str]) -> None:
      for field_name, field_obj in st.fields.items():
        for target_st in StructLayoutPass._iter_inline_structs(field_obj.field_type):
          if target_st.name in path:
            idx = path.index(target_st.name)
            cycle_key = frozenset(path[idx:])
            if cycle_key not in reported_cycles:
              reported_cycles.add(cycle_key)
              checker.error(
                  f"Recursive struct '{target_st.name}' has infinite inline size via field '{field_name}'; "
                  f"use 'Ref<{target_st.name}>', 'SharedRef<{target_st.name}>', dynamic '[{target_st.name}]', "
                  f"or 'proto' in an Arena."
              )
          elif target_st.name not in fully_checked:
            dfs(target_st, path + [target_st.name])

    for st in struct_types:
      if isinstance(st, StructType) and not st.is_prototype and st.name not in fully_checked:
        dfs(st, [st.name])
        fully_checked.add(st.name)

  @staticmethod
  def resolve_struct_layouts(checker: Any, program: ProgramNode) -> None:
    """Pre-pass to resolve static inheritance field copying and layout sizing."""
    structs_to_process = [d for d in program.declarations if isinstance(d, StructDeclNode) and not d.type_params]
    processed = set()
    visiting = set()

    def process_struct(node: StructDeclNode):
      if node.name in processed:
        return
      if node.name in visiting:
        checker.error(f"Circular inheritance detected involving struct '{node.name}'.")
        return
      visiting.add(node.name)

      struct_type = checker.symbol_table.lookup_type(node.name)
      if not isinstance(struct_type, StructType):
        visiting.remove(node.name)
        return

      if node.parent_names:
        for parent_name in node.parent_names:
          parent_type = checker.symbol_table.lookup_type(parent_name)
          if not parent_type:
            checker.error(f"Parent struct '{parent_name}' not found for '{node.name}'.")
          elif not isinstance(parent_type, StructType):
            checker.error(f"Parent '{parent_name}' of '{node.name}' is not a struct type.")
          else:
            parent_node = next((s for s in structs_to_process if s.name == parent_name), None)
            if parent_node:
              process_struct(parent_node)
            for field_name, field_obj in parent_type.fields.items():
              if field_name in struct_type.fields:
                checker.error(f"Duplicate field '{field_name}' in struct '{node.name}' inherited from multiple parents.")
              else:
                struct_type.fields[field_name] = field_obj

      for f in node.fields:
        ftype = checker._resolve_field_type(f, node.name)
        if f.name in struct_type.fields:
          checker.error(f"Field '{f.name}' in struct '{node.name}' shadows inherited parent field.")
        has_default = f.default_expr is not None or checker._has_implicit_default_value(ftype)
        struct_type.fields[f.name] = StructField(
            f.name, ftype, f.is_mutable, has_default=has_default, has_explicit_default=f.default_expr is not None
        )

      visiting.remove(node.name)
      processed.add(node.name)

    for s in structs_to_process:
      process_struct(s)

    resolved_types = [
        checker.symbol_table.lookup_type(s.name) for s in structs_to_process
    ]
    StructLayoutPass.check_unboxed_recursion(checker, resolved_types)
