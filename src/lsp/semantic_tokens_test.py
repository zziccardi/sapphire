"""Unit tests for Sapphire semantic tokens extraction and encoding.

This module validates that positioning coordinates are correctly extracted from AST
nodes and delta-encoded into standard LSP 5-integer arrays.
"""

import unittest
import sys
import os

# Insert workspace src directory into python path to allow direct imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from antlr4 import InputStream, CommonTokenStream
try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from lsp.semantic_tokens import (
      SemanticTokensTypeChecker,
      encode_semantic_tokens,
  )
except ImportError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.lsp.semantic_tokens import (
      SemanticTokensTypeChecker,
      encode_semantic_tokens,
  )


class TestSemanticTokens(unittest.TestCase):
  """Unit tests for Sapphire semantic tokens extraction and encoding."""

  def test_delta_encoding_single_line(self):
    """Verifies relative encoding of multiple tokens on the same line."""
    # Format: (line, col, length, type_str, mods)
    # Note: ANTLR lines are 1-based, columns are 0-based
    raw = [
        (1, 4, 3, "struct", 1),    # line 1 (0 in LSP), col 4, len 3
        (1, 12, 6, "variable", 0),  # line 1 (0 in LSP), col 12, len 6
    ]
    # Expected:
    # 1. line 0, col 4, len 3, struct(2), declaration(1)
    # 2. line 0, col 8 (12-4), len 6, variable(5), none(0)
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 4, 3, 2, 1, 0, 8, 6, 5, 0])

  def test_delta_encoding_multi_line(self):
    """Verifies relative encoding of tokens across multiple lines."""
    raw = [
        (1, 2, 3, "keyword", 0),  # line 1 (0 in LSP), col 2, len 3
        (2, 5, 4, "variable", 4), # line 2 (1 in LSP), col 5, len 4 (readonly=4)
    ]
    # Expected:
    # 1. line 0, col 2, len 3, keyword(9), none(0)
    # 2. line 1 (2-1), col 5 (absolute since line changed), len 4, variable(5), readonly(4)
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 2, 3, 9, 0, 1, 5, 4, 5, 4])

  def test_delta_encoding_sorting(self):
    """Verifies tokens are sorted correctly before delta encoding."""
    raw = [
        (2, 5, 4, "variable", 0),
        (1, 2, 3, "keyword", 0),
    ]
    # Should sort first: line 1, then line 2
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 2, 3, 9, 0, 1, 5, 4, 5, 0])

  def test_token_extraction(self):
    """Verifies that parsing a program extracts correct semantic tokens."""
    code = "let speed: int = 42;"
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()

    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker()
    checker.check(ast)

    # We expect:
    # - 'speed' variable declaration (line 1, col 4, len 5, variable, mods=5 (declaration=1 | readonly=4))
    # - 'int' type reference (line 1, col 11, len 3, type, mods=0)
    raw = checker.raw_tokens

    # Check that we got our expected tokens
    var_token = next((t for t in raw if t[3] == "variable"), None)
    self.assertIsNotNone(var_token)
    self.assertEqual(var_token[0], 1)
    self.assertEqual(var_token[1], 4)
    self.assertEqual(var_token[2], 5)
    self.assertEqual(var_token[4], 5)  # declaration (1) + readonly (4) = 5

    type_token = next((t for t in raw if t[3] == "type"), None)
    self.assertIsNotNone(type_token)
    self.assertEqual(type_token[0], 1)
    self.assertEqual(type_token[1], 11)
    self.assertEqual(type_token[2], 3)

  def test_default_error_position(self):
    """Verifies that checker.error works correctly when current_node is None or lacks positions."""
    checker = SemanticTokensTypeChecker()
    # 1. current_node is None
    checker.current_node = None
    checker.error("Test error 1")
    self.assertEqual(len(checker.lsp_errors), 1)
    self.assertEqual(checker.lsp_errors[0]["range"]["start"]["line"], 0)
    self.assertEqual(checker.lsp_errors[0]["range"]["start"]["character"], 0)

    # 2. current_node is not None but lacks start_line
    from parser.ast import ASTNode
    node = ASTNode()
    checker.current_node = node
    checker.error("Test error 2")
    self.assertEqual(len(checker.lsp_errors), 2)
    self.assertEqual(checker.lsp_errors[1]["range"]["start"]["line"], 0)

  def test_deduplicate_identical_positions(self):
    """Verifies deduplication of semantic tokens sharing the same start position."""
    raw = [
        (1, 5, 3, "variable", 1),
        (1, 5, 3, "keyword", 0),
    ]
    encoded = encode_semantic_tokens(raw)
    self.assertEqual(encoded, [0, 5, 3, 5, 1])

  def test_complex_token_extraction(self):
    """Parses and checks a complex Sapphire program to cover trait, struct, impl, static methods, and member access."""
    code = """
    trait Damageable {
      func take_damage(amount: int);
    }

    struct Entity {
      let id: int;
    }

    struct Character : Entity {
      var health: int;
    }

    impl Damageable for Character {
      static func create() : Character {
        return Character { id = 1, health = 100 };
      }

      func take_damage(amount: int) {
        var mutable_amt = amount;
        mutable_amt = mutable_amt - 1;
        let constant_id = self.id;
        self.health = self.health - mutable_amt;
      }
    }

    func process_character(var char: Character) {
      char.take_damage(10);
    }

    func test_func(param: int) {
      // Covers immutable parameter in global function visitor
    }

    func run_pipeline() {
      let c = Character.create();
      process_character(c);
      test_func(1);
      let handler: Damageable? = none;
      
      // Intentionally trigger a semantic type mismatch to test error diagnostics with position
      let error_trigger: int = "trigger-string";
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()

    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker()
    # Expected type error, check should raise SemanticError
    from semantics.type_checker import SemanticError
    with self.assertRaises(SemanticError):
      checker.check(ast)

    raw = checker.raw_tokens

    # 1. Trait 'Damageable' declaration (interface)
    self.assertTrue(any(t[3] == "interface" and t[4] == 1 for t in raw))

    # 2. Trait member 'take_damage' (method)
    self.assertTrue(any(t[3] == "method" and t[4] == 1 for t in raw))

    # 3. Struct 'Character' declaration (struct)
    self.assertTrue(any(t[3] == "struct" and t[4] == 1 for t in raw))

    # 4. Struct field 'health' declaration (property)
    self.assertTrue(any(t[3] == "property" and t[4] == 1 for t in raw))

    # 5. Parent struct 'Entity' reference in Character declaration
    self.assertTrue(any(t[3] == "struct" and t[2] == len("Entity") for t in raw))

    # 6. Constant/immutable field 'id' declaration (property with readonly=4)
    # declaration (1) + readonly (4) = 5
    self.assertTrue(any(t[3] == "property" and t[4] == 5 and t[2] == len("id") for t in raw))

    # 7. Impl member static function 'create' (static method)
    # declaration (1) + static (2) = 3
    self.assertTrue(any(t[3] == "method" and t[4] == 3 for t in raw))

    # 8. Struct initializer
    self.assertTrue(any(t[3] == "struct" and t[4] == 0 and t[2] == len("Character") for t in raw))

    # 9. Member access: 'self.health' (property access)
    self.assertTrue(any(t[3] == "property" and t[4] == 0 and t[2] == len("health") for t in raw))

    # 10. Global function 'process_character' (function declaration)
    self.assertTrue(any(t[3] == "function" and t[4] == 1 and t[2] == len("process_character") for t in raw))

    # 11. Global function reference 'process_character(c)' (function reference)
    self.assertTrue(any(t[3] == "function" and t[4] == 0 and t[2] == len("process_character") for t in raw))

    # 12. Trait type annotation reference 'Damageable?' (interface reference via OptionalTypeNode and generic_visit)
    self.assertTrue(any(t[3] == "interface" and t[4] == 0 and t[2] == len("Damageable") for t in raw))

    # 13. Verify error position is captured correctly on lines 85, 87, 89
    self.assertTrue(len(checker.lsp_errors) > 0)
    type_mismatch_err = next((e for e in checker.lsp_errors if "Cannot assign expression of type" in e["message"]), None)
    self.assertIsNotNone(type_mismatch_err)
    self.assertGreater(type_mismatch_err["range"]["start"]["line"], 0)
    self.assertGreater(type_mismatch_err["range"]["end"]["character"], 0)

  def test_mock_symbol_lookups(self):
    """Verifies VariableSymbol, TraitSymbol, FunctionSymbol and other lookups in visit_IdentifierNode."""
    from parser.ast import IdentifierNode
    from semantics.symbol_table import TraitSymbol, TraitType, FunctionSymbol, FunctionType, VariableSymbol, PrimitiveType

    checker = SemanticTokensTypeChecker()
    checker.symbol_table.enter_scope()

    # 1. TraitSymbol
    trait_type = TraitType("MyTrait")
    checker.symbol_table.define("MyTrait", TraitSymbol("MyTrait", trait_type))
    node_trait = IdentifierNode("MyTrait")
    node_trait.name_line = 1
    node_trait.name_column = 0
    node_trait.name_length = 7
    checker.visit(node_trait)
    self.assertTrue(any(t[3] == "interface" for t in checker.raw_tokens))

    # 2. FunctionSymbol
    sig = FunctionType([], PrimitiveType("none"))
    checker.symbol_table.define("my_func", FunctionSymbol("my_func", sig))
    node_func = IdentifierNode("my_func")
    node_func.name_line = 2
    node_func.name_column = 0
    node_func.name_length = 7
    checker.visit(node_func)
    self.assertTrue(any(t[3] == "function" for t in checker.raw_tokens))

    # 3. VariableSymbol parameter vs variable
    checker.symbol_table.define("param1", VariableSymbol("param1", PrimitiveType("int"), is_mutable=True, is_parameter=True))
    node_param = IdentifierNode("param1")
    node_param.name_line = 3
    node_param.name_column = 0
    node_param.name_length = 6
    checker.visit(node_param)
    self.assertTrue(any(t[3] == "parameter" and t[4] == 0 for t in checker.raw_tokens))

  def test_enum_semantic_tokens(self):
    """Verifies semantic token extraction for enum declarations and member usage."""
    code = """
    enum Direction {
        North,
        East,
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    token_types = [t[3] for t in checker.raw_tokens]
    self.assertIn("enum", token_types)
    self.assertIn("enumMember", token_types)

  def test_generics_semantic_tokens(self):
    """Verifies semantic token extraction for generic struct initializers, generic function calls, and BasicTypeNode type_args."""
    code = """
    struct Box<T> {
      var val: T;
    }
    func identity<T>(val: T): T {
      return val;
    }
    func main() {
      let b = Box<int> { val = 10 };
      let x = identity<float>(3.14);
      let b2: Box<int> = Box<int> { val = 20 };
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    token_types = [t[3] for t in checker.raw_tokens]
    self.assertIn("struct", token_types)
    self.assertIn("function", token_types)
    self.assertIn("type", token_types)

  def test_map_for_loop_semantic_tokens(self):
    """Verifies semantic token extraction for map for-loop with key and val variables."""
    code = """
    func main() {
      let m = {"a": 1};
      for k, v in m {
        print(k);
      }
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    token_types = [t[3] for t in checker.raw_tokens]
    self.assertIn("variable", token_types)

  def test_multi_parent_semantic_tokens(self):
    """Verifies semantic token extraction for multi-parent struct declarations."""
    code = """
    struct Pos { var x: int; }
    struct Health { var hp: int; }
    struct Player: Pos, Health { var name: String; }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    pos_tokens = [t for t in checker.raw_tokens if t[3] == "struct" and t[2] == len("Pos")]
    health_tokens = [t for t in checker.raw_tokens if t[3] == "struct" and t[2] == len("Health")]
    self.assertTrue(len(pos_tokens) >= 1)
    self.assertTrue(len(health_tokens) >= 1)
