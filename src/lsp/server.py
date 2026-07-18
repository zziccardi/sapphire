"""LSP server implementation for the Sapphire programming language.

This server provides diagnostics (syntax and semantic errors) and semantic tokens for
accurate syntax highlighting in Visual Studio Code.
"""

import sys
import os

# Add parent directories to Python path to allow imports from parser and semantics
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    MarkupContent,
    MarkupKind,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_COMPLETION,
    PublishDiagnosticsParams,
)
from pygls.lsp.server import LanguageServer

# Imports from compiler codebase
try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from lsp.semantic_tokens import (
      SemanticTokensTypeChecker,
      encode_semantic_tokens,
      TOKEN_TYPES,
      TOKEN_MODIFIERS,
      find_node_at_position,
  )
except ImportError:  # pragma: no cover
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
    if offendingSymbol and hasattr(offendingSymbol, "text") and offendingSymbol.text:
      length = len(offendingSymbol.text)

    # LSP Diagnostic structure
    diag = Diagnostic(
        range=Range(
            start=Position(line=line - 1, character=column),
            end=Position(line=line - 1, character=column + length),
        ),
        message=f"Syntax Error: {msg}",
        severity=DiagnosticSeverity.Error,
        source="sapphire-parser",
    )
    self.diagnostics.append(diag)


def validate_source(ls: SapphireLanguageServer, doc_uri: str, doc_text: str) -> None:
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

  # If syntax errors are present, report them immediately and clear semantic cache
  if listener.diagnostics:
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=doc_uri, diagnostics=listener.diagnostics)
    )
    ls.ast_cache.pop(doc_uri, None)
    ls.node_types_cache.pop(doc_uri, None)
    ls.symbol_table_cache.pop(doc_uri, None)
    return

  # 3. AST Building
  try:
    builder = ASTBuilder()
    ast = builder.visit(tree)
  except Exception as e:
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(
            uri=doc_uri,
            diagnostics=[
                Diagnostic(
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=1),
                    ),
                    message=f"Internal AST generation failure: {str(e)}",
                    severity=DiagnosticSeverity.Error,
                    source="sapphire-compiler",
                )
            ],
        )
    )
    ls.ast_cache.pop(doc_uri, None)
    ls.node_types_cache.pop(doc_uri, None)
    ls.symbol_table_cache.pop(doc_uri, None)
    return

  # 4. Semantic Validation & Token Extraction
  checker = SemanticTokensTypeChecker()
  try:
    checker.check(ast)
  except Exception:
    # Standard check raises SemanticError when errors are present.
    # However, checker.lsp_errors contains all collected diagnostics.
    pass

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

  # Cache successfully compiled semantic tokens
  encoded = encode_semantic_tokens(checker.raw_tokens)
  ls.tokens_cache[doc_uri] = encoded
  ls.ast_cache[doc_uri] = ast
  ls.node_types_cache[doc_uri] = checker.node_types
  ls.symbol_table_cache[doc_uri] = checker.symbol_table


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


@server.feature(
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    SemanticTokensLegend(token_types=TOKEN_TYPES, token_modifiers=TOKEN_MODIFIERS),
)
def semantic_tokens_full(ls: SapphireLanguageServer, params: SemanticTokensParams) -> SemanticTokens:
  """Returns the cached semantic tokens for the document."""
  uri = params.text_document.uri
  # Re-validate if document is not in cache (e.g. freshly opened or not validated yet)
  if uri not in ls.tokens_cache:
    doc = ls.workspace.get_text_document(uri)
    validate_source(ls, uri, doc.source)

  tokens_data = ls.tokens_cache.get(uri, [])
  return SemanticTokens(data=tokens_data)


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

  node_type = node_types.get(node)
  if not node_type:
    from parser.ast import IdentifierNode
    if isinstance(node, IdentifierNode) and uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)

  if not node_type:
    return None

  from parser.ast import (
      IdentifierNode,
      MemberAccessNode,
      FuncDeclNode,
      VarDeclNode,
      ParameterNode,
      StructFieldNode,
  )

  node_name = ""
  if isinstance(node, IdentifierNode):
    node_name = node.name
  elif isinstance(node, MemberAccessNode):
    node_name = node.member

  category = "symbol"
  if isinstance(node, IdentifierNode) and uri in ls.symbol_table_cache:
    sym = ls.symbol_table_cache[uri].lookup(node.name)
    if sym:
      from semantics.symbol_table import (
          VariableSymbol,
          FunctionSymbol,
          StructSymbol,
          TraitSymbol,
      )
      if isinstance(sym, VariableSymbol):
        category = "parameter" if sym.is_parameter else "variable"
      elif isinstance(sym, FunctionSymbol):
        category = "function"
      elif isinstance(sym, StructSymbol):
        category = "struct"
      elif isinstance(sym, TraitSymbol):
        category = "trait"

  if isinstance(node, ParameterNode):
    category = "parameter"
    node_name = node.name
  elif isinstance(node, StructFieldNode):
    category = "property"
    node_name = node.name
  elif isinstance(node, VarDeclNode):
    category = "variable"
    node_name = node.name
  elif isinstance(node, FuncDeclNode):
    category = "function"
    node_name = node.name

  type_desc = str(node_type)
  markdown_text = f"**({category})** `{node_name}`: `{type_desc}`" if node_name else f"`{type_desc}`"

  return Hover(
      contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_text)
  )


@server.feature(
    TEXT_DOCUMENT_COMPLETION, CompletionOptions(trigger_characters=["."])
)
def completion(ls: SapphireLanguageServer, params: CompletionParams) -> CompletionList:
  """Triggered when user types a dot for member suggestion."""
  uri = params.text_document.uri
  if uri not in ls.ast_cache or uri not in ls.node_types_cache:
    return CompletionList(is_incomplete=False, items=[])

  ast = ls.ast_cache[uri]
  node_types = ls.node_types_cache[uri]

  # Line coordinates
  line = params.position.line + 1
  col = params.position.character

  # Search receiver at col - 1 (the dot)
  receiver = find_node_at_position(ast, line, col - 1)
  if not receiver:
    return CompletionList(is_incomplete=False, items=[])

  receiver_type = node_types.get(receiver)
  if not receiver_type:
    from parser.ast import IdentifierNode
    if isinstance(receiver, IdentifierNode) and uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(receiver.name)
      if sym:
        receiver_type = getattr(sym, "symbol_type", None)

  if not receiver_type:
    return CompletionList(is_incomplete=False, items=[])

  items = []
  from semantics.symbol_table import StructType
  if isinstance(receiver_type, StructType):
    # Suggest fields
    for field_name, field in receiver_type.fields.items():
      items.append(
          CompletionItem(
              label=field_name,
              kind=10,  # Field
              detail=f"(property) {field_name}: {str(field.field_type)}",
          )
      )
    # Suggest methods
    for method_name, method in receiver_type.methods.items():
      if method_name == "__init__":
        continue
      items.append(
          CompletionItem(
              label=method_name,
              kind=2,  # Method
              detail=f"(method) {method_name}{str(method.method_type)}",
          )
      )

  return CompletionList(is_incomplete=False, items=items)


def main():
  # Start the language server over standard I/O (stdio)
  server.start_io()


if __name__ == "__main__":  # pragma: no cover
  main()
