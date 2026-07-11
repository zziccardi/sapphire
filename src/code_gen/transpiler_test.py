"""Unit tests for the Sapphire-to-Python transpiler.

This module validates that transpiled Python code is syntactically correct
and preserves all Sapphire runtime semantics, including prototypal delegation.
"""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from code_gen.transpiler import Transpiler
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.code_gen.transpiler import Transpiler


class TestTranspiler(unittest.TestCase):
  """Suite of unit tests verifying correct code generation and execution."""

  def _transpile_and_run(self, code: str, run_expr: str) -> Any:
    """Helper to transpile Sapphire code, execute it in Python, and return run_expr value."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    
    builder = ASTBuilder()
    ast = builder.visit(tree)
    
    transpiler = Transpiler()
    py_code = transpiler.transpile(ast)

    # Context for execution
    ctx = {}
    exec(py_code, ctx)  # pylint: disable=exec-used
    return eval(run_expr, ctx)  # pylint: disable=eval-used

  def test_basic_arithmetic(self):
    """Verifies that variable assignments and arithmetic execute correctly."""
    code = """
    let x = 10;
    let y = 20;
    let z = x + y * 3;
    """
    result = self._transpile_and_run(code, "z")
    self.assertEqual(result, 70)

  def test_swift_style_if_let(self):
    """Verifies that optional unwrapping block resolves and executes correctly."""
    code = """
    func run_if_let(): int {
      var opt_val: int? = 42;
      var out = 0;
      if let active = opt_val {
        out = active;
      }
      return out;
    }
    """
    result = self._transpile_and_run(code, "run_if_let()")
    self.assertEqual(result, 42)

  def test_prototypal_inheritance_live_updates(self):
    """Verifies that cloned objects delegate live property lookups and allow shadowing."""
    code = """
    struct Item {
      var price: int;
      var stock: int;
    }
    impl Item {
      func __init__(p: int) {
        self.price = p;
        self.stock = 10;
      }
    }
    func test_delegation() {
      var base = Item(p = 100);
      var promo_item = clone base {
        self.price = 80;
      };
      
      let initial_promo_price = promo_item.price; // Shadowed (80)
      let initial_promo_stock = promo_item.stock; // Delegated (10)
      
      base.stock = 5; // Mutating prototype should reflect live on clone
      let final_promo_stock = promo_item.stock;
      
      return [initial_promo_price, initial_promo_stock, final_promo_stock];
    }
    """
    result = self._transpile_and_run(code, "test_delegation()")
    self.assertEqual(result, [80, 10, 5])


if __name__ == "__main__":
  unittest.main()
