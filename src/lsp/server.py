"""LSP server implementation for the Sapphire programming language.

This server provides diagnostics (syntax and semantic errors) and semantic tokens for
accurate syntax highlighting in Visual Studio Code.
"""

import sys
import os
from typing import Optional

# Add parent directories to Python path to allow imports from parser and semantics
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

from antlr4 import InputStream, CommonTokenStream
from antlr4.error.ErrorListener import ErrorListener
from lsprotocol.types import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokensParams,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    Hover,
    HoverParams,
    CompletionList,
    CompletionItem,
    CompletionParams,
    CompletionOptions,
    DefinitionParams,
    Location,
    SignatureHelp,
    SignatureHelpOptions,
    SignatureHelpParams,
    SignatureInformation,
    ParameterInformation,
    MarkupContent,
    MarkupKind,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_SIGNATURE_HELP,
    PublishDiagnosticsParams,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
)
from pygls.lsp.server import LanguageServer

# Imports from compiler codebase
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.lsp.semantic_tokens import (
    SemanticTokensTypeChecker,
    encode_semantic_tokens,
    TOKEN_TYPES,
    TOKEN_MODIFIERS,
    find_node_at_position,
)



class SapphireLanguageServer(LanguageServer):
  """Language Server instance for Sapphire."""

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # Cache of delta-encoded semantic tokens: uri -> list of integers
    self.tokens_cache = {}
    self.ast_cache = {}
    self.node_types_cache = {}
    self.symbol_table_cache = {}


server = SapphireLanguageServer("sapphire-lsp", "v0.1.0")


class ANTLRDiagnosticListener(ErrorListener):
  """Listener to translate ANTLR parser/lexer errors to LSP Diagnostics."""

  def __init__(self):
    super().__init__()
    self.diagnostics = []

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    length = 1
    if (offendingSymbol and hasattr(offendingSymbol, "text") and
        offendingSymbol.text):
      length = len(offendingSymbol.text)

    from src.code_gen.transpiler import format_syntax_error_message


    custom_msg = format_syntax_error_message(recognizer, offendingSymbol, msg)

    # LSP Diagnostic structure
    diag = Diagnostic(
        range=Range(
            start=Position(line=line - 1, character=column),
            end=Position(line=line - 1, character=column + length),
        ),
        message=f"Syntax Error: {custom_msg}",
        severity=DiagnosticSeverity.Error,
        source="sapphire-parser",
    )
    self.diagnostics.append(diag)


def _resolve_module_path(doc_uri: str, mod_path: str, workspace_root: Optional[str] = None) -> Optional[str]:
  """Resolves a dot-separated Sapphire import path (e.g. 'lib.love2d.enums') to an absolute file path on disk."""
  from pygls.uris import to_fs_path

  doc_path = to_fs_path(doc_uri) if doc_uri.startswith("file://") else doc_uri
  doc_dir = os.path.dirname(doc_path) if doc_path else ""

  rel_parts = mod_path.split(".")
  candidates = [
      os.path.join(*rel_parts) + ".sp",
      os.path.join(*rel_parts, "mod.sp"),
      os.path.join(*rel_parts, "index.sp"),
  ]

  search_dirs = [doc_dir]
  if workspace_root:
    ws_path = to_fs_path(workspace_root) if workspace_root.startswith("file://") else workspace_root
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


def _preload_module_dependencies(ls: SapphireLanguageServer, doc_uri: str, ast: Any, ws_root: Optional[str] = None) -> None:
  from src.parser.ast import ASTNode
  from pygls.uris import from_fs_path
  for s_decl in getattr(ast, "imports", []):
    if getattr(s_decl, "path", None):
      mod_path_fs = _resolve_module_path(doc_uri, s_decl.path, ws_root)
      if mod_path_fs and os.path.isfile(mod_path_fs):
        mod_uri = from_fs_path(os.path.abspath(mod_path_fs))
        s_decl.target_file_uri = mod_uri
        if mod_uri not in ls.ast_cache:
          try:
            with open(mod_path_fs, "r", encoding="utf-8") as f:
              sub_code = f.read()
            sub_stream = InputStream(sub_code)
            sub_lexer = SapphireLexer(sub_stream)
            sub_lexer.removeErrorListeners()
            sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
            sub_parser.removeErrorListeners()
            sub_tree = sub_parser.program()
            sub_ast = ASTBuilder().visit(sub_tree)
            if sub_ast:
              def _mark_file_uri(node):
                if isinstance(node, ASTNode):
                  node.file_uri = mod_uri
                  for v in node.__dict__.values():
                    if isinstance(v, list):
                      for item in v:
                        if isinstance(item, ASTNode):
                          _mark_file_uri(item)
                    elif isinstance(v, ASTNode):
                      _mark_file_uri(v)
              _mark_file_uri(sub_ast)
              sub_checker = SemanticTokensTypeChecker(sub_code, source_file_path=mod_path_fs)
              try:
                sub_checker.check(sub_ast)
              except Exception:
                pass
              ls.ast_cache[mod_uri] = sub_ast
              ls.symbol_table_cache[mod_uri] = sub_checker.symbol_table
              ls.node_types_cache[mod_uri] = sub_checker.node_types
              _preload_module_dependencies(ls, mod_uri, sub_ast, ws_root)
          except Exception:  # pragma: no cover
            pass


def validate_source(ls: SapphireLanguageServer, doc_uri: str,
                    doc_text: str) -> None:
  """Run lexical, syntactic, and semantic validation on the source text."""
  input_stream = InputStream(doc_text)
  listener = ANTLRDiagnosticListener()

  # 1. Lexical validation
  lexer = SapphireLexer(input_stream)
  lexer.removeErrorListeners()
  lexer.addErrorListener(listener)
  token_stream = CommonTokenStream(lexer)

  # 2. Syntax validation
  parser = SapphireParser(token_stream)
  parser.removeErrorListeners()
  parser.addErrorListener(listener)
  tree = parser.program()

  ast = None
  ast_error = None
  from pygls.uris import to_fs_path
  doc_fs_path = to_fs_path(doc_uri) if doc_uri.startswith("file://") else doc_uri
  checker = SemanticTokensTypeChecker(doc_text, source_file_path=doc_fs_path)
  try:
    builder = ASTBuilder()
    ast = builder.visit(tree)
    if ast:
      ast.file_uri = doc_uri
      for s_decl in getattr(ast, "declarations", []):
        s_decl.file_uri = doc_uri
      checker.check(ast)
  except Exception as e:  # pragma: no cover
    ast_error = str(e)

  if ast:
    encoded = encode_semantic_tokens(checker.raw_tokens)
    ls.tokens_cache[doc_uri] = encoded
    ls.ast_cache[doc_uri] = ast
    ls.node_types_cache[doc_uri] = checker.node_types
    ls.symbol_table_cache[doc_uri] = checker.symbol_table

    # Process imports and pre-load dependency ASTs for definition navigation
    ws_root = getattr(getattr(ls, "workspace", None), "root_uri", None)
    _preload_module_dependencies(ls, doc_uri, ast, ws_root)

  # If syntax errors are present, report them immediately
  if listener.diagnostics:
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=doc_uri, diagnostics=listener.diagnostics)
    )
    return

  if ast_error and not ast:
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(
            uri=doc_uri,
            diagnostics=[
                Diagnostic(
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=1),
                    ),
                    message=f"Internal AST generation failure: {ast_error}",
                    severity=DiagnosticSeverity.Error,
                    source="sapphire-compiler",
                )
            ],
        )
    )
    return

  # Map custom diagnostics back to LSP Diagnostic types
  diagnostics = []
  for err in checker.lsp_errors:
    start_pos = Position(
        line=err["range"]["start"]["line"],
        character=err["range"]["start"]["character"],
    )
    end_pos = Position(
        line=err["range"]["end"]["line"],
        character=err["range"]["end"]["character"],
    )
    diagnostics.append(
        Diagnostic(
            range=Range(start=start_pos, end=end_pos),
            message=err["message"],
            severity=DiagnosticSeverity.Error,
            source="sapphire-semantics",
        )
    )

  ls.text_document_publish_diagnostics(
      PublishDiagnosticsParams(uri=doc_uri, diagnostics=diagnostics)
  )


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: SapphireLanguageServer, params):
  """Triggered when a document is opened in the editor."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  validate_source(ls, doc.uri, doc.source)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: SapphireLanguageServer, params):
  """Triggered when a document is modified."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  validate_source(ls, doc.uri, doc.source)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: SapphireLanguageServer, params):
  """Triggered when a document is saved."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  validate_source(ls, doc.uri, doc.source)


@server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
def did_change_watched_files(ls: SapphireLanguageServer, params):
  """No-op handler to silent log warnings from workspace/didChangeWatchedFiles."""
  pass


@server.feature(
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    SemanticTokensLegend(token_types=TOKEN_TYPES,
                         token_modifiers=TOKEN_MODIFIERS))
def semantic_tokens_full(ls: SapphireLanguageServer,
                         params: SemanticTokensParams) -> SemanticTokens:
  """Returns the cached semantic tokens for the document."""
  uri = params.text_document.uri
  # Re-validate if document is not in cache (e.g. freshly opened or not
  # validated yet)
  if uri not in ls.tokens_cache:
    doc = ls.workspace.get_text_document(uri)
    validate_source(ls, uri, doc.source)

  tokens_data = ls.tokens_cache.get(uri, [])
  return SemanticTokens(data=tokens_data)


def _format_ast_expr(expr: Any) -> str:
  if expr is None:
    return ""
  from src.parser.ast import (
      LiteralNode,
      IdentifierNode,
      MemberAccessNode,
      UnaryOpNode,
      BinaryOpNode,
      CallNode,
      BasicTypeNode,
  )
  if isinstance(expr, LiteralNode):
    if expr.lit_type == "string":
      return f'"{expr.value}"'
    elif expr.lit_type == "bool":
      return "true" if expr.value is True or str(expr.value).lower() == "true" else "false"
    elif expr.lit_type == "none":
      return "none"
    return str(expr.value)
  elif isinstance(expr, IdentifierNode):
    return expr.name
  elif isinstance(expr, MemberAccessNode):
    rec = _format_ast_expr(expr.receiver)
    opt = "?." if getattr(expr, "is_optional", False) else "."
    return f"{rec}{opt}{expr.member}"
  elif isinstance(expr, UnaryOpNode):
    return f"{expr.op}{_format_ast_expr(expr.expr)}"
  elif isinstance(expr, BinaryOpNode):
    return f"{_format_ast_expr(expr.left)} {expr.op} {_format_ast_expr(expr.right)}"
  elif isinstance(expr, CallNode):
    callee_str = _format_ast_expr(expr.callee)
    args_str = ", ".join(
        f"{arg.name} = {_format_ast_expr(arg.expr)}" if getattr(arg, "name", None) else _format_ast_expr(arg.expr)
        for arg in getattr(expr, "arguments", [])
    )
    return f"{callee_str}({args_str})"
  elif isinstance(expr, BasicTypeNode):
    return expr.name
  return str(getattr(expr, "value", str(expr)))


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: SapphireLanguageServer, params: HoverParams) -> Optional[Hover]:
  """Triggered when user hovers over an identifier."""
  uri = params.text_document.uri
  if uri not in ls.ast_cache or uri not in ls.node_types_cache:
    return None

  ast = ls.ast_cache[uri]
  node_types = ls.node_types_cache[uri]

  # LSP is 0-based, parser/type checker is 1-based
  line = params.position.line + 1
  col = params.position.character

  node = find_node_at_position(ast, line, col)
  if not node:
    return None

  node_type = None
  from src.parser.ast import CallNode, IdentifierNode, StructDeclNode, TraitDeclNode, ImplBlockNode, BasicTypeNode, EnumDeclNode, EnumMemberNode, HeaderBindingNode, MemberAccessNode, FuncDeclNode
  if isinstance(node, CallNode) and isinstance(node.callee, IdentifierNode) and uri in ls.symbol_table_cache:  # pragma: no cover
    c_sym = ls.symbol_table_cache[uri].lookup(node.callee.name)
    if c_sym and hasattr(c_sym, "symbol_type"):
      node = node.callee
      node_type = c_sym.symbol_type
  elif isinstance(node, CallNode) and isinstance(node.callee, MemberAccessNode) and uri in ls.symbol_table_cache:  # pragma: no cover
    rec_type = node_types.get(node.callee.receiver)
    if rec_type and hasattr(rec_type, "methods") and node.callee.member in rec_type.methods:
      node = node.callee
      node_type = rec_type.methods[node.member]

  if not node_type:
    node_type = node_types.get(node)
  if not node_type:
    if isinstance(node, IdentifierNode) and uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)
    elif isinstance(node, StructDeclNode) and uri in ls.symbol_table_cache:
      node_type = ls.symbol_table_cache[uri].lookup_type(node.name)
    elif isinstance(node, EnumDeclNode) and uri in ls.symbol_table_cache:
      node_type = ls.symbol_table_cache[uri].lookup_type(node.name)
    elif isinstance(node, TraitDeclNode) and uri in ls.symbol_table_cache:
      node_type = ls.symbol_table_cache[uri].lookup_type(node.name)
    elif isinstance(node, FuncDeclNode) and uri in ls.symbol_table_cache:  # pragma: no cover
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)
    elif isinstance(node, ImplBlockNode) and uri in ls.symbol_table_cache:
      s_line = getattr(node, "struct_name_line", None)
      s_col = getattr(node, "struct_name_column", None)
      s_len = getattr(node, "struct_name_length", None)
      t_line = getattr(node, "trait_name_line", None)
      t_col = getattr(node, "trait_name_column", None)
      t_len = getattr(node, "trait_name_length", None)
      if node.trait_name and t_line is not None and t_col is not None and t_len is not None and t_line == line and t_col <= col < t_col + t_len:
        node_type = ls.symbol_table_cache[uri].lookup_type(node.trait_name)
      elif s_line is None or (s_col is not None and s_len is not None and s_line == line and s_col <= col < s_col + s_len):
        node_type = ls.symbol_table_cache[uri].lookup_type(node.struct_name)

  if not node_type and type(node).__name__ != "AnnotationNode":
    return None

  from src.parser.ast import (

      IdentifierNode,
      MemberAccessNode,
      FuncDeclNode,
      VarDeclNode,
      ParameterNode,
      StructFieldNode,
      IfNode,
      ForNode,
      StructDeclNode,
      EnumDeclNode,
      EnumMemberNode,
      TraitDeclNode,
      ImplBlockNode,
      BasicTypeNode,
      TraitMemberNode,
      HeaderBindingNode,
  )

  node_name = ""
  category = "symbol"

  if isinstance(node, IdentifierNode):
    node_name = node.name
    if uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        from src.semantics.symbol_table import (
            VariableSymbol,
            FunctionSymbol,
            StructSymbol,
            TraitSymbol,
            EnumSymbol,
        )

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
    if node.trait_name and t_line is not None and t_col is not None and t_len is not None and t_line == line and t_col <= col < t_col + t_len:
      node_name = node.trait_name
      category = "trait"
    elif s_line is None or (s_col is not None and s_len is not None and s_line == line and s_col <= col < s_col + s_len):
      node_name = node.struct_name
      st = ls.symbol_table_cache[uri].lookup_type(node.struct_name)
      category = "proto" if getattr(st, "is_prototype", False) else "struct"

  elif isinstance(node, ParameterNode):
    category = "parameter"
    node_name = node.name
  elif isinstance(node, StructFieldNode):
    category = "property"
    node_name = node.name
  elif isinstance(node, TraitMemberNode):
    category = "method"
    node_name = node.name
  elif isinstance(node, VarDeclNode):
    is_extern = any(a.name == "extern" for a in getattr(node, "annotations", []))
    category = "extern variable" if is_extern else "variable"
    node_name = node.name
  elif isinstance(node, FuncDeclNode):
    is_export = any(a.name == "export" for a in getattr(node, "annotations", []))
    category = "exported function" if is_export else "function"
    node_name = node.name
  elif type(node).__name__ == "AnnotationNode":
    category = "annotation"
    ann_arg = getattr(node, "arg", None)
    ann_name = getattr(node, "name", "")
    node_name = f"@{ann_name}" + (f'("{ann_arg}")' if ann_arg else "")
    if ann_name == "extern":
      markdown_text = (
          f"**({category})** `{node_name}`\n\n"
          f"Declares an external variable provided by the host runtime "
          f"environment.\n\n"
          f"If no argument is given, uses the Sapphire variable name as the "
          f"external name. Otherwise, uses the argument string as the external "
          f"name.")
    elif ann_name == "export":
      markdown_text = (
          f"**({category})** `{node_name}`\n\n"
          f"Exposes a function to the host runtime environment under the name "
          f"given as the argument.")
    else:
      markdown_text = f"**({category})** `{node_name}`"
    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_text))
  elif isinstance(node, HeaderBindingNode):
    category = "variable"
    node_name = node.let_name
  elif isinstance(node, ForNode):
    category = "variable"
    node_name = node.loop_var
  elif isinstance(node, BasicTypeNode):
    node_name = node.name

  if category == "symbol" and node_type:
    from src.semantics.symbol_table import StructType, TraitType, EnumType

    if isinstance(node_type, StructType):
      category = "proto" if node_type.is_prototype else "struct"
    elif isinstance(node_type, EnumType):
      category = "enum"
    elif isinstance(node_type, TraitType):
      category = "trait"

  from src.semantics.symbol_table import FunctionType, StructType, TraitType, EnumType


  if isinstance(node_type, FunctionType):
    params_lines = []
    ast_decl = getattr(node_type, "ast_decl", None)
    if not ast_decl and isinstance(node, (FuncDeclNode, TraitMemberNode)):
      ast_decl = node
    if not ast_decl and uri in ls.symbol_table_cache:
      target_sym = ls.symbol_table_cache[uri].lookup(node_name)
      if target_sym:
        ast_decl = getattr(target_sym, "ast_decl", None)

    ast_params = getattr(ast_decl, "parameters", None) if ast_decl else None
    from src.parser.ast import ASTNode
    p_defaults = getattr(node_type, "param_defaults", [])

    for idx, p_type in enumerate(node_type.param_types):
      p_name = (node_type.param_names[idx]
                if idx < len(node_type.param_names)
                else f"p{idx}")
      is_mut = (node_type.param_mutabilities[idx]
                if idx < len(node_type.param_mutabilities) else False)
      mut_str = "var " if is_mut else ""

      default_str = ""
      if ast_params and idx < len(ast_params):
        d_expr = getattr(ast_params[idx], "default_expr", None)
        if d_expr is not None:
          default_str = f" = {_format_ast_expr(d_expr)}"
      if not default_str and p_defaults and idx < len(p_defaults) and p_defaults[idx] is not None:  # pragma: no cover
        val = p_defaults[idx]
        default_str = f" = {_format_ast_expr(val) if hasattr(val, 'node_type') or isinstance(val, ASTNode) else str(val)}"

      if p_name == "self":  # pragma: no cover
        params_lines.append("- `self`")
      else:
        params_lines.append(f"- `{mut_str}{p_name}: {str(p_type)}{default_str}`")

    params_section = "\n".join(params_lines)
    markdown_text = f"**({category})** `{node_name}`\n"
    if params_lines:
      markdown_text += f"\nParameters:\n{params_section}\n"
    else:
      markdown_text += "\nParameters: none\n"
    markdown_text += f"\nReturns: `{str(node_type.return_type)}`"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
  elif isinstance(node_type, StructType) and category in ("struct", "proto"):
    kind = "proto" if node_type.is_prototype else "struct"
    inheritance = f" : {', '.join(node_type.parent_names)}" if getattr(node_type, "parent_names", None) else ""
    params_str = f"<{', '.join(node_type.type_params)}>" if getattr(node_type, "type_params", None) else ""
    markdown_text = f"**({kind})** `{node_type.name}{params_str}{inheritance}`"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
  elif isinstance(node_type, EnumType) and category == "enum":
    markdown_text = f"**(enum)** `{node_type.name}`"
    if node_type.variants:
      members_str = "\n".join(f"- `{k} = {v}`" for k, v in node_type.variants.items())
      markdown_text += f"\n\nMembers:\n{members_str}"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
  elif isinstance(node_type, TraitType) and category == "trait":
    params_str = f"<{', '.join(node_type.type_params)}>" if getattr(node_type, "type_params", None) else ""
    markdown_text = f"**(trait)** `{node_type.name}{params_str}`"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
  else:
    type_desc = str(node_type)
    markdown_text = (f"**({category})** `{node_name}`: `{type_desc}`"
                     if node_name else f"`{type_desc}`")

    # Extract property/field comments from parent struct definition:
    field_comments = ""
    declarations = getattr(ast, "declarations", [])
    if isinstance(node, StructFieldNode) and uri in ls.symbol_table_cache:
      parent_struct = None
      for child in declarations:
        if isinstance(child, StructDeclNode) and any(f is node for f in child.fields):
          parent_struct = child
          break
      if parent_struct:
        st = ls.symbol_table_cache[uri].lookup_type(parent_struct.name)
        if st and node.name in st.fields:
          field = st.fields[node.name]
          field_comments = getattr(field, "comments", "")
    elif isinstance(node, MemberAccessNode) and uri in ls.symbol_table_cache:
      receiver_type = node_types.get(node.receiver)
      if receiver_type:
        from src.semantics.symbol_table import StructType

        if isinstance(receiver_type, StructType) and node.member in receiver_type.fields:
          field = receiver_type.fields[node.member]
          field_comments = getattr(field, "comments", "")

    if field_comments:
      markdown_text += f"\n\n{field_comments}"

  return Hover(contents=MarkupContent(kind=MarkupKind.Markdown,
                                      value=markdown_text))


def _find_local_decl(ast, name: str, line: int):
  """Finds local variable or parameter declaration in AST containing line."""
  declarations = getattr(ast, "declarations", [])
  for decl in declarations:
    from src.parser.ast import FuncDeclNode, ImplBlockNode, VarDeclNode, IfNode, ForNode

    if isinstance(decl, FuncDeclNode):
      s_start = getattr(decl, "start_line", None)
      s_end = getattr(decl, "end_line", None)
      if s_start is not None and s_start <= line and (s_end is None or line <= s_end + 10):
        for p in decl.parameters:
          if p.name == name:
            return p
        stmts = getattr(decl.body, "statements", []) if hasattr(decl, "body") else []
        for stmt in stmts:
          st_start = getattr(stmt, "start_line", None)
          if isinstance(stmt, VarDeclNode):
            if st_start is None or st_start <= line:
              if getattr(stmt, "name", None) == name or name in getattr(stmt, "names", []):
                return stmt
          elif type(stmt).__name__ in ("IfNode", "WhileNode") and getattr(stmt, "init_binding", None):
            if st_start is None or st_start <= line:
              if stmt.init_binding.let_name == name:
                return stmt.init_binding
          elif isinstance(stmt, ForNode):
            if st_start is None or st_start <= line:
              if getattr(stmt, "key_var", None) == name or getattr(stmt, "val_var", None) == name or getattr(stmt, "loop_var", None) == name:
                return stmt
    elif isinstance(decl, ImplBlockNode):
      for member in decl.members:
        func_decl = getattr(member, "func_decl", None)
        if func_decl:
          f_start = getattr(func_decl, "start_line", None)
          f_end = getattr(func_decl, "end_line", None)
          if f_start is not None and f_start <= line and (f_end is None or line <= f_end + 10):
            for p in func_decl.parameters:
              if p.name == name:
                return p  # pragma: no cover
            stmts = getattr(func_decl.body, "statements", []) if hasattr(func_decl, "body") else []
            for stmt in stmts:
              st_start = getattr(stmt, "start_line", None)
              if isinstance(stmt, VarDeclNode):
                if st_start is None or st_start <= line:
                  if getattr(stmt, "name", None) == name or name in getattr(stmt, "names", []):
                    return stmt
              elif type(stmt).__name__ in ("IfNode", "WhileNode") and getattr(stmt, "init_binding", None):
                if st_start is None or st_start <= line:
                  if stmt.init_binding.let_name == name:
                    return stmt.init_binding
              elif isinstance(stmt, ForNode):
                if st_start is None or st_start <= line:
                  if getattr(stmt, "key_var", None) == name or getattr(stmt, "val_var", None) == name or getattr(stmt, "loop_var", None) == name:
                    return stmt
    elif isinstance(decl, VarDeclNode):
      if getattr(decl, "name", None) == name or name in getattr(decl, "names", []):
        return decl  # pragma: no cover
  return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: SapphireLanguageServer, params: DefinitionParams) -> Optional[Location]:
  """Triggered when user requests Go to Definition (F12 or Cmd+Click)."""
  uri = params.text_document.uri
  if uri not in ls.ast_cache or uri not in ls.symbol_table_cache:
    return None

  ast = ls.ast_cache[uri]
  sym_table = ls.symbol_table_cache[uri]
  node_types = ls.node_types_cache.get(uri, {})

  line = params.position.line + 1
  col = params.position.character

  node = find_node_at_position(ast, line, col)
  if not node:
    return None

  target_ast = None

  from src.parser.ast import (
      IdentifierNode,
      MemberAccessNode,
      BasicTypeNode,
      StructDeclNode,
      FuncDeclNode,
      VarDeclNode,
      ParameterNode,
      EnumDeclNode,
      EnumMemberNode,
      TraitDeclNode,
      StructFieldNode,
      ImplBlockNode,
      ImportStmtNode,
      CallNode,
  )

  if isinstance(node, CallNode):  # pragma: no cover
    node = node.callee

  if isinstance(node, ImportStmtNode):
    path_line = getattr(node, "path_line", getattr(node, "start_line", None))
    path_col = getattr(node, "path_column", getattr(node, "start_column", None))
    path_len = getattr(node, "path_length", getattr(node, "length", None))
    if path_line is not None and path_col is not None and path_len is not None:
      if path_line == line and path_col <= col < path_col + path_len:
        ws_root = getattr(getattr(ls, "workspace", None), "root_uri", None)
        target_fs = _resolve_module_path(uri, node.path, ws_root)
        if target_fs:
          from pygls.uris import from_fs_path
          target_uri = from_fs_path(os.path.abspath(target_fs))
          return Location(uri=target_uri, range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)))

  elif isinstance(node, IdentifierNode):
    sym = sym_table.lookup(node.name)
    if sym and type(sym).__name__ == "ModuleSymbol" and getattr(sym, "file_path", None):
      from pygls.uris import from_fs_path
      mod_uri = from_fs_path(os.path.abspath(sym.file_path))
      return Location(uri=mod_uri, range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)))

    if sym and hasattr(sym, "ast_decl") and sym.ast_decl:
      target_ast = sym.ast_decl
    elif sym and hasattr(sym, "symbol_type") and hasattr(sym.symbol_type, "ast_decl") and sym.symbol_type.ast_decl:
      target_ast = sym.symbol_type.ast_decl
    else:
      type_obj = sym_table.lookup_type(node.name)
      if type_obj and hasattr(type_obj, "ast_decl") and type_obj.ast_decl:  # pragma: no cover
        target_ast = type_obj.ast_decl

    if not target_ast:
      target_ast = _find_local_decl(ast, node.name, line)

  elif isinstance(node, MemberAccessNode):
    if isinstance(node.receiver, IdentifierNode):
      sym = sym_table.lookup(node.receiver.name)
      if sym and type(sym).__name__ == "ModuleSymbol":
        target_sym = sym.lookup_export(node.member)
        if target_sym:
          if hasattr(target_sym, "ast_decl") and target_sym.ast_decl:
            target_ast = target_sym.ast_decl
          elif hasattr(target_sym, "symbol_type") and hasattr(target_sym.symbol_type, "ast_decl") and target_sym.symbol_type.ast_decl:
            target_ast = target_sym.symbol_type.ast_decl

        mod_file_path = getattr(sym, "file_path", None)
        if mod_file_path:
          from pygls.uris import from_fs_path
          mod_uri = from_fs_path(os.path.abspath(mod_file_path))
          if not target_ast and mod_uri in ls.symbol_table_cache:  # pragma: no cover
            sub_sym_table = ls.symbol_table_cache[mod_uri]
            exp_sym = sub_sym_table.lookup(node.member) or sub_sym_table.lookup_type(node.member)
            if exp_sym:
              if hasattr(exp_sym, "ast_decl") and exp_sym.ast_decl:
                target_ast = exp_sym.ast_decl
              elif hasattr(exp_sym, "symbol_type") and hasattr(exp_sym.symbol_type, "ast_decl") and exp_sym.symbol_type.ast_decl:
                target_ast = exp_sym.symbol_type.ast_decl
          if target_ast:
            target_ast.file_uri = mod_uri

    receiver_type = node_types.get(node.receiver)
    if not target_ast and not receiver_type and isinstance(node.receiver, IdentifierNode):  # pragma: no cover
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
      if not target_ast and hasattr(receiver_type, "parent_names") and receiver_type.parent_names:
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

      if not target_ast and hasattr(receiver_type, "methods") and node.member in receiver_type.methods:
        method = receiver_type.methods[node.member]
        if hasattr(method, "ast_decl") and method.ast_decl:
          target_ast = method.ast_decl
      if not target_ast and hasattr(receiver_type, "ast_decl") and receiver_type.ast_decl:
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
          elif hasattr(exp, "symbol_type") and hasattr(exp.symbol_type, "ast_decl") and exp.symbol_type.ast_decl:  # pragma: no cover
            target_ast = exp.symbol_type.ast_decl

        mod_file_path = getattr(sym, "file_path", None)
        if mod_file_path:
          from pygls.uris import from_fs_path
          mod_uri = from_fs_path(os.path.abspath(mod_file_path))
          if not target_ast and mod_uri in ls.symbol_table_cache:  # pragma: no cover
            exp_sym = ls.symbol_table_cache[mod_uri].lookup_type(parts[1]) or ls.symbol_table_cache[mod_uri].lookup(parts[1])
            if exp_sym:
              if hasattr(exp_sym, "ast_decl") and exp_sym.ast_decl:
                target_ast = exp_sym.ast_decl
              elif hasattr(exp_sym, "symbol_type") and hasattr(exp_sym.symbol_type, "ast_decl") and exp_sym.symbol_type.ast_decl:
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
        if parent_type and hasattr(parent_type, "ast_decl") and parent_type.ast_decl:
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
      if trait_type and hasattr(trait_type, "ast_decl") and trait_type.ast_decl:
        target_ast = trait_type.ast_decl
    if not target_ast:
      struct_type = sym_table.lookup_type(node.struct_name)
      if struct_type and hasattr(struct_type, "ast_decl") and struct_type.ast_decl:
        target_ast = struct_type.ast_decl

  elif isinstance(node, (FuncDeclNode, VarDeclNode, ParameterNode, EnumDeclNode, EnumMemberNode, TraitDeclNode, StructFieldNode)):
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
    e_col = target_ast.end_column if target_ast.end_column is not None else s_col + 1
    start_pos = Position(line=s_line, character=s_col)
    end_pos = Position(line=e_line, character=e_col)
  else:  # pragma: no cover
    return None

  target_uri = getattr(target_ast, "file_uri", None)
  if not target_uri and hasattr(target_decl, "name"):
    target_name = target_decl.name
    from src.parser.ast import TraitDeclNode, StructDeclNode, ImplBlockNode, EnumDeclNode
    for c_uri, c_ast in ls.ast_cache.items():
      def _search_ast(ast_node):
        for c_decl in getattr(ast_node, "declarations", []):
          if c_decl is target_decl or getattr(c_decl, "name", None) == target_name:  # pragma: no cover
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
              if fn is target_decl or getattr(fn, "name", None) == target_name:  # pragma: no cover
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
        elif getattr(matched_node, "start_line", None) is not None:  # pragma: no cover
          s_line = matched_node.start_line - 1
          s_col = matched_node.start_column or 0
          e_line = (matched_node.end_line - 1) if matched_node.end_line else s_line
          e_col = matched_node.end_column if matched_node.end_column is not None else s_col + 1
          start_pos = Position(line=s_line, character=s_col)
          end_pos = Position(line=e_line, character=e_col)
        break

  if not target_uri:
    target_uri = uri

  return Location(uri=target_uri, range=Range(start=start_pos, end=end_pos))


SIGNATURE_HELP_TRIGGER_CHARACTERS = ["(", ","]


@server.feature(
    TEXT_DOCUMENT_SIGNATURE_HELP,
    SignatureHelpOptions(trigger_characters=SIGNATURE_HELP_TRIGGER_CHARACTERS)
)
def signature_help(ls: SapphireLanguageServer, params: SignatureHelpParams) -> Optional[SignatureHelp]:
  """Triggered when user types '(' or ',' or requests parameter hints."""
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

  text_before_cursor = line_text[:col]

  # Parse backwards to find call name and active parameter index
  depth = 0
  commas = 0
  i = len(text_before_cursor) - 1
  in_string = False
  string_char = None
  call_end_index = -1

  while i >= 0:
    ch = text_before_cursor[i]
    if in_string:
      if ch == string_char and (i == 0 or text_before_cursor[i - 1] != '\\'):
        in_string = False
    elif ch in ('"', "'"):
      in_string = True
      string_char = ch
    elif ch in (')', ']', '}'):
      depth += 1
    elif ch in ('(', '[', '{'):
      if ch == '(':
        if depth == 0:
          call_end_index = i
          break
        else:  # pragma: no cover
          depth -= 1
      else:
        if depth > 0:
          depth -= 1
    elif ch == ',' and depth == 0:
      commas += 1
    i -= 1

  if call_end_index == -1:
    return None

  active_param_idx = commas

  # Extract the callee expression immediately before '('
  callee_text = text_before_cursor[:call_end_index].rstrip()
  import re
  match = re.search(r'([a-zA-Z_][a-zA-Z0-9_\.]*)$', callee_text)
  if not match:
    return None

  callee_name = match.group(1)

  func_type = None
  fn_display_name = callee_name

  from src.semantics.symbol_table import FunctionSymbol, StructSymbol, FunctionType

  # Handle member method calls e.g. obj.method_name or String.method_name
  if "." in callee_name:
    parts = callee_name.split(".")
    obj_name = parts[-2]
    method_name = parts[-1]
    fn_display_name = method_name

    receiver_type = None
    if node_types:
      best_node = None
      min_dist = float('inf')
      for node in node_types.keys():
        n_name = (getattr(node, "name", None) or
                  getattr(node, "member", None) or
                  getattr(node, "alias", None) or
                  getattr(node, "let_name", None) or
                  getattr(node, "key_var", None) or
                  getattr(node, "val_var", None) or
                  getattr(node, "loop_var", None))
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

    if receiver_type:
      if hasattr(receiver_type, "get_method"):
        method_obj = receiver_type.get_method(method_name, sym_table)
        if method_obj:
          func_type = getattr(method_obj, "method_type", None)
      elif hasattr(receiver_type, "methods") and method_name in receiver_type.methods:
        method_obj = receiver_type.methods[method_name]
        func_type = getattr(method_obj, "method_type", method_obj)
      elif type(receiver_type).__name__ in ("StringType", "PrimitiveType") and getattr(receiver_type, "name", "") == "String":
        from src.semantics.symbol_table import STRING_METHODS
        func_type = STRING_METHODS.get(method_name)

  else:
    # Direct function call or struct constructor
    sym = sym_table.lookup(callee_name)
    if sym:
      if isinstance(sym, FunctionSymbol):
        func_type = sym.symbol_type
      elif isinstance(sym, StructSymbol):
        st = sym.symbol_type
        param_types = []
        param_names = []
        for f_name, f_obj in getattr(st, "fields", {}).items():
          param_names.append(f_name)
          param_types.append(f_obj.field_type)
        func_type = FunctionType(param_types, st, param_names=param_names)
    else:
      st = sym_table.lookup_type(callee_name)
      if st and hasattr(st, "fields"):
        param_types = []
        param_names = []
        for f_name, f_obj in getattr(st, "fields", {}).items():
          param_names.append(f_name)
          param_types.append(f_obj.field_type)
        func_type = FunctionType(param_types, st, param_names=param_names)

  if not func_type or not isinstance(func_type, FunctionType):
    return None

  param_names = list(func_type.param_names)
  param_types = list(func_type.param_types)
  param_mutabilities = list(getattr(func_type, "param_mutabilities", []))

  if func_type.has_self and param_names and param_names[0] == "self" and "." in callee_name:
    param_names = param_names[1:]
    param_types = param_types[1:]
    if param_mutabilities:
      param_mutabilities = param_mutabilities[1:]

  param_infos = []
  param_strs = []
  for idx, p_name in enumerate(param_names):
    p_type = param_types[idx] if idx < len(param_types) else "Any"
    is_mut = param_mutabilities[idx] if idx < len(param_mutabilities) else False
    mut_str = "var " if is_mut else ""
    p_label = f"{mut_str}{p_name}: {p_type}"
    param_strs.append(p_label)
    param_infos.append(ParameterInformation(label=p_label))

  sig_label = f"{fn_display_name}({', '.join(param_strs)}) -> {func_type.return_type}"
  doc_comments = getattr(func_type, "comments", "")
  doc_content = MarkupContent(kind=MarkupKind.Markdown, value=doc_comments) if doc_comments else None

  sig_info = SignatureInformation(
      label=sig_label,
      documentation=doc_content,
      parameters=param_infos,
      active_parameter=active_param_idx if active_param_idx < len(param_infos) else (len(param_infos) - 1 if param_infos else 0),
  )

  return SignatureHelp(
      signatures=[sig_info],
      active_signature=0,
      active_parameter=active_param_idx,
  )


TRIGGER_CHARACTERS = [
    ".", ":", "@",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "_"
]


def _get_scope_completion_items(ast, line: int, col: int, uri: str, ls: SapphireLanguageServer, node_types: dict) -> List[CompletionItem]:
  items: List[CompletionItem] = []
  seen: set = set()

  def add_item(label: str, kind: int, detail: str) -> None:
    if label and label not in seen:
      seen.add(label)
      items.append(CompletionItem(label=label, kind=kind, detail=detail, insert_text=label))

  # 1. Local Scope AST Traversal
  declarations = getattr(ast, "declarations", [])
  for decl in declarations:
    from src.parser.ast import FuncDeclNode, ImplBlockNode, VarDeclNode, IfNode, ForNode

    if isinstance(decl, FuncDeclNode):
      s_start = getattr(decl, "start_line", None)
      s_end = getattr(decl, "end_line", None)
      if s_start is not None and s_start <= line and (s_end is None or line <= s_end + 10):
        for p in decl.parameters:
          ptype = node_types.get(p)
          type_str = f": {ptype}" if ptype else ""
          add_item(p.name, 6, f"(parameter) {p.name}{type_str}")

        stmts = getattr(decl.body, "statements", []) if hasattr(decl, "body") else []
        for stmt in stmts:
          st_start = getattr(stmt, "start_line", None)
          if isinstance(stmt, VarDeclNode):
            if st_start is None or st_start <= line:
              vtype = node_types.get(stmt)
              type_str = f": {vtype}" if vtype else ""
              add_item(stmt.name, 6, f"(variable) {stmt.name}{type_str}")
          elif type(stmt).__name__ in ("IfNode", "WhileNode") and getattr(stmt, "init_binding", None):
            if st_start is None or st_start <= line:
              let_name = stmt.init_binding.let_name
              add_item(let_name, 6, f"(variable) {let_name}")
          elif isinstance(stmt, ForNode):
            if st_start is None or st_start <= line:
              if getattr(stmt, "key_var", None):
                add_item(stmt.key_var, 6, f"(variable) {stmt.key_var}")
              val_var = getattr(stmt, "val_var", stmt.loop_var)
              add_item(val_var, 6, f"(variable) {val_var}")

    elif isinstance(decl, ImplBlockNode):
      s_start = getattr(decl, "start_line", None)
      s_end = getattr(decl, "end_line", None)
      if s_start is not None and s_start <= line and (s_end is None or line <= s_end + 10):
        for member in decl.members:
          func_decl = getattr(member, "func_decl", None)
          if func_decl:
            f_start = getattr(func_decl, "start_line", None)
            f_end = getattr(func_decl, "end_line", None)
            if f_start is not None and f_start <= line and (f_end is None or line <= f_end + 10):
              if getattr(member, "modifier", None) != "static":
                add_item("self", 6, f"(variable) self: {decl.struct_name}")
              for p in func_decl.parameters:
                ptype = node_types.get(p)
                type_str = f": {ptype}" if ptype else ""
                add_item(p.name, 6, f"(parameter) {p.name}{type_str}")
              stmts = getattr(func_decl.body, "statements", []) if hasattr(func_decl, "body") else []
              for stmt in stmts:
                st_start = getattr(stmt, "start_line", None)
                if isinstance(stmt, VarDeclNode):
                  if st_start is None or st_start <= line:
                    vtype = node_types.get(stmt)
                    type_str = f": {vtype}" if vtype else ""
                    add_item(stmt.name, 6, f"(variable) {stmt.name}{type_str}")
                elif type(stmt).__name__ in ("IfNode", "WhileNode") and getattr(stmt, "init_binding", None):
                  if st_start is None or st_start <= line:
                    let_name = stmt.init_binding.let_name
                    add_item(let_name, 6, f"(variable) {let_name}")
                elif isinstance(stmt, ForNode):
                  if st_start is None or st_start <= line:
                    if getattr(stmt, "key_var", None):
                      add_item(stmt.key_var, 6, f"(variable) {stmt.key_var}")
                    val_var = getattr(stmt, "val_var", stmt.loop_var)
                    add_item(val_var, 6, f"(variable) {val_var}")

  if uri in ls.symbol_table_cache:
    sym_table = ls.symbol_table_cache[uri]
    scope = getattr(sym_table, "current_scope", None)
    while scope:
      from src.semantics.symbol_table import VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol

      for sym_name, sym in scope.symbols.items():



        if sym_name == "Arena":
          continue
        sym_kind = type(sym).__name__
        if sym_kind == "VariableSymbol":
          is_param = getattr(sym, "is_parameter", False)
          detail = f"(parameter) {sym_name}: {sym.symbol_type}" if is_param else f"(variable) {sym_name}: {sym.symbol_type}"
          add_item(sym_name, 6, detail)
        elif sym_kind == "FunctionSymbol":
          add_item(sym_name, 3, f"(function) {sym_name}{sym.symbol_type}")
        elif sym_kind == "StructSymbol":
          kind_name = "proto" if getattr(sym.symbol_type, "is_prototype", False) else "struct"
          add_item(sym_name, 22, f"({kind_name}) {sym_name}")
        elif sym_kind == "EnumSymbol":
          add_item(sym_name, 13, f"(enum) {sym_name}")
        elif sym_kind == "TraitSymbol":
          add_item(sym_name, 8, f"(trait) {sym_name}")

      for type_name, type_obj in scope.types.items():
        if type_name in ("int", "float", "bool", "String", "none", "Arena"):
          add_item(type_name, 14, f"(primitive type) {type_name}")
        else:
          add_item(type_name, 22, f"(type) {type_name}")

      scope = scope.parent

  # 3. Sapphire Keywords & Annotations
  KEYWORDS = [
      "let", "var", "func", "struct", "proto", "enum", "trait", "impl", "if", "else", "guard", "with",
      "for", "in", "while", "break", "continue", "return", "match", "yield", "true", "false", "none", "const", "static",
      "clone", "arena", "import", "export", "as"
  ]
  for kw in KEYWORDS:
    add_item(kw, 14, f"(keyword) {kw}")

  add_item("@extern", 15, "(annotation) @extern")
  add_item("@export", 15, "(annotation) @export")

  # 4. Document Text Word Extraction Fallback
  try:
    doc = ls.workspace.get_text_document(uri)
    source = getattr(doc, "source", None)
    if isinstance(source, str):
      import re
      words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', source)
      for word in words:
        if len(word) > 1:
          add_item(word, 1, f"(text) {word}")
  except (AttributeError, KeyError, IndexError, TypeError):  # pragma: no cover
    pass


  return items


@server.feature(TEXT_DOCUMENT_COMPLETION,
                CompletionOptions(trigger_characters=TRIGGER_CHARACTERS))
def completion(ls: SapphireLanguageServer,
               params: CompletionParams) -> CompletionList:
  """Triggered when user requests completion (either dot-access or scope-level identifier)."""
  uri = params.text_document.uri
  if uri not in ls.ast_cache and uri not in ls.symbol_table_cache:
    return CompletionList(is_incomplete=False, items=[])

  ast = ls.ast_cache.get(uri)
  node_types = ls.node_types_cache.get(uri, {})

  # Line coordinates
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
  except (AttributeError, KeyError, IndexError, TypeError):  # pragma: no cover
    pass


  text_before_cursor = line_text[:col]
  import re

  # Check if cursor is after a dot (dot completion context)
  dot_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z0-9_]*)$', text_before_cursor)
  receiver_name = dot_match.group(1) if dot_match else None

  if receiver_name:
    receiver_type = None

    # 1. Search node_types for AST declaration or identifier node matching receiver_name
    best_node = None
    min_dist = float('inf')
    for node in node_types.keys():
      n_name = (getattr(node, "name", None) or
                getattr(node, "member", None) or
                getattr(node, "alias", None) or
                getattr(node, "let_name", None) or
                getattr(node, "key_var", None) or
                getattr(node, "val_var", None) or
                getattr(node, "loop_var", None))
      if n_name == receiver_name:
        s_line = getattr(node, "start_line", getattr(node, "name_line", None))
        dist = abs(s_line - line) if s_line else 0
        if dist < min_dist:
          min_dist = dist
          best_node = node

    if best_node:
      receiver_type = node_types.get(best_node)

    # 2. Symbol table fallback if not in node_types
    if not receiver_type and uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(receiver_name)
      if sym:
        receiver_type = getattr(sym, "symbol_type", None)

    if type(receiver_type).__name__ == "OptionalType":
      receiver_type = getattr(receiver_type, "base_type", receiver_type)  # pragma: no cover

    if type(receiver_type).__name__ in ("StringType", "PrimitiveType") and getattr(receiver_type, "name", "") == "String":
      from src.semantics.symbol_table import STRING_METHODS

      items = []

      for m_name, sig in STRING_METHODS.items():
        items.append(
            CompletionItem(
                label=m_name,
                kind=2,  # Method
                detail=f"(string method) {m_name}{sig}",
                insert_text=m_name,
            )
        )
      return CompletionList(is_incomplete=False, items=items)

    if type(receiver_type).__name__ == "ModuleType" or (not best_node and uri in ls.symbol_table_cache and type(ls.symbol_table_cache[uri].lookup(receiver_name)).__name__ == "ModuleSymbol"):
      items = []
      mod_sym = ls.symbol_table_cache[uri].lookup(receiver_name) if uri in ls.symbol_table_cache else None
      exports = mod_sym.exports if mod_sym and hasattr(mod_sym, "exports") else {}
      for exp_name, exp_val in exports.items():
        type_str = str(exp_val.symbol_type) if hasattr(exp_val, "symbol_type") else str(exp_val)
        items.append(
            CompletionItem(
                label=exp_name,
                kind=6,  # Variable / Member
                detail=f"(module export) {receiver_name}.{exp_name}: {type_str}",
                insert_text=exp_name,
            )
        )
      return CompletionList(is_incomplete=False, items=items)

    if hasattr(receiver_type, "variants"):
      items = []
      enum_name = getattr(receiver_type, "name", receiver_name)
      for variant_name, val in getattr(receiver_type, "variants", {}).items():
        items.append(
            CompletionItem(
                label=variant_name,
                kind=20,  # EnumMember
                detail=f"(enum member) {enum_name}.{variant_name} = {val}",
                insert_text=variant_name,
            )
        )
      return CompletionList(is_incomplete=True, items=items)

    if hasattr(receiver_type, "fields") or hasattr(receiver_type, "methods"):
      items = []
      # Suggest fields
      for field_name, field in getattr(receiver_type, "fields", {}).items():
        items.append(
            CompletionItem(
                label=field_name,
                kind=10,  # Field
                detail=f"(property) {field_name}: {str(field.field_type)}",
                insert_text=field_name,
            )
        )
      # Suggest methods
      for method_name, method in getattr(receiver_type, "methods", {}).items():
        if method_name == "__init__":
          continue
        m_type = str(getattr(method, "method_type", method))
        items.append(
            CompletionItem(
                label=method_name,
                kind=2,  # Method
                detail=f"(method) {method_name}{m_type}",
                insert_text=method_name,
            )
        )
      return CompletionList(is_incomplete=True, items=items)

  # Fallback to Scope Completion when not in a dot-access expression
  scope_items = _get_scope_completion_items(ast, line, col, uri, ls, node_types)
  return CompletionList(is_incomplete=True, items=scope_items)


def main():  # pragma: no cover
  # Start the language server over standard I/O (stdio)
  server.start_io()


if __name__ == "__main__":  # pragma: no cover
  main()
