"""Ownership, move, borrow, aliasing, and mutability semantic tests."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from src.parser.ast import (
  ArgumentNode,
  BasicTypeNode,
  CallNode,
  IdentifierNode,
  LiteralNode,
)
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.symbol_table import (
  ArrayType,
  PrimitiveType,
  StructField,
  StructType,
)
from src.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerOwnership(TypeCheckerTestBase, unittest.TestCase):
  """Ownership, move, borrow, aliasing, and mutability semantic tests."""

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
      var func mutate(other: Character) { self.val = other.val; }
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
      func query(other: Character): int { return self.val; }
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
      var func mutate(other: Character) { self.val = other.val; }
    }
    func test() {
      var player: Character? = Character();
      player?.mutate(other = player);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_opt_chained_recv)
    self.assertIn("Aliasing conflict: variable 'player' (or a sub-field) is mutably borrowed", str(context.exception))

    # 12. Direct test for _is_reference_type with all types
    from src.semantics.symbol_table import (
      ArenaType,
      MapType,
      NoneType,
      OptionalType,
      PrimitiveType,
      RangeType,
      StringType,
    )

    checker = TypeChecker()
    # Value types
    self.assertFalse(checker._is_reference_type(PrimitiveType("int")))
    self.assertFalse(checker._is_reference_type(PrimitiveType("float")))
    self.assertFalse(checker._is_reference_type(PrimitiveType("bool")))
    self.assertFalse(checker._is_reference_type(NoneType()))
    self.assertFalse(checker._is_reference_type(OptionalType(PrimitiveType("int"))))

    # Reference types
    self.assertTrue(checker._is_reference_type(StringType()))
    self.assertTrue(checker._is_reference_type(ArrayType(PrimitiveType("int"))))
    self.assertTrue(checker._is_reference_type(MapType(StringType(), PrimitiveType("int"))))
    self.assertTrue(checker._is_reference_type(ArenaType()))
    self.assertTrue(checker._is_reference_type(RangeType()))
    self.assertTrue(checker._is_reference_type(StructType("Point")))
    self.assertTrue(checker._is_reference_type(StructType("Enemy", is_prototype=True)))
    self.assertTrue(checker._is_reference_type(OptionalType(StringType())))

    # 13. Verify aliasing conflicts for builtin reference types (String, Array, Map, Arena, Range)
    code_builtin_ref_aliasing = """
    func test_str(var a: String, b: String) {}
    func test_arr(var a: [int], b: [int]) {}
    func test_map(var a: [String: int], b: [String: int]) {}
    func test_arena(var a: Arena, b: Arena) {}
    func test_range(var a: Range, b: Range) {}

    func run() {
      var s = "hello";
      test_str(a = s, b = s);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_builtin_ref_aliasing)
    self.assertIn("Aliasing conflict: variable 's'", str(context.exception))

  def test_top_level_let_type_alias_resolution(self):
    """Verifies type checking of top-level let type aliases (e.g. let Unit = mod.Unit, let Local = Unit)."""
    from src.semantics.symbol_table import (
      ModuleSymbol,
      StringType,
      StructSymbol,
    )

    code = """
    let Unit = mod.Unit;
    let LocalUnit = Unit;

    func process(u: LocalUnit): String {
      return u.name;
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    mod_sym = ModuleSymbol("mod", "mod.sp")
    unit_struct = StructType("Unit")
    unit_struct.fields["name"] = StructField("name", StringType(), False)
    mod_sym.exports["Unit"] = StructSymbol("Unit", unit_struct)
    checker.symbol_table.define("mod", mod_sym)

    checker.check(ast)

  def test_encapsulation_pod_struct_on_let_binding_rejected(self):
    """Verifies that field mutation on a let-bound struct is rejected."""
    from antlr4 import CommonTokenStream, InputStream

    from src.parser.ast_builder import ASTBuilder
    from src.parser.gen.SapphireLexer import SapphireLexer
    from src.parser.gen.SapphireParser import SapphireParser
    from src.semantics.symbol_table import (
      ModuleSymbol,
      PrimitiveType,
    )

    code = """
    func test() {
      let p = math.Point { x = 1.0 };
      p.x = 10.0;
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker(source_file_path="main.sp")
    mod_sym = ModuleSymbol("math", "lib/math.sp")
    point_struct = StructType("Point", defining_module="lib/math.sp", is_imported=True)
    point_struct.fields["x"] = StructField("x", PrimitiveType("float"), is_mutable=True)
    mod_sym.exports["Point"] = point_struct
    checker.symbol_table.define("math", mod_sym)

    with self.assertRaises(SemanticError) as ctx:
      checker.check(ast)
    self.assertIn("Cannot mutate field 'x' of constant struct variable 'p'.", str(ctx.exception))

  def test_move_constant_allowed(self):
    """Verifies that moving a let constant succeeds and invalidates subsequent reads."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let a = 10;
        let b = move a;
        let c = a;
      }
      """)
    self.assertIn("Use of moved variable 'a'.", str(ctx.exception))

  def test_move_use_after_move_rejected(self):
    """Verifies that reading a moved variable produces a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var a = 10;
        let b = move a;
        let c = a;
      }
      """)
    self.assertIn("Use of moved variable 'a'.", str(ctx.exception))

  def test_move_again_after_move_rejected(self):
    """Verifies that moving an already-moved variable produces a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var a = 10;
        let b = move a;
        let c = move a;
      }
      """)
    self.assertIn("Use of moved variable 'a'.", str(ctx.exception))

  def test_move_borrowed_parameter_rejected(self):
    """Verifies that moving out of borrowed parameters is prohibited."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_const(p: int) {
        let b = move p;
      }
      """)
    self.assertIn("Cannot move out of borrowed parameter 'p'.", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_var(var p: int) {
        let b = move p;
      }
      """)
    self.assertIn("Cannot move out of borrowed parameter 'p'.", str(ctx.exception))

  def test_move_reinitialization_restores_liveness(self):
    """Verifies that assigning a new value to a moved var variable restores its liveness."""
    self._check("""
    func test() {
      var a = 10;
      let b = move a;
      a = 20;
      let c = move a;
    }
    """)

  def test_move_undefined_variable_rejected(self):
    """Verifies moving an undefined variable raises a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let b = move not_defined;
      }
      """)
    self.assertIn("Cannot move undefined variable 'not_defined'.", str(ctx.exception))

  def test_move_in_branching(self):
    """Verifies that moving a variable inside an if branch invalidates it after the branch."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(cond: bool) {
        var a = 10;
        if cond {
          let b = move a;
        }
        let c = a;
      }
      """)
    self.assertIn("Use of moved variable 'a'.", str(ctx.exception))

  def test_move_in_loop_without_reinitialization_rejected(self):
    """Verifies that moving an outer variable inside a loop without re-initialization is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var a = 10;
        while true {
          let b = move a;
        }
      }
      """)
    self.assertIn("Cannot move variable 'a' inside a loop without re-assigning it before the next iteration.", str(ctx.exception))

  def test_move_in_loop_with_reinitialization_allowed(self):
    """Verifies that moving and re-initializing an outer variable in a loop is permitted."""
    self._check("""
    func test() {
      var a = 10;
      while true {
        let b = move a;
        a = 20;
      }
    }
    """)

  def test_move_member_access_rejected(self):
    """Verifies accessing a member on a moved variable is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func test() {
        var p = Point { x = 1 };
        let v = move p.x;
      }
      """)
    self.assertIn("Cannot access member 'x' on moved variable 'p'.", str(ctx.exception))

  def test_ref_constructor_and_auto_deref(self):
    """Verifies Ref() creates Ref<T> and auto-dereferences fields and methods."""
    self._check("""
    struct Point {
      var x: int;
      var y: int;
    }
    impl Point {
      func get_sum(): int {
        return self.x + self.y;
      }
    }
    func test() {
      let r = Ref(Point { x = 10, y = 20 });
      let sum = r.get_sum();
      let x_val = r.x;
    }
    """)

  def test_ref_requires_explicit_move_on_assignment(self):
    """Verifies that copying Ref<T> without explicit 'move' is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func test() {
        var a = Ref(Point { x = 10 });
        let b = a; // Error: cannot copy move-only type Ref<Point>
      }
      """)
    self.assertIn("Cannot copy move-only type 'Ref<Point>'; use explicit 'move a' to transfer ownership.", str(ctx.exception))

  def test_ref_explicit_move_succeeds_and_invalidates_source(self):
    """Verifies that 'let b = move a;' succeeds and invalidates 'a'."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func test() {
        var a = Ref(Point { x = 10 });
        let b = move a;
        let v = a.x; // Error: use of moved variable
      }
      """)
    self.assertIn("Use of moved variable 'a'.", str(ctx.exception))

  def test_ref_function_passing_move_vs_borrow(self):
    """Verifies that passing Ref<T> to T borrows, but passing to Ref<T> requires move."""
    self._check("""
    struct Point {
      var x: int;
    }
    func read_point(p: Point) {
      let v = p.x;
    }
    func take_ref(r: Ref<Point>) {
      let v = r.x;
    }
    func test() {
      var a = Ref(Point { x = 10 });
      read_point(a); // Safe auto-borrow; 'a' is not moved!
      take_ref(move a); // Explicit move transfers ownership
    }
    """)

  def test_ref_function_passing_lvalue_without_move_rejected(self):
    """Verifies that passing an lvalue Ref<T> by value without 'move' is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func take_ref(r: Ref<Point>) {}
      func test() {
        var a = Ref(Point { x = 10 });
        take_ref(a); // Error: must use move
      }
      """)
    self.assertIn("Cannot pass move-only type 'Ref<Point>' by value; use explicit 'move a' to transfer ownership.", str(ctx.exception))

  def test_shared_ref_direct_and_from_moved_ref(self):
    """Verifies SharedRef() constructor from value and from moved Ref."""
    self._check("""
    struct Point {
      var x: int;
    }
    func test() {
      // Direct construction
      let s1 = SharedRef(Point { x = 10 });
      let x1 = s1.x;

      // Promotion from unique Ref
      var r = Ref(Point { x = 20 });
      let s2 = SharedRef(move r);
      let x2 = s2.x;
    }
    """)

  def test_shared_ref_share_downgrade_and_upgrade(self):
    """Verifies SharedRef .share(), .downgrade(), and WeakRef .upgrade()."""
    self._check("""
    struct Point {
      var x: int;
    }
    func test() {
      let s = SharedRef(Point { x = 10 });
      let s2 = s.share();
      let w = s.downgrade();
      if let active ?= w.upgrade() {
        let v = active.x;
      }
    }
    """)

  def test_weak_ref_direct_access_rejected(self):
    """Verifies that accessing members directly on WeakRef without upgrade() is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func test() {
        let s = SharedRef(Point { x = 10 });
        let w = s.downgrade();
        let v = w.x; // Error: must call .upgrade()
      }
      """)
    self.assertIn("WeakRef has no member 'x'; call '.upgrade()' to access the underlying value.", str(ctx.exception))

  def test_shared_ref_as_mutable_var_param_rejected(self):
    """Verifies that passing SharedRef to a mutable 'var' parameter is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int;
      }
      func mutate(var p: Point) {
        p.x = 20;
      }
      func test() {
        let s = SharedRef(Point { x = 10 });
        mutate(s);
      }
      """)
    self.assertIn("Cannot pass 'SharedRef<Point>' as mutable 'var' parameter; shared references are read-only borrows.", str(ctx.exception))

  def test_smart_ref_constructor_errors_and_edge_cases(self):
    """Verifies compile-time validation for Ref, SharedRef, and WeakRef constructors."""
    # 1. Ref() in arena rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      func test() {
        var a = Arena();
        let r = Ref(Box { v = 1 }) in a;
      }
      """)
    self.assertIn("Ref() allocations cannot specify an 'in <arena>' clause.", str(ctx.exception))

    # 2. Ref() wrong arity
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let r = Ref();
      }
      """)
    self.assertIn("Ref() constructor expects 1 argument, got 0.", str(ctx.exception))

    # 3. Ref<T> type mismatch via explicit type_args on CallNode
    checker = TypeChecker()
    call_ref_mismatch = CallNode(
        callee=IdentifierNode("Ref"),
        arguments=[ArgumentNode(None, LiteralNode("hi", "string"))],
        type_args=[BasicTypeNode("int")],
    )
    checker.visit_CallNode(call_ref_mismatch)
    self.assertTrue(any("Ref<int> expected argument of type 'int', got 'String'." in e for e in checker.errors))

    # 4. SharedRef() in arena rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      func test() {
        var a = Arena();
        let s = SharedRef(Box { v = 1 }) in a;
      }
      """)
    self.assertIn("SharedRef() allocations cannot specify an 'in <arena>' clause.", str(ctx.exception))

    # 5. SharedRef() wrong arity
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        let s = SharedRef();
      }
      """)
    self.assertIn("SharedRef() constructor expects 1 argument, got 0.", str(ctx.exception))

    # 6. SharedRef(unmoved_ref) move-only copy error
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      func test() {
        var r = Ref(Box { v = 1 });
        let s = SharedRef(r);
      }
      """)
    self.assertIn("Cannot copy move-only type 'Ref<Box>'; use explicit 'move r'", str(ctx.exception))

    # 7. SharedRef<T> type mismatch via explicit type_args on CallNode
    checker2 = TypeChecker()
    call_sref_mismatch = CallNode(
        callee=IdentifierNode("SharedRef"),
        arguments=[ArgumentNode(None, LiteralNode("hi", "string"))],
        type_args=[BasicTypeNode("int")],
    )
    checker2.visit_CallNode(call_sref_mismatch)
    self.assertTrue(any("SharedRef<int> expected argument of type 'int', got 'String'." in e for e in checker2.errors))

    # 8. WeakRef direct construction rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      func test() {
        let w = WeakRef(Box { v = 1 });
      }
      """)
    self.assertIn("WeakRef cannot be constructed directly; use 'shared_ref.downgrade()'.", str(ctx.exception))

    # 9. Reassigning unmoved Ref variable rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      func test() {
        var r1 = Ref(Box { v = 1 });
        var r2 = Ref(Box { v = 2 });
        r2 = r1;
      }
      """)
    self.assertIn("Cannot copy move-only type 'Ref<Box>'; use explicit 'move r1'", str(ctx.exception))

  def test_substitute_type_params_and_bare_smart_ref_type_nodes(self):
    """Verifies _substitute_type_params for composite types and bare Ref/SharedRef/WeakRef type resolution."""
    from src.semantics.symbol_table import (
      FunctionType,
      GenericTypeParameter,
      MapType,
      MultiReturnType,
      OptionalType,
      RefType,
      SharedRefType,
      WeakRefType,
    )

    checker = TypeChecker()
    t_param = GenericTypeParameter("T")
    t_map = {"T": PrimitiveType("int")}

    self.assertEqual(
        checker._substitute_type_params(OptionalType(t_param), t_map),
        OptionalType(PrimitiveType("int")),
    )
    self.assertEqual(
        checker._substitute_type_params(ArrayType(t_param, size=2), t_map),
        ArrayType(PrimitiveType("int"), size=2),
    )
    self.assertEqual(
        checker._substitute_type_params(MapType(t_param, t_param), t_map),
        MapType(PrimitiveType("int"), PrimitiveType("int")),
    )
    self.assertEqual(
        checker._substitute_type_params(MultiReturnType([t_param, t_param]), t_map),
        MultiReturnType([PrimitiveType("int"), PrimitiveType("int")]),
    )
    fn_sub = checker._substitute_type_params(FunctionType([t_param], t_param), t_map)
    self.assertEqual(fn_sub.param_types, [PrimitiveType("int")])
    self.assertEqual(fn_sub.return_type, PrimitiveType("int"))

    self.assertIsInstance(checker._resolve_type_node(BasicTypeNode("Ref")), RefType)
    self.assertIsInstance(checker._resolve_type_node(BasicTypeNode("SharedRef")), SharedRefType)
    self.assertIsInstance(checker._resolve_type_node(BasicTypeNode("WeakRef")), WeakRefType)
    self.assertFalse(checker._expr_references_self(None))

  def test_move_only_types_require_explicit_move(self):
    """Verifies __del__ structs, wrapper structs, Arena, and Coroutine require explicit move."""
    # 1. __del__ struct copy rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Handle {
        var fd: int;
      }
      impl Handle {
        func __del__() {}
      }
      func test() {
        let h1 = Handle { fd = 1 };
        let h2 = h1;
      }
      """)
    self.assertIn("Cannot copy move-only type 'Handle'; use explicit 'move h1'", str(ctx.exception))

    # 2. Struct containing move-only field is transitively move-only
    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Handle {
        var fd: int;
      }
      impl Handle {
        func __del__() {}
      }
      struct Envelope {
        var h: Handle;
      }
      func test() {
        let e1 = Envelope { h = Handle { fd = 1 } };
        let e2 = e1;
      }
      """)
    self.assertIn("Cannot copy move-only type 'Envelope'; use explicit 'move e1'", str(ctx2.exception))

    # 3. Arena copy rejected
    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      func test() {
        var a1 = Arena();
        var a2 = a1;
      }
      """)
    self.assertIn("Cannot copy move-only type 'Arena'; use explicit 'move a1'", str(ctx3.exception))

    # 4. Coroutine copy rejected, explicit move allowed
    with self.assertRaises(SemanticError) as ctx4:
      self._check("""
      func gen(): Coroutine<int> {
        yield 1;
      }
      func test() {
        var c1 = gen();
        var c2 = c1;
      }
      """)
    self.assertIn("Cannot copy move-only type 'Coroutine<int>'; use explicit 'move c1'", str(ctx4.exception))

    self._check("""
    func gen(): Coroutine<int> {
      yield 1;
    }
    func test() {
      var c1 = gen();
      var c2 = move c1;
    }
    """)

  def test_partial_moves_and_borrowed_unwraps_rejected(self):
    """Verifies partial moves out of fields/indices and moves out of borrowed unwraps are rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Handle { var fd: int; }
      impl Handle { func __del__() {} }
      struct Holder { var h: Handle; }
      func test() {
        let holder = Holder { h = Handle { fd = 1 } };
        let stolen = holder.h;
      }
      """)
    self.assertIn("Cannot copy or partially move move-only type 'Handle' out of a field or collection index.", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Handle { var fd: int; }
      impl Handle { func __del__() {} }
      func test() {
        var arr: [Handle] = [Handle { fd = 1 }];
        let stolen = move arr[0];
      }
      """)
    self.assertIn("Cannot index into moved variable 'arr'.", str(ctx2.exception))

    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      struct Handle { var fd: int; }
      impl Handle { func __del__() {} }
      func test() {
        let opt: Handle? = Handle { fd = 1 };
        if let inner ?= opt {
          let moved_out = move inner;
        }
      }
      """)
    self.assertIn("Cannot move out of borrowed unwrap binding 'inner'.", str(ctx3.exception))

  def test_shared_ref_requires_explicit_share_or_move(self):
    """Verifies SharedRef lvalues cannot be copied implicitly without .share() or move."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Node { var v: int; }
      func test() {
        let s1 = SharedRef(Node { v = 1 });
        let s2 = s1;
      }
      """)
    self.assertIn("Cannot implicitly copy 'SharedRef' variable 's1'; call 's1.share()' or use 'move s1'.", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Node { var v: int; }
      func test() {
        let s1 = SharedRef(Node { v = 1 });
        var arr: [SharedRef<Node>] = [];
        arr.push(s1);
      }
      """)
    self.assertIn("Cannot implicitly copy 'SharedRef' variable 's1'", str(ctx2.exception))

    self._check("""
    struct Node { var v: int; }
    func test() {
      let s1 = SharedRef(Node { v = 1 });
      var arr: [SharedRef<Node>] = [s1.share()];
      arr.push(move s1);
    }
    """)

  def test_destructor_self_escape_rejected_while_helper_methods_allowed(self):
    """Verifies self cannot escape __del__() via globals, args, or closures, while self.close() works."""
    self._check("""
    struct FileHandle {
      var is_open: bool;
    }
    impl FileHandle {
      var func close() {
        self.is_open = false;
      }
      func __del__() {
        if self.is_open {
          self.close();
        }
      }
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Zombie { var id: int; }
      func inspect(z: Zombie) {}
      impl Zombie {
        func __del__() {
          inspect(self);
        }
      }
      """)
    self.assertIn("Cannot pass 'self' as an argument from destructor '__del__'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Zombie { var id: int; }
      var ESCAPED: Zombie? = none;
      impl Zombie {
        func __del__() {
          ESCAPED = self;
        }
      }
      """)
    self.assertIn("Cannot allow 'self' to escape from destructor '__del__'.", str(ctx2.exception))

    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      struct Zombie { var id: int; }
      impl Zombie {
        func __del__() {
          let fn = () -> self.id;
        }
      }
      """)
    self.assertIn("Cannot capture 'self' in a closure inside destructor '__del__'.", str(ctx3.exception))

  def test_match_arms_move_union_tracking(self):
    """Verifies mutually exclusive match arms can move the same variable and union-invalidate it."""
    self._check("""
    struct Handle { var id: int; }
    impl Handle { func __del__() {} }
    func pick(code: int): Handle {
      let h = Handle { id = 10 };
      let chosen = match code {
        1 -> move h,
        ... -> move h,
      };
      return move chosen;
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Handle { var id: int; }
      impl Handle { func __del__() {} }
      func bad_pick(code: int): int {
        let h = Handle { id = 10 };
        let chosen = match code {
          1 -> move h,
          ... -> Handle { id = 20 },
        };
        return h.id + chosen.id;
      }
      """)
    self.assertIn("Use of moved variable 'h'.", str(ctx.exception))

  def test_phase3_same_scope_lifo_and_transitive_escapes(self):
    """Rejects same-scope LIFO escapes, container/wrapper/closure/sink escapes, and Ref boxing."""
    lifo_same_scope = """
    proto Goblin { var hp: int; }
    func main() {
      var g: Goblin? = none;
      var a = Arena();
      g = Goblin { hp = 1 } in a;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(lifo_same_scope)
    self.assertIn("later-declared arena", str(ctx.exception))

    push_escape = """
    proto Goblin { var hp: int; }
    func main() {
      var items: [Goblin] = [];
      {
        var a = Arena();
        items.push(Goblin { hp = 1 } in a);
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(push_escape)
    self.assertIn("nested arena", str(ctx2.exception))

    for_escape = """
    proto Goblin { var hp: int; }
    func main() {
      var saved: Goblin? = none;
      {
        var a = Arena();
        let list = [Goblin { hp = 1 } in a];
        for g in list {
          saved = g;
        }
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(for_escape)
    self.assertIn("nested arena", str(ctx3.exception))

    var_sink_escape = """
    proto Goblin { var hp: int; }
    func store(var dst: [Goblin], src: Goblin) {
      dst.push(src);
    }
    func main() {
      var out_list: [Goblin] = [];
      {
        var a = Arena();
        let g = Goblin { hp = 1 } in a;
        store(out_list, g);
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx4:
      self._check(var_sink_escape)
    self.assertIn("nested arena", str(ctx4.exception))

    cross_arena_clone = """
    proto Goblin { var hp: int; }
    func main() {
      var outer_a = Arena();
      {
        var inner_a = Arena();
        let base = Goblin { hp = 1 } in inner_a;
        let bad = clone base {} in outer_a;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx5:
      self._check(cross_arena_clone)
    self.assertIn("shorter-lived Arena", str(ctx5.exception))

    ref_box = """
    proto Goblin { var hp: int; }
    func main() {
      var a = Arena();
      let g = Goblin { hp = 1 } in a;
      let r = Ref(g);
    }
    """
    with self.assertRaises(SemanticError) as ctx6:
      self._check(ref_box)
    self.assertIn("inside 'Ref'", str(ctx6.exception))

    shared_box_none = """
    proto Goblin { var hp: int; }
    func main() {
      let s = SharedRef<Goblin?>(none);
    }
    """
    with self.assertRaises(SemanticError) as ctx7:
      self._check(shared_box_none)
    self.assertIn("inside 'SharedRef'", str(ctx7.exception))

  def test_iteration_freeze_and_unwrap_freeze(self):
    for_in_push = """
    func main() {
      var arr = [1, 2, 3];
      for x in arr {
        arr.push(4);
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(for_in_push)
    self.assertIn(
        "while it is frozen (for-in loop iteration)", str(ctx.exception)
    )

    for_in_assign = """
    func main() {
      var arr = [1, 2, 3];
      for x in arr {
        arr = [4, 5];
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(for_in_assign)
    self.assertIn(
        "while it is frozen (for-in loop iteration)", str(ctx.exception)
    )

    for_in_index_assign = """
    func main() {
      var arr = [1, 2, 3];
      for x in arr {
        arr[0] = 10;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(for_in_index_assign)
    self.assertIn(
        "while it is frozen (for-in loop iteration)", str(ctx.exception)
    )

    for_in_move = """
    func main() {
      var arr = [1, 2, 3];
      for x in arr {
        let y = move arr;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(for_in_move)
    self.assertIn(
        "while it is frozen (for-in loop iteration)", str(ctx.exception)
    )

    map_callback_push = """
    func main() {
      var arr = [1, 2, 3];
      let res = arr.map(x -> {
        arr.push(10);
        return x * 2;
      });
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(map_callback_push)
    self.assertIn("while it is frozen (.map() callback)", str(ctx.exception))

    if_var_unwrap_freeze = """
    func main() {
      var opt: int? = 10;
      if var x ?= opt {
        opt = 20;
        let y = x;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(if_var_unwrap_freeze)
    self.assertIn(
        "while it is frozen (active 'if var' unwrap)", str(ctx.exception)
    )

    guard_var_unwrap_freeze = """
    func main() {
      var opt: int? = 10;
      guard var x ?= opt else { return; }
      opt = 20;
      let y = x;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(guard_var_unwrap_freeze)
    self.assertIn(
        "while it is frozen (active 'guard var' unwrap)", str(ctx.exception)
    )

    guard_var_nll_ok = """
    func main() {
      var opt: int? = 10;
      guard var x ?= opt else { return; }
      x = 15;
      opt = 20;
    }
    """
    self._check(guard_var_nll_ok)

    let_unwrap_ok = """
    func main() {
      var opt: int? = 10;
      if let x ?= opt {
        opt = 20;
      }
      guard let y ?= opt else { return; }
      opt = 30;
    }
    """
    self._check(let_unwrap_ok)

  def test_deep_shared_ref_and_ref_receiver_mutability(self):
    ref_let_mut_reject = """
    struct Counter { var count: int; }
    impl Counter { var func inc() { self.count += 1; } }
    func main() {
      let r = Ref(Counter { count = 0 });
      r.count = 10;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(ref_let_mut_reject)
    self.assertIn("constant Ref variable 'r'", str(ctx.exception))

    ref_let_method_reject = """
    struct Counter { var count: int; }
    impl Counter { var func inc() { self.count += 1; } }
    func main() {
      let r = Ref(Counter { count = 0 });
      r.inc();
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(ref_let_method_reject)
    self.assertIn("constant variable 'r'", str(ctx.exception))

    ref_var_mut_allow = """
    struct Counter { var count: int; }
    impl Counter { var func inc() { self.count += 1; } }
    func main() {
      var r = Ref(Counter { count = 0 });
      r.count = 10;
      r.inc();
    }
    """
    self._check(ref_var_mut_allow)

    ref_array_mutability = """
    func main() {
      var r_mut = Ref([1, 2, 3]);
      r_mut.push(4);
    }
    """
    self._check(ref_array_mutability)

    ref_array_const_reject = """
    func main() {
      let r_const = Ref([1, 2, 3]);
      r_const.push(4);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(ref_array_const_reject)
    self.assertIn("constant variable 'r_const'", str(ctx.exception))

    shared_field_reject = """
    struct Point { var x: int; var y: int; }
    func main() {
      var s = SharedRef(Point { x = 1, y = 2 });
      s.x = 10;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(shared_field_reject)
    self.assertIn("deeply immutable 'SharedRef'", str(ctx.exception))

    shared_method_reject = """
    struct Counter { var count: int; }
    impl Counter { var func inc() { self.count += 1; } }
    func main() {
      var s = SharedRef(Counter { count = 0 });
      s.inc();
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(shared_method_reject)
    self.assertIn("deeply immutable 'SharedRef'", str(ctx.exception))

  def test_closure_stack_capture_escapes(self):
    local_map_ok = """
    struct Point { var x: int; }
    func main() {
      let p = Point { x = 10 };
      let nums = [1, 2, 3];
      let res = nums.map(x -> x + p.x);
    }
    """
    self._check(local_map_ok)

    return_capture_struct_reject = """
    struct Point { var x: int; }
    func make_closure(): () -> int {
      let p = Point { x = 10 };
      return () -> int { return p.x; };
    }
    """
    with self.assertRaises(SemanticError) as ctx1:
      self._check(return_capture_struct_reject)
    self.assertIn("capturing local variable 'p'", str(ctx1.exception))

    return_capture_var_reject = """
    func make_counter(): () -> int {
      var count = 0;
      return () -> int { return count; };
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(return_capture_var_reject)
    self.assertIn("capturing local variable 'count'", str(ctx2.exception))

    return_capture_scalar_const_ok = """
    func make_adder(x: int): (int) -> int {
      return (y: int) -> int { return x + y; };
    }
    """
    self._check(return_capture_scalar_const_ok)

    outer_assign_reject = """
    struct Point { var x: int; }
    func main() {
      var cb: () -> int;
      {
        let p = Point { x = 10 };
        cb = () -> int { return p.x; };
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(outer_assign_reject)
    self.assertIn(
        "Closure capturing local variable 'p' cannot escape",
        str(ctx3.exception),
    )

    earlier_decl_reject = """
    struct Point { var x: int; }
    func main() {
      var cb: () -> int;
      let p = Point { x = 10 };
      cb = () -> int { return p.x; };
    }
    """
    with self.assertRaises(SemanticError) as ctx4:
      self._check(earlier_decl_reject)
    self.assertIn(
        "Closure capturing local variable 'p' cannot escape",
        str(ctx4.exception),
    )

    box_closure_reject = """
    struct Point { var x: int; }
    func main() {
      let p = Point { x = 10 };
      let r = Ref(() -> int { return p.x; });
    }
    """
    with self.assertRaises(SemanticError) as ctx5:
      self._check(box_closure_reject)
    self.assertIn("inside 'Ref'", str(ctx5.exception))

  def test_enhanced_aliasing_hints(self):
    """Verifies that aliasing conflict and frozen collection diagnostics include actionable hints."""
    # 1. Subscript aliasing hint
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Item { var v: int; }
      func process(var a: Item, b: Item) {}
      func main() {
        var items = [Item { v = 1 }, Item { v = 2 }];
        process(items[0], items[1]);
      }
      """)
    err = str(ctx.exception)
    self.assertIn("Aliasing conflict: variable 'items' (or a sub-field) is mutably borrowed", err)
    self.assertIn("Hint: To swap two elements in a collection, use 'items.swap(i, j)'", err)

    # 2. Self-field method call aliasing hint
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Entity { var target: Entity?; }
      impl Entity {
        func __init__() { self.target = none; }
        var func update(other: Entity?) { self.target = other; }
        var func self_update() {
          self.update(self.target);
        }
      }
      """)
    err = str(ctx.exception)
    self.assertIn("Aliasing conflict: variable 'self' (or a sub-field) is mutably borrowed", err)
    self.assertIn("Hint: Invoking a mutating method on 'self' conflicts with borrowing its field 'self.target'", err)

    # 3. Frozen collection in for-in loop hint
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func main() {
        var nums = [1, 2, 3];
        for n in nums {
          nums.remove(0);
        }
      }
      """)
    err = str(ctx.exception)
    self.assertIn("Cannot invoke mutating method 'remove' on 'nums' while it is frozen (for-in loop iteration)", err)
    self.assertIn("Hint: Collections are frozen during iteration to prevent iterator invalidation", err)
    self.assertIn("nums.filter(fn, in_place = true)", err)

  def test_reordered_named_arguments_detect_aliasing_conflict(self):
    """Verifies borrow aliasing checks still trigger with reordered named args."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Counter {
        var val: int;
      }

      func bump(src: Counter, var dst: Counter): int {
        dst.val = dst.val + src.val;
        return dst.val;
      }

      func main(): int {
        var c = Counter { val = 1 };
        return bump(dst = c, src = c);
      }
      """)
    self.assertIn("Aliasing conflict", str(ctx.exception))

  def test_phase3_ownership_and_move_tracking(self):
    """Verifies lambda move rules, continue move checks, yield RAII across branches, multi-return moves, for-var borrows, and Ref? args."""
    # 1. Lambda reading already-moved outer variable rejected
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let r = Ref(1);
        let r2 = move r;
        let f = () -> int { return r; };
      }
      """)

    # 2. Lambda moving captured outer variable rejected
    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let r = Ref(1);
        let f = () -> Ref<int> { return move r; };
      }
      """)

    # 3. Lambda moving its own local variable allowed
    self._check("""
    func consume(x: Ref<int>) {}
    func test() {
      let f = () -> {
        let local_r = Ref(1);
        consume(move local_r);
      };
    }
    """)

    # 4. Continue after moving outer variable without reassignment rejected
    with self.assertRaises(SemanticError):
      self._check("""
      func consume(x: Ref<int>) {}
      func test(flag: bool) {
        var r = Ref(1);
        while flag {
          consume(move r);
          if flag {
            continue;
          }
          r = Ref(2);
        }
      }
      """)

    # 5. Continue after moving loop-local variable allowed
    self._check("""
    func consume(x: Ref<int>) {}
    func test(flag: bool) {
      while flag {
        let local_r = Ref(1);
        consume(move local_r);
        if flag {
          continue;
        }
      }
    }
    """)

    # 6. Branch move must not clear RAII yield check in sibling branch
    with self.assertRaises(SemanticError):
      self._check("""
      func consume(x: Ref<int>) {}
      func gen(flag: bool): Coroutine<int> {
        let r = Ref(1);
        if flag {
          consume(move r);
        } else {
          yield 1;
        }
      }
      """)

    # 7. Multi-return duplicating move-only variable rejected
    with self.assertRaises(SemanticError):
      self._check("""
      func bad(): Ref<int>, Ref<int> {
        let r = Ref(1);
        return r, r;
      }
      """)

    # 8. Moving out of for-var loop binding rejected
    with self.assertRaises(SemanticError):
      self._check("""
      struct Handle { var fd: int; }
      impl Handle { func __del__() {} }
      func test() {
        var arr: [Handle] = [Handle { fd = 1 }];
        for var h in arr {
          let stolen = move h;
        }
      }
      """)

    # 9. Ref<T>? argument move checks + ternary Ref argument checks
    self._check("""
    func take_opt(x: Ref<int>?) {}
    func take_ref(x: Ref<int>) {}
    func test(cond: bool) {
      let a = Ref(1);
      take_opt(move a);
      take_opt(none);
      let r1 = Ref(2);
      let r2 = Ref(3);
      take_ref(cond ? move r1 : move r2);
    }
    """)

    with self.assertRaises(SemanticError):
      self._check("""
      func take_opt(x: Ref<int>?) {}
      func test() {
        let b = Ref(1);
        take_opt(b);
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      func take_ref(x: Ref<int>) {}
      func test(cond: bool) {
        let r1 = Ref(1);
        let r2 = Ref(2);
        take_ref(cond ? r1 : r2);
      }
      """)

    # 10. False move positives fixed: cond ? move r : move r, guard else move+return, if let in loop
    self._check("""
    func consume(x: Ref<int>) {}
    func read_val(x: int): int { return x; }
    func test(cond: bool) {
      let r1 = Ref(1);
      let moved = cond ? move r1 : move r1;

      let r2 = Ref(2);
      guard cond else {
        consume(move r2);
        return;
      }
      let v = read_val(r2);

      while cond {
        if let r3 = Ref(3); true {
          consume(move r3);
        }
      }
    }
    """)

  def test_phase3_deep_mutability_shared_ref_and_encapsulation(self):
    """Verifies SharedRef rebinding vs deref mutation, full lvalue chain immutability, self=, and export encapsulation."""
    # 1. Rebinding var SharedRef itself is allowed
    self._check("""
    func test() {
      var sr = SharedRef(1);
      sr = SharedRef(2);
    }
    """)

    # 2. Mutating nested fields/indices through SharedRef rejected
    with self.assertRaises(SemanticError):
      self._check("""
      struct Inner { var x: int; }
      struct Wrap { var inner: Inner; var arr: [int]; }
      struct Holder { var sr: SharedRef<Wrap>; }
      func test() {
        var h = Holder { sr = SharedRef(Wrap { inner = Inner { x = 1 }, arr = [1] }) };
        h.sr.inner.x = 99;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Wrap { var arr: [int]; }
      struct Holder { var sr: SharedRef<Wrap>; }
      func test() {
        var h = Holder { sr = SharedRef(Wrap { arr = [1] }) };
        h.sr.arr[0] = 99;
      }
      """)

    # 3. Direct self = ... rejected; self.inner.x and self.arr[0] in immutable func rejected
    with self.assertRaises(SemanticError):
      self._check("""
      struct S { var x: int; }
      impl S {
        var func bad(other: S) { self = other; }
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Inner { var x: int; }
      struct S { var inner: Inner; var arr: [int]; }
      impl S {
        func bad1() { self.inner.x = 42; }
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct S { var arr: [int]; }
      impl S {
        func bad2() { self.arr[0] = 99; }
      }
      """)

    # 4. Deep immutability through let array, let nested array, let struct field, and if var
    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      func test() {
        let arr = [Box { x = 1 }];
        arr[0].x = 99;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      func test() {
        let m = [[1, 2]];
        m[0][0] = 99;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Inner { var x: int; }
      struct Outer { let const_inner: Inner; }
      func test() {
        var o = Outer { const_inner = Inner { x = 1 } };
        o.const_inner.x = 99;
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      struct Holder { let const_opt: Box?; }
      func test() {
        var h = Holder { const_opt = Box { x = 1 } };
        if var b ?= h.const_opt {
          b.x = 99;
        }
      }
      """)

    # 5. var func, var param, and collection mutator through let field rejected
    with self.assertRaises(SemanticError):
      self._check("""
      struct Counter { var n: int; }
      impl Counter { var func inc() { self.n += 1; } }
      struct Outer { let c: Counter; }
      func test() {
        var o = Outer { c = Counter { n = 0 } };
        o.c.inc();
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      struct Outer { let b: Box; }
      func bump(var b: Box) { b.x += 1; }
      func test() {
        var o = Outer { b = Box { x = 0 } };
        bump(o.b);
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      struct Outer { let arr: [int]; }
      func test() {
        var o = Outer { arr = [1] };
        o.arr.push(2);
      }
      """)

    # 6. export { ... } manifest preserves imported struct encapsulation
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      mod_path = os.path.join(tmpdir, "encap_mod.sp")
      main_path = os.path.join(tmpdir, "main.sp")
      with open(mod_path, "w") as f:
        f.write("""
        struct Secret {
          var val: int;
        }
        impl Secret {
          func __init__(v: int) {
            self.val = v;
          }
        }
        export { Secret }
        """)
      main_code = """
      import encap_mod;
      func test() {
        var s = encap_mod.Secret(10);
        s.val = 99;
      }
      """
      with open(main_path, "w") as f:
        f.write(main_code)
      with self.assertRaises(SemanticError) as ctx_enc:
        self._check(main_code, source_file_path=main_path)
      self.assertIn("encapsulated struct 'Secret'", str(ctx_enc.exception))


if __name__ == "__main__":
  unittest.main()
