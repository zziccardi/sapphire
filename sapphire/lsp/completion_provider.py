"""LSP code completion provider for Sapphire."""

import re
from collections.abc import Callable
from typing import Any

from lsprotocol.types import CompletionItem, CompletionList, CompletionParams

from sapphire.lsp.definition_provider import (
  _line_in_node_span,
  find_local_decl,
)
from sapphire.lsp.semantic_tokens import utf16_to_codepoint
from sapphire.parser.ast import (
  BlockNode,
  ForNode,
  FuncDeclNode,
  ImplBlockNode,
  VarDeclNode,
  WhileNode,
)

_KEYWORDS = [
  "let",
  "var",
  "func",
  "struct",
  "proto",
  "enum",
  "trait",
  "impl",
  "if",
  "else",
  "guard",
  "for",
  "in",
  "while",
  "break",
  "continue",
  "return",
  "match",
  "yield",
  "true",
  "false",
  "none",
  "static",
  "clone",
  "arena",
  "import",
  "export",
  "as",
]


def _collect_block_stmt_locals(
  stmts: list[Any],
  line: int,
  node_types: dict,
  add_item: Callable[[str, int, str], None],
) -> None:
  """Adds local variables, unwrap bindings, and loop variables visible at
  *line*.
  """
  for stmt in stmts:
    st_start = getattr(stmt, "start_line", None)
    if st_start is not None and st_start > line:
      continue
    if isinstance(stmt, VarDeclNode):
      binding_types = getattr(stmt, "binding_types", {}) or {}
      names = getattr(stmt, "names", None) or (
        [stmt.name] if getattr(stmt, "name", None) else []
      )
      for idx, v_name in enumerate(names):
        vtype = binding_types.get(v_name) or (
          node_types.get(stmt) if idx == 0 else None
        )
        type_str = f": {vtype}" if vtype else ""
        add_item(v_name, 6, f"(variable) {v_name}{type_str}")
    elif type(stmt).__name__ == "GuardStmtNode":
      else_block = getattr(stmt, "else_block", None)
      if else_block is not None and _line_in_node_span(else_block, line):
        _collect_block_stmt_locals(
          getattr(else_block, "statements", []), line, node_types, add_item
        )
        if line > getattr(else_block, "start_line", line):
          continue
      bindings = getattr(
        stmt,
        "bindings",
        [stmt.init_binding] if getattr(stmt, "init_binding", None) else [],
      )
      for b in bindings:
        names = getattr(
          b, "let_names", [b.let_name] if getattr(b, "let_name", None) else []
        )
        for b_name in names:
          add_item(b_name, 6, f"(variable) {b_name}")
    elif type(stmt).__name__ == "IfNode":
      if not _line_in_node_span(stmt, line):
        continue
      then_block = getattr(stmt, "then_block", None)
      else_block = getattr(stmt, "else_block", None)
      in_else = else_block is not None and _line_in_node_span(else_block, line)
      if in_else:
        else_stmts = (
          [else_block]
          if type(else_block).__name__ == "IfNode"
          else getattr(else_block, "statements", [])
        )
        _collect_block_stmt_locals(else_stmts, line, node_types, add_item)
      else:
        bindings = getattr(
          stmt,
          "bindings",
          [stmt.init_binding] if getattr(stmt, "init_binding", None) else [],
        )
        for b in bindings:
          names = getattr(
            b,
            "let_names",
            [b.let_name] if getattr(b, "let_name", None) else [],
          )
          for b_name in names:
            add_item(b_name, 6, f"(variable) {b_name}")
        if then_block is not None and _line_in_node_span(then_block, line):
          _collect_block_stmt_locals(
            getattr(then_block, "statements", []), line, node_types, add_item
          )
    elif isinstance(stmt, ForNode):
      if not _line_in_node_span(stmt, line):
        continue
      if stmt.key_var:
        add_item(stmt.key_var, 6, f"(variable) {stmt.key_var}")
      val_var = getattr(stmt, "val_var", stmt.loop_var)
      add_item(val_var, 6, f"(variable) {val_var}")
      block = getattr(stmt, "block", None)
      if block is not None and _line_in_node_span(block, line):
        _collect_block_stmt_locals(
          getattr(block, "statements", []), line, node_types, add_item
        )
    elif isinstance(stmt, (WhileNode, BlockNode)):
      if not _line_in_node_span(stmt, line):
        continue
      nested = (
        getattr(stmt, "statements", [])
        if isinstance(stmt, BlockNode)
        else getattr(getattr(stmt, "block", None), "statements", [])
      )
      _collect_block_stmt_locals(nested, line, node_types, add_item)


def get_scope_completion_items(
  ast: Any,
  line: int,
  col: int,
  uri: str,
  ls: Any,
  node_types: dict,
) -> list[CompletionItem]:
  """Collects scope-visible locals, symbols, keywords, and document words."""
  items: list[CompletionItem] = []
  seen: set = set()

  def add_item(label: str, kind: int, detail: str) -> None:
    if label and label not in seen:
      seen.add(label)
      items.append(
        CompletionItem(label=label, kind=kind, detail=detail, insert_text=label)
      )

  # 1. Local Scope AST Traversal
  for decl in getattr(ast, "declarations", []):
    s_start = getattr(decl, "start_line", None)
    s_end = getattr(decl, "end_line", None)
    if (
      s_start is None or s_start > line or (s_end is not None and line > s_end)
    ):
      continue

    if isinstance(decl, FuncDeclNode):
      for p in decl.parameters:
        ptype = node_types.get(p)
        type_str = f": {ptype}" if ptype else ""
        add_item(p.name, 6, f"(parameter) {p.name}{type_str}")
      stmts = (
        getattr(decl.body, "statements", []) if hasattr(decl, "body") else []
      )
      _collect_block_stmt_locals(stmts, line, node_types, add_item)
    elif isinstance(decl, ImplBlockNode):
      for member in decl.members:
        func_decl = getattr(member, "func_decl", None)
        if not func_decl:
          continue
        f_start = getattr(func_decl, "start_line", None)
        f_end = getattr(func_decl, "end_line", None)
        if (
          f_start is not None
          and f_start <= line
          and (f_end is None or line <= f_end)
        ):
          if getattr(member, "modifier", None) != "static":
            add_item("self", 6, f"(variable) self: {decl.struct_name}")
          for p in func_decl.parameters:
            ptype = node_types.get(p)
            type_str = f": {ptype}" if ptype else ""
            add_item(p.name, 6, f"(parameter) {p.name}{type_str}")
          stmts = (
            getattr(func_decl.body, "statements", [])
            if hasattr(func_decl, "body")
            else []
          )
          _collect_block_stmt_locals(stmts, line, node_types, add_item)

  # 2. Symbol table scopes
  if uri in ls.symbol_table_cache:
    sym_table = ls.symbol_table_cache[uri]
    scope = getattr(sym_table, "current_scope", None)
    while scope:
      for sym_name, sym in scope.symbols.items():
        if sym_name == "Arena":
          continue
        sym_kind = type(sym).__name__
        if sym_kind == "VariableSymbol":
          is_param = getattr(sym, "is_parameter", False)
          detail = (
            f"(parameter) {sym_name}: {sym.symbol_type}"
            if is_param
            else f"(variable) {sym_name}: {sym.symbol_type}"
          )
          add_item(sym_name, 6, detail)
        elif sym_kind == "FunctionSymbol":
          add_item(sym_name, 3, f"(function) {sym_name}{sym.symbol_type}")
        elif sym_kind == "StructSymbol":
          kind_name = (
            "proto"
            if getattr(sym.symbol_type, "is_prototype", False)
            else "struct"
          )
          add_item(sym_name, 22, f"({kind_name}) {sym_name}")
        elif sym_kind == "EnumSymbol":
          add_item(sym_name, 13, f"(enum) {sym_name}")
        elif sym_kind == "TraitSymbol":
          add_item(sym_name, 8, f"(trait) {sym_name}")

      for type_name in scope.types:
        if type_name in ("int", "float", "bool", "String", "none", "Arena"):
          add_item(type_name, 14, f"(primitive type) {type_name}")
        else:
          add_item(type_name, 22, f"(type) {type_name}")

      scope = scope.parent

  # 3. Sapphire Keywords & Annotations
  for kw in _KEYWORDS:
    add_item(kw, 14, f"(keyword) {kw}")
  add_item("@extern", 15, "(annotation) @extern")
  add_item("@export", 15, "(annotation) @export")

  # 4. Document Text Word Extraction Fallback
  try:
    doc = ls.workspace.get_text_document(uri)
    source = getattr(doc, "source", None)
    if isinstance(source, str):
      for word in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", source):
        if len(word) > 1:
          add_item(word, 1, f"(text) {word}")
  except (AttributeError, KeyError, IndexError, TypeError):  # pragma: no cover
    pass

  return items


def _find_enclosing_impl_struct(
  ast: Any, sym_table: Any, line: int
) -> Any | None:
  """Returns the StructType of the ImplBlockNode enclosing *line*, if any."""
  if not ast or not sym_table:
    return None
  for decl in getattr(ast, "declarations", []):
    if isinstance(decl, ImplBlockNode) and _line_in_node_span(decl, line):
      return sym_table.lookup_type(decl.struct_name)
  return None


class CompletionProvider:
  """Provides dot-access and scope-level completions for Sapphire."""

  @staticmethod
  def _get_dot_completions(
    ls: Any,
    uri: str,
    receiver_name: str,
    line: int,
    node_types: dict,
  ) -> CompletionList | None:
    """Resolves member completions for `<receiver_name>.`."""
    ast = ls.ast_cache.get(uri)
    sym_table = ls.symbol_table_cache.get(uri)
    receiver_type = None
    best_node = None

    # Resolve `self.` directly from the enclosing `impl` block so sibling
    # `impl` blocks never hijack completions.
    if receiver_name == "self":
      receiver_type = _find_enclosing_impl_struct(ast, sym_table, line)

    # Prefer lexically visible local declaration (including multi-var bindings).
    if receiver_type is None and ast is not None:
      local_decl = find_local_decl(ast, receiver_name, line)
      if local_decl is not None:
        binding_types = getattr(local_decl, "binding_types", None)
        if isinstance(binding_types, dict) and receiver_name in binding_types:
          receiver_type = binding_types[receiver_name]
          best_node = local_decl
        elif local_decl in node_types:
          receiver_type = node_types[local_decl]
          best_node = local_decl

    if receiver_type is None:
      min_dist = float("inf")
      for node in node_types.keys():
        binding_types = getattr(node, "binding_types", None)
        if isinstance(binding_types, dict) and receiver_name in binding_types:
          s_line = getattr(node, "start_line", getattr(node, "name_line", None))
          dist = abs(s_line - line) if s_line else 0
          if dist < min_dist:
            min_dist = dist
            best_node = node
            receiver_type = binding_types[receiver_name]
          continue
        n_name = (
          getattr(node, "name", None)
          or getattr(node, "member", None)
          or getattr(node, "alias", None)
          or getattr(node, "let_name", None)
          or getattr(node, "key_var", None)
          or getattr(node, "val_var", None)
          or getattr(node, "loop_var", None)
        )
        if n_name == receiver_name:
          s_line = getattr(node, "start_line", getattr(node, "name_line", None))
          dist = abs(s_line - line) if s_line else 0
          if dist < min_dist:
            min_dist = dist
            best_node = node
            receiver_type = node_types.get(node)

    if not receiver_type and sym_table is not None:
      sym = sym_table.lookup(receiver_name)
      if sym:
        receiver_type = getattr(sym, "symbol_type", None)

    if type(receiver_type).__name__ == "OptionalType":
      receiver_type = getattr(
        receiver_type, "base_type", receiver_type
      )  # pragma: no cover
    if type(receiver_type).__name__ in ("SharedRefType", "RefType"):
      receiver_type = getattr(
        receiver_type, "inner_type", receiver_type
      )  # pragma: no cover

    if (
      type(receiver_type).__name__ in ("StringType", "PrimitiveType")
      and getattr(receiver_type, "name", "") == "String"
    ):
      from sapphire.semantics.symbol_table import STRING_METHODS

      items = [
        CompletionItem(
          label=m_name,
          kind=2,
          detail=f"(string method) {m_name}{sig}",
          insert_text=m_name,
        )
        for m_name, sig in STRING_METHODS.items()
      ]
      return CompletionList(is_incomplete=False, items=items)

    if type(receiver_type).__name__ == "ModuleType" or (
      not best_node
      and sym_table is not None
      and type(sym_table.lookup(receiver_name)).__name__ == "ModuleSymbol"
    ):
      mod_sym = (
        sym_table.lookup(receiver_name) if sym_table is not None else None
      )
      exports = (
        mod_sym.exports if mod_sym and hasattr(mod_sym, "exports") else {}
      )
      items = []
      for exp_name, exp_val in exports.items():
        type_str = (
          str(exp_val.symbol_type)
          if hasattr(exp_val, "symbol_type")
          else str(exp_val)
        )
        items.append(
          CompletionItem(
            label=exp_name,
            kind=6,
            detail=f"(module export) {receiver_name}.{exp_name}: {type_str}",
            insert_text=exp_name,
          )
        )
      return CompletionList(is_incomplete=False, items=items)

    if hasattr(receiver_type, "variants"):
      enum_name = getattr(receiver_type, "name", receiver_name)
      items = [
        CompletionItem(
          label=variant_name,
          kind=20,
          detail=f"(enum member) {enum_name}.{variant_name} = {val}",
          insert_text=variant_name,
        )
        for variant_name, val in getattr(receiver_type, "variants", {}).items()
      ]
      return CompletionList(is_incomplete=True, items=items)

    if hasattr(receiver_type, "fields") or hasattr(receiver_type, "methods"):
      items = []
      seen_fields: set = set()
      seen_methods: set = set()
      visited_types: set = set()
      queue = [receiver_type]
      while queue:
        cur_type = queue.pop(0)
        type_key = getattr(cur_type, "name", None) or id(cur_type)
        if type_key in visited_types:
          continue
        visited_types.add(type_key)
        for field_name, field in getattr(cur_type, "fields", {}).items():
          if field_name in seen_fields:
            continue
          seen_fields.add(field_name)
          items.append(
            CompletionItem(
              label=field_name,
              kind=10,
              detail=f"(property) {field_name}: {str(field.field_type)}",
              insert_text=field_name,
            )
          )
        for method_name, method in getattr(cur_type, "methods", {}).items():
          if (
            method_name in ("__init__", "__del__")
            or method_name in seen_methods
          ):
            continue
          seen_methods.add(method_name)
          m_type = str(getattr(method, "method_type", method))
          items.append(
            CompletionItem(
              label=method_name,
              kind=2,
              detail=f"(method) {method_name}{m_type}",
              insert_text=method_name,
            )
          )
        if sym_table is not None:
          for p_name in getattr(cur_type, "parent_names", []) or []:
            p_type = sym_table.lookup_type(p_name)
            if p_type is not None:
              queue.append(p_type)
      return CompletionList(is_incomplete=True, items=items)

    return None

  @classmethod
  def provide_completion(
    cls, ls: Any, params: CompletionParams
  ) -> CompletionList:
    """Computes CompletionList for dot-access or scope-level identifiers."""
    uri = params.text_document.uri
    if uri not in ls.ast_cache and uri not in ls.symbol_table_cache:
      return CompletionList(is_incomplete=False, items=[])

    ast = ls.ast_cache.get(uri)
    node_types = ls.node_types_cache.get(uri, {})
    line = params.position.line + 1
    col = params.position.character

    line_text = ""
    try:
      doc = ls.workspace.get_text_document(uri)
      source = getattr(doc, "source", None)
      if isinstance(source, str):
        lines = source.splitlines()
        if 0 <= line - 1 < len(lines):
          line_text = lines[line - 1]
          col = utf16_to_codepoint(line_text, col)
    except (
      AttributeError,
      KeyError,
      IndexError,
      TypeError,
    ):  # pragma: no cover
      pass

    dot_match = re.search(
      r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z0-9_]*)$", line_text[:col]
    )
    if dot_match:
      dot_result = cls._get_dot_completions(
        ls, uri, dot_match.group(1), line, node_types
      )
      if dot_result is not None:
        return dot_result

    scope_items = get_scope_completion_items(
      ast, line, col, uri, ls, node_types
    )
    return CompletionList(is_incomplete=True, items=scope_items)
