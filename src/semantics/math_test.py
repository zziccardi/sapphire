"""Unit tests for the std.math standard library module in Sapphire."""

import unittest
from antlr4 import InputStream, CommonTokenStream

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler


class TestMathModule(unittest.TestCase):
  """Suite verifying type checking, code generation, and execution parity for std.math."""

  def _parse_and_check(self, code: str):
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    tree = parser.program()
    if parser.getNumberOfSyntaxErrors() > 0:
      raise SyntaxError(f"Syntax error while parsing code:\n{code}")
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    return ast

  def test_math_imports_and_type_checking(self):
    code = """
    import std.math as math;

    func main() {
      let a = math.abs(-10);
      let b = math.abs(-5.5);
      let c = math.sqrt(25.0);
      let d = math.min(3, 7);
      let e = math.max(3.5, 7.2);
      let f = math.safe_div(10, 2);
      let g = math.safe_div(10, 0);
      let h = math.log(100.0, 10.0);
      let i = math.pow(2.0, 3.0);
      let j = math.ceil(4.2);
      let k = math.floor(4.8);
    }
    """
    ast = self._parse_and_check(code)
    self.assertIsNotNone(ast)

  def test_python_transpilation(self):
    code = """
    import std.math as math;

    func main() {
      let val = math.abs(-42);
      let div = math.safe_div(20, 4);
    }
    """
    ast = self._parse_and_check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("import std.math as math", py_code)

  def test_lua_transpilation(self):
    code = """
    import std.math as math;

    func main() {
      let val = math.abs(-42);
      let div = math.safe_div(20, 4);
    }
    """
    ast = self._parse_and_check(code)
    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn("local math = require(\"std.math\")", lua_code)

  def test_python_execution_parity(self):
    code = """
    import std.math as math;

    func calc(): int {
      let a = math.abs(-10);
      let b = math.min(5, 15);
      let c = math.max(5, 15);
      let d = math.ceil(2.3);
      let e = math.floor(2.8);
      return a + b + c + d + e;
    }
    """
    ast = self._parse_and_check(code)
    import sys, os
    lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
    if lib_dir not in sys.path:
      sys.path.insert(0, lib_dir)
    py_code = PythonTranspiler().transpile(ast)
    namespace = {}
    exec(py_code, namespace)
    res = namespace["calc"]()
    self.assertEqual(res, 10 + 5 + 15 + 3 + 2)


if __name__ == "__main__":
  unittest.main()
