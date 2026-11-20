"""LSP Go to Definition provider for Sapphire.

Finds symbol definitions, declaration locations, imported module targets,
and struct/trait members from cursor position.
"""

import os
from typing import Any, Optional, Tuple
from pygls.uris import from_fs_path, to_fs_path
from lsprotocol.types import (
    DefinitionParams,
    Location,
    Position,
    Range,
)

from src.parser.ast import (
    BasicTypeNode,
    BlockNode,
    CallNode,
    EnumDeclNode,
    EnumMemberNode,
    ForNode,
    FuncDeclNode,
    HeaderBindingNode,
    IdentifierNode,
    ImplBlockNode,
    ImportStmtNode,
    MemberAccessNode,
    ParameterNode,
    StructDeclNode,
    StructFieldNode,
    TraitDeclNode,
    VarDeclNode,
    WhileNode,
)
from src.semantics.symbol_table import (
    OptionalType,
    RefType,
    SharedRefType,
)
from src.semantics.module_resolver import resolve_module_path as sem_resolve_module_path
from src.lsp.semantic_tokens import find_node_at_position


def resolve_module_path(
    doc_uri: str, mod_path: str, workspace_root: Optional[str] = None
) -> Optional[str]:
  """Resolves a dot-separated Sapphire import path to an absolute file path on disk."""
  doc_path = to_fs_path(doc_uri) if doc_uri.startswith("file://") else doc_uri
  res = sem_resolve_module_path(mod_path, source_file_path=doc_path)
  if res and os.path.isfile(res):
    return res

  doc_dir = os.path.dirname(doc_path) if doc_path else ""

  rel_parts = mod_path.split(".")
  candidates = [
      os.path.join(*rel_parts) + ".sp",
      os.path.join(*rel_parts, "mod.sp"),
      os.path.join(*rel_parts, "index.sp"),
  ]

  search_dirs = [doc_dir]
  if workspace_root:
    ws_path = (
        to_fs_path(workspace_root)
        if workspace_root.startswith("file://")
        else workspace_root
    )
    if ws_path and ws_path not in search_dirs:
      search_dirs.append(ws_path)

  for base in search_dirs:
    if not base:
      continue
    for cand in candidates:
      target = os.path.normpath(os.path.join(base, cand))
      if os.path.isfile(target):
        return target

  return None


def _find_decl_in_stmts(stmts: list, name: str, line: int) -> Optional[Any]:
  """Searches statements (including nested control-flow blocks) for local decl."""
  for stmt in stmts:
    st_start = getattr(stmt, "start_line", None)
    if st_start is not None and st_start > line:
      continue
    if isinstance(stmt, VarDeclNode):
      if getattr(stmt, "name", None) == name or name in getattr(
          stmt, "names", []
      ):
        return stmt
    elif type(stmt).__name__ in ("IfNode", "GuardStmtNode"):
      bindings = getattr(
          stmt,
          "bindings",
          [stmt.init_binding]
          if getattr(stmt, "init_binding", None)
          else [],
      )
      for b in bindings:
        b_names = getattr(
            b,
            "let_names",
            [b.let_name] if getattr(b, "let_name", None) else [],
        )
        for b_name in b_names:
          if b_name == name:
            return b
      if type(stmt).__name__ == "IfNode":
        then_block = getattr(stmt, "then_block", None)
        if then_block is not None:
          found = _find_decl_in_stmts(
              getattr(then_block, "statements", []), name, line
          )
          if found:
            return found
        else_block = getattr(stmt, "else_block", None)
        if else_block is not None:
          else_stmts = (
              [else_block]
              if type(else_block).__name__ == "IfNode"
              else getattr(else_block, "statements", [])
          )
          found = _find_decl_in_stmts(else_stmts, name, line)
          if found:
            return found
    elif isinstance(stmt, ForNode):
      if (
          getattr(stmt, "key_var", None) == name
          or getattr(stmt, "val_var", None) == name
          or getattr(stmt, "loop_var", None) == name
      ):
        return stmt
      block = getattr(stmt, "block", None)
      if block is not None:
        found = _find_decl_in_stmts(getattr(block, "statements", []), name, line)
        if found:
          return found
    elif isinstance(stmt, (WhileNode, BlockNode)):
      nested = (
          getattr(stmt, "statements", [])
          if isinstance(stmt, BlockNode)
          else getattr(getattr(stmt, "block", None), "statements", [])
      )
      found = _find_decl_in_stmts(nested, name, line)
      if found:
        return found
  return None


def find_local_decl(ast: Any, name: str, line: int) -> Optional[Any]:
  """Finds local variable or parameter declaration in AST containing line."""
  declarations = getattr(ast, "declarations", [])
  for decl in declarations:
    if isinstance(decl, FuncDeclNode):
      s_start = getattr(decl, "start_line", None)
      s_end = getattr(decl, "end_line", None)
      if (
          s_start is not None
          and s_start <= line
          and (s_end is None or line <= s_end + 10)
      ):
        for p in decl.parameters:
          if p.name == name:
            return p
        stmts = (
            getattr(decl.body, "statements", [])
            if hasattr(decl, "body")
            else []
        )
        found = _find_decl_in_stmts(stmts, name, line)
        if found:
          return found
    elif isinstance(decl, ImplBlockNode):
      for member in decl.members:
        func_decl = getattr(member, "func_decl", None)
        if func_decl:
          f_start = getattr(func_decl, "start_line", None)
          f_end = getattr(func_decl, "end_line", None)
          if (
              f_start is not None
              and f_start <= line
              and (f_end is None or line <= f_end + 10)
          ):
            for p in func_decl.parameters:
              if p.name == name:
                return p  # pragma: no cover
            stmts = (
                getattr(func_decl.body, "statements", [])
                if hasattr(func_decl, "body")
                else []
            )
            found = _find_decl_in_stmts(stmts, name, line)
            if found:
              return found
    elif isinstance(decl, VarDeclNode):
      if getattr(decl, "name", None) == name or name in getattr(
          decl, "names", []
      ):
        return decl  # pragma: no cover
  return None


class DefinitionProvider:
  """Resolves Go to Definition locations for Sapphire AST nodes."""

  @classmethod
  def _extract_decl_ast(cls, sym: Any) -> Optional[Any]:
    """Extracts the underlying AST declaration node from a symbol or type."""
    if not sym:
      return None
    if hasattr(sym, "ast_decl") and sym.ast_decl:
      return sym.ast_decl
    sym_t = getattr(sym, "symbol_type", None)
    if sym_t and hasattr(sym_t, "ast_decl") and sym_t.ast_decl:
      return sym_t.ast_decl
    return None

  @classmethod
  def _resolve_module_export_ast(
      cls, ls: Any, mod_sym: Any, member_name: str
  ) -> Optional[Any]:
    """Resolves an exported symbol from a ModuleSymbol, falling back to cached symbol tables."""
    target_sym = mod_sym.lookup_export(member_name)
    target_ast = cls._extract_decl_ast(target_sym)

    mod_file_path = getattr(mod_sym, "file_path", None)
    if mod_file_path:
      mod_uri = from_fs_path(os.path.abspath(mod_file_path))
      if not target_ast and mod_uri in ls.symbol_table_cache:  # pragma: no cover
        sub_sym_table = ls.symbol_table_cache[mod_uri]
        exp_sym = sub_sym_table.lookup(member_name) or sub_sym_table.lookup_type(
            member_name
        )
        target_ast = cls._extract_decl_ast(exp_sym)
      if target_ast:
        target_ast.file_uri = mod_uri
    return target_ast

  @classmethod
  def _resolve_member_definition(
      cls, ls: Any, node: MemberAccessNode, sym_table: Any, node_types: Any
  ) -> Optional[Any]:
    """Resolves Go to Definition for a MemberAccessNode (module, field, method, enum)."""
    target_ast = None
    if isinstance(node.receiver, IdentifierNode):
      sym = sym_table.lookup(node.receiver.name)
      if sym and type(sym).__name__ == "ModuleSymbol":
        target_ast = cls._resolve_module_export_ast(ls, sym, node.member)

    receiver_type = node_types.get(node.receiver)
    if (
        not target_ast
        and not receiver_type
        and isinstance(node.receiver, IdentifierNode)
    ):  # pragma: no cover
      sym = sym_table.lookup(node.receiver.name)
      if sym:  # pragma: no cover
        receiver_type = getattr(sym, "symbol_type", None)
      if not receiver_type:  # pragma: no cover
        receiver_type = sym_table.lookup_type(node.receiver.name)

    if not receiver_type:
      return target_ast

    if isinstance(receiver_type, OptionalType):
      receiver_type = receiver_type.base_type
    if isinstance(receiver_type, (SharedRefType, RefType)):
      receiver_type = receiver_type.inner_type

    if hasattr(receiver_type, "ast_decl") and receiver_type.ast_decl:
      for field in getattr(receiver_type.ast_decl, "fields", []):
        if getattr(field, "name", None) == node.member:
          target_ast = field
          break

    # Fall back to inherited parent struct fields when not found on child.
    if not target_ast and getattr(receiver_type, "parent_names", None):
      for p_name in receiver_type.parent_names:
        p_type = sym_table.lookup_type(p_name)
        if p_type and getattr(p_type, "ast_decl", None):
          for field in getattr(p_type.ast_decl, "fields", []):
            if getattr(field, "name", None) == node.member:
              target_ast = field
              break
          if target_ast:
            break

    if not target_ast and hasattr(receiver_type, "methods"):
      method = (
          receiver_type.get_method(node.member, sym_table)
          if hasattr(receiver_type, "get_method")
          else receiver_type.methods.get(node.member)
      )
      if method and getattr(method, "ast_decl", None):
        target_ast = method.ast_decl

    if not target_ast and getattr(receiver_type, "ast_decl", None):
      for member in getattr(receiver_type.ast_decl, "members", []):
        if getattr(member, "name", None) == node.member:
          target_ast = member
          break

    return target_ast

  @classmethod
  def _extract_node_range(
      cls, target_ast: Any, node: Any
  ) -> Optional[Range]:
    """Computes the LSP Range for a target AST declaration or binding."""
    target_decl = getattr(target_ast, "func_decl", target_ast)
    name_line = getattr(target_decl, "name_line", None)
    name_col = getattr(target_decl, "name_column", None)
    name_len = getattr(target_decl, "name_length", None)

    if isinstance(target_decl, HeaderBindingNode):
      bindings_info = getattr(target_decl, "bindings_info", None)
      matched_info = None
      if isinstance(bindings_info, list) and bindings_info:
        if isinstance(node, IdentifierNode):
          matched_info = next(
              (info for info in bindings_info if info.get("name") == node.name),
              None,
          )
        if matched_info is None:
          matched_info = bindings_info[0]
      if matched_info is not None:
        name_line = matched_info.get("line")
        name_col = matched_info.get("column")
        name_len = matched_info.get("length")
      else:
        name_line = getattr(target_decl, "let_name_line", None)
        name_col = getattr(target_decl, "let_name_column", None)
        name_len = getattr(target_decl, "let_name_length", None)

    if name_line is not None and name_col is not None and name_len is not None:
      return Range(
          start=Position(line=name_line - 1, character=name_col),
          end=Position(line=name_line - 1, character=name_col + name_len),
      )
    if getattr(target_ast, "start_line", None) is not None:
      s_line = target_ast.start_line - 1
      s_col = target_ast.start_column or 0
      e_line = (target_ast.end_line - 1) if target_ast.end_line else s_line
      e_col = (
          target_ast.end_column
          if target_ast.end_column is not None
          else s_col + 1
      )
      return Range(
          start=Position(line=s_line, character=s_col),
          end=Position(line=e_line, character=e_col),
      )
    return None  # pragma: no cover

  @classmethod
  def _locate_in_ast_cache(
      cls, ls: Any, target_decl: Any
  ) -> Optional[Tuple[str, Range]]:
    """Searches cached ASTs when `target_ast.file_uri` is not directly populated."""
    target_name = getattr(target_decl, "name", None)
    if not target_name:
      return None

    def _search_ast(ast_node: Any) -> Optional[Any]:
      for c_decl in getattr(ast_node, "declarations", []):
        if (
            c_decl is target_decl
            or getattr(c_decl, "name", None) == target_name
        ):  # pragma: no cover
          return c_decl
        if isinstance(c_decl, (TraitDeclNode, EnumDeclNode)):
          for m in getattr(c_decl, "members", []):
            if m is target_decl or getattr(m, "name", None) == target_name:
              return m
        elif isinstance(c_decl, StructDeclNode):
          for f in getattr(c_decl, "fields", []):
            if f is target_decl or getattr(f, "name", None) == target_name:
              return f
        elif isinstance(c_decl, ImplBlockNode):
          for m in getattr(c_decl, "members", []):
            fn = getattr(m, "func_decl", m)
            if (
                fn is target_decl
                or getattr(fn, "name", None) == target_name
            ):  # pragma: no cover
              return fn
      return None

    for c_uri, c_ast in ls.ast_cache.items():
      matched_node = _search_ast(c_ast)
      if not matched_node:
        continue
      target_uri = getattr(c_ast, "file_uri", c_uri)
      matched_range = cls._extract_node_range(matched_node, matched_node)
      if matched_range is not None:
        return target_uri, matched_range
    return None

  @classmethod
  def provide_definition(
      cls,
      ls: Any,
      params: DefinitionParams,
      find_node_fn: Optional[Any] = None,
  ) -> Optional[Location]:
    """Triggered when user requests Go to Definition."""
    uri = params.text_document.uri
    if uri not in ls.ast_cache or uri not in ls.symbol_table_cache:
      return None

    ast = ls.ast_cache[uri]
    sym_table = ls.symbol_table_cache[uri]
    node_types = ls.node_types_cache.get(uri, {})

    line = params.position.line + 1
    col = params.position.character

    if find_node_fn is None:
      find_node_fn = find_node_at_position
    node = find_node_fn(ast, line, col)
    if not node:
      return None

    if isinstance(node, CallNode):  # pragma: no cover
      node = node.callee

    target_ast = None
    if isinstance(node, ImportStmtNode):
      path_line = getattr(node, "path_line", getattr(node, "start_line", None))
      path_col = getattr(
          node, "path_column", getattr(node, "start_column", None)
      )
      path_len = getattr(node, "path_length", getattr(node, "length", None))
      if (
          path_line is not None
          and path_col is not None
          and path_len is not None
          and path_line == line
          and path_col <= col < path_col + path_len
      ):
        ws_root = getattr(getattr(ls, "workspace", None), "root_uri", None)
        target_fs = resolve_module_path(uri, node.path, ws_root)
        if target_fs:
          target_uri = from_fs_path(os.path.abspath(target_fs))
          return Location(
              uri=target_uri,
              range=Range(
                  start=Position(line=0, character=0),
                  end=Position(line=0, character=0),
              ),
          )
    elif isinstance(node, IdentifierNode):
      sym = sym_table.lookup(node.name)
      if (
          sym
          and type(sym).__name__ == "ModuleSymbol"
          and getattr(sym, "file_path", None)
      ):
        mod_uri = from_fs_path(os.path.abspath(sym.file_path))
        return Location(
            uri=mod_uri,
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=0),
            ),
        )
      target_ast = cls._extract_decl_ast(sym)
      if not target_ast:
        type_obj = sym_table.lookup_type(node.name)
        if getattr(type_obj, "ast_decl", None):  # pragma: no cover
          target_ast = type_obj.ast_decl
      if not target_ast:
        target_ast = find_local_decl(ast, node.name, line)
    elif isinstance(node, MemberAccessNode):
      target_ast = cls._resolve_member_definition(
          ls, node, sym_table, node_types
      )
    elif isinstance(node, BasicTypeNode):
      if "." in node.name:
        parts = node.name.split(".", 1)
        sym = sym_table.lookup(parts[0])
        if sym and type(sym).__name__ == "ModuleSymbol":
          target_ast = cls._resolve_module_export_ast(ls, sym, parts[1])
      if not target_ast:
        type_obj = sym_table.lookup_type(node.name)
        if getattr(type_obj, "ast_decl", None):
          target_ast = type_obj.ast_decl
    elif isinstance(node, StructDeclNode):
      for info in getattr(node, "parent_names_info", []):
        if (
            info.get("line") == line
            and info.get("column") <= col < info.get("column") + info.get("length")
        ):
          parent_type = sym_table.lookup_type(info["name"])
          if getattr(parent_type, "ast_decl", None):
            target_ast = parent_type.ast_decl
            break
      if not target_ast:
        target_ast = node
    elif isinstance(node, ImplBlockNode):
      t_line = getattr(node, "trait_name_line", None)
      t_col = getattr(node, "trait_name_column", None)
      t_len = getattr(node, "trait_name_length", None)
      if node.trait_name and t_line == line and t_col <= col < t_col + t_len:
        trait_type = sym_table.lookup_type(node.trait_name)
        if getattr(trait_type, "ast_decl", None):
          target_ast = trait_type.ast_decl
      if not target_ast:
        struct_type = sym_table.lookup_type(node.struct_name)
        if getattr(struct_type, "ast_decl", None):
          target_ast = struct_type.ast_decl
    elif isinstance(
        node,
        (
            FuncDeclNode,
            VarDeclNode,
            HeaderBindingNode,
            ParameterNode,
            EnumDeclNode,
            EnumMemberNode,
            TraitDeclNode,
            StructFieldNode,
        ),
    ):
      target_ast = node

    if not target_ast:  # pragma: no cover
      return None

    loc_range = cls._extract_node_range(target_ast, node)
    if loc_range is None:  # pragma: no cover
      return None

    target_uri = getattr(target_ast, "file_uri", None)
    if not target_uri:
      target_decl = getattr(target_ast, "func_decl", target_ast)
      cached = cls._locate_in_ast_cache(ls, target_decl)
      if cached:
        target_uri, loc_range = cached
    if not target_uri:
      target_uri = uri

    return Location(uri=target_uri, range=loc_range)
