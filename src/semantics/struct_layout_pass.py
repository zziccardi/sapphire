"""Struct layout and inheritance resolution pass for Sapphire semantic analyzer.

Handles Pass 2: resolves static struct inheritance, copies parent fields,
detects circular inheritance, and validates shadowing or duplicate field layouts.
"""

from typing import Any
from src.parser.ast import ProgramNode, StructDeclNode
from src.semantics.symbol_table import StructField, StructType


class StructLayoutPass:
  """Resolves static composition and field layouts for inherited structs."""

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
