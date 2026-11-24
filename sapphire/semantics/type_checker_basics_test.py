"""Core expressions, variables, functions, enums, and diagnostic semantic tests."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast import (
  ArgumentNode,
  BasicTypeNode,
  CallNode,
  IdentifierNode,
  LiteralNode,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.symbol_table import (
  PrimitiveType,
)
from sapphire.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerBasics(TypeCheckerTestBase, unittest.TestCase):
  """Core expressions, variables, functions, enums, and diagnostic semantic tests."""

  def test_valid_variables(self):
    """Verifies that correct type declarations and assignments within functions pass."""
    self._check("""
    func test() {
      let x: int = 10;
      var y = 20.0;
      y = 30.5;
    }
    """)

  def test_lowercase_string_error(self):
    """Verifies that lowercase 'string' is rejected as an invalid/undefined type."""
    code = """
    func greet(name: string) {}
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Undefined type 'string'", str(context.exception))

  def test_multi_binding_if_statement_type_checking(self):
    """Verifies type checking, unwrapping, condition validation, and scoping for multi-binding if statements."""
    # 1. Valid multi-binding if with unwraps and compound boolean condition
    code_valid = """
    func test(opt_a: int?, opt_b: String?): int {
      if let a ?= opt_a; let b ?= opt_b; a > 0 && b.size() > 0 {
        return a + b.size();
      } else {
        return -1;
      }
    }
    """
    self._check(code_valid)

    # 2. Error: non-optional unwrap in second binding
    code_invalid_unwrap = """
    func test(opt_a: int?, non_opt: int) {
      if let a ?= opt_a; let b ?= non_opt {
        let x = 1;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_invalid_unwrap)
    self.assertIn("Expression in optional unwrapping must resolve to an optional type", str(ctx.exception))

    # 3. Error: condition expression resolves to non-bool
    code_non_bool = """
    func test(opt_a: int?, opt_b: int?) {
      if let a ?= opt_a; let b ?= opt_b; a + b {
        let x = 1;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_non_bool)
    self.assertIn("If condition must resolve to 'bool'", str(ctx.exception))

    # 4. Error: multiple boolean conditions separated by semicolons are rejected by syntax
    code_semicolon_conditions = """
    func test(a: int, b: int) {
      if a > 0; b > 0 {
        let x = 1;
      }
    }
    """
    with self.assertRaises(SyntaxError):
      self._check(code_semicolon_conditions)

    # 5. Scope isolation: unwrapped bindings are not defined outside the if block
    code_leak = """
    func test(opt_a: int?) {
      if let a ?= opt_a {
        let inside = a;
      }
      let outside = a; // Error: undefined 'a'
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_leak)
    self.assertIn("Undefined identifier 'a'", str(ctx.exception))

    # 3. ?? operator
    code3 = """
    func test() {
      var opt_x: int? = none;
      let val: int = opt_x ?? 42;
    }
    """
    self._check(code3)

    # 4. ?? incompatible fallback error
    code4 = """
    func test() {
      var opt_x: int? = none;
      let val: int = opt_x ?? "hello";
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code4)
    self.assertIn("Fallback type 'String' is not compatible with the optional's base type 'int'", str(context.exception))

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

  def test_for_range_iteration_valid(self):
    """Verifies valid range iteration with 1, 2, and 3 arguments."""
    code = """
    func test() {
      for i in range(10) {
        let x: int = i;
      }
      for i in range(0, 10) {
        let y: int = i;
      }
      for i in range(0, 10, 2) {
        let z: int = i;
      }
    }
    """
    self._check(code)

  def test_for_range_variable_iteration_valid(self):
    """Verifies stored Range variable iteration."""
    code = """
    func test() {
      let r: Range = range(0, 5);
      for i in r {
        let x: int = i;
      }
    }
    """
    self._check(code)

  def test_for_range_iteration_key_value_error(self):
    """Enforces that iterating over a range prohibits key-value syntax."""
    code = """
    func test() {
      for k, v in range(10) {
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot iterate over a range with key-value syntax", str(context.exception))

  def test_range_call_arg_count_error(self):
    """Enforces 1 to 3 arguments for range()."""
    code = """
    func test() {
      let r = range();
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Not enough arguments passed to call. Expected at least 1, got 0", str(context.exception))

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
      func get_x(): int {
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

  def test_lambda_expressions(self):
    """Verifies lambda parameter type inference and type checking for various forms."""
    # 1. Explicit type annotation on variable \u2014 existing behaviour unchanged.
    self._check("""
    func test() {
      let f: (int) -> int = x -> x * 2;
      let f2: (int) -> int = x -> x + 5;
    }
    """)

    # 2. No annotation on variable or parameter: infer int from arithmetic.
    self._check("""
    func test() {
      let double = x -> x * 2;
      let square = x -> x * x;
    }
    """)

    # 3. Chained arithmetic (x * x * x) — param inferred as int.
    self._check("""
    func test() {
      let cube = x -> x * x * x;
    }
    """)

    # 4. Captured variable adds to param — param inferred as int.
    self._check("""
    func test() {
      let offset = 10;
      let shift = x -> x + offset;
    }
    """)

    # 5. Float literal on one side — param inferred as int, result is float.
    self._check("""
    func test() {
      let scale = x -> x * 2.0;
    }
    """)

    # 6. Boolean operator — param inferred as bool.
    self._check("""
    func test() {
      let negate = x -> x && false;
    }
    """)

    # 7. Identity lambda x -> x without type context: param type cannot be inferred.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let f = x -> x;
      }
      """)
    self.assertIn("Cannot infer type for lambda parameter 'x'", str(ctx.exception))

  def test_lambda_param_inference_coverage(self):
    """Exercises every scan branch in _infer_lambda_param_type for full coverage.

    Each sub-case triggers a distinct code path in the lightweight body scanner
    so that the coverage tool counts every branch.
    """
    # 1. Float literal RHS \u2014 param inferred as float.
    self._check("""
    func test() {
      let f = x -> x * 1.5;
    }
    """)

    # 2. Comparison with int literal (param on left).
    self._check("""
    func test() {
      let f = x -> x == 0;
    }
    """)

    # 3. Comparison with float literal (param on left).
    self._check("""
    func test() {
      let f = x -> x > 0.0;
    }
    """)

    # 4. Comparison with string literal (param on left).
    self._check("""
    func test() {
      let f = x -> x == "hello";
    }
    """)

    # 5. Comparison with non-literal RHS (no type inferred \u2014 falls back to
    #    unconstrained, InferredType resolves to none \u2014 no error expected).
    self._check("""
    func test() {
      var limit = 10;
      let f = x -> x > limit;
    }
    """)

    # 6. Unary negation on param.
    self._check("""
    func test() {
      let f = x -> -x;
    }
    """)

    # 7. Unary op on a non-param sub-expression (recursion through UnaryOpNode).
    self._check("""
    func test() {
      let offset = 1;
      let f = x -> -offset;
    }
    """)

    # 8. BinaryOp recursion: param is nested inside the left subtree
    #    (the BinaryOp recursion branch in scan()).
    self._check("""
    func test() {
      let f = x -> (x + 1) * 2;
    }
    """)

    # 9. Float-literal arithmetic discovered through a nested BinaryOp.
    self._check("""
    func test() {
      let f = x -> x * 1.0 + 0.5;
    }
    """)

    # 10. Unary op on the param nested inside an arithmetic expression
    #     (triggers UnaryOpNode.expr recursion path).
    self._check("""
    func test() {
      let n = 3;
      let f = x -> -n;
    }
    """)

    # 11. InferredType direct API.
    from sapphire.semantics.symbol_table import InferredType

    inf = InferredType()
    self.assertTrue(inf.is_compatible(PrimitiveType("int")))
    self.assertEqual(repr(inf), "<inferred>")

    # 12. Direct AST-level calls to _infer_lambda_param_type to cover the
    #     BlockNode, ReturnNode, VarDeclNode, ExprStmtNode, CallNode,
    #     TernaryExprNode, and None-node guard paths.
    from sapphire.parser.ast import (
      BinaryOpNode,
      BlockNode,
      ExprStmtNode,
      ReturnNode,
      TernaryExprNode,
      VarDeclNode,
    )
    from sapphire.semantics.type_checker import TypeChecker


    tc = TypeChecker()
    infer = tc._infer_lambda_param_type

    # scan(None) guard
    self.assertIsNone(infer("x", None))

    # BlockNode: scan finds arithmetic in first stmt
    block = BlockNode([ReturnNode(BinaryOpNode(IdentifierNode("x"), "*", LiteralNode(2, "int")))])
    self.assertEqual(infer("x", block), PrimitiveType("int"))

    # BlockNode: no match in any stmt -> None
    empty_block = BlockNode([ReturnNode(LiteralNode(1, "int"))])
    self.assertIsNone(infer("x", empty_block))

    # ReturnNode with an expr
    ret = ReturnNode(BinaryOpNode(IdentifierNode("x"), "+", LiteralNode(1, "int")))
    self.assertEqual(infer("x", ret), PrimitiveType("int"))

    # ReturnNode with no expr
    self.assertIsNone(infer("x", ReturnNode(None)))

    # VarDeclNode: finds arithmetic in exprs
    vd = VarDeclNode(False, ["y"], [None], [BinaryOpNode(IdentifierNode("x"), "+", LiteralNode(5, "int"))])
    self.assertEqual(infer("x", vd), PrimitiveType("int"))

    # VarDeclNode: no arithmetic
    vd_none = VarDeclNode(False, ["y"], [None], [LiteralNode(0, "int")])
    self.assertIsNone(infer("x", vd_none))

    # ExprStmtNode
    expr_stmt = ExprStmtNode(BinaryOpNode(IdentifierNode("x"), "-", LiteralNode(1, "int")))
    self.assertEqual(infer("x", expr_stmt), PrimitiveType("int"))

    # CallNode: param used as argument
    call = CallNode(IdentifierNode("f"), [ArgumentNode(None, BinaryOpNode(IdentifierNode("x"), "*", LiteralNode(3, "int")))])
    self.assertEqual(infer("x", call), PrimitiveType("int"))

    # CallNode: no param usage
    call_none = CallNode(IdentifierNode("f"), [ArgumentNode(None, LiteralNode(0, "int"))])
    self.assertIsNone(infer("x", call_none))

    # TernaryExprNode: param in true branch
    tern = TernaryExprNode(
        LiteralNode(True, "bool"),
        BinaryOpNode(IdentifierNode("x"), "+", LiteralNode(1, "int")),
        LiteralNode(0, "int"),
    )
    self.assertEqual(infer("x", tern), PrimitiveType("int"))

    # Unknown node type -> None
    self.assertIsNone(infer("x", LiteralNode(42, "int")))

  def test_cloning(self):
    """Verifies that clone constructs are type checked successfully."""
    self._check("""
    proto Entity {
      var score: int;
    }
    impl Entity {
      func __init__(s: int) {
        self.score = s;
      }
    }
    func test() {
      var arena = Arena();
      var e1 = Entity(s = 10) in arena;
      var e2 = clone e1 {
        self.score = 20;
      };
    }
    """)

  def test_more_semantic_errors(self):
    """Verifies various semantic validation failures and edge cases."""
    # 1. Global redefinition (struct/struct)
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      struct Point {}
      """)

    # 1b. Global redefinition (struct/trait)
    with self.assertRaises(SemanticError):
      self._check("""
      struct T {}
      trait T {}
      """)

    # 2. Global redefinition (func/func)
    with self.assertRaises(SemanticError):
      self._check("""
      func foo() {}
      func foo() {}
      """)

    # 3. Inheritance: missing parent
    with self.assertRaises(SemanticError):
      self._check("struct Child: Parent {}")

    # 4. Inheritance: parent is not a struct
    with self.assertRaises(SemanticError):
      self._check("""
      trait Parent {}
      struct Child: Parent {}
      """)

    # 5. Field shadowing parent field
    with self.assertRaises(SemanticError):
      self._check("""
      struct Parent { var x: int; }
      struct Child: Parent { var x: float; }
      """)

    # 5b. Duplicate field inherited from multiple parents
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Position { var x: float; }
      struct Point { var x: float; }
      struct Player: Position, Point {}
      """)
    self.assertIn("Duplicate field 'x' in struct 'Player' inherited from multiple parents", str(ctx.exception))

    # 5c. Circular struct inheritance
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct A: B {}
      struct B: A {}
      """)
    self.assertIn("Circular inheritance detected involving struct", str(ctx.exception))

  def test_enum_semantics(self):
    """Verifies type checking of valid enum declarations, type inference, member access, and error cases."""
    self._check("""
    enum Direction {
        North,
        East,
        South,
        West,
    }

    enum Status {
        Ok = 200,
        Created = 201,
    }

    func test() {
      let d = Direction.North;
      let d2: Direction = Direction.East;
      let code: int = Direction.South as int;
      let s: Status = Status.Ok;
      if (d == Direction.North) {
        let x: int = 1;
      }
    }
    """)

    # Test invalid enum member access
    with self.assertRaises(SemanticError) as context:
      self._check("""
      enum Direction { North, South }
      func test() {
        let d = Direction.East;
      }
      """)
    self.assertIn("Enum 'Direction' has no member 'East'", str(context.exception))

    # Test duplicate enum member
    with self.assertRaises(SemanticError) as context:
      self._check("""
      enum Direction { North, North }
      """)
    self.assertIn("Duplicate member 'North' in enum 'Direction'", str(context.exception))

    # Test duplicate enum identifier redefinition
    with self.assertRaises(SemanticError) as context:
      self._check("""
      enum Direction { North }
      enum Direction { South }
      """)
    self.assertIn("Redefinition of identifier 'Direction'", str(context.exception))

  def test_top_level_return_error(self):
    """Verifies that return statements outside functions raise a SemanticError."""
    with self.assertRaises(SemanticError) as context:
      self._check("""
      return 42;
      """)
    self.assertTrue(
        "Return statement outside function context" in str(context.exception)
        or "Executable statements are not permitted at module scope" in str(context.exception)
    )

  def test_top_level_executable_statements_rejected(self):
    """Verifies that top-level procedural statements are rejected at module scope."""
    code = """
    var count = 0;
    for i in [1, 2, 3] {
      count += i;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Executable statements are not permitted at module scope", str(context.exception))

  def test_multi_return_and_bindings_type_checking(self):
    """Verifies semantic type checking for multi-return functions, unpacking, and assignments."""
    valid_code = """
    func get_pos(): float, float {
      return 10.0, 20.0;
    }

    func main() {
      let x, y = get_pos();
      var a: float, b: float = 1.0, 2.0;
      a, b = get_pos();
      a, b = 3.0, 4.0;
    }
    """
    self._check(valid_code)

    # Quantity mismatch on return
    bad_return_count = """
    func get_pos(): float, float {
      return 10.0;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(bad_return_count)
    self.assertIn("Function expected 2 return value(s), but return statement provided 1 value(s).", str(context.exception))

    # Type mismatch on return
    bad_return_type = """
    func get_pos(): float, float {
      return 10.0, "invalid";
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(bad_return_type)
    self.assertIn("Cannot return value of type 'String' for return value #2", str(context.exception))

    # Quantity mismatch on unpack
    bad_unpack = """
    func get_pos(): float, float { return 1.0, 2.0; }
    func main() {
      let x, y, z = get_pos();
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(bad_unpack)
    self.assertIn("Cannot unpack 2 value(s) into 3 variable(s).", str(context.exception))

    # Void function returning values
    void_return_err = """
    func no_ret() {
      return 1, 2;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(void_return_err)
    self.assertIn("Function with no return type cannot return 2 values.", str(context.exception))

    # Assignment count mismatch
    assign_mismatch = """
    func main() {
      var a = 1.0;
      var b = 2.0;
      a, b = 1.0, 2.0, 3.0;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(assign_mismatch)
    self.assertIn("Cannot assign 3 value(s) to 2 target(s).", str(context.exception))

    # Uninitialized variable in block
    uninit_block = """
    func main() {
      var x: int;
      var y: int = 10;
    }
    """
    self._check(uninit_block)

    # _resolve_type_node(None) test
    from sapphire.semantics.symbol_table import PrimitiveType
    from sapphire.semantics.type_checker import TypeChecker


    tc = TypeChecker()
    self.assertEqual(tc._resolve_type_node(None), PrimitiveType("none"))

    class DummyWithReturnType:
      return_type = BasicTypeNode("int")

    res_types = tc._resolve_return_types(DummyWithReturnType())
    self.assertEqual(res_types, [PrimitiveType("int")])

  def test_string_enum_type_checking_valid(self):
    """Verifies type compatibility for string-backed enums with explicit casts."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }

    func main() {
      let m: Mode = Mode.Fill;
      let s: String = Mode.Line as String;
    }
    """
    self._check(code)

  def test_enum_implicit_coercion_prohibited(self):
    """Verifies that implicit coercion of enums to String or int is prohibited."""
    code1 = """
    enum Mode { Fill = "fill" }
    func main() {
      let s: String = Mode.Fill;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code1)
    self.assertIn("Cannot assign expression of type 'Mode' to variable 's' of type 'String'.", str(context.exception))

    code2 = """
    enum Direction { North }
    func main() {
      let i: int = Direction.North;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code2)
    self.assertIn("Cannot assign expression of type 'Direction' to variable 'i' of type 'int'.", str(context.exception))

  def test_string_enum_type_checking_invalid(self):
    """Verifies that passing a primitive to a function expecting an enum fails."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }

    func set_mode(m: Mode) {}

    func main() {
      set_mode("fill");
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Argument type mismatch at position 1. Expected 'Mode', got 'String'.", str(context.exception))

  def test_compiler_fixes_and_inference(self):
    """Verifies parenthesized types, optional lambda parameter inference, and struct initializer context propagation."""
    # 1. Parenthesized optional function types
    # TODO: Remove void?
    self._check("""
    func test_parenthesized_type(cb: ((int) -> void)?) {
      let x: ((int) -> void)? = cb;
    }
    func test_unit_callback(cb: (String) -> ()) {
      let x: (String) -> () = cb;
    }
    """)

    # 2. Lambda parameter type inference when the expected type is an OptionalType(FunctionType)
    self._check("""
    struct Handler {
      var callback: ((String) -> void)?;
    }
    func test_handler_infer() {
      var h = Handler {
        callback = button_id -> print(button_id),
      };
    }
    """)

    # 3. Lambda parameter type inference inside struct initializer fields
    self._check("""
    struct Target {
      let operation: (int) -> int;
    }
    func test_struct_lambda() {
      let t = Target {
        operation = val -> val + 1,
      };
    }
    """)

    # 4. Standard if let binding without condition (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        if let x = 42 { }
      }
      """)
    self.assertIn("Init-statement in 'if' must be followed by a condition unless using optional unwrapping", str(ctx.exception))

    # 5. while let is rejected as a syntax error
    with self.assertRaises(SyntaxError):
      self._check("""
      func test() {
        while let x ?= 42; x > 0 { }
      }
      """)

    # 6. Non-boolean condition in while (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        while 42 { }
      }
      """)
    self.assertIn("While condition must resolve to 'bool'", str(ctx.exception))

    # 7. Standard while let binding without condition (syntax error)
    with self.assertRaises(SyntaxError):
      self._check("""
      func test() {
        while let x = 42 { }
      }
      """)

    # 8. Left operand of ?? not optional (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let val = 42 ?? 99;
      }
      """)
    self.assertIn("Left operand of '??' must be an optional type", str(ctx.exception))

  def test_string_methods_valid(self):
    """Verifies that all built-in String instance methods type-check correctly."""
    self._check("""
    func test() {
      let s = " Hello World ";
      let sz: int = s.size();
      let emp: bool = s.empty();
      let low: String = s.lower();
      let up: String = s.upper();
      let strp: String = s.strip();
      let strp_custom: String = s.strip("/");
      let parts = s.split(",");
      let parts_ws = s.split();
      let has: bool = s.contains("World");
      let idx: int? = s.find("World");
      let idx_rev: int? = s.find("World", reverse = true);
      let idx_start: int? = s.find("World", start = 2, reverse = false);
    }
    """)

  def test_string_methods_invalid(self):
    """Enforces type safety on String method calls."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let s = "hello";
        let res = s.invalid_method();
      }
      """)
    self.assertIn("String has no method 'invalid_method'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let s = "hello";
        let x: int = s.contains("h");
      }
      """)
    self.assertIn("Cannot assign expression of type 'bool' to variable 'x' of type 'int'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let s = "hello";
        let res = s.contains();
      }
      """)
    self.assertIn("Not enough arguments passed to call", str(ctx.exception))

  def test_casting_and_conversion_methods(self):
    """Verifies type casting (as) and String.from / str.to_int/float/bool conversion methods."""
    # 1. Valid static casts and string conversions
    self._check("""
    enum Status { Active = 1 }

    func test() {
      let f: float = 10 as float;
      let i: int = 3.14 as int;
      let b: int = true as int;
      let code: int = Status.Active as int;
      let enum_str: String = Status.Active as String;

      let s1: String = String.from(42);
      let s2: String = String.from(3.14);
      let s3: String = String.from(true);
      let s4: String = String.from(Status.Active);

      let parsed_int: int? = "123".to_int();
      let parsed_hex: int? = "FF".to_int(radix = 16);
      let parsed_float: float? = "3.14".to_float();
      let parsed_bool: bool? = "true".to_bool();

      let e1: Status? = Status.from(1);
      let e2: Status? = Status.from("Active");
    }
    """)

    # 2. String to int via 'as' (should error and suggest .to_int())
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let i = "123" as int;
      }
      """)
    self.assertIn("Cannot cast 'String' to 'int' using 'as'", str(ctx.exception))

    # 3. Invalid cast between incompatible types (e.g. struct to float)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point { var x: float; }
      func test() {
        let p = Point { x = 1.0 };
        let f = p as float;
      }
      """)
    self.assertIn("Cannot cast type 'Point' to 'float'", str(ctx.exception))

    # 4. String.from with wrong argument count
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let s = String.from();
      }
      """)
    self.assertIn("String.from() requires exactly 1 argument", str(ctx.exception))

    # 5. String.from with non-primitive argument
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point { var x: float; }
      func test() {
        let p = Point { x = 1.0 };
        let s = String.from(p);
      }
      """)
    self.assertIn("Cannot convert type 'Point' to String using String.from()", str(ctx.exception))

    # 6. Enum.from error cases
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Active = 1 }
      func test() {
        let e = Status.from();
      }
      """)
    self.assertIn("Status.from() requires exactly 1 argument", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Active = 1 }
      func test() {
        let e = Status.from(true);
      }
      """)
    self.assertIn("Cannot convert type 'bool' to Enum 'Status' using .from()", str(ctx.exception))

  def test_interpolated_string_type_checking(self):
    """Verifies type checking of valid f-strings with primitives, enums, none."""
    self._check("""
    enum Direction { North = "North" }
    func test() {
      let name: String = "Hero";
      let count: int = 10;
      let dir: Direction = Direction.North;
      let msg: String = f"Hello {name}, dir: {dir}, count: {count + 1}, none: {none}";
    }
    """)

  def test_default_parameter_ordering_function(self):
    """Verifies that non-default parameters following default parameters in functions raise a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_func(a: int = 1, b: int): int {
        return a + b;
      }
      """)
    self.assertIn("Parameter without a default value 'b' cannot follow a parameter with a default value.", str(ctx.exception))

  def test_default_parameter_ordering_impl(self):
    """Verifies that non-default parameters following default parameters in struct methods raise a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      impl Point {
        func bad_method(opt: int = 0, req: int) {
          self.x = opt + req;
        }
      }
      """)
    self.assertIn("Parameter without a default value 'req' cannot follow a parameter with a default value.", str(ctx.exception))

  def test_default_parameter_ordering_valid(self):
    """Verifies that functions and methods with default parameters placed at the end pass type checking."""
    self._check("""
    func good_func(a: int, b: int = 1): int {
      return a + b;
    }

    trait GoodTrait {
      var func good_method(req: int, opt: int = 0);
    }

    struct GoodStruct {
      var x: int;
    }
    impl GoodStruct {
      var func good_method(req: int, opt: int = 0) {
        self.x = req + opt;
      }
    }
    """)

  def test_cannot_invoke_mutating_method_on_constant(self):
    """Verifies that a mutating method (var func) cannot be called on a constant variable."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Counter {
        var count: int;
      }
      impl Counter {
        func __init__() {
          self.count = 0;
        }
        var func increment() {
          self.count += 1;
        }
      }
      func test() {
        let c = Counter();
        c.increment();
      }
      """)
    self.assertIn("Cannot invoke mutating method 'increment' on constant variable 'c'", str(ctx.exception))

  def test_base_initializer_self_reference_expressions(self):
    """Verifies _expr_references_self across call, binary, unary, and ternary expressions."""
    for expr_str in ("self.helper()", "1 + self.x", "-self.x", "true ? self.x : 0"):
      with self.assertRaises(SemanticError) as ctx:
        self._check(f"""
        struct Parent {{
          var x: int;
        }}
        impl Parent {{
          func __init__(x: int) {{
            self.x = x;
          }}
        }}
        struct Child: Parent {{
          var y: int;
        }}
        impl Child {{
          func helper(): int {{ return 1; }}
          func __init__() : Parent({expr_str}) {{
            self.y = 2;
          }}
        }}
        """)
      self.assertIn("References to 'self' are not allowed in base initializer arguments.", str(ctx.exception))

  def test_parameter_default_type_and_scope_errors(self):
    """Verifies parameter defaults enforce type compatibility and disallow sibling params."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_fn(x: int = "wrong") {}
      """)
    self.assertIn(
        "Default expression of type 'String' is not compatible with parameter 'x' of type 'int'.",
        str(ctx.exception),
    )

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct S {}
      impl S {
        func bad_method(x: int = "wrong") {}
      }
      """)
    self.assertIn(
        "Default expression of type 'String' is not compatible with parameter 'x' of type 'int'.",
        str(ctx.exception),
    )

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_ref(a: int, b: int = a): int {
        return b;
      }
      """)
    self.assertIn("Undefined identifier 'a'", str(ctx.exception))

  def test_named_arguments_validation_errors(self):
    """Verifies ordering, unknown, duplicate, missing, and unnamed fn errors."""
    # Positional argument following a named argument.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func add(a: int, b: int): int {
        return a + b;
      }
      func main(): int {
        return add(a = 1, 2);
      }
      """)
    self.assertIn(
        "Positional argument cannot follow a named argument.",
        str(ctx.exception),
    )

    # Unknown named argument.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func add(a: int, b: int): int {
        return a + b;
      }
      func main(): int {
        return add(a = 1, c = 2);
      }
      """)
    self.assertIn("Unexpected named argument 'c'.", str(ctx.exception))

    # Duplicate via positional + named.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func add(a: int, b: int): int {
        return a + b;
      }
      func main(): int {
        return add(1, a = 2);
      }
      """)
    self.assertIn(
        "Multiple values provided for parameter 'a'.", str(ctx.exception)
    )

    # Duplicate via two named arguments.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func add(a: int, b: int = 10): int {
        return a + b;
      }
      func main(): int {
        return add(a = 1, a = 2);
      }
      """)
    self.assertIn(
        "Multiple values provided for parameter 'a'.", str(ctx.exception)
    )

    # Missing required parameter when optional named args satisfy raw count.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func calc(a: int, b: int = 10, c: int = 20): int {
        return a + b + c;
      }
      func main(): int {
        return calc(b = 1, c = 2);
      }
      """)
    self.assertIn(
        "Missing required argument for parameter 'a'.", str(ctx.exception)
    )

    # Reject named arguments when calling an unnamed FunctionType variable.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func apply_cb(cb: (int) -> int): int {
        return cb(p0 = 5);
      }
      """)
    self.assertIn(
        "Named argument 'p0' is not supported when calling an unnamed function type.",
        str(ctx.exception),
    )

  def test_named_arguments_accepted_across_call_targets_and_range(self):
    """Verifies skipped defaults and reordered named args across call forms."""
    self._check("""
    trait Greeter {
      func greet(a: int, b: int = 10, c: int = 20): int;
    }

    struct Base {
      var x: int;
      var y: int;
      var z: int;
    }

    impl Base {
      func __init__(a: int, b: int = 10, c: int = 20) {
        self.x = a;
        self.y = b;
        self.z = c;
      }

      func compute(a: int, b: int = 10, c: int = 20): int {
        return a + b + c;
      }

      static func create(a: int, b: int = 10, c: int = 20): Base {
        return Base(c = c, a = a);
      }
    }

    impl Greeter for Base {
      func greet(a: int, b: int = 10, c: int = 20): int {
        return a + b + c;
      }
    }

    struct Derived: Base {
      var w: int;
    }

    impl Derived {
      func __init__(a: int, c: int) : Base(c = c, a = a) {
        self.w = 1;
      }
    }

    struct Pair<K, V> {
      let key: K;
      let val: V;
    }

    func make_pair<K, V>(k: K, v: V): Pair<K, V> {
      return Pair<K, V> { key = k, val = v };
    }

    func create_enemy(id: int, hp: int = 10, unit_hp: int = 5): int {
      return id + hp + unit_hp;
    }

    func use_greeter(g: Greeter): int {
      return g.greet(c = 30, a = 5);
    }

    func run(): int {
      let f = create_enemy(id = 1, unit_hp = 19);
      let s = Base.create(c = 3, a = 1);
      let m = s.compute(c = 4, a = 2);
      let d = Derived(c = 7, a = 3);
      let g = use_greeter(d);
      let p = make_pair(v = "hi", k = 42);
      var sum = f + m + g + p.key + d.y + s.z;
      for i in range(stop = 10, step = 2) {
        sum = sum + i;
      }
      return sum;
    }
    """)

  def test_range_invalid_named_calls_rejected(self):
    """Verifies invalid range() named calls fail semantic checking."""
    for bad_call in [
        "range(start = 2)",
        "range(1, start = 2)",
        "range(1, step = 2)",
    ]:
      with self.subTest(bad_call=bad_call):
        with self.assertRaises(SemanticError):
          self._check(f"""
          func main(): int {{
            var s = 0;
            for i in {bad_call} {{
              s = s + i;
            }}
            return s;
          }}
          """)

  def test_semantic_errors_include_source_locations(self):
    """Verifies that call/index semantic errors include line and column."""
    code_non_callable = "func main() {\n  let x = 1;\n  x();\n}\n"
    with self.assertRaises(SemanticError) as ctx:
      self._check_with_file(code_non_callable, "sample.sp") if hasattr(self, "_check_with_file") else None
      input_stream = InputStream(code_non_callable)
      tree = SapphireParser(CommonTokenStream(SapphireLexer(input_stream))).program()
      ast = ASTBuilder().visit(tree)
      checker = TypeChecker(source_file_path="sample.sp", source_content=code_non_callable)
      checker.check(ast)
    self.assertIn("sample.sp:3:2 - Target is not callable.", str(ctx.exception))

    code_arg_mismatch = "func foo(a: int) {}\nfunc main() {\n  foo(\"bad\");\n}\n"
    with self.assertRaises(SemanticError) as ctx:
      input_stream = InputStream(code_arg_mismatch)
      tree = SapphireParser(CommonTokenStream(SapphireLexer(input_stream))).program()
      ast = ASTBuilder().visit(tree)
      checker = TypeChecker(source_file_path="sample.sp", source_content=code_arg_mismatch)
      checker.check(ast)
    self.assertIn("sample.sp:3:6 - Argument type mismatch at position 1.", str(ctx.exception))

  def test_builtin_assert_and_string_slice(self):
    code = """
    func main() {
      assert(true);
      assert(1 + 1 == 2, "math works");
      let s: String = "hello world";
      let a: String = s.slice(0, 5);
      let b: String = s.slice(6);
    }
    """
    self._check(code)

  def test_semantic_warning_does_not_raise(self):
    checker = self._check("func main() {}")
    checker.warning("Test warning message")
    self.assertEqual(len(checker.warnings), 1)
    self.assertIn("Test warning message", checker.warnings[0])
    self.assertEqual(checker.errors, [])

  def test_diagnostic_fix_it_hints(self):
    """Verifies structured diagnostic codes and fix-it hints for common pitfalls."""
    # 1. Struct up-casting
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Parent { var x: int; }
      struct Child: Parent { var y: int; }
      func main() {
        let c = Child { x = 1, y = 2 };
        let p = c as Parent;
      }
      """)
    self.assertIn("Hint: Struct up-casting is prohibited", str(ctx.exception))

    # 2. Borrow escape
    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Box { var x: int; }
      func make_cb(): () -> int {
        let b = Box { x = 5 };
        return () -> int { return b.x; };
      }
      """)
    self.assertIn("Hint: Escaping closures", str(ctx2.exception))

    # 3. Frozen lvalue mutation
    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      func bad(var opt: [int]?) {
        if var arr ?= opt {
          opt = none;
          arr.push(1);
        }
      }
      """)
    self.assertIn("Hint: Capture any needed state", str(ctx3.exception))

  def test_phase4_type_widening_coalescing_comparisons_and_expected_type(self):
    """Verifies Phase 4 widening, ??, ordering ops, optional chaining, and expected_type."""
    # 1. `??` typing: T? ?? T? -> T?, T? ?? none -> T?, reject int? ?? 3.14
    self._check("""
    func f(a: int?, b: int?): int? {
      let c: int? = a ?? b;
      let d: int? = a ?? none;
      return c ?? d;
    }
    """)
    with self.assertRaises(SemanticError):
      self._check("""
      func f(a: int?) {
        let x: int = a ?? 3.14;
      }
      """)
    with self.assertRaises(SemanticError):
      self._check("""
      func f(a: int?, b: int?) {
        let x: int = a ?? b;
      }
      """)

    # 2. Array, map, and match widening
    self._check("""
    func f(opt: int?, flag: bool) {
      let a: [float] = [1, 2.5];
      let b: [int?] = [1, opt];
      let c: [int?] = [1, none];
      let m: [String: int?] = {"a": 1, "b": opt};
      let r: int? = match flag {
        true -> 1,
        false -> opt,
      };
    }
    """)

    # 3. `expected_type` propagated in assignment, return, lambda, and cleared on ternary cond
    self._check("""
    func make_fixed(): [int; 2] {
      return [1, 2];
    }
    func f() {
      var arr: [int; 2] = [0, 0];
      arr = [3, 4];
      let fn: () -> [int; 2] = () -> [5, 6];
      let t: [int; 2] = ([1, 2].size() == 2) ? [7, 8] : [9, 10];
    }
    """)

    # 4. Optional-chained collection calls return OptionalType
    with self.assertRaises(SemanticError):
      self._check("""
      func f(opt_arr: [int]?) {
        let n: int = opt_arr?.size();
      }
      """)
    self._check("""
    func f(opt_arr: [int]?, opt_map: [String: int]?) {
      let n: int? = opt_arr?.size();
      let m: int? = opt_map?.size();
      let g: int? = opt_map?.get("k");
    }
    """)

    # 5. Ordering operators reject optionals, bools, and structs
    for bad_cmp in (
        "func f(a: int?, b: int?): bool { return a < b; }",
        "func f(): bool { return true < false; }",
        "struct S { var x: int; }\nfunc f(a: S, b: S): bool { return a < b; }",
    ):
      with self.assertRaises(SemanticError):
        self._check(bad_cmp)

    # 6. Map indexing strictly rejects int? and float keys on [int: V]
    for bad_key in (
        "func f(m: [int: String], k: int?) { let v = m[k]; }",
        "func f(m: [int: String]) { let v = m[1.5]; }",
        "func f(var m: [int: String], k: int?) { m[k] = \"x\"; }",
    ):
      with self.assertRaises(SemanticError):
        self._check(bad_key)

    # 7. Ref<T> and SharedRef<T> auto-deref on indexing and String/Coroutine/Trait access
    self._check("""
    trait Greeter { func hi(): String; }
    func gen(): Coroutine<int> { yield 1; }
    func f(
        ra: Ref<[int]>,
        sra: SharedRef<[int]>,
        rs: Ref<String>,
        srs: SharedRef<String>,
        rc: Ref<Coroutine<int>>,
        rt: Ref<Greeter>
    ) {
      let a: int = ra[0];
      let b: int = sra[0];
      let u1: String = rs.upper();
      let u2: String = srs.upper();
      let done: bool = rc.is_done();
      let g: String = rt.hi();
    }
    """)

    # 8. Fixed-size array rejects assigning empty dynamic array; var array/map invariance
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let empty = [];
        let fixed: [int; 3] = empty;
      }
      """)
    with self.assertRaises(SemanticError):
      self._check("""
      func push_none(var a: [int?]) { a.push(none); }
      func f() {
        var ints: [int] = [1, 2];
        push_none(ints);
      }
      """)

    # 9. Bare `return;` allowed in `: void` function; `lookup_type` rejects value symbols
    self._check("""
    func f(flag: bool): void {
      if flag { return; }
    }
    """)
    with self.assertRaises(SemanticError):
      self._check("""
      let NOT_A_TYPE = 42;
      func f(x: NOT_A_TYPE) {}
      """)

  def test_phase4_declarations_returns_init_and_diagnostics(self):
    """Verifies return-path, branch-intersected __init__, uninit reads, and decl rules."""
    # 1. Non-void function missing return fails; exhaustive match/if-else passes
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(flag: bool): int {
        if flag { return 1; }
      }
      """)
    self.assertIn("does not return a value on all code paths", str(ctx.exception))

    self._check("""
    enum Mode { A, B }
    func f(m: Mode): int {
      match m {
        Mode.A -> { return 1; },
        Mode.B -> { return 2; },
      }
    }
    """)

    # 2. Branch-intersected __init__ field initialization
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct S { var name: String; }
      impl S {
        func __init__(flag: bool) {
          if flag { self.name = "ok"; }
        }
      }
      """)
    self.assertIn("failed to initialize non-optional field 'name'", str(ctx.exception))

    self._check("""
    struct S { var name: String; }
    impl S {
      func __init__(flag: bool) {
        if flag { self.name = "a"; } else { self.name = "b"; }
      }
    }
    """)

    # 3. Definite-assignment checks for uninitialized non-default locals
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f() {
        let r: Ref<int>;
        let v = r;
      }
      """)
    self.assertIn("Use of uninitialized variable 'r'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(flag: bool) {
        var s: String;
        if flag { s = "hi"; }
        let t = s;
      }
      """)
    self.assertIn("Use of uninitialized variable 's'", str(ctx.exception))

    self._check("""
    func f(flag: bool): String {
      var s: String;
      if flag { s = "a"; } else { s = "b"; }
      return s;
    }
    """)

    # 4. Duplicate parameter names, lambda is_parameter=True, void assignment
    with self.assertRaises(SemanticError):
      self._check("func f(x: int, x: int) {}")
    with self.assertRaises(SemanticError):
      self._check("func f() { let cb = (x: int, x: int) -> x; }")
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let cb = (r: Ref<int>) -> { let r2 = move r; };
      }
      """)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func noop() {}
      func f() { let x = noop(); }
      """)
    self.assertIn("Cannot assign void result", str(ctx.exception))

    # 5. __init__ modifier/return, enum uniformity, duplicate trait method,
    #    self-referencing trait, static-on-instance, and _ASSERTION_NAMES restriction
    with self.assertRaises(SemanticError):
      self._check("struct S { var x: int; }\nimpl S { static func __init__() {} }")
    with self.assertRaises(SemanticError):
      self._check("struct S { var x: int; }\nimpl S { func __init__(): int { self.x = 1; return 1; } }")
    with self.assertRaises(SemanticError):
      self._check('enum Mixed { A = 1, B = "two" }')
    with self.assertRaises(SemanticError):
      self._check("trait T { func f(); func f(); }")
    self._check("trait Mergeable { func merge(other: Mergeable): Mergeable; }")
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct S {}
      impl S { static func make(): int { return 1; } }
      func f() { let s = S {}; s.make(); }
      """)
    self.assertIn("Cannot call static method 'make' on an instance", str(ctx.exception))
    with self.assertRaises(SemanticError):
      self._check("func f() { let x = 42; x.assert_eq(42); }")

    # 6. lints.py suggests `if var` when a `var func` mutating method is called
    checker = self._check("""
    struct Counter { var n: int; }
    impl Counter { var func inc() { self.n += 1; } }
    func f(var m: [String: Counter]) {
      if m.contains("a") {
        m["a"].inc();
      }
    }
    """)
    self.assertTrue(
        any("if var" in w for w in checker.warnings),
        f"Expected 'if var' lint warning, got: {checker.warnings}",
    )

    # 7. Duplicate leaf module names rejected and TestCase not leaked onto std.math
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      import std.math;
      import nonexistent.math;
      func f() {}
      """)
    self.assertIn("Duplicate imported module name 'math'", str(ctx.exception))
    self.assertIn("Cannot resolve imported module 'nonexistent.math'", str(ctx.exception))

    with self.assertRaises(SemanticError):
      self._check("""
      import std.math;
      func f(x: math.TestCase) {}
      """)


if __name__ == "__main__":
  unittest.main()
