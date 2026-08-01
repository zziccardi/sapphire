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
      if let active_x ?= opt_x {
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
      if let active_x ?= x {
        let y = active_x;
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Expression in optional unwrapping must resolve to an optional type", str(context.exception))

  def test_init_statements_and_coalesce(self):
    """Verifies init-statements in if/while loops and coalesce operator type-checking."""
    # 1. if let with init-statement + condition
    code1 = """
    func test() {
      var opt_x: int? = none;
      if let x ?= opt_x; x > 10 {
        let y: int = x;
      }
    }
    """
    self._check(code1)

    # 2. while let with init-statement + condition
    code2 = """
    func test() {
      var opt_x: int? = none;
      while let x ?= opt_x; x < 5 {
        let y: int = x;
      }
    }
    """
    self._check(code2)

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
    self.assertIn("Fallback type 'string' is not compatible with the optional's base type 'int'", str(context.exception))

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
    self.assertIn("For-in loop source must be an array or map type", str(context.exception))

  def test_for_map_iteration_valid(self):
    """Verifies type checking for valid map iteration."""
    code = """
    func test() {
      let m = {"a": 1, "b": 2};
      for k, v in m {
        let k_copy: String = k;
        let v_copy: int = v;
      }
    }
    """
    self._check(code)

  def test_for_map_iteration_single_var_error(self):
    """Enforces that iterating over a map requires dual key-value loop variables."""
    code = """
    func test() {
      let m = {"a": 1};
      for item in m {
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Map iteration requires key and value loop variables", str(context.exception))

  def test_for_array_iteration_dual_var_error(self):
    """Enforces that iterating over an array prohibits dual key-value loop variables."""
    code = """
    func test() {
      let arr = [1, 2, 3];
      for k, v in arr {
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot iterate over an array with key-value syntax", str(context.exception))


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
    proto Entity {
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

    # 6. Impl undefined struct
    with self.assertRaises(SemanticError):
      self._check("impl UndefinedStruct {}")

    # 7. Impl undefined trait
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      impl UndefinedTrait for Point {}
      """)

    # 7b. Impl trait not actual trait
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      struct NonTrait {}
      impl NonTrait for Point {}
      """)

    # 7c. Duplicate method in impl
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      impl Point {
        func f() {}
        func f() {}
      }
      """)

    # 8. Standard if condition not bool
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        if 10 {}
      }
      """)

    # 9. Binary operators on wrong types
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = true && 5;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = 10 + true;
      }
      """)

    # 10. Unary operators on wrong types
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = !5;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = -true;
      }
      """)

    # 11. Member access on non-struct
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = 10;
        let y = x.value;
      }
      """)

    # 12. Non-existent field
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      func test() {
        let p = Point();
        let y = p.z;
      }
      """)

    # 13. Clone target not struct
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let x = 10;
        let y = clone x;
      }
      """)

    # 14. Calling parameter count issues (too many arguments)
    with self.assertRaises(SemanticError):
      self._check("""
      func test(a: int) {}
      func run() {
        test(a = 1, b = 2);
      }
      """)

    # 15. Argument type mismatch
    with self.assertRaises(SemanticError):
      self._check("""
      func test(a: int) {}
      func run() {
        test(a = true);
      }
      """)

    # 16. Lambda without type context
    self._check("""
    func test() {
      let f = x -> x;
    }
    """)

    # 17. Undefined type referenced
    with self.assertRaises(SemanticError):
      self._check("""
      func f(x: UndefinedType) {}
      """)

    # 18. Variable initialized with none alone
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let x = none;
      }
      """)

    # 19. Incompatible reassignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        var x = 1;
        x = true;
      }
      """)

    # 20. Undefined identifier assignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        undefined_var = 1;
      }
      """)

    # 21. Non-variable assignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        f = 1;
      }
      """)

    # 22. Property access target not struct in assignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let x = 10;
        x.field = 5;
      }
      """)

    # 23. Struct has no field in assignment
    with self.assertRaises(SemanticError):
      self._check("""
      struct Point {}
      func f() {
        var p = Point();
        p.z = 5;
      }
      """)

    # 24. Indexing non-array in assignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let x = 10;
        x[0] = 5;
      }
      """)

    # 25. Array index not int in assignment
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        var arr = [10];
        arr[true] = 5;
      }
      """)

    # 26. Invalid assignment target
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        10 = 20;
      }
      """)

    # 27. Return mismatch and return outside function context
    try:
      from parser.ast import ReturnNode
    except ModuleNotFoundError:
      from src.parser.ast import ReturnNode
    checker = TypeChecker()
    checker.visit(ReturnNode(None))
    self.assertTrue(len(checker.errors) > 0)

    # 28. Valid for loop on array
    self._check("""
    func test() {
      let arr = [10, 20];
      for x in arr {
        let y = x;
      }
    }
    """)

    # 29. Undefined identifier in expr
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let x = y;
      }
      """)

    # 30. Incompatible comparison
    with self.assertRaises(SemanticError):
      self._check("""
      func f() {
        let x = true == 5;
      }
      """)

    # 31. Float promotion in binary op
    self._check("""
    func f() {
      let x = 10.5 + 5;
    }
    """)

    # 32. Valid optional chaining
    self._check("""
    struct Person { var name: String; }
    func test() {
      var p: Person? = none;
      let name = p?.name;
    }
    """)

    # 33. NotImplementedError in generic visit
    try:
      from parser.ast import ASTNode
    except ModuleNotFoundError:
      from src.parser.ast import ASTNode
    with self.assertRaises(NotImplementedError):
      checker = TypeChecker()
      checker.visit(ASTNode())

    # 34. Double declaration (trait/struct) to trigger struct layout lookup type mismatch
    with self.assertRaises(SemanticError):
      self._check("""
      trait T {}
      struct T {}
      """)

    # 35. Direct _resolve_type_node calls
    try:
      from semantics.symbol_table import PrimitiveType, FunctionType
    except ModuleNotFoundError:
      from src.semantics.symbol_table import PrimitiveType, FunctionType
    try:
      from parser.ast import TypeNode
    except ModuleNotFoundError:
      from src.parser.ast import TypeNode
    checker = TypeChecker()
    self.assertEqual(checker._resolve_type_node(None), PrimitiveType("none"))
    self.assertEqual(checker._resolve_type_node(TypeNode()), PrimitiveType("none"))

    # 36. Optional property assignment
    self._check("""
    struct Person { var name: String; }
    func test() {
      var p: Person? = none;
      p?.name = "Bob";
    }
    """)

    # 37. Expected return type mismatch
    checker = TypeChecker()
    checker.current_function = FunctionType([], PrimitiveType("int"))
    checker.visit(ReturnNode(None))
    self.assertTrue(len(checker.errors) > 0)

    # 38. Standard if/else statement type check
    self._check("""
    func test() {
      if true {
        let x = 1;
      } else {
        let y = 2;
      }
    }
    """)

    # 39. visit_BinaryOpNode with invalid operator
    try:
      from parser.ast import BinaryOpNode, LiteralNode
    except ModuleNotFoundError:
      from src.parser.ast import BinaryOpNode, LiteralNode
    bnode = BinaryOpNode(LiteralNode(1, "int"), "invalid-op", LiteralNode(2, "int"))
    checker = TypeChecker()
    self.assertEqual(checker.visit(bnode), PrimitiveType("none"))

    # 40. visit_UnaryOpNode with invalid operator
    try:
      from parser.ast import UnaryOpNode
    except ModuleNotFoundError:
      from src.parser.ast import UnaryOpNode
    unode = UnaryOpNode("invalid-op", LiteralNode(1, "int"))
    checker = TypeChecker()
    self.assertEqual(checker.visit(unode), PrimitiveType("none"))

    # 41. Lambda with explicit parameter type
    self._check("""
    func test() {
      let f = (x: int) -> x * 2;
    }
    """)

    # 42. Lambda with explicit return type and block body
    try:
      from parser.ast import LambdaNode, BlockNode, LambdaParamNode, BasicTypeNode
    except ModuleNotFoundError:
      from src.parser.ast import LambdaNode, BlockNode, LambdaParamNode, BasicTypeNode
    lnode = LambdaNode(
        parameters=[LambdaParamNode("x", None)],
        return_type=BasicTypeNode("int"),
        body=BlockNode(statements=[])
    )
    checker = TypeChecker()
    self.assertEqual(checker.visit(lnode).return_type, PrimitiveType("int"))

    # 43. Empty array literal
    self._check("""
    func test() {
      let arr = [];
    }
    """)

    # 44. __proto__ property access
    self._check("""
    struct Person {}
    impl Person {
      func __init__() {}
    }
    func test() {
      let p = Person();
      let parent = p.__proto__;
    }
    """)

  def test_aliasing_rules(self):
    """Verifies that Scope-Bound Aliasing constraints are correctly checked."""
    # 1. Reject overlapping mutable-immutable borrows
    code_mut_imm = """
    struct Character {
      var name: String;
    }
    impl Character {
      func __init__(n: String) { self.name = n; }
    }
    func execute(var target: Character, observer: Character) {}
    func test() {
      var player = Character(n = "A");
      execute(target = player, observer = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_mut_imm)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 2. Reject overlapping double mutable borrows
    code_double_mut = """
    struct Character {
      var name: String;
    }
    impl Character {
      func __init__(n: String) { self.name = n; }
    }
    func execute(var target: Character, var other: Character) {}
    func test() {
      var player = Character(n = "A");
      execute(target = player, other = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_double_mut)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 3. Reject hierarchical overlaps
    code_hierarchical = """
    struct Position { var x: float; }
    impl Position { func __init__() { self.x = 0.0; } }
    struct Entity { var pos: Position; }
    impl Entity { func __init__() { self.pos = Position(); } }
    func execute(var parent: Entity, child: Position) {}
    func test() {
      var player = Entity();
      execute(parent = player, child = player.pos);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_hierarchical)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 4. Allow multiple immutable borrows
    code_multi_imm = """
    struct Character {}
    impl Character { func __init__() {} }
    func execute(first: Character, second: Character) {}
    func test() {
      let player = Character();
      execute(first = player, second = player);
    }
    """
    self._check(code_multi_imm)  # Should compile successfully

    # 5. Ignore primitive value types in aliasing check
    code_primitive = """
    func execute(var a: int, b: int) {}
    func test() {
      var num = 10;
      execute(a = num, b = num);
    }
    """
    self._check(code_primitive)  # Should compile successfully

    # 6. Reject implicit mutable receiver aliasing
    code_recv_mut = """
    struct Character { var val: int; }
    impl Character {
      func __init__() { self.val = 0; }
      func mutate(other: Character) { self.val = other.val; }
    }
    func test() {
      var player = Character();
      player.mutate(other = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_recv_mut)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 7. Allow implicit const receiver aliasing
    code_recv_const = """
    struct Character { var val: int; }
    impl Character {
      func __init__() { self.val = 0; }
      const func query(other: Character): int { return self.val; }
    }
    func test() {
      var player = Character();
      let res = player.query(other = player);
    }
    """
    self._check(code_recv_const)  # Should compile successfully

    # 8. Index expression aliasing conflict (resolves index paths)
    code_index_aliasing = """
    struct Item {}
    impl Item { func __init__() {} }
    func execute(var first: Item, var second: Item) {}
    func test() {
      var arr = [Item()];
      execute(first = arr[0], second = arr[0]);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_index_aliasing)
    self.assertIn("Aliasing conflict: variable 'arr' (or a sub-field) is mutably borrowed", str(context.exception))

    # 9. Optional reference type aliasing
    code_opt_ref_aliasing = """
    struct Character {}
    impl Character { func __init__() {} }
    func execute(var first: Character?, observer: Character?) {}
    func test() {
      var player: Character? = Character();
      execute(first = player, observer = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_opt_ref_aliasing)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 10. NoneType passed as argument (does not trigger aliasing conflict)
    code_none_arg = """
    struct Character {}
    impl Character { func __init__() {} }
    func execute(first: Character?, second: Character?) {}
    func test() {
      execute(first = none, second = none);
    }
    """
    self._check(code_none_arg)  # Should compile successfully

    # 11. Optional chained receiver mutable method aliasing
    code_opt_chained_recv = """
    struct Character { var val: int; }
    impl Character {
      func __init__() { self.val = 0; }
      func mutate(other: Character) { self.val = other.val; }
    }
    func test() {
      var player: Character? = Character();
      player?.mutate(other = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_opt_chained_recv)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 12. Direct test for _is_reference_type with NoneType (edge case coverage)
    try:
      from semantics.symbol_table import NoneType
    except ImportError:
      from src.semantics.symbol_table import NoneType
    checker = TypeChecker()
    self.assertFalse(checker._is_reference_type(NoneType()))

  def test_struct_initialization_checking(self):
    """Verifies semantic checking of struct initializers."""
    # 1. Missing required field
    code_missing = """
    struct Point {
      var x: int;
      var y: int;
    }
    func test() {
      let p = Point { x = 10 }; // Missing required field y
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_missing)
    self.assertIn("Struct initializer for 'Point' is missing required field 'y'", str(context.exception))

    # 2. Type mismatch
    code_mismatch = """
    struct Point {
      var x: int;
      var y: int;
    }
    func test() {
      let p = Point { x = 10, y = "not_int" };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_mismatch)
    self.assertIn("Field 'y' in struct 'Point' initializer has type 'string', but expected 'int'", str(context.exception))

    # 3. Valid with default values
    code_valid_defaults = """
    struct Point {
      var x: int;
      var y: int = 42;
    }
    func test() {
      let p = Point { x = 10 }; // Valid because y has default value
    }
    """
    self._check(code_valid_defaults)

  def test_clone_non_proto_error(self):
    """Verifies that cloning a non-proto struct triggers a semantic error."""
    code = """
    struct Item {
      var x: int;
    }
    func test(it: Item) {
      let c = clone it;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot clone instance of non-proto struct 'Item'", str(context.exception))

  def test_clone_struct_non_struct_parent(self):
    """Verifies that cloning a struct inheriting from a non-struct type triggers a semantic error."""
    code = """
    struct Child: UndefinedParent {
      var x: int;
    }
    func test(c: Child) {
      let x = clone c;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Parent struct 'UndefinedParent' not found for 'Child'.", str(context.exception))
    self.assertIn("Cannot clone instance of non-proto struct 'Child'", str(context.exception))

  def test_struct_init_undefined_or_non_struct(self):
    """Verifies that instantiating an undefined struct name or non-struct type raises a semantic error."""
    code = """
    trait SomeTrait {
      func foo();
    }
    func test() {
      let p1 = UndefinedStruct {};
      let p2 = SomeTrait {};
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot instantiate undefined struct 'UndefinedStruct'", str(context.exception))
    self.assertIn("Cannot instantiate undefined struct 'SomeTrait'", str(context.exception))

  def test_struct_initializer_positional_arg_error(self):
    """Verifies that positional arguments in struct initializers (constructed programmatically) trigger a semantic error."""
    try:
      from parser.ast import StructInitializerNode, ArgumentNode, LiteralNode
      from semantics.symbol_table import StructType
    except ModuleNotFoundError:
      from src.parser.ast import StructInitializerNode, ArgumentNode, LiteralNode
      from src.semantics.symbol_table import StructType
    
    checker = TypeChecker()
    struct_type = StructType("Point")
    checker.symbol_table.define_type("Point", struct_type)
    
    arg = ArgumentNode(None, LiteralNode(10, "int"))
    node = StructInitializerNode("Point", [arg])
    
    with self.assertRaises(SemanticError) as context:
      checker.visit(node)
      if checker.errors:
        raise SemanticError("\n".join(checker.errors))
    self.assertIn("Positional arguments are not allowed in struct initializer of 'Point'", str(context.exception))

  def test_struct_init_undefined_field(self):
    """Verifies that initializing a non-existent field in a struct initializer triggers a semantic error."""
    code = """
    struct Point {
      var x: int;
    }
    func test() {
      let p = Point { x = 10, y = 20 };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Struct 'Point' has no field 'y'", str(context.exception))

  def test_struct_init_duplicate_field(self):
    """Verifies that initializing a field multiple times in a struct initializer triggers a semantic error."""
    code = """
    struct Point {
      var x: int;
      var y: int;
    }
    func test() {
      let p = Point { x = 10, y = 20, x = 30 };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Field 'x' is initialized multiple times in struct initializer", str(context.exception))

  def test_clone_struct_inherits_from_proto(self):
    """Verifies that cloning a struct that inherits from a proto struct is valid and succeeds semantic analysis."""
    code = """
    proto Base {
      var x: int;
    }
    struct SubBase: Base {
      var y: int;
    }
    impl Base {
      func __init__(x: int) {
        self.x = x;
      }
    }
    impl SubBase {
      func __init__(x: int, y: int) {
        self.x = x;
        self.y = y;
      }
    }
    func test() {
      let sb = SubBase(x = 10, y = 20);
      let cloned = clone sb;
    }
    """
    self._check(code)


  def test_arena_type_checking(self):
    """Verifies semantic type checking of explicit arenas and escape analysis."""
    # 1. Valid allocation inside explicit arena
    code_valid = """
    struct Point {
      var x: int;
    }
    func test() {
      let my_arena = Arena();
      let p = Point { x = 10 } in my_arena;
    }
    """
    self._check(code_valid)

    # 2. Invalid arena type expression in struct init
    code_invalid_type = """
    struct Point {
      var x: int;
    }
    func test() {
      let p = Point { x = 10 } in 5; // 5 is not an Arena
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_invalid_type)
    self.assertIn("Explicit arena target must be an instance of Arena", str(context.exception))

    # 2b. Invalid arena type expression in clone
    code_invalid_clone = """
    proto Enemy {
      var hp: int;
    }
    func test(e: Enemy) {
      let c = clone e in 5;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_invalid_clone)
    self.assertIn("Explicit arena target must be an instance of Arena", str(context.exception))

    # 3. Escape check: return reference to local arena
    code_escape_return = """
    proto Enemy {
      var hp: int;
    }
    func escape(): Enemy {
      let local_arena = Arena();
      let e = Enemy { hp = 100 } in local_arena;
      let c = clone e in local_arena;
      var arr = [c];
      arr[0] = c;
      return e; // Error: e is allocated in local_arena
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_escape_return)
    self.assertIn("Cannot return a reference to an object allocated in local arena 'local_arena'", str(context.exception))

    # 4. Escape check: assign local arena reference to outer variable
    code_escape_assign = """
    struct Point {
      var x: int;
    }
    func escape() {
      var outer: Point? = none;
      {
        let local_arena = Arena();
        let p = Point { x = 10 } in local_arena;
        outer = p; // Error: local_arena has nested scope compared to outer
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_escape_assign)
    self.assertIn("Variable 'outer' in outer scope cannot hold a reference to an object allocated in nested arena 'local_arena'", str(context.exception))

    # 5. Type mismatch error using ArenaType.__repr__
    code_type_repr = """
    func need_arena(a: Arena) {}
    func test() {
      need_arena(a = 10);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_type_repr)
    self.assertIn("Expected 'Arena'", str(context.exception))

    # 6. Safe allocation in parent scope's arena inside nested scope (triggers _is_descendant_scope returning False)
    code_parent_arena = """
    struct Point {
      var x: int;
    }
    func test() {
      let my_arena = Arena();
      {
        let p = Point { x = 10 } in my_arena; // Safe!
      }
    }
    """
    self._check(code_parent_arena)

    # 7. Escape check: assign local arena reference to member of outer variable
    code_member_escape = """
    struct Point {
      var x: int;
    }
    struct Outer {
      var pt: Point;
    }
    func escape(out: Outer) {
      {
        let local_arena = Arena();
        let p = Point { x = 10 } in local_arena;
        out.pt = p; // Error: local_arena is nested compared to out
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_member_escape)
    self.assertIn("Variable 'out' in outer scope cannot hold a reference to an object allocated in nested arena 'local_arena'", str(context.exception))

    # 8. Programmatic test for VarDeclNode arena escape (covers type_checker.py line 418)
    try:
      from parser.ast import VarDeclNode, IdentifierNode, StructInitializerNode
      from semantics.symbol_table import VariableSymbol, StructType, ArenaType
    except ImportError:
      from src.parser.ast import VarDeclNode, IdentifierNode, StructInitializerNode
      from src.semantics.symbol_table import VariableSymbol, StructType, ArenaType
    
    checker = TypeChecker()
    # Define parent and nested scopes
    parent_scope = checker.symbol_table.current_scope
    checker.symbol_table.enter_scope()
    nested_scope = checker.symbol_table.current_scope
    # Go back to parent scope
    checker.symbol_table.current_scope = parent_scope
    
    # Define local_arena in parent scope so lookup succeeds, but mock its scope_defined to nested_scope!
    arena_sym = VariableSymbol("local_arena", ArenaType(), is_mutable=False)
    checker.symbol_table.define("local_arena", arena_sym)
    arena_sym.scope_defined = nested_scope
    
    # Try to declare a variable in parent scope pointing to local_arena
    init_expr = StructInitializerNode("Point", [], arena_expr=IdentifierNode("local_arena"))
    node = VarDeclNode(is_mutable=False, name="escaped_var", val_type=None, expr=init_expr)
    
    # We must define Point type so it doesn't fail on Point lookup
    checker.symbol_table.define_type("Point", StructType("Point"))
    
    checker.visit(node)
    self.assertTrue(any("in outer scope cannot hold a reference to an object allocated in nested arena" in err for err in checker.errors))

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
      let code: int = Direction.South;
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
    self.assertIn("Return statement outside function context", str(context.exception))

  def test_top_level_script_statements(self):
    """Verifies that top-level script statements pass semantic analysis cleanly."""
  def test_extern_and_export_type_checking(self):
    """Verifies that @extern var and trait signatures permit type-safe calls and reject invalid arguments."""
    code = """
    trait Graphics {
      func rectangle(mode: String, x: float, y: float, w: float, h: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.rectangle(mode = "fill", x = 10.0, y = 20.0, w = 100.0, h = 50.0);
    }
    """
    self._check(code)

    bad_code = """
    trait Graphics {
      func rectangle(mode: String, x: float, y: float, w: float, h: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.rectangle(mode = 123, x = 10.0, y = 20.0, w = 100.0, h = 50.0);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(bad_code)
    self.assertIn("Argument type mismatch at position 1. Expected 'string', got 'int'.", str(context.exception))

    invalid_member_code = """
    trait Graphics {
      func rectangle(mode: String);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.non_existent();
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(invalid_member_code)
    self.assertIn("Trait 'Graphics' has no member 'non_existent'.", str(context.exception))

  def test_extern_var_redefinition(self):
    """Verifies redefinition error for duplicate @extern var identifiers."""
    code = """
    @extern
    var love: int;

    @extern
    var love: float;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Redefinition of identifier 'love'.", str(context.exception))

  def test_extern_var_invalid_declaration(self):
    """Verifies semantic errors for @extern variable declarations with initializers or missing type annotations."""
    code_init = """
    @extern
    let love = 123;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_init)
    self.assertIn("An '@extern' variable declaration cannot have an initializer expression.", str(context.exception))

    code_missing_type = """
    @extern
    var love;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_missing_type)
    self.assertIn("An '@extern' variable declaration for 'love' requires an explicit type annotation.", str(context.exception))

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
    self.assertIn("Cannot return value of type 'string' for return value #2", str(context.exception))

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
    try:
      from semantics.type_checker import TypeChecker
      from semantics.symbol_table import PrimitiveType
      from parser.ast import BasicTypeNode
    except ModuleNotFoundError:
      from src.semantics.type_checker import TypeChecker
      from src.semantics.symbol_table import PrimitiveType
      from src.parser.ast import BasicTypeNode

    tc = TypeChecker()
    self.assertEqual(tc._resolve_type_node(None), PrimitiveType("none"))

    class DummyWithReturnType:
      return_type = BasicTypeNode("int")

    res_types = tc._resolve_return_types(DummyWithReturnType())
    self.assertEqual(res_types, [PrimitiveType("int")])

  def test_string_enum_type_checking_valid(self):
    """Verifies type compatibility for string-backed enums with string primitive values."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }

    func main() {
      let m: Mode = Mode.Fill;
      let s: String = Mode.Line;
    }
    """
    self._check(code)

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
    self.assertIn("Argument type mismatch at position 1. Expected 'Mode', got 'string'.", str(context.exception))

  def test_trait_self_parameter_type_checking(self):
    """Verifies argument checking for trait methods with explicit self parameters."""
    code = """
    trait ImageHandle {
      func draw(self, x: float, y: float);
      func getWidth(var self): float;
    }

    @extern
    var img: ImageHandle;

    func main() {
      img.draw(10.0, 20.0);
      let w = img.getWidth();
    }
    """
    self._check(code)

  def test_trait_export_method_type_checking(self):
    """Verifies type checking for trait methods annotated with @export."""
    code = """
    trait Graphics {
      @export("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }

    @extern
    var g: Graphics;

    func main() {
      g.setColorRGBA(1.0, 0.0, 0.0);
    }
    """
    self._check(code)


  def test_module_export_manifest_validation(self):
    """Verifies that export manifests with valid definitions and re-exported symbols type check clean."""
    code = """
    import lib.love2d.enums;

    export {
      Player,
      create_player,
      enums.DrawMode,
    };

    struct Player {
      var name: String;
    }

    func create_player(name: String): Player {
      return Player { name = name };
    }
    """
    self._check(code)

  def test_undefined_export_symbol_error(self):
    """Verifies that exporting an undefined symbol raises a SemanticError."""
    code = """
    export {
      NonExistentSymbol,
    };
    """
    with self.assertRaises(SemanticError):
      self._check(code)

  def test_module_export_errors_and_type_resolution(self):
    """Verifies module type resolution and export error branches."""
    try:
      from semantics.symbol_table import ModuleSymbol, PrimitiveType, VariableSymbol, StructType, EnumType
    except ModuleNotFoundError:
      from src.semantics.symbol_table import ModuleSymbol, PrimitiveType, VariableSymbol, StructType, EnumType

    # 1. Export from non-imported module
    with self.assertRaises(SemanticError):
      self._check("""
      export {
        unimported.Symbol,
      };
      """)

    # 2. Export non-existent symbol from imported module with populated exports
    code = """
    import lib.love2d.enums;
    export {
      enums.MissingSymbol,
    };
    """
    checker = TypeChecker()
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker._declare_imports(ast)
    enums_sym = checker.symbol_table.lookup("enums")
    if isinstance(enums_sym, ModuleSymbol):
      enums_sym.exports["DrawMode"] = VariableSymbol("DrawMode", PrimitiveType("int"), is_mutable=False)

    with self.assertRaises(SemanticError):
      checker.check(ast)

  def test_module_qualified_type_and_member_access(self):
    """Verifies type resolution for dot-qualified types (enums.DrawMode) and member access."""
    try:
      from semantics.symbol_table import ModuleSymbol, PrimitiveType, VariableSymbol, StructType, EnumType
    except ModuleNotFoundError:
      from src.semantics.symbol_table import ModuleSymbol, PrimitiveType, VariableSymbol, StructType, EnumType

    code = """
    import lib.love2d.enums;

    var mode: enums.DrawMode;
    let mode_val = enums.DrawMode;
    let missing_member = enums.NonExistent;
    """
    checker = TypeChecker()
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker._declare_imports(ast)
    enums_sym = checker.symbol_table.lookup("enums")
    if isinstance(enums_sym, ModuleSymbol):
      enums_sym.exports["DrawMode"] = EnumType("DrawMode")

    checker.check(ast)

  def test_real_file_module_import(self):
    """Verifies that type checking graphics.sp automatically resolves lib.love2d.enums."""
    import os
    graphics_path = os.path.join("lib", "love2d", "graphics.sp")
    with open(graphics_path, "r", encoding="utf-8") as f:
      code = f.read()

    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker(source_file_path=graphics_path)
    checker.check(ast)
    self.assertEqual(len(checker.errors), 0)

  def test_unqualified_module_type_rejected(self):
    """Verifies that using an unqualified type from an imported module raises an error."""
    code = """
    import lib.love2d.enums;
    func test(mode: DrawMode) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    with self.assertRaises(SemanticError) as cm:
      checker.check(ast)
    self.assertIn("Undefined type 'DrawMode'", str(cm.exception))

  def test_qualified_module_type_accepted(self):
    """Verifies that using a dot-qualified type from an imported module succeeds."""
    code = """
    import lib.love2d.enums;
    func test(mode: enums.DrawMode) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(len(checker.errors), 0)

  def test_reexport_module_specifier(self):
    """Verifies re-exporting a symbol from an imported module."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
      mod_a = os.path.join(tmpdir, "mod_a.sp")
      with open(mod_a, "w") as f:
        f.write("import lib.love2d.enums as e;\nexport {\n  e.DrawMode,\n};\n")

      code = f"import mod_a;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)
      mod_a_sym = checker.symbol_table.lookup("mod_a")
      self.assertIsNotNone(mod_a_sym)
      self.assertIn("DrawMode", mod_a_sym.exports)

  def test_qualified_type_fallback_struct(self):
    """Verifies dot-qualified fallback to StructType when not ending in Mode or Code."""
    code = """
    import lib.love2d.enums;
    func test(s: enums.CustomStruct) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(len(checker.errors), 0)


  def test_module_import_with_error(self):
    """Verifies graceful handling when an imported module contains syntax or semantic errors."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
      invalid_sp = os.path.join(tmpdir, "invalid.sp")
      with open(invalid_sp, "w") as f:
        f.write("let x: int = true;\n")

      code = "import invalid;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)

      syntax_err_sp = os.path.join(tmpdir, "syntax_err.sp")
      with open(syntax_err_sp, "w") as f:
        f.write("func {\n")

      code2 = "import syntax_err;\n"
      input_stream2 = InputStream(code2)
      lexer2 = SapphireLexer(input_stream2)
      stream2 = CommonTokenStream(lexer2)
      parser2 = SapphireParser(stream2)
      tree2 = parser2.program()
      ast2 = ASTBuilder().visit(tree2)

      checker2 = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker2.check(ast2)

  def test_import_module_without_export_block(self):
    """Verifies importing a module without explicit export manifest exports all top-level types and symbols."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
      no_exp = os.path.join(tmpdir, "no_exp.sp")
      with open(no_exp, "w") as f:
        f.write("struct CustomItem {}\n")

      code = "import no_exp;\nvar item: no_exp.CustomItem;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)
  def test_match_expression(self):
    """Tests semantic analysis and type checking of match expressions."""
    valid_code = """
    enum Status { Ok, NotFound, Error }

    func test_match(s: Status): String {
      let msg = match s {
        Status.Ok -> "Success",
        Status.NotFound -> {
          yield "Not Found";
        },
        ... -> "Generic Error",
      };
      return msg;
    }

    func test_side_effect(s: Status) {
      match s {
        Status.Ok -> {
          let x = 1;
        },
        ... -> {
          let y = 2;
        },
      };
    }
    """
    self._check(valid_code)

    non_exhaustive = """
    enum Status { Ok, NotFound, Error }
    func test_bad(s: Status) {
      let x = match s {
        Status.Ok -> 1,
      };
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(non_exhaustive)
    self.assertIn("Match expression for enum 'Status' is not exhaustive", str(ctx.exception))

    # Bool exhaustiveness
    self._check("func b(v: bool): int { return match v { true -> 1, false -> 0 }; }")
    with self.assertRaises(SemanticError) as ctx:
      self._check("func b(v: bool) { let x = match v { true -> 1 }; }")
    self.assertIn("Match expression for bool is not exhaustive", str(ctx.exception))

    # Optional exhaustiveness
    self._check("func o(v: int?): int { return match v { none -> 0, ... -> 1 }; }")
    with self.assertRaises(SemanticError) as ctx:
      self._check("func o(v: int?) { let x = match v { none -> 0 }; }")
    self.assertIn("Match expression for optional", str(ctx.exception))

    # Identifier catch-all pattern
    self._check("func i(v: int): String { return match v { val -> \"ok\" }; }")

    # Incompatible pattern type
    with self.assertRaises(SemanticError) as ctx:
      self._check("func i(v: int) { let x = match v { \"bad\" -> 1, ... -> 0 }; }")
    self.assertIn("Pattern type 'string' is incompatible with subject type 'int'", str(ctx.exception))

    # Incompatible yield types
    with self.assertRaises(SemanticError) as ctx:
      self._check("func i(v: int) { let x = match v { 1 -> { yield 10; yield \"str\"; }, ... -> 0 }; }")
    self.assertIn("Incompatible yield types in match case", str(ctx.exception))

    # Incompatible branch return types
    with self.assertRaises(SemanticError) as ctx:
      self._check("func i(v: int) { let x = match v { 1 -> 10, ... -> \"str\" }; }")
    self.assertIn("Incompatible return types in match branches", str(ctx.exception))

    # Enum member access pattern
    self._check("""
    enum Status { Ok, NotFound }
    func test_enum_pat(s: Status): int {
      return match s {
        Status.Ok -> 1,
        Status.NotFound -> 2,
      };
    }
    """)

    # Struct member pattern type mismatch
    with self.assertRaises(SemanticError):
      self._check("""
      struct Item { var id: int; }
      func test_item(i: Item) {
        let x = match i {
          i.id -> 1,
          ... -> 0,
        };
      }
      """)

    # Non-literal/non-member pattern type mismatch
    with self.assertRaises(SemanticError):
      self._check("""
      func test_bin_pat(n: int) {
        let a = 1;
        let b = 2;
        let x = match n {
          "invalid" -> 1,
          ... -> 0,
        };
      }
      """)

    # Enum identifier pattern matching enum type name
    self._check("""
    enum Status { Status }
    func test_enum_name(s: Status): int {
      return match s {
        Status -> 1,
        ... -> 0,
      };
    }
    """)

    # Optional type wrapping fallback in match return
    self._check("""
    func test_opt_fall(n: int): int? {
      return match n {
        1 -> 10,
        ... -> none,
      };
    }
    """)

    # Arena return escaping error
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Item {}
      func test_arena_escape(): Item {
        let a = Arena();
        return Item {} in a;
      }
      """)
    self.assertIn("Cannot return a reference to an object allocated in local arena", str(ctx.exception))

  def test_compiler_fixes_and_inference(self):
    """Verifies parenthesized types, optional lambda parameter inference, and struct initializer context propagation."""
    # 1. Parenthesized optional function types
    self._check("""
    func test_parenthesized_type(cb: ((int) -> void)?) {
      let x: ((int) -> void)? = cb;
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

    # 5. Unwrapping non-optional in while let (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        while let x ?= 42; x > 0 { }
      }
      """)
    self.assertIn("Expression in optional unwrapping must resolve to an optional type", str(ctx.exception))

    # 6. Non-boolean condition in while let (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var opt_x: int? = none;
        while let x ?= opt_x; 42 { }
      }
      """)
    self.assertIn("While condition must resolve to 'bool'", str(ctx.exception))

    # 7. Standard while let binding without condition (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        while let x = 42 { }
      }
      """)
    self.assertIn("Init-statement in 'while' must be followed by a condition unless using optional unwrapping", str(ctx.exception))

    # 8. Left operand of ?? not optional (should error)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let val = 42 ?? 99;
      }
      """)
    self.assertIn("Left operand of '??' must be an optional type", str(ctx.exception))

  def test_map_literal_type_checking(self):
    """Verifies type checking for map literals, key type restrictions, homogeneity, and indexing."""
    # 1. Valid string, int, and enum keyed maps
    self._check("""
    enum Direction { North, South }

    func test() {
      let string_map = {"alice": 100, "bob": 95,};
      let int_map = {1: "low", 2: "high"};
      let enum_map = {Direction.North: 10, Direction.South: 20};

      let score: int = string_map["alice"];
      let level: String = int_map[1];
      let speed: int = enum_map[Direction.North];
    }
    """)

    # 2. Invalid key type (boolean key)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {true: 1};
      }
      """)
    self.assertIn("Map key must be a string, int, or enum.", str(ctx.exception))

    # 3. Inconsistent key types (mixed int and string keys)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, 2: 95};
      }
      """)
    self.assertIn("Inconsistent key types in map literal.", str(ctx.exception))

    # 4. Inconsistent value types (mixed int and string values)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, "bob": "95"};
      }
      """)
    self.assertIn("Inconsistent value types in map literal.", str(ctx.exception))

    # 5. Map index type mismatch
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let string_map = {"alice": 100};
        let val = string_map[123];
      }
      """)
    self.assertIn("Map index type 'int' is not compatible with key type 'string'.", str(ctx.exception))

    # 6. Empty map literal
    self._check("""
    func test() {
      let empty_map = {};
    }
    """)

    # 7. Invalid key type on subsequent entry
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let bad_map = {"alice": 100, true: 200};
      }
      """)
    self.assertIn("Map key must be a string, int, or enum.", str(ctx.exception))

  def test_array_compile_time_bounds_checking(self):
    """Verifies compile-time bounds checking for array indexing."""
    # 1. Out of bounds index on array literal
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let x = [10, 20, 30][3];
      }
      """)
    self.assertIn("Array index out of bounds: index 3 is out of bounds for array of size 3.", str(ctx.exception))

    # 2. Negative index on array literal
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let x = [10, 20, 30][-1];
      }
      """)
    self.assertIn("Array index out of bounds: negative index '-1' is not allowed.", str(ctx.exception))

    # 3. Out of bounds index on array variable
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let arr = [10, 20];
        let val = arr[5];
      }
      """)
    self.assertIn("Array index out of bounds: index 5 is out of bounds for array of size 2.", str(ctx.exception))

    # 4. Out of bounds assignment to array variable
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var arr = [1, 2, 3];
        arr[10] = 50;
      }
      """)
    self.assertIn("Array index out of bounds: index 10 is out of bounds for array of size 3.", str(ctx.exception))

    # 5. Valid constant indexing
    self._check("""
    func test() {
      let arr = [10, 20, 30];
      let first = arr[0];
      let last = arr[2];
    }
    """)

  def test_map_compile_time_key_validation(self):
    """Verifies compile-time key checking for map literals."""
    # 1. Missing key in map literal
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let val = {"alice": 100, "bob": 95}["charlie"];
      }
      """)
    self.assertIn("Key 'charlie' not found in map literal.", str(ctx.exception))

    # 2. Valid key in map literal
    self._check("""
    func test() {
      let score = {"alice": 100, "bob": 95}["alice"];
    }
    """)

  def test_array_type_node_resolution_and_none_inference(self):
    """Verifies ArrayTypeNode resolution and error when inferring type from none alone."""
    try:
      from parser.ast import ArrayTypeNode, BasicTypeNode, VarDeclNode, ArrayLiteralNode, LiteralNode
      from semantics.symbol_table import ArrayType, PrimitiveType
    except ModuleNotFoundError:
      from src.parser.ast import ArrayTypeNode, BasicTypeNode, VarDeclNode, ArrayLiteralNode, LiteralNode
      from src.semantics.symbol_table import ArrayType, PrimitiveType

    checker = TypeChecker()
    res = checker._resolve_type_node(ArrayTypeNode(BasicTypeNode("int")))
    self.assertEqual(res, ArrayType(PrimitiveType("int")))

    var_decl = VarDeclNode(
        is_mutable=False,
        names=["arr"],
        val_types=[ArrayTypeNode(BasicTypeNode("int"))],
        exprs=[ArrayLiteralNode([LiteralNode(10, "int"), LiteralNode(20, "int")])],
    )
    checker.visit_VarDeclNode(var_decl)
    sym = checker.symbol_table.lookup("arr")
    self.assertEqual(sym.symbol_type, ArrayType(PrimitiveType("int"), size=2))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let x = none;
      }
      """)
    self.assertIn("Cannot infer type of 'x' from 'none' alone.", str(ctx.exception))

  def test_clone_shadow_let_field(self):
    self._check("""
    proto Hero {
      let id: int;
      var hp: int;
    }
    func test() {
      let base = Hero { id = 1, hp = 100 };
      let cloned = clone base {
        self.id = 2;
        self.hp = 90;
      };
    }
    """)


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
    self.assertIn("Cannot cast 'string' to 'int' using 'as'", str(ctx.exception))

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

  def test_interpolated_string_struct_error(self):
    """Verifies that interpolating a struct directly triggers a type error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Player {
        var name: String;
      }
      func test() {
        var p: Player = Player { name = "Hero" };
        let msg = f"Player: {p}";
      }
      """)
    self.assertIn("Cannot interpolate struct type 'Player' directly into string", str(ctx.exception))


if __name__ == "__main__":
  unittest.main()



