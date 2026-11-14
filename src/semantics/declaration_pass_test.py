"""Unit tests for DeclarationPass in src/semantics/declaration_pass.py."""

import os
import tempfile
import unittest
from antlr4 import CommonTokenStream, InputStream

from src.common.errors import SemanticError
from src.parser.ast import IdentifierNode, ParameterNode
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.type_checker import TypeChecker


def _parse_program(source: str):
  """Parses *source* into a Sapphire AST ProgramNode."""
  lexer = SapphireLexer(InputStream(source))
  lexer.removeErrorListeners()
  parser = SapphireParser(CommonTokenStream(lexer))
  parser.removeErrorListeners()
  return ASTBuilder().visit(parser.program())


class TestDeclarationPass(unittest.TestCase):
  """Unit tests for parameter default validation and declaration helpers."""

  def setUp(self):
    DeclarationPass.clear_cache()

  def test_validate_parameter_defaults_valid(self):
    checker = TypeChecker()
    p1 = ParameterNode(False, "a")
    p2 = ParameterNode(False, "b", default_expr=IdentifierNode("x"))
    DeclarationPass.validate_parameter_defaults(checker, [p1, p2])
    self.assertEqual(len(checker.errors), 0)

  def test_validate_parameter_defaults_invalid_ordering(self):
    checker = TypeChecker()
    p1 = ParameterNode(False, "a", default_expr=IdentifierNode("x"))
    p2 = ParameterNode(False, "b")
    DeclarationPass.validate_parameter_defaults(checker, [p1, p2])
    self.assertEqual(len(checker.errors), 1)
    self.assertIn("cannot follow a parameter with a default value", checker.errors[0])

  def test_imported_mutable_var_export_propagates_without_cascading(self):
    """Verifies imported mutable export error propagates while valid sibling exports still resolve."""
    with tempfile.TemporaryDirectory() as tmpdir:
      dep_sp = os.path.join(tmpdir, "dep_mod.sp")
      with open(dep_sp, "w", encoding="utf-8") as f:
        f.write(
            "export {\n"
            "  StructA,\n"
            "  state\n"
            "}\n"
            "struct StructA {\n"
            "  var value: int = 1;\n"
            "}\n"
            "var state: int = 0;\n"
        )
      main_sp = os.path.join(tmpdir, "main.sp")
      main_code = (
          "import dep_mod;\n"
          "func use_valid(): int {\n"
          "  let item = dep_mod.StructA {};\n"
          "  return item.value;\n"
          "}\n"
      )
      checker = TypeChecker(source_file_path=main_sp, source_content=main_code)
      with self.assertRaises(SemanticError):
        checker.check(_parse_program(main_code))
      self.assertEqual(len(checker.errors), 1)
      self.assertIn("dep_mod.sp", checker.errors[0])
      self.assertNotIn("StructA", checker.errors[0])

  def test_imported_duplicate_export_block_reports_syntax_error(self):
    """Verifies duplicate export block SyntaxError from ASTBuilder propagates."""
    with tempfile.TemporaryDirectory() as tmpdir:
      dup_sp = os.path.join(tmpdir, "dup_export.sp")
      with open(dup_sp, "w", encoding="utf-8") as f:
        f.write(
            "export { foo }\n"
            "export { foo }\n"
            "func foo(): int { return 1; }\n"
        )
      main_sp = os.path.join(tmpdir, "main.sp")
      main_code = "import dup_export;\n"
      checker = TypeChecker(source_file_path=main_sp, source_content=main_code)
      with self.assertRaises(SemanticError) as ctx:
        checker.check(_parse_program(main_code))
      self.assertIn("Syntax Error:", str(ctx.exception))
      self.assertIn("Only a single export block is allowed", str(ctx.exception))

  def test_diamond_import_deduplicates_errors(self):
    """Verifies diamond imports report errors from shared leaf module only once."""
    with tempfile.TemporaryDirectory() as tmpdir:
      broken_sp = os.path.join(tmpdir, "leaf.sp")
      left_sp = os.path.join(tmpdir, "left.sp")
      right_sp = os.path.join(tmpdir, "right.sp")
      main_sp = os.path.join(tmpdir, "main.sp")
      with open(broken_sp, "w", encoding="utf-8") as f:
        f.write("let broken: int = \"bad\";\n")
      with open(left_sp, "w", encoding="utf-8") as f:
        f.write("import leaf;\n")
      with open(right_sp, "w", encoding="utf-8") as f:
        f.write("import leaf;\n")

      main_code = "import left;\nimport right;\n"
      checker = TypeChecker(source_file_path=main_sp, source_content=main_code)
      with self.assertRaises(SemanticError):
        checker.check(_parse_program(main_code))
      self.assertEqual(len(checker.errors), 1)
      self.assertIn("leaf.sp", checker.errors[0])
      self.assertNotIn(os.path.abspath(broken_sp), DeclarationPass._module_cache)
      self.assertNotIn(os.path.abspath(left_sp), DeclarationPass._module_cache)
      self.assertNotIn(os.path.abspath(right_sp), DeclarationPass._module_cache)

  def test_circular_import_terminates_without_caching(self):
    """Verifies mutually importing modules do not recurse infinitely or enter cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
      a_sp = os.path.join(tmpdir, "mod_a.sp")
      b_sp = os.path.join(tmpdir, "mod_b.sp")
      main_sp = os.path.join(tmpdir, "main.sp")
      with open(a_sp, "w", encoding="utf-8") as f:
        f.write("import mod_b;\n")
      with open(b_sp, "w", encoding="utf-8") as f:
        f.write("import mod_a;\n")

      main_code = "import mod_a;\n"
      checker = TypeChecker(source_file_path=main_sp, source_content=main_code)
      checker.check(_parse_program(main_code))
      self.assertNotIn(os.path.abspath(a_sp), DeclarationPass._module_cache)
      self.assertNotIn(os.path.abspath(b_sp), DeclarationPass._module_cache)

  def test_broken_module_not_cached_and_transitive_edit_invalidates_mid(self):
    """Verifies broken modules skip cache and transitive dependency edits invalidate mid cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
      leaf_sp = os.path.join(tmpdir, "leaf.sp")
      mid_sp = os.path.join(tmpdir, "mid.sp")
      main_sp = os.path.join(tmpdir, "main.sp")
      with open(leaf_sp, "w", encoding="utf-8") as f:
        f.write("export { val }\nlet val: int = 10;\n")
      with open(mid_sp, "w", encoding="utf-8") as f:
        f.write("import leaf;\nexport { get_v }\nfunc get_v(): int { return leaf.val; }\n")

      main_code = "import mid;\nfunc main(): int { return mid.get_v(); }\n"
      checker1 = TypeChecker(source_file_path=main_sp, source_content=main_code)
      checker1.check(_parse_program(main_code))
      self.assertIn(os.path.abspath(leaf_sp), DeclarationPass._module_cache)
      self.assertIn(os.path.abspath(mid_sp), DeclarationPass._module_cache)

      # Break leaf.sp with a different file size/content; cached mid must invalidate.
      with open(leaf_sp, "w", encoding="utf-8") as f:
        f.write('export { val }\nlet val: int = "broken_leaf_value";\n')

      checker2 = TypeChecker(source_file_path=main_sp, source_content=main_code)
      with self.assertRaises(SemanticError) as ctx:
        checker2.check(_parse_program(main_code))
      self.assertIn("leaf.sp", str(ctx.exception))
      self.assertNotIn(os.path.abspath(leaf_sp), DeclarationPass._module_cache)
      self.assertNotIn(os.path.abspath(mid_sp), DeclarationPass._module_cache)


if __name__ == "__main__":
  unittest.main()
