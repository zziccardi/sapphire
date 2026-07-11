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

  def test_variable_redefinition(self):
    """Enforces that re-declaring an identifier in the same scope level fails."""
    code = """
    func test() {
      let x = 10;
      let x = 20;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Identifier 'x' is already defined in this scope", str(context.exception))

  def test_inconsistent_array_literal(self):
    """Enforces that array literals have consistent element types."""
    code = """
    func test() {
      let arr = [1, "hello"];
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Inconsistent element types in array literal", str(context.exception))

  def test_index_non_array(self):
    """Enforces that indexing is only allowed on array types."""
    code = """
    func test() {
      let x = 10;
      let y = x[0];
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot index non-array type", str(context.exception))

  def test_index_non_integer(self):
    """Enforces that array index must resolve to an int."""
    code = """
    func test() {
      let arr = [10, 20];
      let y = arr[1.5];
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Array index must be an 'int'", str(context.exception))

  def test_assign_index_const_array(self):
    """Enforces that indexing assignment requires a mutable array variable."""
    code = """
    func test() {
      let arr = [10, 20];
      arr[0] = 30;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign to index of constant array 'arr'", str(context.exception))

  def test_call_non_callable(self):
    """Enforces that you cannot call a non-callable expression."""
    code = """
    func test() {
      let x = 10;
      x();
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Target is not callable", str(context.exception))

  def test_mutate_field_const_method(self):
    """Enforces that you cannot mutate fields inside a constant method."""
    code = """
    struct Point {
      var x: int;
    }
    impl Point {
      func __init__() {
        self.x = 0;
      }
      const func change() {
        self.x = 10;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot mutate field 'x' within a constant method", str(context.exception))

  def test_mutate_const_field(self):
    """Enforces that constant let fields of structs cannot be mutated outside __init__."""
    code = """
    struct Point {
      let x: int;
    }
    impl Point {
      func __init__() {
        self.x = 0;
      }
      func change() {
        self.x = 10;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign to constant field 'x'", str(context.exception))

  def test_trait_missing_method(self):
    """Enforces that impl of a trait must implement all methods of the trait."""
    code = """
    trait Target {
      func resolve(): int;
    }
    struct Runner {}
    impl Target for Runner {
      // Missing resolve method
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("does not implement trait method 'resolve'", str(context.exception))

  def test_trait_signature_mismatch(self):
    """Enforces that impl methods of a trait must match trait signatures exactly."""
    code = """
    trait Target {
      func resolve(x: int): int;
    }
    struct Runner {}
    impl Target for Runner {
      func resolve(x: float): int {
        return 10;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("signature", str(context.exception))

  def test_direct_access_on_optional(self):
    """Enforces that optional receivers require optional chaining (?.) for property accesses."""
    code = """
    struct Person {
      var name: String;
    }
    func test() {
      var p: Person? = none;
      let name = p.name;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Must use optional chaining '?.'", str(context.exception))

  def test_optional_chaining_on_non_optional(self):
    """Enforces that optional chaining (?.) is only allowed on optional receivers."""
    code = """
    struct Person {
      var name: String;
    }
    impl Person {
      func __init__(n: String) {
        self.name = n;
      }
    }
    func test() {
      let p = Person(n = "Alice");
      let name = p?.name;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Optional chaining '?.' requires an optional receiver", str(context.exception))

  def test_while_condition_not_bool(self):
    """Enforces that while loop conditions must resolve to bool."""
    code = """
    func test() {
      while 10 {
        let x = 1;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("While condition must resolve to 'bool'", str(context.exception))

  def test_for_target_not_array(self):
    """Enforces that for loop iterables must be arrays."""
    code = """
    func test() {
      let x = 10;
      for item in x {
        let y = item;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("For-in loop source must be an array type", str(context.exception))


  def test_binary_and_unary_ops(self):
    """Verifies that all binary and unary operators are semantically type checked."""
    self._check("""
    func test() {
      let a = true;
      let b = !a;
      let c = a && b || true;
      let x = 10;
      let y = -x;
      let cmp = x == y;
      let add = x + y * 2;
    }
    """)

  def test_calls_and_member_access(self):
    """Verifies that static calls, instance calls, and properties resolve correctly."""
    self._check("""
    struct Point {
      var x: int;
    }
    impl Point {
      func __init__(val: int) {
        self.x = val;
      }
      const func get_x(): int {
        return self.x;
      }
      static func create(): Point {
        return Point(val = 5);
      }
    }
    func run() {
      let p = Point.create();
      let val = p.get_x();
    }
    """)

  def test_arrays_and_indexing(self):
    """Verifies that array literal types and indexing resolve successfully."""
    self._check("""
    func test() {
      let arr = [10, 20];
      let first = arr[0];
    }
    """)

  def test_lambda_expressions(self):
    """Verifies that lambda parameter inference and execution type checking succeed."""
    self._check("""
    func test() {
      let f: (int) -> int = x -> x * 2;
      let f2: (int) -> int = x -> x + 5;
    }
    """)

  def test_cloning(self):
    """Verifies that clone constructs are type checked successfully."""
    self._check("""
    struct Entity {
      var score: int;
    }
    impl Entity {
      func __init__(s: int) {
        self.score = s;
      }
    }
    func test() {
      var e1 = Entity(s = 10);
      var e2 = clone e1 {
        self.score = 20;
      };
    }
    """)


if __name__ == "__main__":
  unittest.main()
