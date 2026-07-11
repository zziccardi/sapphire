"""Unit tests for the Sapphire Semantic Analyzer and Type Checker.

This module validates compile-time safety checks, optional type safety, mutability
rules, struct constructor initialization, and inheritance casting restrictions.
"""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.semantics.type_checker import TypeChecker, SemanticError


class TestTypeChecker(unittest.TestCase):
  """Suite of unit tests verifying semantic and type constraints in Sapphire."""

  def _check(self, code: str) -> None:
    """Helper to parse and run the semantic check on a code string."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)

  def test_valid_variables(self):
    """Verifies that correct type declarations and assignments within functions pass."""
    self._check("""
    func test() {
      let x: int = 10;
      var y = 20.0;
      y = 30.5;
    }
    """)

  def test_let_immutability(self):
    """Enforces that assigning to a let binding fails at compile time."""
    code = """
    func test() {
      let x: int = 10;
      x = 20;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign to constant variable 'x'", str(context.exception))

  def test_type_mismatch(self):
    """Enforces that assigning an incompatible type fails at compile time."""
    code = """
    func test() {
      let x: int = "hello";
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign expression of type 'string' to variable 'x' of type 'int'", str(context.exception))

  def test_optional_unwrapping_if_let(self):
    """Verifies that if let binds the unwrapped optional value in the scope."""
    code = """
    func test() {
      var opt_x: int? = none;
      if let active_x = opt_x {
        let y: int = active_x;
      }
    }
    """
    # Should succeed without errors
    self._check(code)

  def test_if_let_non_optional(self):
    """Enforces that if let requires an optional expression target."""
    code = """
    func test() {
      let x: int = 10;
      if let active_x = x {
        let y = active_x;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Expression in 'if let' must resolve to an optional type", str(context.exception))

  def test_struct_constructor_field_initialization(self):
    """Verifies struct constructors require all fields to be initialized."""
    code = """
    struct Point {
      let x: int;
      let y: int;
    }
    impl Point {
      func __init__(val: int) {
        self.x = val;
        // y is not initialized
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Constructor '__init__' failed to initialize non-optional field 'y'", str(context.exception))

  def test_disallowed_static_upcasting(self):
    """Enforces that child structures cannot be cast/assigned to parent structures."""
    code = """
    struct Animal {
      var age: int;
    }
    struct Cat: Animal {
      var lives: int;
    }
    impl Animal {
      func __init__(a: int) {
        self.age = a;
      }
    }
    impl Cat {
      func __init__(a: int, l: int) {
        self.age = a;
        self.lives = l;
      }
    }
    func test() {
      let pet: Animal = Cat(a = 2, l = 9);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign expression of type 'Cat' to variable 'pet' of type 'Animal'", str(context.exception))


if __name__ == "__main__":
  unittest.main()
