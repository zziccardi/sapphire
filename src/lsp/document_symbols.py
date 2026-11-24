"""Extracts hierarchical LSP DocumentSymbol instances from Sapphire AST.

This module inspects the top-level ProgramNode AST and translates all defined
symbols (structs, prototypes, enums, traits, impl blocks, methods, functions,
and variables/constants) into LSP DocumentSymbol trees for VS Code's Outline
view, Breadcrumbs, and Go-to-Symbol.
"""

from typing import Any, List, Optional, Tuple

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
    if node.size is not None:
      return f"[{_format_type_node(node.element_type)}; {node.size}]"
    return f"[{_format_type_node(node.element_type)}]"
  if isinstance(node, MapTypeNode):
    key_t = _format_type_node(node.key_type)
    val_t = _format_type_node(node.val_type)
    return f"[{key_t}: {val_t}]"
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
  """Creates an LSP 0-based Range from 1-based line and 0-based column numbers.
  """
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
  if full_range.start.line > sel_range.start.line or (
    full_range.start.line == sel_range.start.line
    and full_range.start.character > sel_range.start.character
  ):
    full_range.start = Position(
      line=sel_range.start.line, character=sel_range.start.character
    )
  if full_range.end.line < sel_range.end.line or (
    full_range.end.line == sel_range.end.line
    and full_range.end.character < sel_range.end.character
  ):
    full_range.end = Position(
      line=sel_range.end.line, character=sel_range.end.character
    )


def _get_name_position(node: Any, fallback_name: str) -> Tuple[int, int, int]:
  """Returns (line, col, length) for a node's symbol name, with robust
  fallbacks.
  """
  line = getattr(node, "name_line", None) or getattr(node, "start_line", 1)
  col = getattr(node, "name_column", None)
  if col is None:
    col = getattr(node, "start_column", 0) or 0
  length = getattr(node, "name_length", None) or len(fallback_name)
  return line, col, length


def _format_func_signature(parameters: list, return_types: list) -> str:
  """Formats parameter list and return types into a signature string."""
  params_parts = []
  for p in parameters:
    mut = "var " if getattr(p, "is_mutable", False) else ""
    t_str = (
      f": {_format_type_node(p.param_type)}"
      if getattr(p, "param_type", None)
      else ""
    )
    params_parts.append(f"{mut}{p.name}{t_str}")
  params_str = ", ".join(params_parts)
  ret_str = ""
  if return_types:
    ret_types_str = ", ".join(_format_type_node(r) for r in return_types)
    ret_str = f": {ret_types_str}"
  return f"({params_str}){ret_str}"


def _decl_ranges(decl: Any, name: str) -> tuple[Any, Any]:
  """Builds full and selection LSP Ranges for a named AST declaration."""
  full_range = _create_range(
    decl.start_line, decl.start_column, decl.end_line, decl.end_column
  )
  name_line, name_col, name_len = _get_name_position(decl, name)
  sel_range = _create_range(name_line, name_col, name_line, name_col + name_len)
  _ensure_contained(full_range, sel_range)
  return full_range, sel_range


def _build_struct_symbol(decl: StructDeclNode) -> DocumentSymbol:
  kind = SymbolKind.Class if decl.is_prototype else SymbolKind.Struct
  details = []
  if getattr(decl, "type_params", None):
    details.append(f"<{', '.join(decl.type_params)}>")
  if getattr(decl, "parent_names", None):
    details.append(f": {', '.join(decl.parent_names)}")
  detail_str = "".join(details) or ("proto" if decl.is_prototype else "struct")
  full_range, sel_range = _decl_ranges(decl, decl.name)

  field_symbols: List[DocumentSymbol] = []
  for field in decl.fields:
    f_range, f_sel_range = _decl_ranges(field, field.name)
    field_symbols.append(
      DocumentSymbol(
        name=field.name,
        kind=SymbolKind.Property if field.is_mutable else SymbolKind.Field,
        range=f_range,
        selection_range=f_sel_range,
        detail=_format_type_node(field.field_type) or None,
      )
    )

  return DocumentSymbol(
    name=decl.name,
    kind=kind,
    range=full_range,
    selection_range=sel_range,
    detail=detail_str,
    children=field_symbols or None,
  )


def _build_enum_symbol(decl: EnumDeclNode) -> DocumentSymbol:
  full_range, sel_range = _decl_ranges(decl, decl.name)
  member_symbols: List[DocumentSymbol] = []
  for m in decl.members:
    m_range, m_sel = _decl_ranges(m, m.name)
    member_symbols.append(
      DocumentSymbol(
        name=m.name,
        kind=SymbolKind.EnumMember,
        range=m_range,
        selection_range=m_sel,
        detail=f"= {m.value}" if m.value is not None else None,
      )
    )
  return DocumentSymbol(
    name=decl.name,
    kind=SymbolKind.Enum,
    range=full_range,
    selection_range=sel_range,
    detail="enum",
    children=member_symbols or None,
  )


def _build_trait_symbol(decl: TraitDeclNode) -> DocumentSymbol:
  full_range, sel_range = _decl_ranges(decl, decl.name)
  method_symbols: List[DocumentSymbol] = []
  for tm in decl.members:
    tm_range, tm_sel = _decl_ranges(tm, tm.name)
    method_symbols.append(
      DocumentSymbol(
        name=tm.name,
        kind=SymbolKind.Method,
        range=tm_range,
        selection_range=tm_sel,
        detail=_format_func_signature(tm.parameters, tm.return_types),
      )
    )
  detail_trait = (
    f"<{', '.join(decl.type_params)}>"
    if getattr(decl, "type_params", None)
    else "trait"
  )
  return DocumentSymbol(
    name=decl.name,
    kind=SymbolKind.Interface,
    range=full_range,
    selection_range=sel_range,
    detail=detail_trait,
    children=method_symbols or None,
  )


def _build_impl_symbol(decl: ImplBlockNode) -> DocumentSymbol:
  impl_name = (
    f"impl {decl.trait_name} for {decl.struct_name}"
    if getattr(decl, "trait_name", None)
    else f"impl {decl.struct_name}"
  )
  full_range = _create_range(
    decl.start_line, decl.start_column, decl.end_line, decl.end_column
  )
  sel_line = (
    getattr(decl, "struct_name_line", None)
    or getattr(decl, "trait_name_line", None)
    or getattr(decl, "start_line", 1)
  )
  sel_col = getattr(decl, "struct_name_column", None)
  if sel_col is None:
    sel_col = getattr(decl, "trait_name_column", None)
  if sel_col is None:
    sel_col = getattr(decl, "start_column", 0) or 0
  sel_len = (
    getattr(decl, "struct_name_length", None)
    or getattr(decl, "trait_name_length", None)
    or len(decl.struct_name)
  )
  sel_range = _create_range(sel_line, sel_col, sel_line, sel_col + sel_len)
  _ensure_contained(full_range, sel_range)

  methods: List[DocumentSymbol] = []
  for m in decl.members:
    fn = m.func_decl
    fn_range, fn_sel = _decl_ranges(fn, fn.name)
    methods.append(
      DocumentSymbol(
        name=fn.name,
        kind=(
          SymbolKind.Constructor if fn.name == "__init__" else SymbolKind.Method
        ),
        range=fn_range,
        selection_range=fn_sel,
        detail=_format_func_signature(fn.parameters, fn.return_types),
      )
    )

  return DocumentSymbol(
    name=impl_name,
    kind=SymbolKind.Namespace,
    range=full_range,
    selection_range=sel_range,
    children=methods or None,
  )


def _build_var_symbols(decl: VarDeclNode) -> List[DocumentSymbol]:
  kind = SymbolKind.Variable if decl.is_mutable else SymbolKind.Constant
  full_range = _create_range(
    decl.start_line, decl.start_column, decl.end_line, decl.end_column
  )
  out: List[DocumentSymbol] = []
  bindings_info = getattr(decl, "bindings_info", None)
  if bindings_info:
    for b in bindings_info:
      b_name = b["name"]
      b_line = b.get("line", decl.start_line)
      b_col = b.get("column", decl.start_column)
      b_len = b.get("length", len(b_name))
      b_sel = _create_range(b_line, b_col, b_line, (b_col or 0) + b_len)
      _ensure_contained(full_range, b_sel)
      out.append(
        DocumentSymbol(
          name=b_name,
          kind=kind,
          range=full_range,
          selection_range=b_sel,
          detail=_format_type_node(b.get("val_type")) or None,
        )
      )
    return out

  for idx, name in enumerate(decl.names):
    v_type = (
      _format_type_node(decl.val_types[idx])
      if idx < len(decl.val_types)
      else None
    )
    out.append(
      DocumentSymbol(
        name=name,
        kind=kind,
        range=full_range,
        selection_range=full_range,
        detail=v_type or None,
      )
    )
  return out


def extract_document_symbols(ast: Any) -> List[DocumentSymbol]:
  """Extracts all symbols defined in the given ProgramNode AST, ordered by
  position.
  """
  symbols: List[DocumentSymbol] = []
  if not isinstance(ast, ProgramNode):
    return symbols

  for decl in ast.declarations:
    if isinstance(decl, StructDeclNode):
      symbols.append(_build_struct_symbol(decl))
    elif isinstance(decl, EnumDeclNode):
      symbols.append(_build_enum_symbol(decl))
    elif isinstance(decl, TraitDeclNode):
      symbols.append(_build_trait_symbol(decl))
    elif isinstance(decl, ImplBlockNode):
      symbols.append(_build_impl_symbol(decl))
    elif isinstance(decl, FuncDeclNode):
      full_range, sel_range = _decl_ranges(decl, decl.name)
      symbols.append(
        DocumentSymbol(
          name=decl.name,
          kind=SymbolKind.Function,
          range=full_range,
          selection_range=sel_range,
          detail=_format_func_signature(decl.parameters, decl.return_types),
        )
      )
    elif isinstance(decl, VarDeclNode):
      symbols.extend(_build_var_symbols(decl))

  # Sort all symbols and their children strictly by start position in document.
  symbols.sort(key=lambda s: (s.range.start.line, s.range.start.character))
  for s in symbols:
    if s.children:
      s.children.sort(
        key=lambda c: (c.range.start.line, c.range.start.character)
      )

  return symbols
