"""Unit tests for Generics (Parametric Polymorphism) in Sapphire."""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
  from code_gen.python_transpiler import PythonTranspiler
except ModuleNotFoundError:  # pragma: no cover
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError
  from src.code_gen.python_transpiler import PythonTranspiler


class TestGenerics(unittest.TestCase):
  """Suite of unit tests verifying generic struct and function behavior."""

  def _check(self, code: str):
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    return ast

  def test_generic_struct_and_impl(self):
    """Verifies that generic structs and generic impl blocks monomorphize cleanly."""
    code = """
    struct Box<T> {
      var val: T;
    }

    impl<T> Box<T> {
      func __init__(val: T) {
        self.val = val;
      }
    }

    func main() {
      let b = Box<int>(val = 42);
    }
    """
    ast = self._check(code)
    transpiler = PythonTranspiler()
    py_code = transpiler.transpile(ast)
    self.assertIn("class Box__int", py_code)

  def test_generic_function_inference(self):
    """Verifies contextual inference for generic function arguments."""
    code = """
    func identity<T>(val: T): T {
      return val;
    }

    func main() {
      let x = identity(100);
      let y = identity<float>(3.14);
    }
    """
    ast = self._check(code)
    transpiler = PythonTranspiler()
    py_code = transpiler.transpile(ast)
    self.assertIn("def identity__int", py_code)
    self.assertIn("def identity__float", py_code)

  def test_generic_struct_initializer(self):
    """Verifies struct initializers with generic type arguments."""
    code = """
    struct Pair<K, V> {
      var key: K;
      var value: V;
    }

    func main() {
      let p = Pair<String, int> {
        key = "score",
        value = 100,
      };
    }
    """
    ast = self._check(code)
    transpiler = PythonTranspiler()
    py_code = transpiler.transpile(ast)
    self.assertIn("class Pair__string_int", py_code)
