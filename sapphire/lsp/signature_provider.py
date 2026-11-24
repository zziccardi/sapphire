"""LSP signature help provider for Sapphire."""

import re
from typing import Any

from lsprotocol.types import (
  MarkupContent,
  MarkupKind,
  ParameterInformation,
  SignatureHelp,
  SignatureHelpParams,
  SignatureInformation,
)

from sapphire.lsp.completion_provider import _find_enclosing_impl_struct
from sapphire.lsp.definition_provider import find_local_decl as _find_local_decl
from sapphire.lsp.semantic_tokens import utf16_to_codepoint
from sapphire.semantics.symbol_table import (
  FunctionSymbol,
  FunctionType,
  ModuleSymbol,
  StructSymbol,
)


def _strip_trailing_type_args(text: str) -> str:
  """Strips balanced trailing generic type arguments `<...>` from a callee."""
  s = text.rstrip()
  if not s.endswith(">"):
    return s
  depth = 0
  for idx in range(len(s) - 1, -1, -1):
    ch = s[idx]
    if ch == ">":
      depth += 1
    elif ch == "<":
      depth -= 1
      if depth == 0:
        return s[:idx].rstrip()
  return s


def _struct_constructor_signature(st: Any) -> FunctionType | None:
  """Builds a constructor FunctionType from `__init__` if defined, else struct
  fields.
  """
  methods = getattr(st, "methods", None) or {}
  if "__init__" in methods:
    init_method = methods["__init__"]
    m_type = getattr(init_method, "method_type", init_method)
    if isinstance(m_type, FunctionType):
      param_names = list(m_type.param_names)
      param_types = list(m_type.param_types)
      param_mutabilities = list(getattr(m_type, "param_mutabilities", []))
      param_defaults = list(getattr(m_type, "param_defaults", []))
      if param_names and param_names[0] == "self":
        param_names = param_names[1:]
        param_types = param_types[1:]
        if param_mutabilities:
          param_mutabilities = param_mutabilities[1:]
        if param_defaults:
          param_defaults = param_defaults[1:]
      ctor_sig = FunctionType(
        param_types,
        st,
        param_mutabilities=param_mutabilities,
        param_names=param_names,
        num_defaults=getattr(m_type, "num_defaults", 0),
        param_defaults=param_defaults,
        ast_decl=getattr(m_type, "ast_decl", None),
      )
      ctor_sig.comments = getattr(m_type, "comments", "") or getattr(
        st, "comments", ""
      )
      return ctor_sig

  if hasattr(st, "fields"):
    param_names = list(getattr(st, "fields", {}).keys())
    param_types = [
      f_obj.field_type for f_obj in getattr(st, "fields", {}).values()
    ]
    ctor_sig = FunctionType(param_types, st, param_names=param_names)
    ctor_sig.comments = getattr(st, "comments", "")
    return ctor_sig
  return None


class SignatureProvider:
  """Resolves active call signatures and parameter hints for Sapphire code."""

  @staticmethod
  def _parse_active_call(text_before_cursor: str) -> tuple[str, int] | None:
    """Scans forward to cursor to find active `(callee_name, active_param_idx)`.
    """
    stack: list = []  # Each entry: [open_char, index, comma_count]
    matching = {")": "(", "]": "[", "}": "{"}
    n = len(text_before_cursor)
    i = 0
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False

    while i < n:
      ch = text_before_cursor[i]
      nxt = text_before_cursor[i + 1] if i + 1 < n else ""

      if in_line_comment:
        if ch == "\n":
          in_line_comment = False
        i += 1
        continue
      if in_block_comment:
        if ch == "*" and nxt == "/":
          in_block_comment = False
          i += 2
          continue
        i += 1
        continue
      if in_string is not None:
        if ch == "\\" and i + 1 < n:
          i += 2
          continue
        if ch == in_string:
          in_string = None
        i += 1
        continue

      if ch == "/" and nxt == "/":
        in_line_comment = True
        i += 2
        continue
      if ch == "/" and nxt == "*":
        in_block_comment = True
        i += 2
        continue
      if ch in ('"', "'"):
        in_string = ch
        i += 1
        continue

      if ch in ("(", "[", "{"):
        stack.append([ch, i, 0])
      elif ch in (")", "]", "}"):
        expected = matching[ch]
        if stack and stack[-1][0] == expected:
          stack.pop()
      elif ch == "," and stack and stack[-1][0] == "(":
        stack[-1][2] += 1
      i += 1

    call_entry = None
    for entry in reversed(stack):
      if entry[0] == "(":
        call_entry = entry
        break
    if call_entry is None:
      return None

    call_end_index = call_entry[1]
    commas = call_entry[2]

    callee_text = _strip_trailing_type_args(text_before_cursor[:call_end_index])
    match = re.search(
      r"([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\.\s*[a-zA-Z_][a-zA-Z0-9_]*)*)$",
      callee_text,
    )
    if not match:
      return None
    callee_name = re.sub(r"\s*\.\s*", ".", match.group(1))
    return callee_name, commas

  @staticmethod
  def _resolve_module_export_callable(
    mod_sym: Any, member_name: str
  ) -> FunctionType | None:
    """Resolves a callable function or struct constructor exported from a
    module.
    """
    exp = mod_sym.lookup_export(member_name)
    if exp is None:
      return None
    if isinstance(exp, FunctionSymbol):
      return exp.symbol_type
    if isinstance(exp, FunctionType):
      return exp
    if isinstance(exp, StructSymbol):
      return _struct_constructor_signature(exp.symbol_type)
    if hasattr(exp, "fields") or hasattr(exp, "methods"):
      return _struct_constructor_signature(exp)
    sym_t = getattr(exp, "symbol_type", None)
    if isinstance(sym_t, FunctionType):
      return sym_t
    return None

  @classmethod
  def _resolve_member_callee(
    cls,
    ls: Any,
    uri: str,
    callee_name: str,
    line: int,
    sym_table: Any,
    node_types: dict,
  ) -> tuple[FunctionType | None, str]:
    """Resolves a dotted `obj.method` or `mod.func` call to its FunctionType and
    display name.
    """
    parts = callee_name.split(".")
    obj_name = parts[-2]
    method_name = parts[-1]
    ast = ls.ast_cache.get(uri)

    # Check imported module exports first (`math.sqrt(`, `mod.Struct(`).
    mod_sym = sym_table.lookup(obj_name)
    if (
      isinstance(mod_sym, ModuleSymbol)
      or type(mod_sym).__name__ == "ModuleSymbol"
    ):
      func_type = cls._resolve_module_export_callable(mod_sym, method_name)
      return func_type, method_name

    receiver_type = None
    if obj_name == "self":
      receiver_type = _find_enclosing_impl_struct(ast, sym_table, line)

    if receiver_type is None and ast is not None:
      decl_node = _find_local_decl(ast, obj_name, line)
      if decl_node is not None:
        binding_types = getattr(decl_node, "binding_types", None)
        if isinstance(binding_types, dict) and obj_name in binding_types:
          receiver_type = binding_types[obj_name]
        else:
          receiver_type = node_types.get(decl_node)

    if receiver_type is None and node_types:
      min_dist = float("inf")
      for node in node_types.keys():
        binding_types = getattr(node, "binding_types", None)
        if isinstance(binding_types, dict) and obj_name in binding_types:
          s_line = getattr(node, "start_line", getattr(node, "name_line", None))
          dist = abs(s_line - line) if s_line else 0
          if dist < min_dist:
            min_dist = dist
            receiver_type = binding_types[obj_name]
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
        if n_name == obj_name:
          s_line = getattr(node, "start_line", getattr(node, "name_line", None))
          dist = abs(s_line - line) if s_line else 0
          if dist < min_dist:
            min_dist = dist
            receiver_type = node_types.get(node)

    if not receiver_type:
      sym = sym_table.lookup(obj_name)
      if sym:
        receiver_type = getattr(sym, "symbol_type", None)
    if not receiver_type:  # pragma: no cover
      receiver_type = sym_table.lookup_type(obj_name)

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
      hasattr(receiver_type, "methods") and method_name in receiver_type.methods
    ):
      method_obj = receiver_type.methods[method_name]
      func_type = getattr(method_obj, "method_type", method_obj)
    elif (
      type(receiver_type).__name__ in ("StringType", "PrimitiveType")
      and getattr(receiver_type, "name", "") == "String"
    ):
      from sapphire.semantics.symbol_table import STRING_METHODS

      func_type = STRING_METHODS.get(method_name)

    return func_type, method_name

  @staticmethod
  def _resolve_direct_callee(
    callee_name: str, sym_table: Any
  ) -> FunctionType | None:
    """Resolves a direct function call or struct constructor signature."""
    sym = sym_table.lookup(callee_name)
    if sym:
      if isinstance(sym, FunctionSymbol):
        return sym.symbol_type
      if isinstance(sym, StructSymbol):
        return _struct_constructor_signature(sym.symbol_type)
      return None

    st = sym_table.lookup_type(callee_name)
    if st and (hasattr(st, "fields") or hasattr(st, "methods")):
      return _struct_constructor_signature(st)
    return None

  @classmethod
  def provide_signature_help(
    cls, ls: Any, params: SignatureHelpParams
  ) -> SignatureHelp | None:
    """Computes SignatureHelp for the call expression at the cursor."""
    uri = params.text_document.uri
    if uri not in ls.symbol_table_cache:  # pragma: no cover
      return None

    sym_table = ls.symbol_table_cache[uri]
    node_types = ls.node_types_cache.get(uri, {})
    line = params.position.line + 1
    col = params.position.character

    text_before_cursor = ""
    try:
      doc = ls.workspace.get_text_document(uri)
      source = getattr(doc, "source", None)
      if isinstance(source, str):
        lines = source.splitlines()
        if 0 <= line - 1 < len(lines):
          cp_col = utf16_to_codepoint(lines[line - 1], col)
          prefix_lines = lines[: line - 1]
          prefix_lines.append(lines[line - 1][:cp_col])
          text_before_cursor = "\n".join(prefix_lines)
        elif line - 1 >= len(lines):
          text_before_cursor = source
    except Exception:  # pragma: no cover
      pass

    parsed = cls._parse_active_call(text_before_cursor)
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

    sig_label = (
      f"{fn_display_name}({', '.join(param_strs)}) -> {func_type.return_type}"
    )
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
