"""Unit tests for Sapphire C-style ternary expression support."""

import unittest
from antlr4 import InputStream, CommonTokenStream

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler


def parse_and_check(code: str):
  input_stream = InputStream(code)
  lexer = SapphireLexer(input_stream)
  stream = CommonTokenStream(lexer)
  parser = SapphireParser(stream)
  tree = parser.program()
  builder = ASTBuilder()
  ast = builder.visit(tree)
  checker = TypeChecker()
  checker.visit(ast)
  return ast, checker


class TernaryOperatorTest(unittest.TestCase):

  def test_valid_basic_ternary(self):
    code = """
    let age = 20;
    let status = age >= 18 ? "Adult" : "Minor";
    """
    ast, checker = parse_and_check(code)
    self.assertEqual(len(checker.errors), 0)

  def test_type_widening_int_to_float(self):
    code = """
    let is_high = true;
    let val: float = is_high ? 10 : 2.5;
    """
    ast, checker = parse_and_check(code)
    self.assertEqual(len(checker.errors), 0)

  def test_optional_branch(self):
    code = """
    let active = true;
    let num: int? = active ? 42 : none;
    """
    ast, checker = parse_and_check(code)
    self.assertEqual(len(checker.errors), 0)

  def test_non_bool_condition_error(self):
    code = """
    let val = 123 ? 10 : 20;
    """
    ast, checker = parse_and_check(code)
    self.assertTrue(any("Ternary condition must be of type 'bool'" in err for err in checker.errors))

  def test_incompatible_branches_error(self):
    code = """
    let val = true ? 10 : "text";
    """
    ast, checker = parse_and_check(code)
    self.assertTrue(any("Incompatible types in ternary branches" in err for err in checker.errors))

  def test_unparenthesized_nested_ternary_error(self):
    code = """
    let score = 85;
    let grade = score >= 90 ? "A" : score >= 80 ? "B" : "C";
    """
    ast, checker = parse_and_check(code)
    self.assertTrue(any("Nested ternary expressions must be explicitly enclosed in parentheses." in err for err in checker.errors))

  def test_parenthesized_nested_ternary_valid(self):
    code = """
    let score = 85;
    let grade = score >= 90 ? "A" : (score >= 80 ? "B" : "C");
    """
    ast, checker = parse_and_check(code)
    self.assertEqual(len(checker.errors), 0)

  def test_python_transpilation(self):
    code = """
    let age = 20;
    let status = age >= 18 ? "Adult" : "Minor";
    """
    ast, checker = parse_and_check(code)
    py_transpiler = PythonTranspiler()
    output = py_transpiler.transpile(ast)
    self.assertIn('("Adult" if (age >= 18) else "Minor")', output)

  def test_lua_transpilation(self):
    code = """
    let age = 20;
    let status = age >= 18 ? "Adult" : "Minor";
    """
    ast, checker = parse_and_check(code)
    lua_transpiler = LuaTranspiler()
    output = lua_transpiler.transpile(ast)
    self.assertIn('((function() if (age >= 18) then return "Adult" else return "Minor" end end)())', output)


if __name__ == "__main__":
  unittest.main()
