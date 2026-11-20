"""LSP signature help provider for Sapphire."""

import re
from typing import Any, Optional, Tuple

from lsprotocol.types import (
    MarkupContent,
    MarkupKind,
    ParameterInformation,
    SignatureHelp,
    SignatureHelpParams,
    SignatureInformation,
)

from src.lsp.definition_provider import find_local_decl as _find_local_decl
from src.semantics.symbol_table import FunctionSymbol, FunctionType, StructSymbol


class SignatureProvider:
  """Resolves active call signatures and parameter hints for Sapphire code."""

  @staticmethod
  def _parse_active_call(text_before_cursor: str) -> Optional[Tuple[str, int]]:
    """Walks backward from cursor to find `(callee_name, active_param_idx)`."""
    depth = 0
    commas = 0
    i = len(text_before_cursor) - 1
    in_string = False
    string_char = None
    call_end_index = -1

    while i >= 0:
      ch = text_before_cursor[i]
      if in_string:
        if ch == string_char and (i == 0 or text_before_cursor[i - 1] != "\\"):
          in_string = False
      elif ch in ('"', "'"):
        in_string = True
        string_char = ch
      elif ch in (")", "]", "}"):
        depth += 1
      elif ch in ("(", "[", "{"):
        if ch == "(":
          if depth == 0:
            call_end_index = i
            break
          depth -= 1  # pragma: no cover
        elif depth > 0:
          depth -= 1
      elif ch == "," and depth == 0:
        commas += 1
      i -= 1

    if call_end_index == -1:
      return None

    callee_text = text_before_cursor[:call_end_index].rstrip()
    match = re.search(r"([a-zA-Z_][a-zA-Z0-9_\.]*)$", callee_text)
    if not match:
      return None
    return match.group(1), commas

  @staticmethod
  def _resolve_member_callee(
      ls: Any,
      uri: str,
      callee_name: str,
      line: int,
      sym_table: Any,
      node_types: dict,
  ) -> Tuple[Optional[FunctionType], str]:
    """Resolves a dotted `obj.method` call to its FunctionType and display name."""
    parts = callee_name.split(".")
    obj_name = parts[-2]
    method_name = parts[-1]

    receiver_type = None
    if node_types:
      best_node = None
      min_dist = float("inf")
      for node in node_types.keys():
        n_name = (
            getattr(node, "name", None)
            or getattr(node, "member", None)
            or getattr(node, "alias", None)
            or getattr(node, "let_name", None)
            or getattr(node, "key_var", None)
            or getattr(node, "val_var", None)
            or getattr(node, "loop_var", None)
        )
        if n_name == obj_name:
          s_line = getattr(node, "start_line", getattr(node, "name_line", None))
          dist = abs(s_line - line) if s_line else 0
          if dist < min_dist:
            min_dist = dist
            best_node = node
      if best_node:
        receiver_type = node_types.get(best_node)

    if not receiver_type:
      sym = sym_table.lookup(obj_name)
      if sym:
        receiver_type = getattr(sym, "symbol_type", None)
    if not receiver_type:  # pragma: no cover
      receiver_type = sym_table.lookup_type(obj_name)
    if not receiver_type and uri in ls.ast_cache:  # pragma: no cover
      decl_node = _find_local_decl(ls.ast_cache[uri], obj_name, line)
      if decl_node:
        receiver_type = node_types.get(decl_node)

    if not receiver_type:
      return None, method_name

    if type(receiver_type).__name__ == "OptionalType":
      receiver_type = getattr(receiver_type, "base_type", receiver_type)
    if type(receiver_type).__name__ in ("SharedRefType", "RefType") and not (
        type(receiver_type).__name__ == "SharedRefType"
        and method_name in ("share", "downgrade")
    ):
      receiver_type = getattr(receiver_type, "inner_type", receiver_type)

    func_type = None
    if hasattr(receiver_type, "get_method"):
      method_obj = receiver_type.get_method(method_name, sym_table)
      if method_obj:
        func_type = getattr(method_obj, "method_type", None)
    elif (
        hasattr(receiver_type, "methods")
        and method_name in receiver_type.methods
    ):
      method_obj = receiver_type.methods[method_name]
      func_type = getattr(method_obj, "method_type", method_obj)
    elif (
        type(receiver_type).__name__ in ("StringType", "PrimitiveType")
        and getattr(receiver_type, "name", "") == "String"
    ):
      from src.semantics.symbol_table import STRING_METHODS

      func_type = STRING_METHODS.get(method_name)

    return func_type, method_name

  @staticmethod
  def _resolve_direct_callee(
      callee_name: str, sym_table: Any
  ) -> Optional[FunctionType]:
    """Resolves a direct function call or struct initializer signature."""
    sym = sym_table.lookup(callee_name)
    if sym:
      if isinstance(sym, FunctionSymbol):
        return sym.symbol_type
      if isinstance(sym, StructSymbol):
        st = sym.symbol_type
        param_names = list(getattr(st, "fields", {}).keys())
        param_types = [
            f_obj.field_type for f_obj in getattr(st, "fields", {}).values()
        ]
        return FunctionType(param_types, st, param_names=param_names)
      return None

    st = sym_table.lookup_type(callee_name)
    if st and hasattr(st, "fields"):
      param_names = list(getattr(st, "fields", {}).keys())
      param_types = [
          f_obj.field_type for f_obj in getattr(st, "fields", {}).values()
      ]
      return FunctionType(param_types, st, param_names=param_names)
    return None

  @classmethod
  def provide_signature_help(
      cls, ls: Any, params: SignatureHelpParams
  ) -> Optional[SignatureHelp]:
    """Computes SignatureHelp for the call expression at the cursor."""
    uri = params.text_document.uri
    if uri not in ls.symbol_table_cache:  # pragma: no cover
      return None

    sym_table = ls.symbol_table_cache[uri]
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
    except Exception:  # pragma: no cover
      pass

    parsed = cls._parse_active_call(line_text[:col])
    if not parsed:
      return None
    callee_name, active_param_idx = parsed

    if "." in callee_name:
      func_type, fn_display_name = cls._resolve_member_callee(
          ls, uri, callee_name, line, sym_table, node_types
      )
    else:
      func_type = cls._resolve_direct_callee(callee_name, sym_table)
      fn_display_name = callee_name

    if not func_type or not isinstance(func_type, FunctionType):
      return None

    param_names = list(func_type.param_names)
    param_types = list(func_type.param_types)
    param_mutabilities = list(getattr(func_type, "param_mutabilities", []))

    if (
        func_type.has_self
        and param_names
        and param_names[0] == "self"
        and "." in callee_name
    ):
      param_names = param_names[1:]
      param_types = param_types[1:]
      if param_mutabilities:
        param_mutabilities = param_mutabilities[1:]

    param_infos = []
    param_strs = []
    for idx, p_name in enumerate(param_names):
      p_type = param_types[idx] if idx < len(param_types) else "Any"
      is_mut = (
          param_mutabilities[idx] if idx < len(param_mutabilities) else False
      )
      mut_str = "var " if is_mut else ""
      p_label = f"{mut_str}{p_name}: {p_type}"
      param_strs.append(p_label)
      param_infos.append(ParameterInformation(label=p_label))

    sig_label = f"{fn_display_name}({', '.join(param_strs)}) -> {func_type.return_type}"
    doc_comments = getattr(func_type, "comments", "")
    doc_content = (
        MarkupContent(kind=MarkupKind.Markdown, value=doc_comments)
        if doc_comments
        else None
    )

    sig_info = SignatureInformation(
        label=sig_label,
        documentation=doc_content,
        parameters=param_infos,
        active_parameter=(
            active_param_idx
            if active_param_idx < len(param_infos)
            else (len(param_infos) - 1 if param_infos else 0)
        ),
    )

    return SignatureHelp(
        signatures=[sig_info],
        active_signature=0,
        active_parameter=active_param_idx,
    )
