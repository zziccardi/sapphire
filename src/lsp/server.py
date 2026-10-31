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
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    DocumentSymbol,
    DocumentSymbolParams,
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
from src.lsp.document_symbols import extract_document_symbols
from src.lsp.hover_provider import (
    HoverProvider,
    format_ast_expr as _format_ast_expr,
)
from src.lsp.definition_provider import (
    DefinitionProvider,
    find_local_decl as _find_local_decl,
    resolve_module_path as _resolve_module_path,
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


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(
    ls: SapphireLanguageServer, params: DocumentSymbolParams
) -> list:
  """Triggered to populate the Outline pane, Breadcrumbs, and Go to Symbol in File."""
  uri = params.text_document.uri
  if uri not in ls.ast_cache:
    doc = ls.workspace.get_text_document(uri)
    if doc and getattr(doc, "source", None):
      validate_source(ls, uri, doc.source)

  from src.parser.ast import ProgramNode
  ast = ls.ast_cache.get(uri)
  if not ast or not isinstance(ast, ProgramNode):
    return []

  return extract_document_symbols(ast)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: SapphireLanguageServer, params: HoverParams) -> Optional[Hover]:
  """Triggered when user hovers over an identifier."""
  return HoverProvider.provide_hover(ls, params, find_node_fn=find_node_at_position)


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: SapphireLanguageServer, params: DefinitionParams) -> Optional[Location]:
  """Triggered when user requests Go to Definition (F12 or Cmd+Click)."""
  return DefinitionProvider.provide_definition(ls, params, find_node_fn=find_node_at_position)


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
          elif type(stmt).__name__ == "IfNode":
            if st_start is None or st_start <= line:
              for b in getattr(stmt, "bindings", [stmt.init_binding] if getattr(stmt, "init_binding", None) else []):
                for b_name in getattr(b, "let_names", [b.let_name] if getattr(b, "let_name", None) else []):
                  add_item(b_name, 6, f"(variable) {b_name}")
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
                elif type(stmt).__name__ == "IfNode":
                  if st_start is None or st_start <= line:
                    for b in getattr(stmt, "bindings", [stmt.init_binding] if getattr(stmt, "init_binding", None) else []):
                      for b_name in getattr(b, "let_names", [b.let_name] if getattr(b, "let_name", None) else []):
                        add_item(b_name, 6, f"(variable) {b_name}")
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
      "let", "var", "func", "struct", "proto", "enum", "trait", "impl", "if", "else", "guard",
      "for", "in", "while", "break", "continue", "return", "match", "yield", "true", "false", "none", "static",
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
        if method_name in ("__init__", "__del__"):
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
