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
    MarkupContent,
    MarkupKind,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_COMPLETION,
    PublishDiagnosticsParams,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
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
    if (offendingSymbol and hasattr(offendingSymbol, "text") and
        offendingSymbol.text):
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

  # If syntax errors are present, report them immediately (but retain last successful semantic cache)
  if listener.diagnostics:
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=doc_uri, diagnostics=listener.diagnostics)
    )
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
    return

  # 4. Semantic Validation & Token Extraction
  checker = SemanticTokensTypeChecker(doc_text)
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
    try:
      from parser.ast import IdentifierNode, StructDeclNode, TraitDeclNode, ImplBlockNode, BasicTypeNode
    except ImportError:  # pragma: no cover
      from src.parser.ast import IdentifierNode, StructDeclNode, TraitDeclNode, ImplBlockNode, BasicTypeNode

    if isinstance(node, IdentifierNode) and uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        node_type = getattr(sym, "symbol_type", None)
    elif isinstance(node, StructDeclNode) and uri in ls.symbol_table_cache:
      node_type = ls.symbol_table_cache[uri].lookup_type(node.name)
    elif isinstance(node, TraitDeclNode) and uri in ls.symbol_table_cache:
      node_type = ls.symbol_table_cache[uri].lookup_type(node.name)
    elif isinstance(node, ImplBlockNode) and uri in ls.symbol_table_cache:
      if node.struct_name_line == line and node.struct_name_column <= col < node.struct_name_column + node.struct_name_length:
        node_type = ls.symbol_table_cache[uri].lookup_type(node.struct_name)
      elif node.trait_name and node.trait_name_line == line and node.trait_name_column <= col < node.trait_name_column + node.trait_name_length:
        node_type = ls.symbol_table_cache[uri].lookup_type(node.trait_name)

  if not node_type:
    return None

  try:
    from parser.ast import (
        IdentifierNode,
        MemberAccessNode,
        FuncDeclNode,
        VarDeclNode,
        ParameterNode,
        StructFieldNode,
        IfNode,
        ForNode,
        StructDeclNode,
        TraitDeclNode,
        ImplBlockNode,
        BasicTypeNode,
        TraitMemberNode,
    )
  except ImportError:  # pragma: no cover
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
        TraitDeclNode,
        ImplBlockNode,
        BasicTypeNode,
        TraitMemberNode,
    )

  node_name = ""
  category = "symbol"

  if isinstance(node, IdentifierNode):
    node_name = node.name
    if uri in ls.symbol_table_cache:
      sym = ls.symbol_table_cache[uri].lookup(node.name)
      if sym:
        try:
          from semantics.symbol_table import (
              VariableSymbol,
              FunctionSymbol,
              StructSymbol,
              TraitSymbol,
          )
        except ImportError:  # pragma: no cover
          from src.semantics.symbol_table import (
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


  elif isinstance(node, MemberAccessNode):
    node_name = node.member
  elif isinstance(node, StructDeclNode):
    node_name = node.name
    category = "proto" if node.is_prototype else "struct"
  elif isinstance(node, TraitDeclNode):
    node_name = node.name
    category = "trait"
  elif isinstance(node, ImplBlockNode):
    if node.struct_name_line == line and node.struct_name_column <= col < node.struct_name_column + node.struct_name_length:
      node_name = node.struct_name
      st = ls.symbol_table_cache[uri].lookup_type(node.struct_name)
      category = "proto" if getattr(st, "is_prototype", False) else "struct"
    elif node.trait_name and node.trait_name_line == line and node.trait_name_column <= col < node.trait_name_column + node.trait_name_length:
      node_name = node.trait_name
      category = "trait"

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
    category = "variable"
    node_name = node.name
  elif isinstance(node, FuncDeclNode):
    category = "function"
    node_name = node.name
  elif isinstance(node, IfNode) and node.is_if_let:
    category = "variable"
    node_name = node.let_name
  elif isinstance(node, ForNode):
    category = "variable"
    node_name = node.loop_var
  elif isinstance(node, BasicTypeNode):
    node_name = node.name

  if category == "symbol" and node_type:
    try:
      from semantics.symbol_table import StructType, TraitType
    except ImportError:  # pragma: no cover
      from src.semantics.symbol_table import StructType, TraitType
    if isinstance(node_type, StructType):
      category = "proto" if node_type.is_prototype else "struct"
    elif isinstance(node_type, TraitType):
      category = "trait"

  try:
    from semantics.symbol_table import FunctionType, StructType, TraitType
  except ImportError:  # pragma: no cover
    from src.semantics.symbol_table import FunctionType, StructType, TraitType

  if isinstance(node_type, FunctionType):
    params_lines = []
    for idx, p_type in enumerate(node_type.param_types):
      p_name = (node_type.param_names[idx]
                if idx < len(node_type.param_names)
                else f"p{idx}")
      is_mut = (node_type.param_mutabilities[idx]
                if idx < len(node_type.param_mutabilities) else False)
      mut_str = "var " if is_mut else ""
      # Show bulleted list of params & their types.
      params_lines.append(f"- `{mut_str}{p_name}: {str(p_type)}`")

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
    inheritance = f" : {node_type.parent_name}" if node_type.parent_name else ""
    markdown_text = f"**({kind})** `{node_type.name}{inheritance}`"
    if getattr(node_type, "comments", None):
      markdown_text += f"\n\n{node_type.comments}"
  elif isinstance(node_type, TraitType) and category == "trait":
    markdown_text = f"**(trait)** `{node_type.name}`"
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
        try:
          from semantics.symbol_table import StructType
        except ImportError:  # pragma: no cover
          from src.semantics.symbol_table import StructType
        if isinstance(receiver_type, StructType) and node.member in receiver_type.fields:
          field = receiver_type.fields[node.member]
          field_comments = getattr(field, "comments", "")

    if field_comments:
      markdown_text += f"\n\n{field_comments}"

  return Hover(contents=MarkupContent(kind=MarkupKind.Markdown,
                                      value=markdown_text))


@server.feature(TEXT_DOCUMENT_COMPLETION,
                CompletionOptions(trigger_characters=["."]))
def completion(ls: SapphireLanguageServer,
               params: CompletionParams) -> CompletionList:
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
  receiver_type = None
  if receiver:
    receiver_type = node_types.get(receiver)
    if not receiver_type:
      from parser.ast import IdentifierNode
      if isinstance(receiver, IdentifierNode) and uri in ls.symbol_table_cache:
        sym = ls.symbol_table_cache[uri].lookup(receiver.name)
        if sym:
          receiver_type = getattr(sym, "symbol_type", None)

  # Robust fallback: extract identifier right before the dot from the current document source
  if not receiver_type:
    try:
      doc = ls.workspace.get_text_document(uri)
      lines = doc.source.splitlines()
      if 0 <= line - 1 < len(lines):
        line_text = lines[line - 1]
        text_before_dot = line_text[:col - 1]
        import re
        match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)$', text_before_dot)
        if match:
          ident_name = match.group(1)
          # Find the IdentifierNode in node_types with this name closest to the current line
          best_node = None
          min_dist = float('inf')
          for node in node_types.keys():
            from parser.ast import IdentifierNode
            if isinstance(node, IdentifierNode) and node.name == ident_name:
              dist = abs(node.start_line - line)
              if dist < min_dist:
                min_dist = dist
                best_node = node
          if best_node:
            receiver_type = node_types[best_node]
    except Exception:
      pass

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
