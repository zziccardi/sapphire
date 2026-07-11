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

  def test_control_flow_loops(self):
    """Verifies while loops, for loops, and boolean logic transpile correctly."""
    code = """
    func run_loops() {
      var sum = 0;
      var count = 3;
      while count > 0 {
        sum += count;
        count -= 1;
      }
      
      let scores = [10, 20, 30];
      var loop_sum = 0;
      for score in scores {
        loop_sum += score;
      }
      
      return [sum, loop_sum];
    }
    """
    result = self._transpile_and_run(code, "run_loops()")
    self.assertEqual(result, [6, 60])

  def test_static_methods(self):
    """Verifies static method decorators and const struct methods compile and run."""
    code = """
    struct Counter {
      var val: int;
    }
    impl Counter {
      func __init__(v: int) {
        self.val = v;
      }
      const func get_val(): int {
        return self.val;
      }
      static func create_default(): Counter {
        return Counter(v = 100);
      }
    }
    func test_static() {
      let c = Counter.create_default();
      return c.get_val();
    }
    """
    result = self._transpile_and_run(code, "test_static()")
    self.assertEqual(result, 100)

  def test_optional_chaining(self):
    """Verifies optional chaining (?.) expressions return correctly."""
    code = """
    struct Node {
      var score: int;
    }
    impl Node {
      func __init__(s: int) {
        self.score = s;
      }
    }
    func test_chain() {
      var n1: Node? = none;
      var n2: Node? = Node(s = 99);
      
      let val1 = n1?.score;
      let val2 = n2?.score;
      return [val1, val2];
    }
    """
    result = self._transpile_and_run(code, "test_chain()")
    self.assertEqual(result, [None, 99])

  def test_unary_operators(self):
    """Verifies logical NOT (!) and arithmetic negation (-) transpile correctly."""
    code = """
    func test_unary() {
      let is_true = true;
      let is_false = !is_true;
      let num = 5;
      let neg_num = -num;
      return [is_false, neg_num];
    }
    """
    result = self._transpile_and_run(code, "test_unary()")
    self.assertEqual(result, [False, -5])


  def test_lambda_expression(self):
    """Verifies that lambda functions can be transpiled and executed."""
    code = """
    func run_lambda(): int {
      var f = x -> (x + 5);
      return f(10);
    }
    """
    result = self._transpile_and_run(code, "run_lambda()")
    self.assertEqual(result, 15)

  def test_array_indexing(self):
    """Verifies that array indexing transpiles and executes correctly."""
    code = """
    func run_index(): int {
      let arr = [100, 200];
      return arr[1];
    }
    """
    result = self._transpile_and_run(code, "run_index()")
    self.assertEqual(result, 200)


if __name__ == "__main__":
  unittest.main()
