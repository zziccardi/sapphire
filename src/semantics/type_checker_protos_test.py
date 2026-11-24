"""Prototype, clone, and Arena semantic type-checking tests."""

import unittest

from src.parser.ast import (
  BasicTypeNode,
  IdentifierNode,
  LiteralNode,
)
from src.semantics.symbol_table import (
  PrimitiveType,
  StructType,
  VariableSymbol,
)
from src.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerProtos(TypeCheckerTestBase, unittest.TestCase):
  """Prototype, clone, and Arena semantic type-checking tests."""

  def test_clone_proto_parent_cycle(self):
    """Verifies that clone prototype check handles circular struct inheritance safely without infinite recursion."""
    code = """
    proto A: B { var x: int; }
    proto B: A { var y: int; }
    func test(a: A) {
      let c = clone a;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("Circular inheritance detected involving struct", str(ctx.exception))

  def test_clone_check_proto_cycle_coverage(self):
    """Directly tests check_proto cycle protection in visit_CloneNode."""
    from src.parser.ast import CloneNode


    checker = TypeChecker()
    st_a = StructType("A", parent_names=["B"])
    st_b = StructType("B", parent_names=["A"])
    checker.symbol_table.define_type("A", st_a)
    checker.symbol_table.define_type("B", st_b)
    checker.symbol_table.define("a", VariableSymbol("a", st_a, is_mutable=False))
    node = CloneNode(IdentifierNode("a"))
    checker.visit_CloneNode(node)
    self.assertTrue(any("Cannot clone instance of non-proto struct 'A'" in err for err in checker.errors))

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

    # 16. Lambda without type context fails with unresolved parameter type
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let f = x -> x;
      }
      """)
    self.assertIn("Cannot infer type for lambda parameter 'x'", str(ctx.exception))

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
    from src.parser.ast import TypeNode
    from src.semantics.symbol_table import FunctionType

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
    from src.parser.ast import BinaryOpNode

    bnode = BinaryOpNode(LiteralNode(1, "int"), "invalid-op", LiteralNode(2, "int"))
    checker = TypeChecker()
    self.assertEqual(checker.visit(bnode), PrimitiveType("none"))

    # 40. visit_UnaryOpNode with invalid operator
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
    from src.parser.ast import (
      BlockNode,
      LambdaNode,
      LambdaParamNode,
    )

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
    # Standard struct rejecting __proto__
    with self.assertRaises(SemanticError) as ctx:
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
    self.assertIn("Cannot access '__proto__' on standard struct 'Person'; '__proto__' is only available on 'proto' instances.", str(ctx.exception))

    # Prototype struct allowing __proto__
    self._check("""
    proto Goblin {
      var hp: int;
    }
    func test() {
      var a = Arena();
      let g = Goblin { hp = 100 } in a;
      let parent = g.__proto__;
    }
    """)

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
      func __init__(x: int, y: int): Base(x = x) {
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
      var my_arena = Arena();
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
      var local_arena = Arena();
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

    # 3b. Escape check: return multiple values where a non-first value is arena-allocated
    code_escape_multi_return = """
    proto Enemy {
      var hp: int;
    }
    func escape_multi(): int, Enemy {
      var local_arena = Arena();
      let e = Enemy { hp = 100 } in local_arena;
      return 42, e;
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_escape_multi_return)
    self.assertIn("Cannot return a reference to an object allocated in local arena 'local_arena'", str(context.exception))

    # 4. Escape check: assign local arena reference to outer variable
    code_escape_assign = """
    struct Point {
      var x: int;
    }
    func escape() {
      var outer: Point? = none;
      {
        var local_arena = Arena();
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
      var my_arena = Arena();
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
        var local_arena = Arena();
        let p = Point { x = 10 } in local_arena;
        out.pt = p; // Error: local_arena is nested compared to out
      }
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_member_escape)
    self.assertIn("Variable 'out' in outer scope cannot hold a reference to an object allocated in nested arena 'local_arena'", str(context.exception))

    # 8. Programmatic test for VarDeclNode arena escape (covers type_checker.py line 418)
    from src.parser.ast import (
      StructInitializerNode,
      VarDeclNode,
    )
    from src.semantics.symbol_table import ArenaType


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

  def test_clone_shadow_let_field(self):
    self._check("""
    proto Hero {
      let id: int;
      var hp: int;
    }
    func test() {
      var arena = Arena();
      let base = Hero { id = 1, hp = 100 } in arena;
      let cloned = clone base {
        self.id = 2;
        self.hp = 90;
      };
    }
    """)

  def test_arena_type_has_destructor(self):
    """Verifies that ArenaType defines has_destructor = True."""
    from src.semantics.symbol_table import ArenaType
    arena_t = ArenaType()
    self.assertTrue(arena_t.has_destructor)

  def test_proto_initializer_requires_explicit_arena(self):
    """Verifies that instantiating a proto struct via curly braces without an arena raises a SemanticError."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      proto Goblin {
        var hp: int;
      }
      func test() {
        let g = Goblin { hp = 50 };
      }
      """)
    self.assertIn("Proto instantiation of 'Goblin' requires an explicit arena", str(ctx.exception))

  def test_proto_constructor_requires_explicit_arena(self):
    """Verifies that invoking a proto constructor without an arena raises a SemanticError."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      proto Goblin {
        var hp: int;
      }
      impl Goblin {
        func __init__(hp: int) {
          self.hp = hp;
        }
      }
      func test() {
        let g = Goblin(hp = 50);
      }
      """)
    self.assertIn("Proto constructor call for 'Goblin' requires an explicit arena", str(ctx.exception))

  def test_proto_allocations_with_explicit_arena_succeed(self):
    """Verifies that proto initializer and constructor calls with 'in <arena>' pass type checking."""
    self._check("""
    proto Goblin {
      var hp: int;
    }
    impl Goblin {
      func __init__(hp: int) {
        self.hp = hp;
      }
    }
    func test() {
      var a = Arena();
      let g1 = Goblin(hp = 50) in a;
      let g2 = clone g1 {
        self.hp = 100;
      };
    }
    """)

  def test_function_call_with_in_arena_rejected(self):
    """Verifies that standard function calls cannot have an 'in <arena>' clause."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func compute(x: int): int {
        return x * 2;
      }
      func test() {
        var a = Arena();
        let r = compute(5) in a;
      }
      """)
    self.assertIn("The 'in <arena>' clause can only be used on struct/proto instantiations and clone expressions.", str(ctx.exception))

  def test_proto_let_mutability_and_var_param_enforcement(self):
    """Verifies that let-bound proto instances cannot mutate fields, invoke var func, or be passed to var parameters."""
    # 1. Field mutation on let-bound proto rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      proto Goblin {
        var hp: int;
      }
      func test() {
        var a = Arena();
        let g = Goblin { hp = 50 } in a;
        g.hp = 40;
      }
      """)
    self.assertIn("Cannot mutate field 'hp' of constant struct variable 'g'.", str(ctx.exception))

    # 2. var func call on let-bound proto rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      proto Goblin {
        var hp: int;
      }
      impl Goblin {
        var func hurt() {
          self.hp -= 10;
        }
      }
      func test() {
        var a = Arena();
        let g = Goblin { hp = 50 } in a;
        g.hurt();
      }
      """)
    self.assertIn("Cannot invoke mutating method 'hurt' on constant variable 'g'.", str(ctx.exception))

    # 3. Passing let variable to var parameter rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func shift(var p: Point) {
        p.x += 1;
      }
      func test() {
        let pt = Point { x = 0 };
        shift(p = pt);
      }
      """)
    self.assertIn("Cannot pass constant variable 'pt' to mutable 'var' parameter.", str(ctx.exception))

  def test_boxed_dynamic_and_proto_recursive_types_allowed(self):
    """Verifies Ref, SharedRef, WeakRef, dynamic arrays/maps, and proto break layout recursion."""
    self._check("""
    struct HeapTree {
      var val: int;
      var left: Ref<HeapTree>?;
      var shared_parent: SharedRef<HeapTree>?;
      var weak_parent: WeakRef<HeapTree>?;
      var children: [HeapTree] = [];
      var named: [String: HeapTree] = {};
    }
    proto ArenaNode {
      var id: int;
      var next: ArenaNode?;
    }
    func test() {
      var a = Arena();
      let n = ArenaNode { id = 1, next = none } in a;
      let t = HeapTree {
        val = 1,
        left = none,
        shared_parent = none,
        weak_parent = none,
      };
    }
    """)

  def test_phase3_immutable_and_temp_arena_rejected(self):
    """Rejects `let` arena and temporary/moved arena in `in <arena>`."""
    immut_code = """
    proto Goblin { var hp: int; }
    func main() {
      let a = Arena();
      let g = Goblin { hp = 10 } in a;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(immut_code)
    self.assertIn("immutable Arena 'a'", str(ctx.exception))

    temp_code = """
    proto Goblin { var hp: int; }
    func main() {
      let g = Goblin { hp = 10 } in Arena();
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(temp_code)
    self.assertIn("mutable 'var' Arena variable", str(ctx2.exception))

  def test_phase3_arena_reassignment_and_move_invalidation(self):
    """Rejects using proto refs after arena reset or move; allows overwrite or prior block exit."""
    use_after_reset = """
    proto Goblin { var hp: int; }
    func main(): int {
      var a = Arena();
      var g = Goblin { hp = 10 } in a;
      a = Arena();
      return g.hp;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(use_after_reset)
    self.assertIn("was reassigned or reset", str(ctx.exception))

    use_after_move = """
    proto Goblin { var hp: int; }
    func main(): int {
      var a = Arena();
      let g = Goblin { hp = 10 } in a;
      let b = move a;
      return g.hp;
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(use_after_move)
    self.assertIn("has been moved", str(ctx2.exception))

    valid_reuse = """
    proto Goblin { var hp: int; }
    func main(): int {
      var a = Arena();
      {
        let inner = Goblin { hp = 5 } in a;
      }
      var g = Goblin { hp = 10 } in a;
      a = Arena();
      g = Goblin { hp = 20 } in a;
      return g.hp;
    }
    """
    self._check(valid_reuse)

  def test_phase3_self_arena_reassignment_and_field_order(self):
    """Enforces Arena field order before proto fields and init-only self.arena assignment."""
    bad_order = """
    proto Goblin { var hp: int; }
    struct BadEngine {
      var g: Goblin?;
      var arena: Arena;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(bad_order)
    self.assertIn("must be declared before prototype-referencing field", str(ctx.exception))

    reassign_in_method = """
    proto Goblin { var hp: int; }
    struct Engine {
      var arena: Arena;
      var g: Goblin?;
    }
    impl Engine {
      func __init__() {
        self.arena = Arena();
        self.g = Goblin { hp = 10 } in self.arena;
      }
      var func reset() {
        self.arena = Arena();
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(reassign_in_method)
    self.assertIn("Cannot reassign Arena field 'arena'", str(ctx2.exception))

    dup_init = """
    proto Goblin { var hp: int; }
    struct Engine {
      var arena: Arena;
      var g: Goblin?;
    }
    impl Engine {
      func __init__() {
        self.arena = Arena();
        self.arena = Arena();
        self.g = none;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(dup_init)
    self.assertIn("after initial assignment", str(ctx3.exception))

  def test_directional_proto_lineage_aliasing(self):
    ancestor_conflict = """
    proto Monster { var hp: int; }
    func duel(var m1: Monster, m2: Monster) {}
    func main() {
      var a = Arena();
      var base = Monster { hp = 100 } in a;
      var minion = clone base {};
      duel(base, minion);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(ancestor_conflict)
    self.assertIn(
        "prototype 'base' is mutably borrowed while its cloned descendant "
        "'minion'",
        str(ctx.exception),
    )

    sibling_clones_ok = """
    proto Monster { var hp: int; }
    func duel(var m1: Monster, var m2: Monster) {}
    func main() {
      var a = Arena();
      var base = Monster { hp = 100 } in a;
      var c1 = clone base {};
      var c2 = clone base {};
      duel(c1, c2);
    }
    """
    self._check(sibling_clones_ok)

    immutable_borrows_ok = """
    proto Monster { var hp: int; }
    func observe(m1: Monster, m2: Monster) {}
    func main() {
      var a = Arena();
      var base = Monster { hp = 100 } in a;
      var minion = clone base {};
      observe(base, minion);
    }
    """
    self._check(immutable_borrows_ok)

  def test_phase3_arena_and_stack_borrow_escape_bypasses(self):
    """Verifies all Phase 3 arena and stack-borrow escape bypasses are rejected."""
    # 1. Match block arm yield escaping inner arena
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      func test(flag: bool) {
        var out: Item? = none;
        {
          var a = Arena();
          let p = Item { v = 1 } in a;
          out = match flag {
            true -> { yield p; },
            false -> none
          };
        }
      }
      """)

    # 2. Match expression escaping closure stack borrow
    with self.assertRaises(SemanticError):
      self._check("""
      func test(flag: bool): () -> int {
        var x = 10;
        return match flag {
          true -> { yield () -> x; },
          false -> () -> 0
        };
      }
      """)

    # 3. Calling closure capturing inner-arena proto
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      func test() {
        var out: Item? = none;
        {
          var a = Arena();
          let p = Item { v = 1 } in a;
          let get_p = () -> p;
          out = get_p();
        }
      }
      """)

    # 4. Multi-var decl inside lambda capturing inner-arena proto
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      func test() {
        var out: (() -> int)? = none;
        {
          var a = Arena();
          let p = Item { v = 1 } in a;
          out = () -> int {
            let x, y = 1, p;
            return x + y.v;
          };
        }
      }
      """)

    # 5. Clone initializer block storing shorter-lived proto into longer-lived arena
    with self.assertRaises(SemanticError):
      self._check("""
      proto Node { var next: Node? = none; }
      func test() {
        var outer = Arena();
        let base = Node {} in outer;
        {
          var inner = Arena();
          let short_lived = Node {} in inner;
          let bad = clone base {
            self.next = short_lived;
          } in outer;
        }
      }
      """)

    # 6. Storing borrowed proto parameter into module-level global
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      var G: Item? = none;
      func leak(p: Item) {
        G = p;
      }
      """)

    # 6b. Storing borrowed trait parameter (directly or via local struct) into
    # module-level global must still be rejected.
    with self.assertRaises(SemanticError):
      self._check("""
      trait Service { func run(); }
      struct Holder { var svc: Service; }
      var G: Holder? = none;
      func leak(s: Service) {
        let h = Holder { svc = s };
        G = h;
      }
      """)

    # 6c. Storing concrete non-proto struct with trait fields into module-level
    # global (e.g. Love2D Engine / mock globals) must be allowed.
    self._check("""
    trait Service { func run(); }
    struct ConcreteSvc {}
    impl Service for ConcreteSvc { func run() {} }
    struct Engine { var svc: Service; }
    func create_engine(): Engine {
      return Engine { svc = ConcreteSvc {} };
    }
    var G: Engine? = none;
    func init_global() {
      var eng = create_engine();
      G = eng;
    }
    """)

    # 7. Delegated var method & optional receiver var method escape
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      struct BaseHolder { var slot: Item? = none; }
      impl BaseHolder {
        var func add(it: Item) { self.slot = it; }
      }
      struct ChildHolder : BaseHolder {}
      func test() {
        var child = ChildHolder {};
        {
          var a = Arena();
          let p = Item { v = 1 } in a;
          child.add(p);
        }
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      struct Holder { var slot: Item? = none; }
      impl Holder {
        var func add(it: Item) { self.slot = it; }
      }
      func test() {
        var opt_h: Holder? = Holder {};
        {
          var a = Arena();
          let p = Item { v = 1 } in a;
          opt_h?.add(p);
        }
      }
      """)

    # 8. Arena allocation through intermediate let field and SharedRef
    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      struct Inner { var a: Arena; }
      struct Outer { let inner: Inner; }
      func test() {
        var o = Outer { inner = Inner { a = Arena() } };
        let it = Item { v = 1 } in o.inner.a;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      proto Item { var v: int; }
      struct Holder { var a: Arena; }
      func test() {
        var sr = SharedRef(Holder { a = Arena() });
        let it = Item { v = 1 } in sr.a;
      }
      """)


if __name__ == "__main__":
  unittest.main()
