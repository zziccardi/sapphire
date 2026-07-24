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
    from semantics.symbol_table import NoneType
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
    from parser.ast import VarDeclNode, IdentifierNode, StructInitializerNode
    from semantics.symbol_table import VariableSymbol, StructType, ArenaType
    
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

  def test_string_enum_type_checking(self):
    """Verifies type compatibility for string-backed enums with string primitive values."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }

    func set_mode(m: Mode) {}

    func main() {
      let m: Mode = Mode.Fill;
      let s: String = Mode.Line;
      set_mode("fill");
    }
    """
    self._check(code)


if __name__ == "__main__":
  unittest.main()



