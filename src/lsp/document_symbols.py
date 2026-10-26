"""Extracts hierarchical LSP DocumentSymbol instances from Sapphire AST.

This module inspects the top-level ProgramNode AST and translates all defined symbols
(structs, prototypes, enums, traits, impl blocks, functions, and variables/constants)
into LSP DocumentSymbol trees for VS Code's Outline view, Breadcrumbs, and Go-to-Symbol.
"""

from typing import Any, Dict, List, Optional
from lsprotocol.types import DocumentSymbol, Position, Range, SymbolKind
from src.parser.ast import (
    ArrayTypeNode,
    BasicTypeNode,
    EnumDeclNode,
    FuncDeclNode,
    FunctionTypeNode,
    ImplBlockNode,
    MapTypeNode,
    OptionalTypeNode,
    ProgramNode,
    StructDeclNode,
    TraitDeclNode,
    TypeNode,
    VarDeclNode,
)


def _format_type_node(node: Optional[TypeNode]) -> str:
  """Formats an AST TypeNode into a concise, human-readable type string."""
  if node is None:
    return ""
  if isinstance(node, BasicTypeNode):
    if getattr(node, "type_args", None):
      args = ", ".join(_format_type_node(a) for a in node.type_args)
      return f"{node.name}<{args}>"
    return node.name
  if isinstance(node, OptionalTypeNode):
    return f"{_format_type_node(node.base_type)}?"
  if isinstance(node, ArrayTypeNode):
    return f"[{_format_type_node(node.element_type)}]"
  if isinstance(node, MapTypeNode):
    return f"[{_format_type_node(node.key_type)}: {_format_type_node(node.val_type)}]"
  if isinstance(node, FunctionTypeNode):
    params = ", ".join(_format_type_node(p) for p in node.param_types)
    returns = ", ".join(_format_type_node(r) for r in node.return_types)
    return f"({params}) -> ({returns})"
  return str(getattr(node, "name", str(node)))


def _create_range(
    start_line: Optional[int],
    start_col: Optional[int],
    end_line: Optional[int],
    end_col: Optional[int],
) -> Range:
  """Creates an LSP 0-based Range from 1-based line and 0-based column numbers."""
  s_line = (start_line - 1) if start_line is not None and start_line > 0 else 0
  s_col = start_col if start_col is not None and start_col >= 0 else 0
  e_line = (end_line - 1) if end_line is not None and end_line > 0 else s_line
  e_col = end_col if end_col is not None and end_col >= 0 else s_col + 1
  return Range(
      start=Position(line=s_line, character=s_col),
      end=Position(line=e_line, character=e_col),
  )


def _ensure_contained(full_range: Range, sel_range: Range) -> None:
  """Ensures full_range bounds encompass sel_range according to LSP spec."""
  if (full_range.start.line > sel_range.start.line or
      (full_range.start.line == sel_range.start.line and full_range.start.character > sel_range.start.character)):
    full_range.start = Position(line=sel_range.start.line, character=sel_range.start.character)
  if (full_range.end.line < sel_range.end.line or
      (full_range.end.line == sel_range.end.line and full_range.end.character < sel_range.end.character)):
    full_range.end = Position(line=sel_range.end.line, character=sel_range.end.character)


def _format_func_signature(parameters: list, return_types: list) -> str:
  """Formats parameter list and return types into a signature string."""
  params_parts = []
  for p in parameters:
    mut = "var " if getattr(p, "is_mutable", False) else ""
    t_str = f": {_format_type_node(p.param_type)}" if getattr(p, "param_type", None) else ""
    params_parts.append(f"{mut}{p.name}{t_str}")
  params_str = ", ".join(params_parts)
  ret_str = ""
  if return_types:
    ret_types_str = ", ".join(_format_type_node(r) for r in return_types)
    ret_str = f": {ret_types_str}"
  return f"({params_str}){ret_str}"


def extract_document_symbols(ast: Any) -> List[DocumentSymbol]:
  """Extracts all symbols defined in the given ProgramNode AST."""
  symbols: List[DocumentSymbol] = []
  if not isinstance(ast, ProgramNode):
    return symbols

  for decl in ast.declarations:
    # 1. Struct and Proto Declarations
    if isinstance(decl, StructDeclNode):
      kind = SymbolKind.Class if decl.is_prototype else SymbolKind.Struct
      details = []
      if getattr(decl, "type_params", None):
        details.append(f"<{', '.join(decl.type_params)}>")
      if getattr(decl, "parent_names", None):
        details.append(f": {', '.join(decl.parent_names)}")
      detail_str = "".join(details) or ("proto" if decl.is_prototype else "struct")

      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)
      name_line = getattr(decl, "name_line", decl.start_line)
      name_col = getattr(decl, "name_column", decl.start_column)
      name_len = getattr(decl, "name_length", len(decl.name))
      sel_range = _create_range(name_line, name_col, name_line, (name_col or 0) + name_len)
      _ensure_contained(full_range, sel_range)

      field_symbols: List[DocumentSymbol] = []
      for field in decl.fields:
        f_type_str = _format_type_node(field.field_type)
        f_range = _create_range(field.start_line, field.start_column, field.end_line, field.end_column)
        fn_line = getattr(field, "name_line", field.start_line)
        fn_col = getattr(field, "name_column", field.start_column)
        fn_len = getattr(field, "name_length", len(field.name))
        f_sel_range = _create_range(fn_line, fn_col, fn_line, (fn_col or 0) + fn_len)
        _ensure_contained(f_range, f_sel_range)

        field_symbols.append(
            DocumentSymbol(
                name=field.name,
                kind=SymbolKind.Property if field.is_mutable else SymbolKind.Field,
                range=f_range,
                selection_range=f_sel_range,
                detail=f_type_str or None,
            )
        )

      symbols.append(
          DocumentSymbol(
              name=decl.name,
              kind=kind,
              range=full_range,
              selection_range=sel_range,
              detail=detail_str,
              children=field_symbols or None,
          )
      )

    # 2. Enum Declarations
    elif isinstance(decl, EnumDeclNode):
      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)
      name_line = getattr(decl, "name_line", decl.start_line)
      name_col = getattr(decl, "name_column", decl.start_column)
      name_len = getattr(decl, "name_length", len(decl.name))
      sel_range = _create_range(name_line, name_col, name_line, (name_col or 0) + name_len)
      _ensure_contained(full_range, sel_range)

      member_symbols: List[DocumentSymbol] = []
      for m in decl.members:
        m_range = _create_range(m.start_line, m.start_column, m.end_line, m.end_column)
        mn_line = getattr(m, "name_line", m.start_line)
        mn_col = getattr(m, "name_column", m.start_column)
        mn_len = getattr(m, "name_length", len(m.name))
        m_sel = _create_range(mn_line, mn_col, mn_line, (mn_col or 0) + mn_len)
        _ensure_contained(m_range, m_sel)

        detail = f"= {m.value}" if m.value is not None else None
        member_symbols.append(
            DocumentSymbol(
                name=m.name,
                kind=SymbolKind.EnumMember,
                range=m_range,
                selection_range=m_sel,
                detail=detail,
            )
        )

      symbols.append(
          DocumentSymbol(
              name=decl.name,
              kind=SymbolKind.Enum,
              range=full_range,
              selection_range=sel_range,
              detail="enum",
              children=member_symbols or None,
          )
      )

    # 3. Trait Declarations
    elif isinstance(decl, TraitDeclNode):
      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)
      name_line = getattr(decl, "name_line", decl.start_line)
      name_col = getattr(decl, "name_column", decl.start_column)
      name_len = getattr(decl, "name_length", len(decl.name))
      sel_range = _create_range(name_line, name_col, name_line, (name_col or 0) + name_len)
      _ensure_contained(full_range, sel_range)

      method_symbols: List[DocumentSymbol] = []
      for tm in decl.members:
        tm_range = _create_range(tm.start_line, tm.start_column, tm.end_line, tm.end_column)
        tmn_line = getattr(tm, "name_line", tm.start_line)
        tmn_col = getattr(tm, "name_column", tm.start_column)
        tmn_len = getattr(tm, "name_length", len(tm.name))
        tm_sel = _create_range(tmn_line, tmn_col, tmn_line, (tmn_col or 0) + tmn_len)
        _ensure_contained(tm_range, tm_sel)

        detail_sig = _format_func_signature(tm.parameters, tm.return_types)
        method_symbols.append(
            DocumentSymbol(
                name=tm.name,
                kind=SymbolKind.Method,
                range=tm_range,
                selection_range=tm_sel,
                detail=detail_sig,
            )
        )

      detail_trait = f"<{', '.join(decl.type_params)}>" if getattr(decl, "type_params", None) else "trait"
      symbols.append(
          DocumentSymbol(
              name=decl.name,
              kind=SymbolKind.Interface,
              range=full_range,
              selection_range=sel_range,
              detail=detail_trait,
              children=method_symbols or None,
          )
      )

    # 4. Impl Blocks
    elif isinstance(decl, ImplBlockNode):
      impl_name = (
          f"impl {decl.trait_name} for {decl.struct_name}"
          if getattr(decl, "trait_name", None)
          else f"impl {decl.struct_name}"
      )
      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)
      sel_line = getattr(decl, "struct_name_line", decl.start_line)
      sel_col = getattr(decl, "struct_name_column", decl.start_column)
      sel_len = getattr(decl, "struct_name_length", len(decl.struct_name))
      sel_range = _create_range(sel_line, sel_col, sel_line, (sel_col or 0) + sel_len)
      _ensure_contained(full_range, sel_range)

      methods: List[DocumentSymbol] = []
      for m in decl.members:
        fn = m.func_decl
        fn_range = _create_range(fn.start_line, fn.start_column, fn.end_line, fn.end_column)
        fnn_line = getattr(fn, "name_line", fn.start_line)
        fnn_col = getattr(fn, "name_column", fn.start_column)
        fnn_len = getattr(fn, "name_length", len(fn.name))
        fn_sel = _create_range(fnn_line, fnn_col, fnn_line, (fnn_col or 0) + fnn_len)
        _ensure_contained(fn_range, fn_sel)

        detail_sig = _format_func_signature(fn.parameters, fn.return_types)
        kind = SymbolKind.Constructor if fn.name == "__init__" else SymbolKind.Method
        methods.append(
            DocumentSymbol(
                name=fn.name,
                kind=kind,
                range=fn_range,
                selection_range=fn_sel,
                detail=detail_sig,
            )
        )

      symbols.append(
          DocumentSymbol(
              name=impl_name,
              kind=SymbolKind.Namespace,
              range=full_range,
              selection_range=sel_range,
              children=methods or None,
          )
      )

    # 5. Top-level Functions
    elif isinstance(decl, FuncDeclNode):
      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)
      name_line = getattr(decl, "name_line", decl.start_line)
      name_col = getattr(decl, "name_column", decl.start_column)
      name_len = getattr(decl, "name_length", len(decl.name))
      sel_range = _create_range(name_line, name_col, name_line, (name_col or 0) + name_len)
      _ensure_contained(full_range, sel_range)

      detail_sig = _format_func_signature(decl.parameters, decl.return_types)
      symbols.append(
          DocumentSymbol(
              name=decl.name,
              kind=SymbolKind.Function,
              range=full_range,
              selection_range=sel_range,
              detail=detail_sig,
          )
      )

    # 6. Top-level Variables and Constants
    elif isinstance(decl, VarDeclNode):
      kind = SymbolKind.Variable if decl.is_mutable else SymbolKind.Constant
      full_range = _create_range(decl.start_line, decl.start_column, decl.end_line, decl.end_column)

      bindings_info = getattr(decl, "bindings_info", None)
      if bindings_info:
        for b in bindings_info:
          b_name = b["name"]
          b_line = b.get("line", decl.start_line)
          b_col = b.get("column", decl.start_column)
          b_len = b.get("length", len(b_name))
          b_sel = _create_range(b_line, b_col, b_line, (b_col or 0) + b_len)
          _ensure_contained(full_range, b_sel)
          b_type = _format_type_node(b.get("val_type"))
          symbols.append(
              DocumentSymbol(
                  name=b_name,
                  kind=kind,
                  range=full_range,
                  selection_range=b_sel,
                  detail=b_type or None,
              )
          )
      else:
        for idx, name in enumerate(decl.names):
          v_type = _format_type_node(decl.val_types[idx]) if idx < len(decl.val_types) else None
          symbols.append(
              DocumentSymbol(
                  name=name,
                  kind=kind,
                  range=full_range,
                  selection_range=full_range,
                  detail=v_type or None,
              )
          )

  return symbols
