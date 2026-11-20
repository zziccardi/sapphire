"""LSP server implementation for the Sapphire programming language.

This server provides diagnostics (syntax and semantic errors) and semantic
tokens for accurate syntax highlighting in Visual Studio Code.
"""

import sys
import os
from typing import Any, List, Optional

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
    self.mtime_cache = {}


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
        abs_mod_path = os.path.abspath(mod_path_fs)
        mod_uri = from_fs_path(abs_mod_path)
        s_decl.target_file_uri = mod_uri
        try:
          stat_res = os.stat(abs_mod_path)
          mtime_key = (stat_res.st_mtime_ns, stat_res.st_size)
        except OSError:
          mtime_key = None

        cached_mtime = ls.mtime_cache.get(mod_uri)
        if mod_uri not in ls.ast_cache or (mtime_key is not None and cached_mtime != mtime_key):
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
              if mtime_key is not None:
                ls.mtime_cache[mod_uri] = mtime_key
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
  ls.mtime_cache.pop(doc.uri, None)
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
def signature_help(
    ls: SapphireLanguageServer, params: SignatureHelpParams
) -> Optional[SignatureHelp]:
  """Triggered when user types '(' or ',' or requests parameter hints."""
  from src.lsp.signature_provider import SignatureProvider

  return SignatureProvider.provide_signature_help(ls, params)


TRIGGER_CHARACTERS = [
    ".", ":", "@",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "_",
]


def _get_scope_completion_items(
    ast, line: int, col: int, uri: str, ls: SapphireLanguageServer, node_types: dict
) -> List[CompletionItem]:
  """Backward-compatible wrapper around completion_provider.get_scope_completion_items."""
  from src.lsp.completion_provider import get_scope_completion_items

  return get_scope_completion_items(ast, line, col, uri, ls, node_types)


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=TRIGGER_CHARACTERS),
)
def completion(
    ls: SapphireLanguageServer, params: CompletionParams
) -> CompletionList:
  """Triggered when user requests completion (dot-access or scope-level identifier)."""
  from src.lsp.completion_provider import CompletionProvider

  return CompletionProvider.provide_completion(ls, params)


def main():  # pragma: no cover
  # Start the language server over standard I/O (stdio)
  server.start_io()


if __name__ == "__main__":  # pragma: no cover
  main()
