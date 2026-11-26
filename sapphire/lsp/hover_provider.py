"""LSP Hover provider for Sapphire.

Inspects Sapphire AST nodes and semantic types at cursor position to provide
rich hover tooltips, signatures, documentation, and parameter information.
"""

from typing import Any

from lsprotocol.types import Hover, HoverParams, MarkupContent, MarkupKind

from sapphire.lsp.definition_provider import find_local_decl
from sapphire.lsp.semantic_tokens import (
  find_node_at_position,
  get_doc_line,
  utf16_to_codepoint,
)
from sapphire.parser.ast import (
  ASTNode,
  BasicTypeNode,
  BinaryOpNode,
  CallNode,
  EnumDeclNode,
  EnumMemberNode,
  ForNode,
  FuncDeclNode,
  HeaderBindingNode,
  IdentifierNode,
  ImplBlockNode,
  LiteralNode,
  MemberAccessNode,
  ParameterNode,
  StructDeclNode,
  StructFieldNode,
  TraitDeclNode,
  TraitMemberNode,
  UnaryOpNode,
  VarDeclNode,
)
from sapphire.semantics.symbol_table import (
  EnumSymbol,
  EnumType,
  FunctionSymbol,
  FunctionType,
  ModuleType,
  StructSymbol,
  StructType,
  TraitSymbol,
  TraitType,
  VariableSymbol,
)


def format_ast_expr(expr: Any) -> str:
  """Formats an AST expression into a human-readable Sapphire code string."""
  if expr is None:
    return ""
  if isinstance(expr, LiteralNode):
    if expr.lit_type == "string":
      return f'"{expr.value}"'
    elif expr.lit_type == "bool":
      return (
        "true"
        if expr.value is True or str(expr.value).lower() == "true"
        else "false"
      )
    elif expr.lit_type == "none":
      return "none"
    return str(expr.value)
  elif isinstance(expr, IdentifierNode):
    return expr.name
  elif isinstance(expr, MemberAccessNode):
    rec = format_ast_expr(expr.receiver)
    opt = "?." if getattr(expr, "is_optional", False) else "."
    return f"{rec}{opt}{expr.member}"
  elif isinstance(expr, UnaryOpNode):
    return f"{expr.op}{format_ast_expr(expr.expr)}"
  elif isinstance(expr, BinaryOpNode):
    return (
      f"{format_ast_expr(expr.left)} {expr.op} {format_ast_expr(expr.right)}"
    )
  elif isinstance(expr, CallNode):
    callee_str = format_ast_expr(expr.callee)
    args_str = ", ".join(
      f"{arg.name} = {format_ast_expr(arg.expr)}"
      if getattr(arg, "name", None)
      else format_ast_expr(arg.expr)
      for arg in getattr(expr, "arguments", [])
    )
    return f"{callee_str}({args_str})"
  elif isinstance(expr, BasicTypeNode):
    return expr.name
  return str(getattr(expr, "value", str(expr)))


class HoverProvider:
  """Extracts hover documentation and tooltips from Sapphire AST and types."""

  @staticmethod
  def _match_binding_name(node: Any, line: int, col: int) -> str | None:
    """Finds the specific binding name under `(line, col)` in a multi-var node.
    """
    for info in getattr(node, "bindings_info", []) or []:
      b_line = info.get("line")
      b_col = info.get("column")
      b_len = info.get("length", 0)
      if b_line == line and b_col is not None and b_col <= col < b_col + b_len:
        return info.get("name")
    return None

  @classmethod
  def _resolve_hover_node_and_type(
    cls, ls: Any, uri: str, node: Any, line: int, col: int, node_types: Any
  ) -> tuple[Any, Any]:
    """Resolves the effective AST node and semantic Type for hover inspection.
    """
    node_type = None
    if (
      isinstance(node, CallNode)
      and isinstance(node.callee, IdentifierNode)
      and uri in ls.symbol_table_cache
    ):  # pragma: no cover
      c_sym = ls.symbol_table_cache[uri].lookup(node.callee.name)
      if c_sym and hasattr(c_sym, "symbol_type"):
        node = node.callee
        node_type = c_sym.symbol_type
    elif (
      isinstance(node, CallNode)
      and isinstance(node.callee, MemberAccessNode)
      and uri in ls.symbol_table_cache
    ):  # pragma: no cover
      from sapphire.semantics.symbol_table import (
        OptionalType,
        RefType,
        SharedRefType,
      )

      rec_type = node_types.get(node.callee.receiver)
      if isinstance(rec_type, OptionalType):
        rec_type = rec_type.base_type
      if isinstance(rec_type, (SharedRefType, RefType)):
        rec_type = rec_type.inner_type
      sym_table = ls.symbol_table_cache[uri]
      method_obj = None
      if rec_type and hasattr(rec_type, "get_method"):
        method_obj = rec_type.get_method(node.callee.member, sym_table)
      elif (
        rec_type
        and hasattr(rec_type, "methods")
        and node.callee.member in rec_type.methods
      ):
        method_obj = rec_type.methods[node.callee.member]
      if method_obj is not None:
        node = node.callee
        node_type = getattr(method_obj, "method_type", method_obj)

    if not node_type and isinstance(node, VarDeclNode):
      matched_name = cls._match_binding_name(node, line, col)
      binding_types = getattr(node, "binding_types", None)
      if (
        matched_name
        and isinstance(binding_types, dict)
        and matched_name in binding_types
      ):
        node_type = binding_types[matched_name]

    if not node_type:
      node_type = node_types.get(node)
    if node_type or uri not in ls.symbol_table_cache:
      return node, node_type

    sym_table = ls.symbol_table_cache[uri]
    if isinstance(node, IdentifierNode):
      sym = sym_table.lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)
    elif isinstance(node, (StructDeclNode, EnumDeclNode, TraitDeclNode)):
      node_type = sym_table.lookup_type(node.name)
    elif isinstance(node, FuncDeclNode):  # pragma: no cover
      sym = sym_table.lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)
    elif isinstance(node, ImplBlockNode):
      s_line = getattr(node, "struct_name_line", None)
      s_col = getattr(node, "struct_name_column", None)
      s_len = getattr(node, "struct_name_length", None)
      t_line = getattr(node, "trait_name_line", None)
      t_col = getattr(node, "trait_name_column", None)
      t_len = getattr(node, "trait_name_length", None)
      if (
        node.trait_name
        and t_line is not None
        and t_col is not None
        and t_len is not None
        and t_line == line
        and t_col <= col < t_col + t_len
      ):
        node_type = sym_table.lookup_type(node.trait_name)
      elif s_line is None or (
        s_col is not None
        and s_len is not None
        and s_line == line
        and s_col <= col < s_col + s_len
      ):
        node_type = sym_table.lookup_type(node.struct_name)

    return node, node_type

  @classmethod
  def _classify_hover_node(
    cls,
    ls: Any,
    uri: str,
    node: Any,
    node_type: Any,
    line: int,
    col: int,
    node_types: Any,
  ) -> tuple[str, str]:
    """Determines the display name and category label for a hovered AST node."""
    node_name = ""
    category = "symbol"

    if isinstance(node, IdentifierNode):
      node_name = node.name
      # Check local declarations first so locals/params shadowing globals are
      # not misclassified as global functions, structs, or enums.
      ast = ls.ast_cache.get(uri)
      local_decl = (
        find_local_decl(ast, node.name, line) if ast is not None else None
      )
      if isinstance(local_decl, ParameterNode):
        category = "parameter"
      elif local_decl is not None:
        category = "variable"
      elif uri in ls.symbol_table_cache:
        sym = ls.symbol_table_cache[uri].lookup(node.name)
        if isinstance(sym, VariableSymbol):
          category = "parameter" if sym.is_parameter else "variable"
        elif isinstance(sym, FunctionSymbol):
          category = "function"
        elif isinstance(sym, StructSymbol):
          category = "struct"
        elif isinstance(sym, EnumSymbol):
          category = "enum"
        elif isinstance(sym, TraitSymbol):
          category = "trait"
    elif isinstance(node, MemberAccessNode):
      node_name = node.member
      receiver_type = node_types.get(node.receiver)
      if isinstance(receiver_type, ModuleType):
        if isinstance(node_type, FunctionType):
          category = "function"
        elif isinstance(node_type, StructType):
          category = "struct"
        elif isinstance(node_type, EnumType):
          category = "enum"
        elif isinstance(node_type, TraitType):
          category = "trait"
        else:
          category = "variable"
      elif isinstance(receiver_type, EnumType):
        category = "enum member"
      elif isinstance(node_type, FunctionType):
        category = "method"
      else:
        category = "property"
    elif isinstance(node, StructDeclNode):
      node_name = node.name
      category = "proto" if node.is_prototype else "struct"
    elif isinstance(node, EnumDeclNode):
      node_name = node.name
      category = "enum"
    elif isinstance(node, EnumMemberNode):
      node_name = node.name
      category = "enum member"
    elif isinstance(node, TraitDeclNode):
      node_name = node.name
      category = "trait"
    elif isinstance(node, ImplBlockNode):
      s_line = getattr(node, "struct_name_line", None)
      s_col = getattr(node, "struct_name_column", None)
      s_len = getattr(node, "struct_name_length", None)
      t_line = getattr(node, "trait_name_line", None)
      t_col = getattr(node, "trait_name_column", None)
      t_len = getattr(node, "trait_name_length", None)
      if (
        node.trait_name
        and t_line is not None
        and t_col is not None
        and t_len is not None
        and t_line == line
        and t_col <= col < t_col + t_len
      ):
        node_name = node.trait_name
        category = "trait"
      elif s_line is None or (
        s_col is not None
        and s_len is not None
        and s_line == line
        and s_col <= col < s_col + s_len
      ):
        node_name = node.struct_name
        st = ls.symbol_table_cache[uri].lookup_type(node.struct_name)
        category = "proto" if getattr(st, "is_prototype", False) else "struct"
    elif isinstance(node, ParameterNode):
      category, node_name = "parameter", node.name
    elif isinstance(node, StructFieldNode):
      category, node_name = "property", node.name
    elif isinstance(node, TraitMemberNode):
      category, node_name = "method", node.name
    elif isinstance(node, VarDeclNode):
      is_extern = any(
        a.name == "extern" for a in getattr(node, "annotations", [])
      )
      category = "extern variable" if is_extern else "variable"
      node_name = cls._match_binding_name(node, line, col) or node.name
    elif isinstance(node, FuncDeclNode):
      is_export = any(
        a.name == "export" for a in getattr(node, "annotations", [])
      )
      category = "exported function" if is_export else "function"
      node_name = node.name
    elif isinstance(node, HeaderBindingNode):
      category = "variable"
      node_name = cls._match_binding_name(node, line, col) or node.let_name
    elif isinstance(node, ForNode):
      category, node_name = "variable", node.loop_var
    elif isinstance(node, BasicTypeNode):
      node_name = node.name

    if category == "symbol" and node_type:
      if isinstance(node_type, StructType):
        category = "proto" if node_type.is_prototype else "struct"
      elif isinstance(node_type, EnumType):
        category = "enum"
      elif isinstance(node_type, TraitType):
        category = "trait"
      elif isinstance(node_type, FunctionType):
        category = "function"

    return node_name, category

  @classmethod
  def _format_function_hover(
    cls,
    ls: Any,
    uri: str,
    node: Any,
    node_type: FunctionType,
    node_name: str,
    category: str,
  ) -> str:
    """Formats markdown hover text for a function or method signature."""
    params_lines = []
    ast_decl = getattr(node_type, "ast_decl", None)
    if not ast_decl and isinstance(node, (FuncDeclNode, TraitMemberNode)):
      ast_decl = node
    if not ast_decl and uri in ls.symbol_table_cache:
      target_sym = ls.symbol_table_cache[uri].lookup(node_name)
      if target_sym:
        ast_decl = getattr(target_sym, "ast_decl", None)

    ast_params = getattr(ast_decl, "parameters", None) if ast_decl else None
    p_defaults = getattr(node_type, "param_defaults", [])

    for idx, p_type in enumerate(node_type.param_types):
      p_name = (
        node_type.param_names[idx]
        if idx < len(node_type.param_names)
        else f"p{idx}"
      )
      is_mut = (
        node_type.param_mutabilities[idx]
        if idx < len(node_type.param_mutabilities)
        else False
      )
      mut_str = "var " if is_mut else ""

      default_str = ""
      if ast_params and idx < len(ast_params):
        d_expr = getattr(ast_params[idx], "default_expr", None)
        if d_expr is not None:
          default_str = f" = {format_ast_expr(d_expr)}"
      if (
        not default_str
        and p_defaults
        and idx < len(p_defaults)
        and p_defaults[idx] is not None
      ):  # pragma: no cover
        val = p_defaults[idx]
        if hasattr(val, "node_type") or isinstance(val, ASTNode):
          default_str = f" = {format_ast_expr(val)}"
        else:
          default_str = f" = {val}"

      if p_name == "self":  # pragma: no cover
        params_lines.append("- `self`")
      else:
        params_lines.append(
          f"- `{mut_str}{p_name}: {str(p_type)}{default_str}`"
        )

    params_section = "\n".join(params_lines)
    markdown_text = f"**({category})** `{node_name}`\n"
    if params_lines:
      markdown_text += f"\nParameters:\n{params_section}\n"
    else:
      markdown_text += "\nParameters: none\n"
    markdown_text += f"\nReturns: `{str(node_type.return_type)}`"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
    return markdown_text

  @classmethod
  def provide_hover(
    cls,
    ls: Any,
    params: HoverParams,
    find_node_fn: Any | None = None,
  ) -> Hover | None:
    """Triggered when user hovers over an identifier in the document."""
    uri = params.text_document.uri
    if uri not in ls.ast_cache or uri not in ls.node_types_cache:
      return None

    ast = ls.ast_cache[uri]
    node_types = ls.node_types_cache[uri]

    # LSP is 0-based UTF-16; parser/type checker line numbers are 1-based code
    # points.
    line = params.position.line + 1
    line_text = get_doc_line(ls, uri, line)
    col = (
      utf16_to_codepoint(line_text, params.position.character)
      if line_text is not None
      else params.position.character
    )

    if find_node_fn is None:
      find_node_fn = find_node_at_position
    node = find_node_fn(ast, line, col)
    if not node:
      return None

    node, node_type = cls._resolve_hover_node_and_type(
      ls, uri, node, line, col, node_types
    )
    if not node_type and type(node).__name__ != "AnnotationNode":
      return None

    if type(node).__name__ == "AnnotationNode":
      ann_arg = getattr(node, "arg", None)
      ann_name = getattr(node, "name", "")
      ann_display = f"@{ann_name}" + (f'("{ann_arg}")' if ann_arg else "")
      if ann_name == "extern":
        markdown_text = (
          f"**(annotation)** `{ann_display}`\n\n"
          "Declares an external variable provided by the host runtime "
          "environment.\n\n"
          "If no argument is given, uses the Sapphire variable name as the "
          "external name. Otherwise, uses the argument string as the external "
          "name."
        )
      elif ann_name == "export":
        markdown_text = (
          f"**(annotation)** `{ann_display}`\n\n"
          "Exposes a function to the host runtime environment under the name "
          "given as the argument."
        )
      else:
        markdown_text = f"**(annotation)** `{ann_display}`"
      return Hover(
        contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_text)
      )

    node_name, category = cls._classify_hover_node(
      ls, uri, node, node_type, line, col, node_types
    )

    if isinstance(node_type, FunctionType):
      markdown_text = cls._format_function_hover(
        ls, uri, node, node_type, node_name, category
      )
    elif isinstance(node_type, StructType) and category in ("struct", "proto"):
      kind = "proto" if node_type.is_prototype else "struct"
      inheritance = (
        f" : {', '.join(node_type.parent_names)}"
        if getattr(node_type, "parent_names", None)
        else ""
      )
      params_str = (
        f"<{', '.join(node_type.type_params)}>"
        if getattr(node_type, "type_params", None)
        else ""
      )
      markdown_text = (
        f"**({kind})** `{node_type.name}{params_str}{inheritance}`"
      )
      if getattr(node_type, "comments", None):
        markdown_text += f"\n\n{node_type.comments}"
    elif isinstance(node_type, EnumType) and category == "enum":
      markdown_text = f"**(enum)** `{node_type.name}`"
      if node_type.variants:
        members_str = "\n".join(
          f"- `{k} = {v}`" for k, v in node_type.variants.items()
        )
        markdown_text += f"\n\nMembers:\n{members_str}"
      if getattr(node_type, "comments", None):
        markdown_text += f"\n\n{node_type.comments}"
    elif isinstance(node_type, TraitType) and category == "trait":
      params_str = (
        f"<{', '.join(node_type.type_params)}>"
        if getattr(node_type, "type_params", None)
        else ""
      )
      markdown_text = f"**(trait)** `{node_type.name}{params_str}`"
      if getattr(node_type, "comments", None):
        markdown_text += f"\n\n{node_type.comments}"
    else:
      type_desc = str(node_type)
      markdown_text = (
        f"**({category})** `{node_name}`: `{type_desc}`"
        if node_name
        else f"`{type_desc}`"
      )
      field_comments = ""
      declarations = getattr(ast, "declarations", [])
      if isinstance(node, StructFieldNode) and uri in ls.symbol_table_cache:
        parent_struct = next(
          (
            child
            for child in declarations
            if isinstance(child, StructDeclNode)
            and any(f is node for f in child.fields)
          ),
          None,
        )
        if parent_struct:
          st = ls.symbol_table_cache[uri].lookup_type(parent_struct.name)
          if st and node.name in st.fields:
            field_comments = getattr(st.fields[node.name], "comments", "")
          elif st and node.name in getattr(st, "static_fields", {}):
            field_comments = getattr(
              st.static_fields[node.name], "comments", ""
            )
      elif isinstance(node, MemberAccessNode) and uri in ls.symbol_table_cache:
        from sapphire.semantics.symbol_table import (
          OptionalType,
          RefType,
          SharedRefType,
        )

        receiver_type = node_types.get(node.receiver)
        if isinstance(receiver_type, OptionalType):
          receiver_type = receiver_type.base_type
        if isinstance(receiver_type, (SharedRefType, RefType)):
          receiver_type = receiver_type.inner_type
        if isinstance(receiver_type, StructType):
          if node.member in receiver_type.fields:
            field_comments = getattr(
              receiver_type.fields[node.member], "comments", ""
            )
          else:
            static_field = receiver_type.get_static_field(
              node.member, ls.symbol_table_cache[uri]
            )
            if static_field is not None:
              field_comments = getattr(static_field, "comments", "")
      if field_comments:
        markdown_text += f"\n\n{field_comments}"

    return Hover(
      contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_text)
    )
