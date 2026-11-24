"""LSP server implementation for the Sapphire programming language.

This server provides diagnostics (syntax and semantic errors) and semantic
tokens for accurate syntax highlighting in Visual Studio Code.
"""

import os
from typing import Any

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener
from lsprotocol.types import (
  TEXT_DOCUMENT_COMPLETION,
  TEXT_DOCUMENT_DEFINITION,
  TEXT_DOCUMENT_DID_CHANGE,
  TEXT_DOCUMENT_DID_OPEN,
  TEXT_DOCUMENT_DID_SAVE,
  TEXT_DOCUMENT_DOCUMENT_SYMBOL,
  TEXT_DOCUMENT_HOVER,
  TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
  TEXT_DOCUMENT_SIGNATURE_HELP,
  WORKSPACE_DID_CHANGE_WATCHED_FILES,
  CompletionItem,
  CompletionList,
  CompletionOptions,
  CompletionParams,
  DefinitionParams,
  Diagnostic,
  DiagnosticSeverity,
  DocumentSymbolParams,
  Hover,
  HoverParams,
  Location,
  Position,
  PublishDiagnosticsParams,
  Range,
  SemanticTokens,
  SemanticTokensLegend,
  SemanticTokensParams,
  SignatureHelp,
  SignatureHelpOptions,
  SignatureHelpParams,
)
from pygls.lsp.server import LanguageServer

# Imports from compiler codebase
from sapphire.common.errors import SapphireSyntaxError
from sapphire.lsp.definition_provider import (
  DefinitionProvider,
)
from sapphire.lsp.definition_provider import (
  resolve_module_path as _resolve_module_path,
)
from sapphire.lsp.document_symbols import extract_document_symbols
from sapphire.lsp.hover_provider import (
  HoverProvider,
)
from sapphire.lsp.semantic_tokens import (
  TOKEN_MODIFIERS,
  TOKEN_TYPES,
  SemanticTokensTypeChecker,
  codepoint_span_to_utf16,
  encode_semantic_tokens,
  find_node_at_position,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser


class SapphireLanguageServer(LanguageServer):
  """Language Server instance for Sapphire."""

  def __init__(self, *args, workspace: Any | None = None, **kwargs):
    super().__init__(*args, **kwargs)
    self._custom_workspace = workspace
    # Cache of delta-encoded semantic tokens: uri -> list of integers
    self.tokens_cache = {}
    self.ast_cache = {}
    self.node_types_cache = {}
    self.symbol_table_cache = {}
    self.mtime_cache = {}

  @property
  def workspace(self):
    if self._custom_workspace is not None:
      return self._custom_workspace
    return super().workspace


class ANTLRDiagnosticListener(ErrorListener):
  """Listener to translate ANTLR parser/lexer errors to LSP Diagnostics."""

  def __init__(self, doc_text: str | None = None):
    super().__init__()
    self.diagnostics = []
    self._lines = doc_text.splitlines() if isinstance(doc_text, str) else None

  def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
    length = 1
    if (
      offendingSymbol
      and hasattr(offendingSymbol, "text")
      and offendingSymbol.text
    ):
      length = len(offendingSymbol.text)

    from sapphire.parser.error_listener import format_syntax_error_message

    custom_msg = format_syntax_error_message(recognizer, offendingSymbol, msg)

    start_char = column
    end_char = column + length
    if self._lines is not None and 0 <= line - 1 < len(self._lines):
      start_char, u16_len = codepoint_span_to_utf16(
        self._lines[line - 1], column, length
      )
      end_char = start_char + u16_len

    # LSP Diagnostic structure
    diag = Diagnostic(
      range=Range(
        start=Position(line=line - 1, character=start_char),
        end=Position(line=line - 1, character=end_char),
      ),
      message=f"Syntax Error: {custom_msg}",
      severity=DiagnosticSeverity.Error,
      source="sapphire-parser",
    )
    self.diagnostics.append(diag)


def _mark_file_uri(node: Any, uri: str) -> None:
  """Recursively tags every reachable ASTNode in *node* with *uri*."""
  from sapphire.parser.ast import ASTNode

  visited: set = set()

  def _walk(cur: Any) -> None:
    if not isinstance(cur, ASTNode):
      return
    obj_id = id(cur)
    if obj_id in visited:
      return
    visited.add(obj_id)
    cur.file_uri = uri
    for val in cur.__dict__.values():
      if isinstance(val, ASTNode):
        _walk(val)
      elif isinstance(val, (list, tuple)):
        for item in val:
          if isinstance(item, ASTNode):
            _walk(item)
      elif isinstance(val, dict):
        for item in val.values():
          if isinstance(item, ASTNode):
            _walk(item)

  _walk(node)


def _is_uri_open_in_workspace(ls: SapphireLanguageServer, uri: str) -> bool:
  """Returns True when *uri* is currently open in the editor workspace."""
  workspace = getattr(ls, "workspace", None)
  if workspace is None:
    return False
  open_docs = getattr(workspace, "text_documents", None)
  if isinstance(open_docs, dict) and uri in open_docs:
    return True
  return False


def _preload_module_dependencies(
  ls: SapphireLanguageServer,
  doc_uri: str,
  ast: Any,
  ws_root: str | None = None,
) -> None:
  from pygls.uris import from_fs_path

  for s_decl in getattr(ast, "imports", []):
    if getattr(s_decl, "path", None):
      mod_path_fs = _resolve_module_path(doc_uri, s_decl.path, ws_root)
      if mod_path_fs and os.path.isfile(mod_path_fs):
        abs_mod_path = os.path.abspath(mod_path_fs)
        mod_uri = from_fs_path(abs_mod_path)
        s_decl.target_file_uri = mod_uri
        # Do not clobber unsaved in-memory editor buffers with stale on-disk
        # files.
        if _is_uri_open_in_workspace(ls, mod_uri) and mod_uri in ls.ast_cache:
          continue
        try:
          stat_res = os.stat(abs_mod_path)
          mtime_key = (stat_res.st_mtime_ns, stat_res.st_size)
        except OSError:
          mtime_key = None

        cached_mtime = ls.mtime_cache.get(mod_uri)
        if mod_uri not in ls.ast_cache or (
          mtime_key is not None and cached_mtime != mtime_key
        ):
          try:
            with open(mod_path_fs, encoding="utf-8") as f:
              sub_code = f.read()
            sub_stream = InputStream(sub_code)
            sub_lexer = SapphireLexer(sub_stream)
            sub_lexer.removeErrorListeners()
            sub_parser = SapphireParser(CommonTokenStream(sub_lexer))
            sub_parser.removeErrorListeners()
            sub_tree = sub_parser.program()
            sub_ast = ASTBuilder().visit(sub_tree)
            if sub_ast:
              _mark_file_uri(sub_ast, mod_uri)
              sub_checker = SemanticTokensTypeChecker(
                sub_code, source_file_path=mod_path_fs
              )
              try:
                sub_checker.check(sub_ast)
              except Exception:
                pass
              ls.ast_cache[mod_uri] = sub_ast
              ls.symbol_table_cache[mod_uri] = sub_checker.symbol_table
              ls.node_types_cache[mod_uri] = sub_checker.node_types
              if mtime_key is not None:
                ls.mtime_cache[mod_uri] = mtime_key
              _preload_module_dependencies(ls, mod_uri, sub_ast, ws_root)
          except Exception:  # pragma: no cover
            pass


def validate_source(
  ls: SapphireLanguageServer, doc_uri: str, doc_text: str
) -> None:
  """Run lexical, syntactic, and semantic validation on the source text."""
  input_stream = InputStream(doc_text)
  listener = ANTLRDiagnosticListener(doc_text)

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

  doc_fs_path = (
    to_fs_path(doc_uri) if doc_uri.startswith("file://") else doc_uri
  )
  checker = SemanticTokensTypeChecker(doc_text, source_file_path=doc_fs_path)
  try:
    builder = ASTBuilder()
    ast = builder.visit(tree)
    if ast:
      _mark_file_uri(ast, doc_uri)
      checker.check(ast)
  except SapphireSyntaxError as syn_err:
    err_line = max(1, syn_err.line or 1)
    err_col = max(0, syn_err.column or 0)
    err_len = max(1, getattr(syn_err, "length", 1) or 1)
    lines = doc_text.splitlines()
    start_char = err_col
    end_char = err_col + err_len
    if 0 <= err_line - 1 < len(lines):
      start_char, u16_len = codepoint_span_to_utf16(
        lines[err_line - 1], err_col, err_len
      )
      end_char = start_char + max(1, u16_len)
    listener.diagnostics.append(
      Diagnostic(
        range=Range(
          start=Position(line=err_line - 1, character=start_char),
          end=Position(line=err_line - 1, character=end_char),
        ),
        message=f"Syntax Error: {syn_err.message}",
        severity=DiagnosticSeverity.Error,
        source="sapphire-parser",
      )
    )
  except Exception as e:  # pragma: no cover
    ast_error = str(e)

  has_syntax_errors = bool(listener.diagnostics)
  has_usable_ast = bool(
    ast
    and (
      getattr(ast, "declarations", None)
      or getattr(ast, "imports", None)
      or doc_uri not in ls.ast_cache
    )
  )
  # Preserve existing semantic tokens when syntax errors occur during typing,
  # while still keeping partial AST/symbol caches fresh when declarations exist.
  if not has_syntax_errors and ast:
    encoded = encode_semantic_tokens(checker.raw_tokens, doc_text=doc_text)
    ls.tokens_cache[doc_uri] = encoded
  elif ast and doc_uri not in ls.tokens_cache:
    ls.tokens_cache[doc_uri] = encode_semantic_tokens(
      checker.raw_tokens, doc_text=doc_text
    )

  if has_usable_ast and (
    not has_syntax_errors
    or getattr(ast, "declarations", None)
    or doc_uri not in ls.ast_cache
  ):
    ls.ast_cache[doc_uri] = ast
    ls.node_types_cache[doc_uri] = checker.node_types
    ls.symbol_table_cache[doc_uri] = checker.symbol_table

    # Process imports and pre-load dependency ASTs for definition navigation
    ws_root = getattr(getattr(ls, "workspace", None), "root_uri", None)
    _preload_module_dependencies(ls, doc_uri, ast, ws_root)

  # If syntax errors are present, report them immediately
  if has_syntax_errors:
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
  for warn in getattr(checker, "lsp_warnings", []):
    start_pos = Position(
      line=warn["range"]["start"]["line"],
      character=warn["range"]["start"]["character"],
    )
    end_pos = Position(
      line=warn["range"]["end"]["line"],
      character=warn["range"]["end"]["character"],
    )
    diagnostics.append(
      Diagnostic(
        range=Range(start=start_pos, end=end_pos),
        message=warn["message"],
        severity=DiagnosticSeverity.Warning,
        source="sapphire-semantics",
      )
    )

  ls.text_document_publish_diagnostics(
    PublishDiagnosticsParams(uri=doc_uri, diagnostics=diagnostics)
  )


def did_open(ls: SapphireLanguageServer, params):
  """Triggered when a document is opened in the editor."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  validate_source(ls, doc.uri, doc.source)


def did_change(ls: SapphireLanguageServer, params):
  """Triggered when a document is modified."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  validate_source(ls, doc.uri, doc.source)


def did_save(ls: SapphireLanguageServer, params):
  """Triggered when a document is saved."""
  doc = ls.workspace.get_text_document(params.text_document.uri)
  ls.mtime_cache.pop(doc.uri, None)
  validate_source(ls, doc.uri, doc.source)


def did_change_watched_files(ls: SapphireLanguageServer, params):
  """No-op handler to silent log warnings from workspace/didChangeWatchedFiles.
  """
  pass


def semantic_tokens_full(
  ls: SapphireLanguageServer, params: SemanticTokensParams
) -> SemanticTokens:
  """Returns the cached semantic tokens for the document."""
  uri = params.text_document.uri
  # Re-validate if document is not in cache (e.g. freshly opened or not
  # validated yet)
  if uri not in ls.tokens_cache:
    doc = ls.workspace.get_text_document(uri)
    validate_source(ls, uri, doc.source)

  tokens_data = ls.tokens_cache.get(uri, [])
  return SemanticTokens(data=tokens_data)


def document_symbol(
  ls: SapphireLanguageServer, params: DocumentSymbolParams
) -> list:
  """Triggered to populate the Outline pane, Breadcrumbs, and Go to Symbol in
  File.
  """
  uri = params.text_document.uri
  if uri not in ls.ast_cache:
    doc = ls.workspace.get_text_document(uri)
    if doc and getattr(doc, "source", None):
      validate_source(ls, uri, doc.source)

  from sapphire.parser.ast import ProgramNode

  ast = ls.ast_cache.get(uri)
  if not ast or not isinstance(ast, ProgramNode):
    return []

  return extract_document_symbols(ast)


def hover(ls: SapphireLanguageServer, params: HoverParams) -> Hover | None:
  """Triggered when user hovers over an identifier."""
  return HoverProvider.provide_hover(
    ls, params, find_node_fn=find_node_at_position
  )


def definition(
  ls: SapphireLanguageServer, params: DefinitionParams
) -> Location | None:
  """Triggered when user requests Go to Definition (F12 or Cmd+Click)."""
  return DefinitionProvider.provide_definition(
    ls, params, find_node_fn=find_node_at_position
  )


SIGNATURE_HELP_TRIGGER_CHARACTERS = ["(", ","]


def signature_help(
  ls: SapphireLanguageServer, params: SignatureHelpParams
) -> SignatureHelp | None:
  """Triggered when user types '(' or ',' or requests parameter hints."""
  from sapphire.lsp.signature_provider import SignatureProvider

  return SignatureProvider.provide_signature_help(ls, params)


TRIGGER_CHARACTERS = [
  ".",
  ":",
  "@",
  "a",
  "b",
  "c",
  "d",
  "e",
  "f",
  "g",
  "h",
  "i",
  "j",
  "k",
  "l",
  "m",
  "n",
  "o",
  "p",
  "q",
  "r",
  "s",
  "t",
  "u",
  "v",
  "w",
  "x",
  "y",
  "z",
  "A",
  "B",
  "C",
  "D",
  "E",
  "F",
  "G",
  "H",
  "I",
  "J",
  "K",
  "L",
  "M",
  "N",
  "O",
  "P",
  "Q",
  "R",
  "S",
  "T",
  "U",
  "V",
  "W",
  "X",
  "Y",
  "Z",
  "_",
]


def _get_scope_completion_items(
  ast,
  line: int,
  col: int,
  uri: str,
  ls: SapphireLanguageServer,
  node_types: dict,
) -> list[CompletionItem]:
  """Backward-compatible wrapper around
  completion_provider.get_scope_completion_items.
  """
  from sapphire.lsp.completion_provider import get_scope_completion_items

  return get_scope_completion_items(ast, line, col, uri, ls, node_types)


def completion(
  ls: SapphireLanguageServer, params: CompletionParams
) -> CompletionList:
  """Triggered when user requests completion (dot-access or scope-level
  identifier).
  """
  from sapphire.lsp.completion_provider import CompletionProvider

  return CompletionProvider.provide_completion(ls, params)


def register_features(ls: SapphireLanguageServer) -> None:
  """Binds all Sapphire LSP feature handlers onto *ls*."""
  ls.feature(TEXT_DOCUMENT_DID_OPEN)(did_open)
  ls.feature(TEXT_DOCUMENT_DID_CHANGE)(did_change)
  ls.feature(TEXT_DOCUMENT_DID_SAVE)(did_save)
  ls.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)(did_change_watched_files)
  ls.feature(
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    SemanticTokensLegend(
      token_types=TOKEN_TYPES, token_modifiers=TOKEN_MODIFIERS
    ),
  )(semantic_tokens_full)
  ls.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)(document_symbol)
  ls.feature(TEXT_DOCUMENT_HOVER)(hover)
  ls.feature(TEXT_DOCUMENT_DEFINITION)(definition)
  ls.feature(
    TEXT_DOCUMENT_SIGNATURE_HELP,
    SignatureHelpOptions(trigger_characters=SIGNATURE_HELP_TRIGGER_CHARACTERS),
  )(signature_help)
  ls.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=TRIGGER_CHARACTERS),
  )(completion)


def create_server(
  name: str = "sapphire-lsp",
  version: str = "v0.1.0",
  *,
  workspace: Any | None = None,
) -> SapphireLanguageServer:
  """Creates a fresh SapphireLanguageServer with all LSP features registered.
  """
  ls = SapphireLanguageServer(name, version, workspace=workspace)
  register_features(ls)
  return ls


def main():  # pragma: no cover
  # Start the language server over standard I/O (stdio)
  create_server().start_io()


if __name__ == "__main__":  # pragma: no cover
  main()
