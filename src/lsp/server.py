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

  # 3. AST Building & Semantic Tokens Extraction (Attempt AST generation & cache even with syntax errors)
  ast = None
  ast_error = None
  checker = SemanticTokensTypeChecker(doc_text)
  try:
    builder = ASTBuilder()
    ast = builder.visit(tree)
    if ast:
      checker.check(ast)
  except Exception as e:
    ast_error = str(e)

  if ast:
    encoded = encode_semantic_tokens(checker.raw_tokens)
    ls.tokens_cache[doc_uri] = encoded
    ls.ast_cache[doc_uri] = ast
    ls.node_types_cache[doc_uri] = checker.node_types
    ls.symbol_table_cache[doc_uri] = checker.symbol_table

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
      from parser.ast import IdentifierNode, StructDeclNode, TraitDeclNode, ImplBlockNode, BasicTypeNode, EnumDeclNode, EnumMemberNode
    except ImportError:  # pragma: no cover
      from src.parser.ast import IdentifierNode, StructDeclNode, TraitDeclNode, ImplBlockNode, BasicTypeNode, EnumDeclNode, EnumMemberNode

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
    elif isinstance(node, ImplBlockNode) and uri in ls.symbol_table_cache:
      if node.struct_name_line == line and node.struct_name_column <= col < node.struct_name_column + node.struct_name_length:
        node_type = ls.symbol_table_cache[uri].lookup_type(node.struct_name)
      elif node.trait_name and node.trait_name_line == line and node.trait_name_column <= col < node.trait_name_column + node.trait_name_length:
        node_type = ls.symbol_table_cache[uri].lookup_type(node.trait_name)

  if not node_type and type(node).__name__ != "AnnotationNode":
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
        EnumDeclNode,
        EnumMemberNode,
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
        EnumDeclNode,
        EnumMemberNode,
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
              EnumSymbol,
          )
        except ImportError:  # pragma: no cover
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
      markdown_text = f"**({category})** `{node_name}`\n\nDeclares an external variable provided by the host runtime environment."
    elif ann_name == "export":
      markdown_text = f"**({category})** `{node_name}`\n\nExposes a function as a global callback for the host runtime environment."
    else:
      markdown_text = f"**({category})** `{node_name}`"
    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_text))
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
      from semantics.symbol_table import StructType, TraitType, EnumType
    except ImportError:  # pragma: no cover
      from src.semantics.symbol_table import StructType, TraitType, EnumType
    if isinstance(node_type, StructType):
      category = "proto" if node_type.is_prototype else "struct"
    elif isinstance(node_type, EnumType):
      category = "enum"
    elif isinstance(node_type, TraitType):
      category = "trait"

  try:
    from semantics.symbol_table import FunctionType, StructType, TraitType, EnumType
  except ImportError:  # pragma: no cover
    from src.semantics.symbol_table import FunctionType, StructType, TraitType, EnumType

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
  elif isinstance(node_type, EnumType) and category == "enum":
    markdown_text = f"**(enum)** `{node_type.name}`"
    if node_type.variants:
      members_str = "\n".join(f"- `{k} = {v}`" for k, v in node_type.variants.items())
      markdown_text += f"\n\nMembers:\n{members_str}"
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
    try:
      from parser.ast import FuncDeclNode, ImplBlockNode, VarDeclNode, IfNode, ForNode
    except ImportError:  # pragma: no cover
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
          elif isinstance(stmt, IfNode) and getattr(stmt, "is_if_let", False):
            if st_start is None or st_start <= line:
              add_item(stmt.let_name, 6, f"(variable) {stmt.let_name}")
          elif isinstance(stmt, ForNode):
            if st_start is None or st_start <= line:
              add_item(stmt.loop_var, 6, f"(variable) {stmt.loop_var}")

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
                elif isinstance(stmt, IfNode) and getattr(stmt, "is_if_let", False):
                  if st_start is None or st_start <= line:
                    add_item(stmt.let_name, 6, f"(variable) {stmt.let_name}")
                elif isinstance(stmt, ForNode):
                  if st_start is None or st_start <= line:
                    add_item(stmt.loop_var, 6, f"(variable) {stmt.loop_var}")

  # 2. Symbols and Types from Symbol Table
  if uri in ls.symbol_table_cache:
    sym_table = ls.symbol_table_cache[uri]
    scope = getattr(sym_table, "current_scope", None)
    while scope:
      try:
        from semantics.symbol_table import VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol
      except ImportError:  # pragma: no cover
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
      "let", "var", "func", "struct", "proto", "enum", "trait", "impl", "if", "else",
      "for", "in", "while", "return", "true", "false", "none", "const", "static",
      "clone", "arena"
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
  except Exception:  # pragma: no cover
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
  except Exception:  # pragma: no cover
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
      n_name = getattr(node, "name", None) or getattr(node, "let_name", None) or getattr(node, "loop_var", None)
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

    if hasattr(receiver_type, "fields"):
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
        items.append(
            CompletionItem(
                label=method_name,
                kind=2,  # Method
                detail=f"(method) {method_name}{str(method.method_type)}",
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
