import unittest
from unittest.mock import MagicMock, patch
from lsprotocol.types import SemanticTokensParams

# Import server components
try:
  from lsp.server import (
      SapphireLanguageServer,
      ANTLRDiagnosticListener,
      validate_source,
      did_open,
      did_change,
      did_save,
      semantic_tokens_full,
      main,
  )
except ImportError:
  from src.lsp.server import (
      SapphireLanguageServer,
      ANTLRDiagnosticListener,
      validate_source,
      did_open,
      did_change,
      did_save,
      semantic_tokens_full,
      main,
  )


class TestLSPServer(unittest.TestCase):

  def setUp(self):
    self.ls = SapphireLanguageServer("test-lsp", "0.1.0")
    # Mock text_document_publish_diagnostics
    self.ls.text_document_publish_diagnostics = MagicMock()
    # Mock workspace lookup method by setting protocol._workspace
    self.ls.protocol._workspace = MagicMock()

  def test_validate_source_valid(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published (should be empty list)
    self.ls.text_document_publish_diagnostics.assert_called_once()
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertEqual(call_arg.diagnostics, [])
    # Check cache contains encoded tokens
    self.assertIn(doc_uri, self.ls.tokens_cache)
    self.assertTrue(len(self.ls.tokens_cache[doc_uri]) > 0)

  def test_validate_source_syntax_error(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x int 42;"  # Syntax error: missing colon and assignment
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published
    self.ls.text_document_publish_diagnostics.assert_called_once()
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertTrue(len(call_arg.diagnostics) > 0)
    self.assertEqual(call_arg.diagnostics[0].source, "sapphire-parser")

  def test_validate_source_ast_builder_failure(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    # Mock ASTBuilder.visit to throw an exception to simulate compiler error
    # Try importing either local or global path for mock
    try:
      patch_path = "lsp.server.ASTBuilder.visit"
      with patch(patch_path, side_effect=ValueError("Mock AST generation error")):
        validate_source(self.ls, doc_uri, doc_text)
    except (ImportError, ModuleNotFoundError, AttributeError):  # pragma: no cover
      patch_path = "src.lsp.server.ASTBuilder.visit"
      with patch(patch_path, side_effect=ValueError("Mock AST generation error")):
        validate_source(self.ls, doc_uri, doc_text)

    self.ls.text_document_publish_diagnostics.assert_called_once()
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertEqual(call_arg.diagnostics[0].source, "sapphire-compiler")
    self.assertIn("Internal AST generation failure", call_arg.diagnostics[0].message)

  def test_validate_source_semantic_error(self):
    doc_uri = "file:///test.sp"
    doc_text = 'let x: int = "string";'  # Type mismatch
    validate_source(self.ls, doc_uri, doc_text)

    # Check diagnostics published
    self.ls.text_document_publish_diagnostics.assert_called_once()
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertTrue(len(call_arg.diagnostics) > 0)
    self.assertEqual(call_arg.diagnostics[0].source, "sapphire-semantics")

  def test_did_open_change_save(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Mock params
    params = MagicMock()
    params.text_document.uri = doc_uri

    # 1. did_open
    did_open(self.ls, params)
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertEqual(call_arg.diagnostics, [])
    self.ls.text_document_publish_diagnostics.reset_mock()

    # 2. did_change
    did_change(self.ls, params)
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertEqual(call_arg.diagnostics, [])
    self.ls.text_document_publish_diagnostics.reset_mock()

    # 3. did_save
    did_save(self.ls, params)
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertEqual(call_arg.uri, doc_uri)
    self.assertEqual(call_arg.diagnostics, [])

  def test_semantic_tokens_full(self):
    doc_uri = "file:///test.sp"
    doc_text = "let x: int = 42;"

    # Mock params
    params = MagicMock()
    params.text_document.uri = doc_uri

    # Mock document lookup
    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # 1. First retrieval when not cached (triggers validation)
    tokens = semantic_tokens_full(self.ls, params)
    self.assertTrue(len(tokens.data) > 0)
    self.assertEqual(self.ls.tokens_cache[doc_uri], tokens.data)

    # 2. Subsequent retrieval from cache
    self.ls.text_document_publish_diagnostics.reset_mock()
    self.ls.workspace.get_text_document.reset_mock()
    tokens2 = semantic_tokens_full(self.ls, params)
    self.assertEqual(tokens2.data, tokens.data)
    # Shouldn't require document lookup or validate again
    self.ls.workspace.get_text_document.assert_not_called()

  def test_hover_and_completion(self):
    from lsprotocol.types import HoverParams, CompletionParams, Position, TextDocumentIdentifier

    # 1. Setup a valid document that has fields, methods, parameters, etc.
    doc_uri = "file:///test.sp"
    doc_text = """
    struct Character {
      var health: int;
    }
    func test_func(char: Character) {
      char.health = char.health - 10;
    }
    """

    # Populate the LS caches by validating
    validate_source(self.ls, doc_uri, doc_text)
    self.assertIn(doc_uri, self.ls.ast_cache)
    self.assertIn(doc_uri, self.ls.node_types_cache)

    # 2. Test Hover on variable 'char' in `char.health = ...`
    # We test hover at line=5, character=7 (0-based)
    params_hover = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=7)
    )

    from src.lsp.server import hover
    res_hover = hover(self.ls, params_hover)
    self.assertIsNotNone(res_hover)
    self.assertIn("char", res_hover.contents.value)
    self.assertIn("Character", res_hover.contents.value)

    # Test Hover on field access 'health' in `char.health`
    # LSP line is 5, character is 26 (in right-hand `char.health`)
    params_hover_field = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=26)
    )
    res_hover_field = hover(self.ls, params_hover_field)
    self.assertIsNotNone(res_hover_field)
    self.assertIn("health", res_hover_field.contents.value)
    self.assertIn("int", res_hover_field.contents.value)

    # Test Hover on an invalid position
    params_hover_invalid = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=0)
    )
    res_hover_invalid = hover(self.ls, params_hover_invalid)
    self.assertIsNone(res_hover_invalid)

    # Test Hover when doc is not cached
    params_hover_uncached = HoverParams(
        text_document=TextDocumentIdentifier(uri="file:///uncached.sp"),
        position=Position(line=0, character=0)
    )
    self.assertIsNone(hover(self.ls, params_hover_uncached))

    # 3. Test Completion on 'char.'
    # The dot in `char.` on line 6 (LSP line 5, character 24)
    params_completion = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=25) # Position after the dot
    )

    from src.lsp.server import completion
    res_completion = completion(self.ls, params_completion)
    self.assertIsNotNone(res_completion)
    self.assertTrue(len(res_completion.items) > 0)

    # We expect 'health' as field suggestion
    field_item = next((item for item in res_completion.items if item.label == "health"), None)
    self.assertIsNotNone(field_item)
    self.assertEqual(field_item.kind, 10) # Field

    # Test Completion on invalid receiver position (no receiver expression found)
    params_completion_invalid = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=0)
    )
    res_completion_invalid = completion(self.ls, params_completion_invalid)
    self.assertEqual(len(res_completion_invalid.items), 0)

    # Test Completion when doc is not cached
    params_completion_uncached = CompletionParams(
        text_document=TextDocumentIdentifier(uri="file:///uncached.sp"),
        position=Position(line=0, character=0)
    )
    self.assertEqual(len(completion(self.ls, params_completion_uncached).items), 0)

  def test_hover_and_completion_edge_cases(self):
    from lsprotocol.types import HoverParams, CompletionParams, Position, TextDocumentIdentifier
    from parser.ast import ASTNode, IdentifierNode, ParameterNode, StructFieldNode, VarDeclNode, FuncDeclNode, BasicTypeNode
    from semantics.symbol_table import SymbolTable, VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol, StructType, StructField, StructMethod, FunctionType
    from src.lsp.semantic_tokens import find_node_at_position

    # 1. Test find_node_at_position edge cases
    # Node with no start_line
    node_no_lines = ASTNode()
    self.assertIsNone(find_node_at_position(node_no_lines, 1, 1))

    # Node with position
    node_with_pos = ASTNode()
    node_with_pos.start_line = 5
    node_with_pos.end_line = 5
    node_with_pos.start_column = 10
    node_with_pos.end_column = 20

    # Hover before start column
    self.assertIsNone(find_node_at_position(node_with_pos, 5, 5))

    # Hover after end column
    self.assertIsNone(find_node_at_position(node_with_pos, 5, 25))

    # Node attributes to skip: key in ("current_node", "lsp_errors", "raw_tokens", "node_types")
    node_with_pos.current_node = ASTNode()
    node_with_pos.lsp_errors = ASTNode()
    node_with_pos.raw_tokens = ASTNode()
    node_with_pos.node_types = ASTNode()
    # Query it to trigger the iteration and skipped attributes continue branch
    self.assertEqual(find_node_at_position(node_with_pos, 5, 15), node_with_pos)

    # 2. Test Hover edge cases with mocked caches
    doc_uri = "file:///mock.sp"
    self.ls.ast_cache[doc_uri] = node_with_pos
    self.ls.node_types_cache[doc_uri] = {} # Empty, so lookup in node_types fails

    # Mock symbol table
    sym_table = SymbolTable()
    self.ls.symbol_table_cache[doc_uri] = sym_table

    # Hovering on an IdentifierNode which is not in node_types but is in symbol_table
    ident_node = IdentifierNode("x")
    ident_node.start_line = 5
    ident_node.end_line = 5
    ident_node.start_column = 10
    ident_node.end_column = 20

    # Mock find_node_at_position to return ident_node
    with patch("src.lsp.server.find_node_at_position", return_value=ident_node):
      # Case A: sym is VariableSymbol (not parameter)
      sym_var = VariableSymbol("x", "int", is_mutable=True, is_parameter=False)
      sym_var.symbol_type = "int"
      sym_table.define("x", sym_var)

      params = HoverParams(
          text_document=TextDocumentIdentifier(uri=doc_uri),
          position=Position(line=4, character=15)
      )
      from src.lsp.server import hover
      res = hover(self.ls, params)
      self.assertIsNotNone(res)
      self.assertIn("(variable)", res.contents.value)

      # Case B: sym is VariableSymbol (is parameter)
      sym_param = VariableSymbol("x", "int", is_mutable=False, is_parameter=True)
      sym_param.symbol_type = "int"
      sym_table.current_scope.symbols["x"] = sym_param # Overwrite
      res = hover(self.ls, params)
      self.assertIsNotNone(res)
      self.assertIn("(parameter)", res.contents.value)

      # Case C: sym is FunctionSymbol
      sym_func = FunctionSymbol("x", FunctionType([], "void"))
      sym_func.symbol_type = "function_type"
      sym_table.current_scope.symbols["x"] = sym_func
      res = hover(self.ls, params)
      self.assertIsNotNone(res)
      self.assertIn("(function)", res.contents.value)

      # Case D: sym is StructSymbol
      sym_struct = StructSymbol("x", StructType("x"))
      sym_struct.symbol_type = "struct_type"
      sym_table.current_scope.symbols["x"] = sym_struct
      res = hover(self.ls, params)
      self.assertIsNotNone(res)
      self.assertIn("(struct)", res.contents.value)

      # Case E: sym is TraitSymbol
      from semantics.symbol_table import TraitType
      sym_trait = TraitSymbol("x", TraitType("x"))
      sym_trait.symbol_type = "trait_type"
      sym_table.current_scope.symbols["x"] = sym_trait
      res = hover(self.ls, params)
      self.assertIsNotNone(res)
      self.assertIn("(trait)", res.contents.value)

      # Case F: hover on ParameterNode directly
      param_node = ParameterNode(False, "p", BasicTypeNode("int"))
      param_node.start_line = 5
      param_node.end_line = 5
      param_node.start_column = 10
      param_node.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=param_node):
        self.ls.node_types_cache[doc_uri] = {param_node: "int"}
        res = hover(self.ls, params)
        self.assertIsNotNone(res)
        self.assertIn("(parameter)", res.contents.value)

      # Case G: hover on StructFieldNode directly
      field_node = StructFieldNode(True, "f", BasicTypeNode("int"))
      field_node.start_line = 5
      field_node.end_line = 5
      field_node.start_column = 10
      field_node.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=field_node):
        self.ls.node_types_cache[doc_uri] = {field_node: "int"}
        res = hover(self.ls, params)
        self.assertIsNotNone(res)
        self.assertIn("(property)", res.contents.value)

      # Case H: hover on VarDeclNode directly
      var_decl = VarDeclNode(True, "v", BasicTypeNode("int"), ASTNode())
      var_decl.start_line = 5
      var_decl.end_line = 5
      var_decl.start_column = 10
      var_decl.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=var_decl):
        self.ls.node_types_cache[doc_uri] = {var_decl: "int"}
        res = hover(self.ls, params)
        self.assertIsNotNone(res)
        self.assertIn("(variable)", res.contents.value)

      # Case I: hover on FuncDeclNode directly
      func_decl = FuncDeclNode("f", [], BasicTypeNode("int"), None)
      func_decl.start_line = 5
      func_decl.end_line = 5
      func_decl.start_column = 10
      func_decl.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=func_decl):
        self.ls.node_types_cache[doc_uri] = {func_decl: "func_type"}
        res = hover(self.ls, params)
        self.assertIsNotNone(res)
        self.assertIn("(function)", res.contents.value)

      # Case J: Hover on node with no resolved type (returns None)
      ident_node_y = IdentifierNode("y")
      ident_node_y.start_line = 5
      ident_node_y.end_line = 5
      ident_node_y.start_column = 10
      ident_node_y.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=ident_node_y):
        self.assertIsNone(hover(self.ls, params))

    # 3. Test Completion edge cases with mocked caches
    # Completion when receiver type lookup in node_types fails but exists in symbol table
    with patch("src.lsp.server.find_node_at_position", return_value=ident_node):
      # Reset node types to empty
      self.ls.node_types_cache[doc_uri] = {}

      # Make sym "x" a StructSymbol with fields/methods
      st_type = StructType("x")
      st_type.fields["f1"] = StructField("f1", "int", is_mutable=True)
      st_type.methods["m1"] = StructMethod("m1", FunctionType([], "void"), None)
      st_type.methods["__init__"] = StructMethod("__init__", FunctionType([], "void"), None) # should be skipped

      sym_struct = StructSymbol("x", st_type)
      sym_struct.symbol_type = st_type
      sym_table.current_scope.symbols["x"] = sym_struct

      params_comp = CompletionParams(
          text_document=TextDocumentIdentifier(uri=doc_uri),
          position=Position(line=4, character=21)
      )
      from src.lsp.server import completion
      res_comp = completion(self.ls, params_comp)
      self.assertIsNotNone(res_comp)
      self.assertEqual(len(res_comp.items), 2) # f1 and m1, __init__ skipped
      self.assertIsNone(next((item for item in res_comp.items if item.label == "__init__"), None))

      # Completion on receiver with no resolved type (returns empty list)
      ident_node_y = IdentifierNode("y")
      ident_node_y.start_line = 5
      ident_node_y.end_line = 5
      ident_node_y.start_column = 10
      ident_node_y.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=ident_node_y):
        self.assertEqual(len(completion(self.ls, params_comp).items), 0)

  def test_main(self):
    try:
      patch_path = "lsp.server.server.start_io"
      with patch(patch_path) as mock_start_io:
        main()
        mock_start_io.assert_called_once()
    except (ImportError, ModuleNotFoundError, AttributeError):  # pragma: no cover
      patch_path = "src.lsp.server.server.start_io"
      with patch(patch_path) as mock_start_io:
        main()
        mock_start_io.assert_called_once()


if __name__ == "__main__":
  unittest.main()
