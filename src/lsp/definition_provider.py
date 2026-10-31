"""LSP Go to Definition provider for Sapphire.

Finds symbol definitions, declaration locations, imported module targets,
and struct/trait members from cursor position.
"""

import os
from typing import Any, Optional
from pygls.uris import from_fs_path, to_fs_path
from lsprotocol.types import (
    DefinitionParams,
    Location,
    Position,
    Range,
)

from src.parser.ast import (
    BasicTypeNode,
    CallNode,
    EnumDeclNode,
    EnumMemberNode,
    ForNode,
    FuncDeclNode,
    IdentifierNode,
    IfNode,
    ImplBlockNode,
    ImportStmtNode,
    MemberAccessNode,
    ParameterNode,
    StructDeclNode,
    StructFieldNode,
    TraitDeclNode,
    VarDeclNode,
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
        for stmt in stmts:
          st_start = getattr(stmt, "start_line", None)
          if isinstance(stmt, VarDeclNode):
            if st_start is None or st_start <= line:
              if getattr(stmt, "name", None) == name or name in getattr(
                  stmt, "names", []
              ):
                return stmt
          elif type(stmt).__name__ == "IfNode":
            if st_start is None or st_start <= line:
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
          elif isinstance(stmt, ForNode):
            if st_start is None or st_start <= line:
              if (
                  getattr(stmt, "key_var", None) == name
                  or getattr(stmt, "val_var", None) == name
                  or getattr(stmt, "loop_var", None) == name
              ):
                return stmt
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
            for stmt in stmts:
              st_start = getattr(stmt, "start_line", None)
              if isinstance(stmt, VarDeclNode):
                if st_start is None or st_start <= line:
                  if getattr(stmt, "name", None) == name or name in getattr(
                      stmt, "names", []
                  ):
                    return stmt
              elif type(stmt).__name__ == "IfNode":
                if st_start is None or st_start <= line:
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
              elif isinstance(stmt, ForNode):
                if st_start is None or st_start <= line:
                  if (
                      getattr(stmt, "key_var", None) == name
                      or getattr(stmt, "val_var", None) == name
                      or getattr(stmt, "loop_var", None) == name
                  ):
                    return stmt
    elif isinstance(decl, VarDeclNode):
      if getattr(decl, "name", None) == name or name in getattr(
          decl, "names", []
      ):
        return decl  # pragma: no cover
  return None


class DefinitionProvider:
  """Resolves Go to Definition locations for Sapphire AST nodes."""

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

    target_ast = None

    if isinstance(node, CallNode):  # pragma: no cover
      node = node.callee

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
      ):
        if path_line == line and path_col <= col < path_col + path_len:
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

      if sym and hasattr(sym, "ast_decl") and sym.ast_decl:
        target_ast = sym.ast_decl
      elif (
          sym
          and hasattr(sym, "symbol_type")
          and hasattr(sym.symbol_type, "ast_decl")
          and sym.symbol_type.ast_decl
      ):
        target_ast = sym.symbol_type.ast_decl
      else:
        type_obj = sym_table.lookup_type(node.name)
        if (
            type_obj
            and hasattr(type_obj, "ast_decl")
            and type_obj.ast_decl
        ):  # pragma: no cover
          target_ast = type_obj.ast_decl

      if not target_ast:
        target_ast = find_local_decl(ast, node.name, line)

    elif isinstance(node, MemberAccessNode):
      if isinstance(node.receiver, IdentifierNode):
        sym = sym_table.lookup(node.receiver.name)
        if sym and type(sym).__name__ == "ModuleSymbol":
          target_sym = sym.lookup_export(node.member)
          if target_sym:
            if hasattr(target_sym, "ast_decl") and target_sym.ast_decl:
              target_ast = target_sym.ast_decl
            elif (
                hasattr(target_sym, "symbol_type")
                and hasattr(target_sym.symbol_type, "ast_decl")
                and target_sym.symbol_type.ast_decl
            ):
              target_ast = target_sym.symbol_type.ast_decl

          mod_file_path = getattr(sym, "file_path", None)
          if mod_file_path:
            mod_uri = from_fs_path(os.path.abspath(mod_file_path))
            if (
                not target_ast and mod_uri in ls.symbol_table_cache
            ):  # pragma: no cover
              sub_sym_table = ls.symbol_table_cache[mod_uri]
              exp_sym = sub_sym_table.lookup(
                  node.member
              ) or sub_sym_table.lookup_type(node.member)
              if exp_sym:
                if hasattr(exp_sym, "ast_decl") and exp_sym.ast_decl:
                  target_ast = exp_sym.ast_decl
                elif (
                    hasattr(exp_sym, "symbol_type")
                    and hasattr(exp_sym.symbol_type, "ast_decl")
                    and exp_sym.symbol_type.ast_decl
                ):
                  target_ast = exp_sym.symbol_type.ast_decl
            if target_ast:
              target_ast.file_uri = mod_uri

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

      if receiver_type:
        if hasattr(receiver_type, "ast_decl") and receiver_type.ast_decl:
          struct_decl = receiver_type.ast_decl
          if hasattr(struct_decl, "fields"):
            for field in struct_decl.fields:
              if getattr(field, "name", None) == node.member:
                target_ast = field
                break
        if (
            not target_ast
            and hasattr(receiver_type, "parent_names")
            and receiver_type.parent_names
        ):
          for p_name in receiver_type.parent_names:
            p_type = sym_table.lookup_type(p_name)
            if p_type and hasattr(p_type, "ast_decl") and p_type.ast_decl:
              p_decl = p_type.ast_decl
              if hasattr(p_decl, "fields"):
                for field in p_decl.fields:
                  if getattr(field, "name", None) == node.member:
                    target_ast = field
                    break
              if target_ast:
                break

        if (
            not target_ast
            and hasattr(receiver_type, "methods")
            and node.member in receiver_type.methods
        ):
          method = receiver_type.methods[node.member]
          if hasattr(method, "ast_decl") and method.ast_decl:
            target_ast = method.ast_decl
        if (
            not target_ast
            and hasattr(receiver_type, "ast_decl")
            and receiver_type.ast_decl
        ):
          enum_decl = receiver_type.ast_decl
          if hasattr(enum_decl, "members"):
            for member in enum_decl.members:
              if getattr(member, "name", None) == node.member:
                target_ast = member
                break

    elif isinstance(node, BasicTypeNode):
      if "." in node.name:
        parts = node.name.split(".", 1)
        sym = sym_table.lookup(parts[0])
        if sym and type(sym).__name__ == "ModuleSymbol":
          exp = sym.lookup_export(parts[1])
          if exp:
            if hasattr(exp, "ast_decl") and exp.ast_decl:
              target_ast = exp.ast_decl
            elif (
                hasattr(exp, "symbol_type")
                and hasattr(exp.symbol_type, "ast_decl")
                and exp.symbol_type.ast_decl
            ):  # pragma: no cover
              target_ast = exp.symbol_type.ast_decl

          mod_file_path = getattr(sym, "file_path", None)
          if mod_file_path:
            mod_uri = from_fs_path(os.path.abspath(mod_file_path))
            if (
                not target_ast and mod_uri in ls.symbol_table_cache
            ):  # pragma: no cover
              exp_sym = ls.symbol_table_cache[mod_uri].lookup_type(
                  parts[1]
              ) or ls.symbol_table_cache[mod_uri].lookup(parts[1])
              if exp_sym:
                if hasattr(exp_sym, "ast_decl") and exp_sym.ast_decl:
                  target_ast = exp_sym.ast_decl
                elif (
                    hasattr(exp_sym, "symbol_type")
                    and hasattr(exp_sym.symbol_type, "ast_decl")
                    and exp_sym.symbol_type.ast_decl
                ):
                  target_ast = exp_sym.symbol_type.ast_decl
            if target_ast:
              target_ast.file_uri = mod_uri

      if not target_ast:
        type_obj = sym_table.lookup_type(node.name)
        if type_obj and hasattr(type_obj, "ast_decl") and type_obj.ast_decl:
          target_ast = type_obj.ast_decl

    elif isinstance(node, StructDeclNode):
      for info in getattr(node, "parent_names_info", []):
        p_line = info.get("line")
        p_col = info.get("column")
        p_len = info.get("length")
        if p_line == line and p_col <= col < p_col + p_len:
          parent_type = sym_table.lookup_type(info["name"])
          if (
              parent_type
              and hasattr(parent_type, "ast_decl")
              and parent_type.ast_decl
          ):
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
        if (
            trait_type
            and hasattr(trait_type, "ast_decl")
            and trait_type.ast_decl
        ):
          target_ast = trait_type.ast_decl
      if not target_ast:
        struct_type = sym_table.lookup_type(node.struct_name)
        if (
            struct_type
            and hasattr(struct_type, "ast_decl")
            and struct_type.ast_decl
        ):
          target_ast = struct_type.ast_decl

    elif isinstance(
        node,
        (
            FuncDeclNode,
            VarDeclNode,
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

    # Extract positioning from target AST node
    target_decl = getattr(target_ast, "func_decl", target_ast)
    name_line = getattr(target_decl, "name_line", None)
    name_col = getattr(target_decl, "name_column", None)
    name_len = getattr(target_decl, "name_length", None)

    if name_line is not None and name_col is not None and name_len is not None:
      start_pos = Position(line=name_line - 1, character=name_col)
      end_pos = Position(line=name_line - 1, character=name_col + name_len)
    elif getattr(target_ast, "start_line", None) is not None:
      s_line = target_ast.start_line - 1
      s_col = target_ast.start_column or 0
      e_line = (target_ast.end_line - 1) if target_ast.end_line else s_line
      e_col = (
          target_ast.end_column
          if target_ast.end_column is not None
          else s_col + 1
      )
      start_pos = Position(line=s_line, character=s_col)
      end_pos = Position(line=e_line, character=e_col)
    else:  # pragma: no cover
      return None

    target_uri = getattr(target_ast, "file_uri", None)
    if not target_uri and hasattr(target_decl, "name"):
      target_name = target_decl.name
      for c_uri, c_ast in ls.ast_cache.items():

        def _search_ast(ast_node):
          for c_decl in getattr(ast_node, "declarations", []):
            if (
                c_decl is target_decl
                or getattr(c_decl, "name", None) == target_name
            ):  # pragma: no cover
              return c_decl
            if isinstance(c_decl, TraitDeclNode):
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
            elif isinstance(c_decl, EnumDeclNode):
              for m in getattr(c_decl, "members", []):
                if m is target_decl or getattr(m, "name", None) == target_name:
                  return m
          return None

        matched_node = _search_ast(c_ast)
        if matched_node:
          target_uri = getattr(c_ast, "file_uri", c_uri)
          matched_decl = getattr(matched_node, "func_decl", matched_node)
          n_line = getattr(matched_decl, "name_line", None)
          n_col = getattr(matched_decl, "name_column", None)
          n_len = getattr(matched_decl, "name_length", None)
          if n_line is not None and n_col is not None and n_len is not None:
            start_pos = Position(line=n_line - 1, character=n_col)
            end_pos = Position(line=n_line - 1, character=n_col + n_len)
          elif (
              getattr(matched_node, "start_line", None) is not None
          ):  # pragma: no cover
            s_line = matched_node.start_line - 1
            s_col = matched_node.start_column or 0
            e_line = (
                (matched_node.end_line - 1)
                if matched_node.end_line
                else s_line
            )
            e_col = (
                matched_node.end_column
                if matched_node.end_column is not None
                else s_col + 1
            )
            start_pos = Position(line=s_line, character=s_col)
            end_pos = Position(line=e_line, character=e_col)
          break

    if not target_uri:
      target_uri = uri

    return Location(uri=target_uri, range=Range(start=start_pos, end=end_pos))
