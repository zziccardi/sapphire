import unittest
from unittest.mock import MagicMock, patch
from lsprotocol.types import SemanticTokensParams

# Import server components
from src.lsp.server import (
    SapphireLanguageServer,
    ANTLRDiagnosticListener,
    validate_source,
    did_open,
    did_change,
    did_save,
    semantic_tokens_full,
    definition,
    signature_help,
    main,
)



class TestLSPServer(unittest.TestCase):

  def setUp(self):
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
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

    # 4. did_change_watched_files
    from src.lsp.server import did_change_watched_files

    did_change_watched_files(self.ls, params)

  def test_semantic_tokens_full(self):
    doc_uri = "file:///test.sp"
    doc_text = "func test() { let opt_x: int? = none; while let x = 5; x < 5 { let y = x; } while let x ?= opt_x; x < 5 { let z = x; } }"

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
    // A player character in the game.
    struct Character {
      // The current health of the character.
      var health: int;
    }
    // A base game entity.
    proto Entity {
      let id: int;
    }
    // A contract for damageable entities.
    trait Damageable {
      /*
       * Inflicts damage on the entity.
       */
      func take_damage(var amount: int);
    }
    impl Character {
      /*
       * Damages the character by amount.
       * Decreases self.health.
       */
      func take_damage(var amount: int) {
        self.health = self.health - amount;
      }
    }
    // Implements Damageable for Character
    impl Damageable for Character {
      func take_damage(var amount: int) {
        self.health = self.health - amount;
      }
    }
    // Tests function functionality.
    // Also does some other tests.
    func test_func(char: Character) {
      let score: int = 100;
      char.health = char.health - 10;
      
      let opt_char: Character? = char;
      if let active ?= opt_char {
        let h: int = active.health;
      }
      
      let items = [1, 2, 3];
      for x in items {
        let val: int = x;
      }
      let c = Character(health=100);
      let d: Damageable = char;
    }
    // Another test function
    func another_func(char: Character) {
      test_func(char);
    }
    // This comment is separated by an empty line
    
    func no_param_func() {
    }
    """

    # Populate the LS caches by validating
    validate_source(self.ls, doc_uri, doc_text)
    self.assertIn(doc_uri, self.ls.ast_cache)
    self.assertIn(doc_uri, self.ls.node_types_cache)

    # 2. Test Hover on variable 'char' in `char.health = ...` (LHS of assignment)
    # We test hover at line=36, character=7 (0-based)
    params_hover = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=36, character=7)
    )

    from src.lsp.server import hover
    res_hover = hover(self.ls, params_hover)
    self.assertIsNotNone(res_hover)
    self.assertIn("char", res_hover.contents.value)
    self.assertIn("Character", res_hover.contents.value)

    # Test Hover on field access 'health' in LHS of assignment `char.health = ...`
    # LSP line is 36, character is 13 (in LHS `char.health`)
    params_hover_lhs_field = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=36, character=13)
    )
    res_hover_lhs_field = hover(self.ls, params_hover_lhs_field)
    self.assertIsNotNone(res_hover_lhs_field)
    self.assertIn("health", res_hover_lhs_field.contents.value)
    self.assertIn("int", res_hover_lhs_field.contents.value)
    self.assertIn("The current health of the character.", res_hover_lhs_field.contents.value)

    # Test Hover on variable declaration 'score' (LHS name of declaration)
    # LSP line is 35, character is 11 (in `score` inside `let score: int = ...`)
    params_hover_decl = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=35, character=11)
    )
    res_hover_decl = hover(self.ls, params_hover_decl)
    self.assertIsNotNone(res_hover_decl)
    self.assertIn("score", res_hover_decl.contents.value)
    self.assertIn("int", res_hover_decl.contents.value)

    # Test Hover on field access 'health' in RHS `char.health`
    # LSP line is 36, character is 26 (in right-hand `char.health`)
    params_hover_field = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=36, character=26)
    )
    res_hover_field = hover(self.ls, params_hover_field)
    self.assertIsNotNone(res_hover_field)
    self.assertIn("health", res_hover_field.contents.value)
    self.assertIn("int", res_hover_field.contents.value)
    self.assertIn("The current health of the character.", res_hover_field.contents.value)

    # Test Hover on 'if let' variable 'active'
    # LSP line is 39, character is 14 (inside `if let active = ...`)
    params_hover_if_let = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=39, character=14)
    )
    res_hover_if_let = hover(self.ls, params_hover_if_let)
    self.assertIsNotNone(res_hover_if_let)
    self.assertIn("active", res_hover_if_let.contents.value)
    self.assertIn("Character", res_hover_if_let.contents.value)

    # Test Hover on 'for' loop variable 'x'
    # LSP line is 44, character is 10 (inside `for x in ...`)
    params_hover_for = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=44, character=10)
    )
    res_hover_for = hover(self.ls, params_hover_for)
    self.assertIsNotNone(res_hover_for)
    self.assertIn("x", res_hover_for.contents.value)
    self.assertIn("int", res_hover_for.contents.value)

    # Test Hover on function name 'test_func' at call site
    # LSP line is 52, character is 7 (inside `test_func(char);`)
    params_hover_call = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=52, character=7)
    )
    res_hover_call = hover(self.ls, params_hover_call)
    self.assertIsNotNone(res_hover_call)
    self.assertIn("test_func", res_hover_call.contents.value)
    self.assertIn("Parameters:", res_hover_call.contents.value)
    self.assertIn("char: Character", res_hover_call.contents.value)
    self.assertIn("Returns: `none`", res_hover_call.contents.value)
    self.assertIn("Tests function functionality.", res_hover_call.contents.value)
    self.assertIn("Also does some other tests.", res_hover_call.contents.value)

    # Test Hover on function with no parameters
    # LSP line is 56, character is 10 (inside `no_param_func`)
    params_hover_no_param = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=56, character=10)
    )
    res_hover_no_param = hover(self.ls, params_hover_no_param)
    self.assertIsNotNone(res_hover_no_param)
    self.assertIn("no_param_func", res_hover_no_param.contents.value)
    self.assertIn("Parameters: none", res_hover_no_param.contents.value)
    self.assertNotIn("separated by an empty line", res_hover_no_param.contents.value)

    # Test Hover on method 'take_damage' declaration in impl block
    # LSP line is 22, character is 16 (inside `func take_damage`)
    params_hover_method = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=22, character=16)
    )
    res_hover_method = hover(self.ls, params_hover_method)
    self.assertIsNotNone(res_hover_method)
    self.assertIn("take_damage", res_hover_method.contents.value)
    self.assertIn("var amount: int", res_hover_method.contents.value)
    self.assertIn("Damages the character by amount.", res_hover_method.contents.value)
    self.assertIn("Decreases self.health.", res_hover_method.contents.value)

    # Test Hover on struct name declaration
    params_hover_struct = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=11)
    )
    res_hover_struct = hover(self.ls, params_hover_struct)
    self.assertIsNotNone(res_hover_struct)
    self.assertIn("struct", res_hover_struct.contents.value)
    self.assertIn("Character", res_hover_struct.contents.value)
    self.assertIn("A player character in the game.", res_hover_struct.contents.value)

    # Test Hover on proto name declaration
    params_hover_proto = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=7, character=10)
    )
    res_hover_proto = hover(self.ls, params_hover_proto)
    self.assertIsNotNone(res_hover_proto)
    self.assertIn("proto", res_hover_proto.contents.value)
    self.assertIn("Entity", res_hover_proto.contents.value)
    self.assertIn("A base game entity.", res_hover_proto.contents.value)

    # Test Hover on trait name declaration
    params_hover_trait = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=11, character=10)
    )
    res_hover_trait = hover(self.ls, params_hover_trait)
    self.assertIsNotNone(res_hover_trait)
    self.assertIn("trait", res_hover_trait.contents.value)
    self.assertIn("Damageable", res_hover_trait.contents.value)
    self.assertIn("A contract for damageable entities.", res_hover_trait.contents.value)

    # Test Hover on struct name in impl block
    params_hover_impl = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=17, character=9)
    )
    res_hover_impl = hover(self.ls, params_hover_impl)
    self.assertIsNotNone(res_hover_impl)
    self.assertIn("struct", res_hover_impl.contents.value)
    self.assertIn("Character", res_hover_impl.contents.value)
    self.assertIn("A player character in the game.", res_hover_impl.contents.value)

    # Test Hover on trait name in impl block (impl Damageable for Character)
    params_hover_impl_trait = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=27, character=9)
    )
    res_hover_impl_trait = hover(self.ls, params_hover_impl_trait)
    self.assertIsNotNone(res_hover_impl_trait)
    self.assertIn("trait", res_hover_impl_trait.contents.value)
    self.assertIn("Damageable", res_hover_impl_trait.contents.value)
    self.assertIn("A contract for damageable entities.", res_hover_impl_trait.contents.value)

    # Test Hover on type identifier reference in signature
    params_hover_ref = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=34, character=25)
    )
    res_hover_ref = hover(self.ls, params_hover_ref)
    self.assertIsNotNone(res_hover_ref)
    self.assertIn("struct", res_hover_ref.contents.value)
    self.assertIn("Character", res_hover_ref.contents.value)
    self.assertIn("A player character in the game.", res_hover_ref.contents.value)

    # Test Hover on instantiation call fallback lookup
    params_hover_instantiation = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=47, character=14)
    )
    res_hover_instantiation = hover(self.ls, params_hover_instantiation)
    self.assertIsNotNone(res_hover_instantiation)
    self.assertIn("struct", res_hover_instantiation.contents.value)
    self.assertIn("Character", res_hover_instantiation.contents.value)

    # Test Hover on trait type reference in variable declaration
    params_hover_trait_ref = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=48, character=13)
    )
    res_hover_trait_ref = hover(self.ls, params_hover_trait_ref)
    self.assertIsNotNone(res_hover_trait_ref)
    self.assertIn("trait", res_hover_trait_ref.contents.value)
    self.assertIn("Damageable", res_hover_trait_ref.contents.value)

    # Test Hover on struct field identifier declaration site (health)
    params_hover_field_decl = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=4, character=10)
    )
    res_hover_field_decl = hover(self.ls, params_hover_field_decl)
    self.assertIsNotNone(res_hover_field_decl)
    self.assertIn("property", res_hover_field_decl.contents.value)
    self.assertIn("health", res_hover_field_decl.contents.value)
    self.assertIn("int", res_hover_field_decl.contents.value)
    self.assertIn("The current health of the character.", res_hover_field_decl.contents.value)

    # Test Hover on trait method identifier declaration site (take_damage)
    params_hover_trait_method_decl = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=15, character=11)
    )
    res_hover_trait_method_decl = hover(self.ls, params_hover_trait_method_decl)
    self.assertIsNotNone(res_hover_trait_method_decl)
    self.assertIn("method", res_hover_trait_method_decl.contents.value)
    self.assertIn("take_damage", res_hover_trait_method_decl.contents.value)
    self.assertIn("Inflicts damage on the entity.", res_hover_trait_method_decl.contents.value)

    # Test Hover on an invalid position
    params_hover_invalid = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=60, character=0)
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
    # The dot in `char.` on line 37 (LSP line 36, character 25)
    mock_doc_main = MagicMock()
    mock_doc_main.uri = doc_uri
    mock_doc_main.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc_main

    params_completion = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=36, character=25) # Position after the dot
    )

    from src.lsp.server import completion
    res_completion = completion(self.ls, params_completion)
    self.assertIsNotNone(res_completion)
    self.assertTrue(len(res_completion.items) > 0)

    # We expect 'health' as field suggestion
    field_item = next((item for item in res_completion.items if item.label == "health"), None)
    self.assertIsNotNone(field_item)
    self.assertEqual(field_item.kind, 10) # Field

    # Test Scope Completion (suggests variables, parameters, functions, structs, types, keywords)
    params_completion_scope = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=35, character=15)
    )
    res_completion_scope = completion(self.ls, params_completion_scope)
    self.assertIsNotNone(res_completion_scope)
    self.assertTrue(len(res_completion_scope.items) > 0)
    
    labels = {item.label for item in res_completion_scope.items}
    self.assertIn("char", labels)
    self.assertIn("score", labels)
    self.assertIn("Character", labels)
    self.assertIn("test_func", labels)
    self.assertIn("int", labels)
    self.assertIn("let", labels)
    self.assertIn("match", labels)
    self.assertIn("yield", labels)

    # Test Scope Completion inside if-let block (active variable)
    res_iflet = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=40, character=10)
    ))
    labels_iflet = {item.label for item in res_iflet.items}
    self.assertIn("active", labels_iflet)

    # Test Scope Completion inside for-loop block (x variable)
    res_for = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=45, character=10)
    ))
    labels_for = {item.label for item in res_for.items}
    self.assertIn("x", labels_for)

    # Test Scope Completion inside impl block (self and method parameters)
    res_impl = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=23, character=2)
    ))
    labels_impl = {item.label for item in res_impl.items}
    self.assertIn("self", labels_impl)
    self.assertIn("amount", labels_impl)

    # Test Completion on optional type receiver
    from src.parser.ast import IdentifierNode
    from src.semantics.symbol_table import OptionalType, StructType
    mock_opt_node = IdentifierNode("opt_char_test")
    mock_opt_node.start_line = 38
    mock_opt_node.end_line = 38
    mock_opt_node.start_column = 15
    mock_opt_node.end_column = 23
    st_char = self.ls.symbol_table_cache[doc_uri].lookup_type("Character")
    self.ls.node_types_cache[doc_uri][mock_opt_node] = OptionalType(st_char)
    with patch("src.lsp.server.find_node_at_position", return_value=mock_opt_node):
      res_opt = completion(self.ls, CompletionParams(
          text_document=TextDocumentIdentifier(uri=doc_uri),
          position=Position(line=37, character=24)
      ))
      self.assertIn("health", {item.label for item in res_opt.items})

    # Test Completion inside impl block containing let, if-let, and for statements
    doc_impl_stmts = """
    struct Dummy { var val: int; }
    impl Dummy {
      func test_method(var p: int) {
        let local_var: int = 1;
        let opt_d: Dummy? = self;
        if let active_d ?= opt_d {
          let inner: int = 2;
        }
        let arr = [1, 2];
        for loop_i in arr {
          let in_loop: int = 3;
        }
      }
    }
    """
    validate_source(self.ls, doc_uri, doc_impl_stmts)
    mock_doc_impl = MagicMock()
    mock_doc_impl.uri = doc_uri
    mock_doc_impl.source = doc_impl_stmts
    self.ls.workspace.get_text_document.return_value = mock_doc_impl

    # Scope completion inside if-let in impl
    res_impl_iflet = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=7, character=10)
    ))
    labels_impl_iflet = {item.label for item in res_impl_iflet.items}
    self.assertIn("local_var", labels_impl_iflet)
    self.assertIn("active_d", labels_impl_iflet)

    # Scope completion inside for loop in impl
    res_impl_for = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=11, character=10)
    ))
    labels_impl_for = {item.label for item in res_impl_for.items}
    self.assertIn("loop_i", labels_impl_for)

    # Reset workspace mock and doc_text
    validate_source(self.ls, doc_uri, doc_text)
    mock_doc_reset = MagicMock()
    mock_doc_reset.uri = doc_uri
    mock_doc_reset.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc_reset

    # Test VariableSymbol in symbol table scope for completion
    from src.semantics.symbol_table import VariableSymbol, PrimitiveType
    self.ls.symbol_table_cache[doc_uri].define("temp_var", VariableSymbol("temp_var", PrimitiveType("int"), is_mutable=False))
    res_sym_var = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=35, character=15)
    ))
    self.assertIn("temp_var", {item.label for item in res_sym_var.items})

    # Test Completion when doc is not cached
    params_completion_uncached = CompletionParams(
        text_document=TextDocumentIdentifier(uri="file:///uncached.sp"),
        position=Position(line=0, character=0)
    )
    self.assertEqual(len(completion(self.ls, params_completion_uncached).items), 0)

    # 4. Test Completion fallback when document has syntax errors (incomplete receiver at current line)
    doc_text_err = """
    struct Character {
      var health: int;
    }
    func test_func(char: Character) {
      char.health = char.health - 10;
    }
    char.
    """
    validate_source(self.ls, doc_uri, doc_text_err)
    # Mock workspace.get_text_document to return the new document with syntax error
    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text_err
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Position at line 7 (LSP is 0-based), after "char." (character 9)
    params_completion_fallback = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=7, character=9)
    )
    res_comp_fallback = completion(self.ls, params_completion_fallback)
    self.assertIsNotNone(res_comp_fallback)
    self.assertTrue(len(res_comp_fallback.items) > 0)
    field_item_fallback = next((item for item in res_comp_fallback.items if item.label == "health"), None)
    self.assertIsNotNone(field_item_fallback)

  def test_hover_and_completion_edge_cases(self):
    from lsprotocol.types import HoverParams, CompletionParams, Position, TextDocumentIdentifier
    from src.parser.ast import ASTNode, IdentifierNode, ParameterNode, StructFieldNode, VarDeclNode, FuncDeclNode, BasicTypeNode
    from src.semantics.symbol_table import SymbolTable, VariableSymbol, FunctionSymbol, StructSymbol, TraitSymbol, StructType, StructField, StructMethod, FunctionType

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
      from src.semantics.symbol_table import TraitType

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

      # Test visit_IfNode fallback when condition is not OptionalType
      mock_if_node = MagicMock()
      mock_if_node.init_binding = MagicMock()
      mock_if_node.init_binding.is_unwrap = True
      mock_if_node.init_binding.let_name_line = 1
      mock_if_node.init_binding.let_name_column = 1
      mock_if_node.init_binding.let_name_length = 5
      mock_if_node.init_binding.expr = MagicMock()
      from src.lsp.semantic_tokens import SemanticTokensTypeChecker

      checker = SemanticTokensTypeChecker()
      from src.semantics.symbol_table import PrimitiveType

      with patch.object(checker, "visit", return_value=PrimitiveType("int")):
        with patch.object(checker, "symbol_table") as mock_st:
          checker.visit_IfNode(mock_if_node)
          self.assertEqual(checker.node_types[mock_if_node.init_binding], PrimitiveType("int"))

      # Test visit_ForNode fallback when iterable is not ArrayType
      mock_for_node = MagicMock()
      mock_for_node.is_mutable = False
      mock_for_node.loop_var_line = 1
      mock_for_node.loop_var_column = 1
      mock_for_node.loop_var_length = 5
      mock_for_node.iterable = MagicMock()
      with patch.object(checker, "visit", return_value=PrimitiveType("int")):
        with patch.object(checker, "symbol_table") as mock_st:
          checker.visit_ForNode(mock_for_node)
          self.assertEqual(checker.node_types[mock_for_node], PrimitiveType("none"))

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

      mock_doc_comp = MagicMock()
      mock_doc_comp.uri = doc_uri
      mock_doc_comp.source = "    let x = x.\n"
      self.ls.workspace.get_text_document.return_value = mock_doc_comp

      params_comp = CompletionParams(
          text_document=TextDocumentIdentifier(uri=doc_uri),
          position=Position(line=0, character=14)
      )
      from src.lsp.server import completion
      res_comp = completion(self.ls, params_comp)
      self.assertIsNotNone(res_comp)
      self.assertEqual(len(res_comp.items), 2) # f1 and m1, __init__ skipped
      self.assertIsNone(next((item for item in res_comp.items if item.label == "__init__"), None))

      from src.semantics.symbol_table import StringType, VariableSymbol

      sym_str = VariableSymbol("str_var", StringType(), is_mutable=False)
      sym_table.current_scope.symbols["str_var"] = sym_str

      mock_doc_comp_str = MagicMock()
      mock_doc_comp_str.uri = doc_uri
      mock_doc_comp_str.source = "    let y = str_var.\n"
      self.ls.workspace.get_text_document.return_value = mock_doc_comp_str

      params_comp_str = CompletionParams(
          text_document=TextDocumentIdentifier(uri=doc_uri),
          position=Position(line=0, character=20)
      )
      res_comp_str = completion(self.ls, params_comp_str)
      self.assertIsNotNone(res_comp_str)
      labels = [item.label for item in res_comp_str.items]
      self.assertIn("lower", labels)
      self.assertIn("split", labels)
      self.assertIn("find", labels)

      # Completion on receiver with no resolved type (falls back to scope completion)
      ident_node_y = IdentifierNode("y")
      ident_node_y.start_line = 5
      ident_node_y.end_line = 5
      ident_node_y.start_column = 10
      ident_node_y.end_column = 20
      with patch("src.lsp.server.find_node_at_position", return_value=ident_node_y):
        self.assertTrue(len(completion(self.ls, params_comp).items) > 0)

      # Completion fallback when get_text_document raises an exception
      with patch("src.lsp.server.find_node_at_position", return_value=None):
        self.ls.workspace.get_text_document.side_effect = Exception("Test get_text_document exception")
  def test_completion_typing_between_statements(self):
    doc_uri = "file:///between_test.sp"
    doc_text_between = """
    func test_func(char: Character) {
      let score: int = 100;

      let opt_char: Character? = char;
    }
    """
    validate_source(self.ls, doc_uri, doc_text_between)

    # Simulate user typing 'c' on line 3
    doc_text_typing_c = """
    func test_func(char: Character) {
      let score: int = 100;
      c
      let opt_char: Character? = char;
    }
    """
    validate_source(self.ls, doc_uri, doc_text_typing_c)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text_typing_c
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Position on line 3 (LSP 0-based line 3, character 7 after 'c')
    from lsprotocol.types import CompletionParams, TextDocumentIdentifier, Position
    params = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=3, character=7)
    )
    from src.lsp.server import completion
    res = completion(self.ls, params)
    self.assertIsNotNone(res)
    labels = {item.label for item in res.items}
    self.assertIn("char", labels)
    self.assertIn("score", labels)
    self.assertIn("Character", labels)
    self.assertIn("int", labels)
    self.assertIn("let", labels)

  def test_extract_comments_above(self):
    from src.lsp.semantic_tokens import extract_comments_above
    # Test line is None
    self.assertEqual(extract_comments_above("any text", None), "")
    # Test idx <= 0
    self.assertEqual(extract_comments_above("func foo()", 1), "")
    # Test single-line block comment
    doc = "/* Single-line block */\nfunc foo()"
    self.assertEqual(extract_comments_above(doc, 2), "Single-line block")

  def test_enum_lsp_hover_and_completion(self):
    """Verifies LSP hover and completion for enums and enum members."""
    from lsprotocol.types import HoverParams, CompletionParams, TextDocumentIdentifier, Position
    from src.lsp.server import hover, completion, validate_source


    doc_uri = "file:///enum_test.sp"
    doc_text = """// Cardinal Directions
enum Direction {
    North,
    East,
}
func test() {
    let d: Direction = Direction.North;
}
"""
    validate_source(self.ls, doc_uri, doc_text)

    # 1. Test Hover on Enum Declaration (line 1, col 5)
    params_hover_decl = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=1, character=5)
    )
    hover_res = hover(self.ls, params_hover_decl)
    self.assertIsNotNone(hover_res)
    self.assertIn("(enum)", hover_res.contents.value)
    self.assertIn("Direction", hover_res.contents.value)
    self.assertIn("Cardinal Directions", hover_res.contents.value)

    # 2. Test Hover on Enum Member Declaration (line 2, col 4 -> North)
    params_hover_member = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=4)
    )
    hover_res_m = hover(self.ls, params_hover_member)
    self.assertIsNotNone(hover_res_m)
    self.assertIn("North", hover_res_m.contents.value)

    # 3. Test Hover on EnumSymbol Identifier (line 6, col 11 -> Direction type annotation)
    params_hover_sym = HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=6, character=11)
    )
    hover_res_sym = hover(self.ls, params_hover_sym)
    self.assertIsNotNone(hover_res_sym)
    self.assertIn("Direction", hover_res_sym.contents.value)

    # 4. Test Dot Completion on Enum (line 6, col 33 -> "Direction.")
    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = """enum Direction {
    North,
    East,
}
func test() {
    let d = Direction.
}"""
    self.ls.workspace.get_text_document.return_value = mock_doc
    params_comp = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=22)
    )
    comp_res = completion(self.ls, params_comp)
    labels = [item.label for item in comp_res.items]
    self.assertIn("North", labels)
    self.assertIn("East", labels)

    # 5. Test Scope Completion (line 6, col 4 in empty function body)
    mock_doc_scope = MagicMock()
    mock_doc_scope.uri = doc_uri
    mock_doc_scope.source = """enum Direction { North }
func test() {
    
}"""
    self.ls.workspace.get_text_document.return_value = mock_doc_scope
    params_scope = CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=4)
    )
    scope_res = completion(self.ls, params_scope)
    scope_labels = [item.label for item in scope_res.items]
    self.assertIn("Direction", scope_labels)
    self.assertIn("enum", scope_labels)

  def test_annotation_hover_and_completion_and_semantic_tokens(self):
    """Verifies LSP server hover, completion, and semantic tokens for annotations."""
    doc_uri = "file:///annotations_test.sp"
    source = """
    trait Graphics {
      func clear(r: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    @export("love.update")
    func update(dt: float) {
      love.graphics.clear(dt);
    }
    """
    validate_source(self.ls, doc_uri, source)

    # 1. Semantic tokens cache check
    self.assertIn(doc_uri, self.ls.tokens_cache)
    tokens = self.ls.tokens_cache[doc_uri]
    self.assertTrue(len(tokens) > 0)

    # 2. Hover on @extern
    from lsprotocol.types import HoverParams, TextDocumentIdentifier, Position, CompletionParams
    from src.lsp.server import hover, completion


    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = source
    self.ls.workspace.get_text_document.return_value = mock_doc

    hover_extern = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=9, character=5)
    ))
    self.assertIsNotNone(hover_extern)
    self.assertIn("@extern", hover_extern.contents.value)
    self.assertIn("external variable", hover_extern.contents.value)

    # 3. Hover on @export
    hover_export = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=12, character=5)
    ))
    self.assertIsNotNone(hover_export)
    self.assertIn("@export", hover_export.contents.value)
    self.assertIn("global callback", hover_export.contents.value)

    # 4. Hover on extern variable love
    hover_love = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=9)
    ))
    self.assertIsNotNone(hover_love)
    self.assertIn("extern variable", hover_love.contents.value)

    # 6. Hover on custom annotation @custom
    custom_source = "@custom func foo() {}"
    validate_source(self.ls, "file:///custom_ann.sp", custom_source)
    mock_doc_custom = MagicMock()
    mock_doc_custom.uri = "file:///custom_ann.sp"
    mock_doc_custom.source = custom_source
    self.ls.workspace.get_text_document.return_value = mock_doc_custom
    hover_custom = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri="file:///custom_ann.sp"),
        position=Position(line=0, character=2)
    ))
    self.assertIsNotNone(hover_custom)
    self.assertIn("@custom", hover_custom.contents.value)

    # 7. Hover on enum identifier symbol
    enum_source = "enum Status { Active }\nvar current: Status = Status.Active;"
    validate_source(self.ls, "file:///enum_hover.sp", enum_source)
    mock_doc_enum = MagicMock()
    mock_doc_enum.uri = "file:///enum_hover.sp"
    mock_doc_enum.source = enum_source
    self.ls.workspace.get_text_document.return_value = mock_doc_enum
    hover_enum_id = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri="file:///enum_hover.sp"),
        position=Position(line=1, character=22)
    ))
    self.assertIsNotNone(hover_enum_id)

  def test_module_lsp_features(self):
    """Verifies LSP server diagnostics, hover, and completion for module imports and exports."""
    doc_uri = "file:///module_test.sp"
    code = """import lib.love2d.enums as e;

func create_player() {}

export {
  create_player,
  e.DrawMode,
}

func main() {
  let mode = e.DrawMode;
}
"""
    validate_source(self.ls, doc_uri, code)
    self.assertIn(doc_uri, self.ls.ast_cache)

    mod_sym = self.ls.symbol_table_cache[doc_uri].lookup("e")
    if mod_sym and hasattr(mod_sym, "exports"):
      from src.semantics.symbol_table import VariableSymbol, PrimitiveType
      mod_sym.exports["DrawMode"] = VariableSymbol("DrawMode", PrimitiveType("int"), is_mutable=False)

    # 1. Semantic Tokens
    from src.lsp.server import semantic_tokens_full, completion
    from lsprotocol.types import SemanticTokensParams, CompletionParams, TextDocumentIdentifier, Position

    tokens_res = semantic_tokens_full(self.ls, SemanticTokensParams(text_document=TextDocumentIdentifier(uri=doc_uri)))
    self.assertIsNotNone(tokens_res)
    self.assertTrue(len(tokens_res.data) > 0)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = code
    self.ls.workspace.get_text_document.return_value = mock_doc

    comp_res = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=15)
    ))
    self.assertIsNotNone(comp_res)
    self.assertIn("DrawMode", [i.label for i in comp_res.items])

  def test_missing_semicolon_after_match_lsp_diagnostic(self):
    """Verifies LSP diagnostics return helpful missing semicolon message for match statements."""
    doc_uri = "file:///missing_semi.sp"
    doc_text = """
    func main() {
      match 1 {
        1 -> { let a = 1; },
        ... -> { let b = 2; },
      }
      let y = 10;
    }
    """
    validate_source(self.ls, doc_uri, doc_text)
    self.ls.text_document_publish_diagnostics.assert_called_once()
    call_arg = self.ls.text_document_publish_diagnostics.call_args[0][0]
    self.assertTrue(len(call_arg.diagnostics) > 0)
    self.assertIn("Missing semicolon ';' after closing brace '}' of match expression", call_arg.diagnostics[0].message)

  def test_map_for_loop_lsp_completion(self):
    """Verifies LSP completion for key_var and val_var inside map for loops."""
    from lsprotocol.types import CompletionParams, Position, TextDocumentIdentifier
    from src.lsp.server import completion


    doc_uri = "file:///map_completion.sp"
    doc_text = """
    func main() {
      let my_map = {"a": 1};
      for map_k, map_v in my_map {
        let x = 10;
      }
    }
    struct TestStruct { var val: int; }
    impl TestStruct {
      func test_method() {
        let m = {"a": 1};
        for impl_k, impl_v in m {
          let y = 20;
        }
      }
    }
    """
    validate_source(self.ls, doc_uri, doc_text)
    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Completion inside top-level func map for loop
    res_func = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=4, character=10)
    ))
    labels_func = {item.label for item in res_func.items}
    self.assertIn("map_k", labels_func)

    # Completion inside impl block method map for loop
    res_impl = completion(self.ls, CompletionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=11, character=10)
    ))
    labels_impl = {item.label for item in res_impl.items}
    self.assertIn("impl_k", labels_impl)

  def test_impl_block_node_position_missing_fallback(self):
    """Verifies hover on ImplBlockNode gracefully handles missing position metadata."""
    from lsprotocol.types import HoverParams, TextDocumentIdentifier, Position
    from src.lsp.server import hover
    from src.parser.ast import ImplBlockNode

    doc_uri = "file:///impl_fallback.sp"
    doc_text = """
    struct Dummy {}
    impl Dummy {}
    """
    validate_source(self.ls, doc_uri, doc_text)

    # Remove position attributes from ImplBlockNode
    ast = self.ls.ast_cache.get(doc_uri)
    for decl in getattr(ast, "declarations", []):
      if isinstance(decl, ImplBlockNode):
        if hasattr(decl, "struct_name_line"):
          delattr(decl, "struct_name_line")

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Hover on impl block
    res_hover = hover(self.ls, HoverParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=9)
    ))
    self.assertIsNotNone(res_hover)
    self.assertIn("Dummy", res_hover.contents.value)

  def test_definition_variable_and_function(self):
    """Verifies Go to Definition for functions, parameters, and local variables."""
    from lsprotocol.types import DefinitionParams, TextDocumentIdentifier, Position

    doc_uri = "file:///def_test1.sp"
    doc_text = """func add(x: int, y: int) -> int {
  return x + y;
}
let total: int = add(10, 20);"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Go to Definition for 'add' on line 3 (0-indexed line 3, col 18)
    res_def = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=3, character=18)
    ))
    self.assertIsNotNone(res_def)
    self.assertEqual(res_def.uri, doc_uri)
    self.assertEqual(res_def.range.start.line, 0)
    self.assertEqual(res_def.range.start.character, 5)

    # Go to Definition for 'x' on line 1 (col 9)
    res_x = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=1, character=9)
    ))
    self.assertIsNotNone(res_x)
    self.assertEqual(res_x.range.start.line, 0)
    self.assertEqual(res_x.range.start.character, 9)

  def test_definition_struct_field_and_inheritance(self):
    """Verifies Go to Definition for struct types, fields, and inheritance parents."""
    from lsprotocol.types import DefinitionParams, TextDocumentIdentifier, Position

    doc_uri = "file:///def_test2.sp"
    doc_text = """struct Animal {
  var age: int;
}
struct Dog : Animal {
  var breed: String;
}
let d = Dog();
let a = d.age;"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Definition for 'Dog' on line 6 ('Dog()')
    res_dog = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=6, character=9)
    ))
    self.assertIsNotNone(res_dog)
    self.assertEqual(res_dog.range.start.line, 3)

    # Definition for 'Animal' parent on line 3 ('struct Dog : Animal')
    res_animal = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=3, character=14)
    ))
    self.assertIsNotNone(res_animal)
    self.assertEqual(res_animal.range.start.line, 0)

    # Definition for field access 'age' on line 7 ('d.age')
    res_age = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=7, character=11)
    ))
    self.assertIsNotNone(res_age)
    self.assertEqual(res_age.range.start.line, 1)

  def test_definition_enum_and_trait(self):
    """Verifies Go to Definition for enum types and enum variants."""
    from lsprotocol.types import DefinitionParams, TextDocumentIdentifier, Position

    doc_uri = "file:///def_test3.sp"
    doc_text = """enum Color { Red, Green, Blue }
let c = Color.Green;"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Definition for 'Color' on line 1
    res_color = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=1, character=9)
    ))
    self.assertIsNotNone(res_color)
    self.assertEqual(res_color.range.start.line, 0)

    # Definition for 'Color.Green' member on line 1
    res_green = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=1, character=15)
    ))
    self.assertIsNotNone(res_green)
    self.assertEqual(res_green.range.start.line, 0)

  def test_definition_none_for_missing(self):
    """Verifies definition returns None when symbol is unknown or position invalid."""
    from lsprotocol.types import DefinitionParams, TextDocumentIdentifier, Position

    doc_uri = "file:///def_missing.sp"
    doc_text = "let x = 42;"
    validate_source(self.ls, doc_uri, doc_text)

    # Non-existent URI
    res_bad = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri="file:///nonexistent.sp"),
        position=Position(line=0, character=0)
    ))
    self.assertIsNone(res_bad)

    # Out of bounds position
    res_oob = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=100, character=100)
    ))
    self.assertIsNone(res_oob)

  def test_signature_help_function_call(self):
    """Verifies signature help for function calls and active parameter tracking."""
    from lsprotocol.types import SignatureHelpParams, TextDocumentIdentifier, Position

    doc_uri = "file:///sig_test1.sp"
    doc_text = """func calculate(a: int, b: float, msg: String): bool {
  return true;
}
let res = calculate(10, 3.14, "hello");"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Signature help at parameter 0 ('calculate(10,')
    res_sig0 = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=3, character=22)
    ))
    self.assertIsNotNone(res_sig0)
    self.assertEqual(len(res_sig0.signatures), 1)
    self.assertEqual(res_sig0.active_parameter, 0)
    self.assertIn("calculate(a: int, b: float, msg: String) -> bool", res_sig0.signatures[0].label)

    # Signature help at parameter 1 ('calculate(10, 3.14,')
    res_sig1 = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=3, character=28)
    ))
    self.assertIsNotNone(res_sig1)
    self.assertEqual(res_sig1.active_parameter, 1)

  def test_signature_help_method_call(self):
    """Verifies signature help for method calls with 'self' parameter excluded."""
    from lsprotocol.types import SignatureHelpParams, TextDocumentIdentifier, Position

    doc_uri = "file:///sig_test2.sp"
    doc_text = """struct Point {
  var x: float;
  var y: float;
}
impl Point {
  func move(var self, dx: float, dy: float) {
    self.x = self.x + dx;
  }
}
let p = Point(1.0, 2.0);
p.move(5.0, 10.0);"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Signature help at parameter 1 in 'p.move(5.0, 10.0)'
    res_sig = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=13)
    ))
    self.assertIsNotNone(res_sig)
    self.assertEqual(res_sig.active_parameter, 1)
    # Check parameters count is 2 (dx, dy; self is excluded)
    params_labels = [p.label for p in res_sig.signatures[0].parameters]
    self.assertEqual(params_labels, ["dx: float", "dy: float"])

  def test_signature_help_constructor_and_none(self):
    """Verifies signature help for struct constructors and fallback when not in a call."""
    from lsprotocol.types import SignatureHelpParams, TextDocumentIdentifier, Position

    doc_uri = "file:///sig_test3.sp"
    doc_text = """struct Point {
  var x: float;
  var y: float;
}
let p = Point(1.0, 2.0);"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # Signature help for struct constructor 'Point(1.0,'
    from src.semantics.symbol_table import StructType, StructField, PrimitiveType
    validate_source(self.ls, doc_uri, doc_text)
    custom_st = StructType("OnlyType")
    custom_st.fields["val"] = StructField("val", PrimitiveType("int"), False)
    self.ls.symbol_table_cache[doc_uri].define_type("OnlyType", custom_st)

    res_ctor = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=4, character=17)
    ))
    self.assertIsNotNone(res_ctor)
    self.assertEqual(len(res_ctor.signatures[0].parameters), 2)

    # Signature help outside any call
    res_none = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=0)
    ))
    self.assertIsNone(res_none)

  def test_definition_additional_branches(self):
    """Cover additional definition branches (BasicTypeNode, ImplBlockNode, fallback positions, local declarations)."""
    from lsprotocol.types import DefinitionParams, TextDocumentIdentifier, Position

    doc_uri = "file:///def_branches.sp"
    doc_text = """struct Item { var id: int; }
trait Action { func do_it(self); }
impl Action for Item {
  func do_it(self) {
    let internal_val = 100;
    let copy_val = internal_val;
    let opt_val: Item? = self;
    if let active ?= opt_val {
      let active_use = active;
    }
    let list = [1, 2];
    for elem in list {
      let elem_use = elem;
    }
  }
}
let item_var: Item = Item(1);
let test_action: Action = item_var;
item_var.do_it();"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # 1. BasicTypeNode annotation 'Action' on line 17 ('let test_action: Action = ...')
    res_type = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=17, character=18)
    ))
    self.assertIsNotNone(res_type)
    self.assertEqual(res_type.range.start.line, 1)

    # 2. Local variable 'internal_val' on line 5
    res_local = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=5, character=20)
    ))
    self.assertIsNotNone(res_local)
    self.assertEqual(res_local.range.start.line, 4)

    # 3. IfNode init binding 'active' on line 8
    res_active = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=8, character=24)
    ))
    self.assertIsNotNone(res_active)
    self.assertEqual(res_active.range.start.line, 7)

    # 4. ForNode loop var 'elem' on line 12
    res_elem = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=12, character=22)
    ))
    self.assertIsNotNone(res_elem)
    self.assertEqual(res_elem.range.start.line, 11)

    # 5. Method call 'item_var.do_it()' on line 18
    res_method = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=18, character=11)
    ))
    self.assertIsNotNone(res_method)

    # 6. ImplBlockNode trait name 'Action' on line 2
    res_impl_trait = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=7)
    ))
    self.assertIsNotNone(res_impl_trait)

    # 7. ImplBlockNode struct name 'Item' on line 2
    res_impl_struct = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=2, character=18)
    ))
    self.assertIsNotNone(res_impl_struct)

    # 8. Fallback positioning when target_ast has no name_line
    ast = self.ls.ast_cache.get(doc_uri)
    for decl in getattr(ast, "declarations", []):
      if hasattr(decl, "name_line"):
        delattr(decl, "name_line")
    res_fallback = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=17, character=15)
    ))
    self.assertIsNotNone(res_fallback)

  def test_signature_help_additional_branches(self):
    """Cover string methods, constructor lookup, string quotes, and nested parens/brackets."""
    from lsprotocol.types import SignatureHelpParams, TextDocumentIdentifier, Position

    doc_uri = "file:///sig_branches.sp"
    doc_text = """struct Config {
  var port: int;
}
func calc(a: int, b: int): int { return a + b; }
func test() {
  let s = "hello world";
  s.split(",");
  let c = Config(8080);
  calc([1, 2], "esc\\\"quote", 3);
}"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # 1. String built-in method 's.split(",")'
    res_str = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=6, character=10)
    ))
    self.assertIsNotNone(res_str)
    self.assertIn("split", res_str.signatures[0].label)

    # 2. Constructor lookup by type name 'Config(8080)'
    res_ctor = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=7, character=17)
    ))
    self.assertIsNotNone(res_ctor)
    self.assertEqual(len(res_ctor.signatures[0].parameters), 1)

    # 3. String quotes with escaped quotes and bracket balance 'calc([1, 2], "esc\"quote", 3)'
    res_esc = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=8, character=30)
    ))
    self.assertIsNotNone(res_esc)
    self.assertEqual(res_esc.active_parameter, 2)

    # 4. Invalid callee regex match (e.g. + ( 10, ))
    mock_doc.source = "let x = + (10, 20);"
    res_invalid = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=15)
    ))
    self.assertIsNone(res_invalid)

  def test_server_100_percent_coverage(self):
    """Hits all remaining lines in server.py to reach 100% test coverage."""
    from lsprotocol.types import DefinitionParams, SignatureHelpParams, TextDocumentIdentifier, Position

    doc_uri = "file:///cov100.sp"
    doc_text = """struct Point {
  var x: int;
}
struct Container {
  var p: Point;
}
func top_process(p_param: Point) {
  let top_a = 1, top_b = 2;
  let top_c = top_a;
  while let active ?= p_param {
    let active_val = active;
  }
  let m = [1: 2];
  for k, v in m {
    let k_val = k;
    let v_val = v;
  }
}
impl Point {
  func process(p_param: Point) {
    let a = 1, b = 2;
    let c = a;
    while let active ?= p_param {
      let active_val = active;
    }
    let m = [1: 2];
    for k, v in m {
      let k_val = k;
      let v_val = v;
    }
  }
}
let pt_var = Point(10);
let c_var = Container(pt_var);
let field_ref = c_var.p.x;
"""

    validate_source(self.ls, doc_uri, doc_text)

    mock_doc = MagicMock()
    mock_doc.uri = doc_uri
    mock_doc.source = doc_text
    self.ls.workspace.get_text_document.return_value = mock_doc

    # 1. Top-level func WhileNode in _find_local_decl (lines 518-520)
    res_top_while = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=23)
    ))
    self.assertIsNotNone(res_top_while)

    # 2. Top-level func ForNode in _find_local_decl (lines 522-524)
    res_top_k = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=14, character=18)
    ))
    self.assertIsNotNone(res_top_k)
    res_top_v = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=15, character=18)
    ))
    self.assertIsNotNone(res_top_v)

    # 3. Top-level VarDeclNode match in _find_local_decl (lines 551-553)
    res_top_b = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=8, character=16)
    ))
    self.assertIsNotNone(res_top_b)

    # 4. sym.symbol_type.ast_decl when sym has no ast_decl (line 596)
    from src.semantics.symbol_table import VariableSymbol
    st_point = self.ls.symbol_table_cache[doc_uri].lookup_type("Point")
    sym_no_ast = VariableSymbol("var_no_ast", st_point, is_mutable=False)
    self.ls.symbol_table_cache[doc_uri].define("var_no_ast", sym_no_ast)

    mock_doc.source = "let use_no_ast = var_no_ast;"
    res_sym_type_ast = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=20)
    ))
    self.assertIsNotNone(res_sym_type_ast)

    # 5. Multi-name VarDeclNode inside func ('let c = a;')
    mock_doc.source = doc_text
    res_b = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=21, character=12)
    ))
    self.assertIsNotNone(res_b)

    # 6. WhileNode in _find_local_decl inside func ('let active_val = active;')
    res_while = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=23, character=23)
    ))
    self.assertIsNotNone(res_while)

    # 7. ForNode in _find_local_decl inside func ('let k_val = k;' and 'let v_val = v;')
    res_k = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=27, character=18)
    ))
    self.assertIsNotNone(res_k)
    res_v = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=28, character=18)
    ))
    self.assertIsNotNone(res_v)

    # 4. ImplBlockNode parameter match in _find_local_decl ('while let active ?= p_param')
    res_p_param = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=10, character=24)
    ))
    self.assertIsNotNone(res_p_param)

    # 5. sym.symbol_type.ast_decl ('let c_var = Container(pt_var)')
    res_sym_type = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=21, character=5)
    ))
    self.assertIsNotNone(res_sym_type)

    # 6. MemberAccessNode receiver symbol lookup & field match ('c_var.p.x')
    res_field = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=22, character=24)
    ))
    self.assertIsNotNone(res_field)

    # 7. StructDeclNode fallback target_ast = node
    res_struct = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=7)
    ))
    self.assertIsNotNone(res_struct)

    # 8. ImplBlockNode parameter match in _find_local_decl (line 534)
    res_p_param_impl = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=22, character=24)
    ))
    self.assertIsNotNone(res_p_param_impl)

    # 9. sym.symbol_type.ast_decl when sym has no ast_decl (line 596)
    from src.semantics.symbol_table import VariableSymbol, StructType
    from src.parser.ast import StructDeclNode
    mock_doc.source = "let use_no_ast = var_no_ast;"
    validate_source(self.ls, doc_uri, mock_doc.source)

    target_struct = StructDeclNode("Point", [], [])
    target_struct.name_line = 1
    target_struct.name_column = 0
    target_struct.name_length = 5
    st_point = StructType("Point", ast_decl=target_struct)

    sym_no_ast = VariableSymbol("var_no_ast", st_point, is_mutable=False)
    self.ls.symbol_table_cache[doc_uri].define("var_no_ast", sym_no_ast)

    res_sym_type_ast = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=17)
    ))
    self.assertIsNotNone(res_sym_type_ast)

    # 10. Direct _find_local_decl test for top-level VarDeclNode & missing variable (lines 551-553)
    from src.lsp.server import _find_local_decl
    from src.parser.ast import VarDeclNode
    top_var_decl = VarDeclNode(False, ["top_g1", "top_g2"], [], [])
    top_ast = self.ls.ast_cache[doc_uri]
    top_ast.declarations.append(top_var_decl)
    res_local_top = _find_local_decl(top_ast, "top_g2", 1)
    self.assertEqual(res_local_top, top_var_decl)
    res_none_local = _find_local_decl(top_ast, "nonexistent_var_123", 1)
    self.assertIsNone(res_none_local)

    # 11. Direct _find_local_decl test for ImplBlockNode parameter (line 534)
    validate_source(self.ls, doc_uri, doc_text)
    impl_ast = self.ls.ast_cache[doc_uri]
    res_impl_p = _find_local_decl(impl_ast, "p_param", 20)
    self.assertIsNotNone(res_impl_p)

    # 11. MemberAccessNode struct field match (lines 620-621)
    mock_doc.source = doc_text
    validate_source(self.ls, doc_uri, doc_text)
    res_field_match = definition(self.ls, DefinitionParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=34, character=24)
    ))
    self.assertIsNotNone(res_field_match)

    # 12. SignatureHelp constructor lookup by lookup_type (lines 836-841)
    from src.semantics.symbol_table import StructType, StructField, PrimitiveType
    mock_doc.source = "OnlyType("
    validate_source(self.ls, doc_uri, mock_doc.source)

    custom_st = StructType("OnlyType")
    custom_st.fields["val"] = StructField("val", PrimitiveType("int"), False)
    self.ls.symbol_table_cache[doc_uri].define_type("OnlyType", custom_st)

    res_ctor = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=9)
    ))
    self.assertIsNotNone(res_ctor)

    # 9. SignatureHelp method lookup via receiver_type.methods without get_method (lines 813-814)
    from src.semantics.symbol_table import VariableSymbol, FunctionType, PrimitiveType
    class SimpleObj:
      def __init__(self):
        fn_t = FunctionType([PrimitiveType("int")], PrimitiveType("none"), param_names=["x"])
        self.methods = {"simple_m": fn_t}

    sym_simple = VariableSymbol("obj_simple", SimpleObj(), is_mutable=False)
    self.ls.symbol_table_cache[doc_uri].define("obj_simple", sym_simple)

    mock_doc.source = "obj_simple.simple_m("
    res_simple_m = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=0, character=20)
    ))
    self.assertIsNotNone(res_simple_m)

    # 10. SignatureHelp fallback when func_type is None/invalid (line 844)
    mock_doc.source = "let dummy = 5;\ndummy("
    res_not_fn = signature_help(self.ls, SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=doc_uri),
        position=Position(line=1, character=6)
    ))
    self.assertIsNone(res_not_fn)


if __name__ == "__main__":
  unittest.main()
