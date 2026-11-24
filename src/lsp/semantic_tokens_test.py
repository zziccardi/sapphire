"""Unit tests for Sapphire semantic tokens extraction and encoding.

This module validates that positioning coordinates are correctly extracted from AST
nodes and delta-encoded into standard LSP 5-integer arrays.
"""

import os
import sys
import tempfile
import unittest

# Insert workspace src directory into python path to allow direct imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from antlr4 import CommonTokenStream, InputStream

from src.lsp.semantic_tokens import (
  SemanticTokensTypeChecker,
  encode_semantic_tokens,
)
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser


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
    from src.parser.ast import ASTNode

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
    from src.semantics.type_checker import SemanticError

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
    from src.parser.ast import IdentifierNode
    from src.semantics.symbol_table import (
      FunctionSymbol,
      FunctionType,
      PrimitiveType,
      TraitSymbol,
      TraitType,
      VariableSymbol,
    )


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

  def test_interpolated_string_semantic_token_positions(self):
    """Verifies interpolated string expressions emit tokens at their actual file line/column, not line 1."""
    code = (
        "// Module for managing combat calculations and attack rounds.\n"
        "struct Stats { var hp: int; }\n"
        "func log_hp(stats: Stats) {\n"
        '  print(f"HP: {stats.hp}");\n'
        "}\n"
    )
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    # Line 1 is a comment and must have zero semantic tokens
    line_1_tokens = [t for t in checker.raw_tokens if t[0] == 1]
    self.assertEqual(line_1_tokens, [])

    # Line 4 ('  print(f"HP: {stats.hp}");') should have tokens for 'stats' (col 15) and 'hp' (col 21)
    line_4_tokens = [t for t in checker.raw_tokens if t[0] == 4]
    self.assertIn((4, 15, 5, "parameter", 4), line_4_tokens)
    self.assertIn((4, 21, 2, "property", 0), line_4_tokens)

  def test_imported_generic_monomorphization_does_not_leak_tokens(self):
    """Verifies monomorphizing imported generic functions (e.g. std.math) does not emit tokens at imported lines."""
    comment_lines = "\n".join(f"// Comment line {i}" for i in range(1, 35))
    code = (
        f"{comment_lines}\n"
        "import lib.std.math;\n"
        "func calc(a: int, b: int): int {\n"
        "  return math.max(a, b) + math.floor(1.5) + math.ceil(1.5);\n"
        "}\n"
    )
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    # Lines 1..34 are all comments and must have zero semantic tokens (even though math.max is on lines 27-32 of math.sp)
    comment_tokens = [t for t in checker.raw_tokens if t[0] <= 34]
    self.assertEqual(comment_tokens, [])

  def test_multi_binding_if_and_guard_and_move_no_false_errors(self):
    """Verifies multi-binding if/guard headers, if-var mutability, and move."""
    code = """
    struct DagNode {
      let label: String;
      let parent: WeakRef<DagNode>?;
    }

    func get_opt(flag: bool): int? {
      if flag {
        return 10;
      }
      return none;
    }

    func check_headers(var opt_int: int?) {
      let root = SharedRef(DagNode { label = "root", parent = none });
      let leaf = SharedRef(DagNode {
        label = "leaf",
        parent = root.downgrade(),
      });
      let shared_alias = leaf.share();
      if let p ?= shared_alias.parent; let up ?= p.upgrade() {
        print(up.label);
      }

      guard let gp ?= shared_alias.parent; let gup ?= gp.upgrade() else {
        return;
      }
      print(gup.label);

      if var mut_val ?= opt_int {
        mut_val = mut_val + 1;
      }

      if let typed_p: int ?= get_opt(true) {
        print(String.from(typed_p));
      }

      if let a, b = [1, 2]; a < b {
        print(String.from(a + b));
      }

      let r = Ref(10);
      if let owned = move r; owned.valueOf() == 10 {
        print("moved");
      }
    }
    """
    # Wait: owned is int inside Ref(10)? No, Ref(10) is Ref<int>, so owned is Ref<int>,
    # use a simple struct with __del__ or Ref<DagNode> instead of .valueOf()!
    code = code.replace("owned.valueOf() == 10", "true")
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)

    self.assertEqual(checker.lsp_errors, [])

    # Verify mut_val (line 30) has declaration modifier (1) without readonly (4)
    lines = code.splitlines()
    mut_line = next(i + 1 for i, ln in enumerate(lines) if "if var mut_val" in ln)
    mut_col = lines[mut_line - 1].index("mut_val")
    mut_tok = next(
        (t for t in checker.raw_tokens if t[0] == mut_line and t[1] == mut_col),
        None,
    )
    self.assertEqual(mut_tok, (mut_line, mut_col, len("mut_val"), "variable", 1))

    # Verify p and up (line 21) have declaration | readonly (5)
    if_line = next(i + 1 for i, ln in enumerate(lines) if "if let p ?=" in ln)
    p_col = lines[if_line - 1].index("p ?=")
    up_col = lines[if_line - 1].index("up ?=")
    p_tok = next(
        (t for t in checker.raw_tokens if t[0] == if_line and t[1] == p_col),
        None,
    )
    up_tok = next(
        (t for t in checker.raw_tokens if t[0] == if_line and t[1] == up_col),
        None,
    )
    self.assertEqual(p_tok, (if_line, p_col, 1, "variable", 5))
    self.assertEqual(up_tok, (if_line, up_col, 2, "variable", 5))

    # Verify guard let bindings (gp, gup) receive declaration | readonly tokens
    g_line = next(i + 1 for i, ln in enumerate(lines) if "guard let gp ?=" in ln)
    gp_col = lines[g_line - 1].index("gp ?=")
    gup_col = lines[g_line - 1].index("gup ?=")
    gp_tok = next(
        (t for t in checker.raw_tokens if t[0] == g_line and t[1] == gp_col),
        None,
    )
    gup_tok = next(
        (t for t in checker.raw_tokens if t[0] == g_line and t[1] == gup_col),
        None,
    )
    self.assertEqual(gp_tok, (g_line, gp_col, 2, "variable", 5))
    self.assertEqual(gup_tok, (g_line, gup_col, 3, "variable", 5))

  def test_all_samples_have_zero_lsp_errors(self):
    """Ensures every .sp sample parses and checks cleanly with zero LSP errors."""
    import pathlib

    samples_dir = pathlib.Path(__file__).resolve().parents[2] / "samples"
    sample_files = sorted(samples_dir.glob("**/*.sp"))
    self.assertTrue(sample_files)

    for sample_path in sample_files:
      with self.subTest(sample=sample_path.name):
        code = sample_path.read_text(encoding="utf-8")
        input_stream = InputStream(code)
        lexer = SapphireLexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = SapphireParser(stream)
        tree = parser.program()
        ast = ASTBuilder().visit(tree)

        checker = SemanticTokensTypeChecker(
            doc_text=code, source_file_path=str(sample_path)
        )
        checker.check(ast)
        self.assertEqual(checker.lsp_errors, [])

  def test_imported_module_error_anchored_on_import_line(self):
    """Ensures imported-module diagnostics anchor to the import statement in LSP."""
    import os
    import tempfile

    from src.common.errors import SemanticError
    from src.semantics.declaration_pass import DeclarationPass

    DeclarationPass.clear_cache()
    with tempfile.TemporaryDirectory() as tmpdir:
      dep_sp = os.path.join(tmpdir, "broken_dep.sp")
      with open(dep_sp, "w", encoding="utf-8") as f:
        f.write(
            "\n\n\n\n"
            "func fail_on_line_5() {\n"
            "  let bad: int = \"nope\";\n"
            "}\n"
        )

      main_sp = os.path.join(tmpdir, "main.sp")
      code = "import broken_dep;\nfunc ok() {}\n"
      lexer = SapphireLexer(InputStream(code))
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      ast = ASTBuilder().visit(parser.program())

      checker = SemanticTokensTypeChecker(
          doc_text=code, source_file_path=main_sp
      )
      with self.assertRaises(SemanticError):
        checker.check(ast)

      self.assertEqual(len(checker.lsp_errors), 1)
      self.assertEqual(checker.lsp_errors[0]["range"]["start"]["line"], 0)
      self.assertIn(
          "Imported module 'broken_dep' contains syntax or semantic errors.",
          checker.lsp_errors[0]["message"],
      )
      self.assertNotIn(
          os.path.abspath(dep_sp), DeclarationPass._module_cache
      )

  def test_module_let_constant_tokens_in_defaults_not_duplicated(self):
    """Verifies module let constant tokens highlight once and resolve inside struct and param defaults."""
    code = (
        "let STANDING_FRAME: int = 1;\n"
        "struct Character {\n"
        "  var frame: int = STANDING_FRAME;\n"
        "}\n"
        "func reset(frame: int = STANDING_FRAME) {}\n"
    )
    lexer = SapphireLexer(InputStream(code))
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    ast = ASTBuilder().visit(parser.program())

    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)
    self.assertEqual(checker.lsp_errors, [])

    decl_tok = (1, 4, len("STANDING_FRAME"), "variable", 5)
    self.assertEqual(checker.raw_tokens.count(decl_tok), 1)

    struct_default_tok = (3, 19, len("STANDING_FRAME"), "variable", 4)
    param_default_tok = (5, 24, len("STANDING_FRAME"), "variable", 4)
    self.assertEqual(checker.raw_tokens.count(struct_default_tok), 1)
    self.assertEqual(checker.raw_tokens.count(param_default_tok), 1)

  def test_qualified_ancestor_dispatch_tokens(self):
    """Verifies semantic tokens for Base.method(self) and mod.Base.method(self)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      base_sp = os.path.join(tmp_dir, "base_mod.sp")
      main_sp = os.path.join(tmp_dir, "main.sp")
      with open(base_sp, "w", encoding="utf-8") as f:
        f.write(
            "struct Base {\n"
            "  var x: int;\n"
            "}\n"
            "impl Base {\n"
            "  func draw(): int {\n"
            "    return self.x;\n"
            "  }\n"
            "}\n"
            "export { Base, }\n"
        )
      code = (
          "import base_mod;\n"
          "struct Child: base_mod.Base {\n"
          "  var y: int;\n"
          "}\n"
          "impl Child {\n"
          "  func draw(): int {\n"
          "    return base_mod.Base.draw(self) + self.y;\n"
          "  }\n"
          "}\n"
      )
      with open(main_sp, "w", encoding="utf-8") as f:
        f.write(code)

      parser = SapphireParser(CommonTokenStream(SapphireLexer(InputStream(code))))
      ast = ASTBuilder().visit(parser.program())
      checker = SemanticTokensTypeChecker(doc_text=code, source_file_path=main_sp)
      checker.check(ast)
      self.assertEqual(checker.lsp_errors, [])

      # Line 7: '    return base_mod.Base.draw(self) + self.y;'
      line_7_tokens = [t for t in checker.raw_tokens if t[0] == 7]
      self.assertIn((7, 20, 4, "struct", 0), line_7_tokens)
      self.assertIn((7, 25, 4, "method", 0), line_7_tokens)

  def test_multivar_tokens_parameter_scope_and_utf16_encoding(self):
    """Verifies multi-var tokens, parameter isolation from globals, UTF-16 encoding, and non-overlap."""
    from unittest.mock import MagicMock

    from src.lsp.semantic_tokens import find_node_at_position
    from src.lsp.server import SapphireLanguageServer, validate_source

    code = (
        'func foo(): int { return 1; }\n'
        'func bar(foo: int) {\n'
        '  let s = "🚀"; let a, b = 1, "hi";\n'
        '}\n'
    )
    parser = SapphireParser(CommonTokenStream(SapphireLexer(InputStream(code))))
    ast = ASTBuilder().visit(parser.program())
    checker = SemanticTokensTypeChecker(doc_text=code)
    checker.check(ast)
    self.assertEqual(checker.lsp_errors, [])

    # Parameter `foo` must NOT overwrite global `func foo`'s ast_decl.
    global_foo = checker.symbol_table.lookup("foo")
    self.assertEqual(type(global_foo.ast_decl).__name__, "FuncDeclNode")

    # Both `a` and `b` in multi-var decl must get variable tokens.
    lines = code.splitlines()
    a_col = lines[2].index(" a,") + 1
    b_col = lines[2].index(" b =") + 1
    line3_toks = [t for t in checker.raw_tokens if t[0] == 3]
    self.assertIn((3, a_col, 1, "variable", 5), line3_toks)
    self.assertIn((3, b_col, 1, "variable", 5), line3_toks)

    # UTF-16 encoding shifts columns after "🚀" by +1 code unit.
    encoded = encode_semantic_tokens(
        [(3, a_col, 1, "variable", 5), (3, a_col, 1, "variable", 5)],
        doc_text=code,
    )
    expected_u16 = len(lines[2][:a_col].encode("utf-16-le")) // 2
    self.assertEqual(len(encoded), 5)  # Duplicate/overlapping token dropped.
    self.assertEqual(encoded[1], expected_u16)

    # Exclusive end_column boundary check.
    bar_decl = ast.declarations[1]
    self.assertIsNone(
        find_node_at_position(bar_decl, bar_decl.end_line, bar_decl.end_column)
    )

    # Invalid f-string interpolation must publish an LSP syntax diagnostic.
    from testing.test_utils import FakeWorkspace

    ls = SapphireLanguageServer("test", "0.1", workspace=FakeWorkspace())
    ls.text_document_publish_diagnostics = MagicMock()
    bad_uri = "file:///bad_fstring.sp"
    validate_source(ls, bad_uri, 'func main() { let x = f"bad {1 + }"; }\n')
    diags = ls.text_document_publish_diagnostics.call_args[0][0].diagnostics
    self.assertGreaterEqual(len(diags), 1)
    self.assertIn("Syntax Error", diags[0].message)

    # Subsequent syntax error preserves previously cached valid semantic tokens.
    good_uri = "file:///preserve_toks.sp"
    validate_source(ls, good_uri, "func ok(): int { return 1; }\n")
    valid_tokens = list(ls.tokens_cache[good_uri])
    self.assertTrue(len(valid_tokens) > 0)
    validate_source(ls, good_uri, "func ok(): int { return ; }\n")
    self.assertEqual(ls.tokens_cache[good_uri], valid_tokens)





