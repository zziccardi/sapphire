"""Struct, constructor, destructor, inheritance, and generic semantic tests."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast import (
  ArgumentNode,
  LiteralNode,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.struct_layout_pass import StructLayoutPass
from sapphire.semantics.symbol_table import (
  ArrayType,
  StructField,
  StructType,
)
from sapphire.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerStructs(TypeCheckerTestBase, unittest.TestCase):
  """Struct, constructor, destructor, inheritance, and generic semantic tests."""

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

  def test_mutate_field_immutable_method(self):
    """Enforces that you cannot mutate fields inside an immutable method by default."""
    code = """
    struct Point {
      var x: int;
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
    self.assertIn("Cannot mutate field 'x' within an immutable method", str(context.exception))

  def test_mutate_field_var_method(self):
    """Verifies that methods declared with 'var func' can mutate self fields."""
    code = """
    struct Point {
      var x: int;
    }
    impl Point {
      func __init__() {
        self.x = 0;
      }
      var func change() {
        self.x = 10;
      }
    }
    """
    self._check(code)

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

  def test_multi_parent_struct_type_checking(self):
    """Verifies that multi-parent struct field inlining registers all inherited fields in the symbol table."""
    code = """
    struct Position { var x: float; var y: float; }
    struct Health { var hp: int; }
    struct Player: Position, Health { var name: String; }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    player_type = checker.symbol_table.lookup_type("Player")
    self.assertIn("x", player_type.fields)
    self.assertIn("y", player_type.fields)
    self.assertIn("hp", player_type.fields)
    self.assertIn("name", player_type.fields)

  def test_struct_initialization_checking(self):
    """Verifies semantic checking of struct initializers."""
    # 1. Missing required field (non-primitive, non-optional reference type)
    code_missing = """
    struct Point {
      var x: int;
      var owner: String;
    }
    func test() {
      let p = Point { x = 10 }; // Missing required field owner
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_missing)
    self.assertIn("Struct initializer for 'Point' is missing required field 'owner'", str(context.exception))

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
    self.assertIn("Field 'y' in struct 'Point' initializer has type 'String', but expected 'int'", str(context.exception))

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
    from sapphire.parser.ast import StructInitializerNode
    from sapphire.semantics.symbol_table import StructType


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

  def test_struct_init_with_constructor_disallowed(self):
    """Verifies that literal struct initializer syntax is forbidden when __init__ is defined."""
    code = """
    struct Weapon {
      var damage: int;
    }
    impl Weapon {
      func __init__(dmg: int) {
        self.damage = dmg;
      }
    }
    func test() {
      let w = Weapon { damage = 50 };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn(
        "Cannot use literal initializer for struct 'Weapon' because it defines an '__init__' constructor. Use constructor call syntax 'Weapon(...)' instead.",
        str(context.exception),
    )

  def test_generic_struct_init_with_constructor_disallowed(self):
    """Verifies that literal initializer syntax is forbidden for generic structs defining __init__."""
    code = """
    struct Pair<K, V> {
      var key: K;
      var value: V;
    }
    impl Pair<K, V> {
      func __init__(key: K, value: V) {
        self.key = key;
        self.value = value;
      }
    }
    func test() {
      let p = Pair<String, int> { key = "score", value = 100 };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn(
        "Cannot use literal initializer for struct 'Pair' because it defines an '__init__' constructor. Use constructor call syntax 'Pair(...)' instead.",
        str(context.exception),
    )

  def test_inherited_struct_init_with_constructor_disallowed(self):
    """Verifies that literal initializer is forbidden when an inherited parent defines __init__."""
    code = """
    struct Parent {
      var p: int;
    }
    impl Parent {
      func __init__(val: int) {
        self.p = val;
      }
    }
    struct Child: Parent {
      var c: int;
    }
    func test() {
      let c = Child { p = 1, c = 2 };
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn(
        "Cannot use literal initializer for struct 'Child' because it defines an '__init__' constructor. Use constructor call syntax 'Child(...)' instead.",
        str(context.exception),
    )

  def test_struct_field_implicit_defaults(self):
    """Verifies that fields of type int, float, bool, and T? implicitly default and can be omitted from initializers."""
    self._check("""
    struct Entity {
      var id: int;
      var speed: float;
      var is_alive: bool;
      var target: String?;
      let name: String;
    }

    func test() {
      // id, speed, is_alive, and target can all be omitted because they have implicit defaults
      let e = Entity { name = "Hero" };
    }
    """)

  def test_constructor_default_parameters(self):
    """Verifies that calling a constructor or function with default arguments allows omitting those parameters."""
    self._check("""
    struct Character {
      let id: int;
      let name: String;
      let max_hp: int;
    }
    impl Character {
      func __init__(id: int, name: String, max_hp: int = 100) {
        self.id = id;
        self.name = name;
        self.max_hp = max_hp;
      }
    }
    func test() {
      let player = Character(id = 1, name = "Galahad");
    }
    """)

  def test_constructor_chaining_single_and_multi_parent(self):
    """Verifies constructor chaining with single-line and multi-line Layout Variation A."""
    code = """
    struct Transform2D {
      var x: float;
      var y: float;
    }
    impl Transform2D {
      func __init__(x: float, y: float) {
        self.x = x;
        self.y = y;
      }
    }
    struct Health {
      var hp: int;
    }
    impl Health {
      func __init__(max_hp: int) {
        self.hp = max_hp;
      }
    }
    struct Player: Transform2D, Health {
      var name: String;
    }
    impl Player {
      func __init__(name: String, x: float, y: float, hp: int):
          Transform2D(x = x, y = y),
          Health(max_hp = hp) {
        self.name = name;
      }
    }
    func test() {
      let p = Player(name = "Hero", x = 1.0, y = 2.0, hp = 100);
    }
    """
    self._check(code)

  def test_constructor_chaining_missing_parent_init(self):
    """Verifies error when parent with __init__ is omitted from child constructor."""
    code = """
    struct Base {
      var x: int;
    }
    impl Base {
      func __init__(x: int) {
        self.x = x;
      }
    }
    struct Child: Base {
      var y: int;
    }
    impl Child {
      func __init__(x: int, y: int) {
        self.x = x;
        self.y = y;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("must initialize parent struct 'Base'", str(ctx.exception))

  def test_constructor_chaining_invalid_parent(self):
    """Verifies error when initializing a struct that is not an inherited parent."""
    code = """
    struct Other {
      var a: int;
    }
    impl Other {
      func __init__(a: int) { self.a = a; }
    }
    struct Base {
      var x: int;
    }
    impl Base {
      func __init__(x: int) { self.x = x; }
    }
    struct Child: Base {
      var y: int;
    }
    impl Child {
      func __init__(x: int, y: int): Base(x = x), Other(a = 1) {
        self.y = y;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("'Other' is not a parent of struct 'Child'", str(ctx.exception))

  def test_constructor_chaining_duplicate_parent(self):
    """Verifies error when initializing the same parent multiple times."""
    code = """
    struct Base {
      var x: int;
    }
    impl Base {
      func __init__(x: int) { self.x = x; }
    }
    struct Child: Base {
      var y: int;
    }
    impl Child {
      func __init__(x: int, y: int): Base(x = x), Base(x = y) {
        self.y = y;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("Duplicate initialization of parent struct 'Base'", str(ctx.exception))

  def test_constructor_chaining_rejects_self_reference(self):
    """Verifies error when referencing self in base initializer arguments."""
    code = """
    struct Base {
      var x: int;
    }
    impl Base {
      func __init__(x: int) { self.x = x; }
    }
    struct Child: Base {
      var y: int;
    }
    impl Child {
      func __init__(y: int): Base(x = self.y) {
        self.y = y;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("References to 'self' are not allowed in base initializer arguments", str(ctx.exception))

  def test_constructor_chaining_non_init_method_rejected(self):
    """Verifies that base initializers are rejected on regular methods and functions."""
    code = """
    struct Base {
      var x: int;
    }
    impl Base {
      func __init__(x: int) { self.x = x; }
    }
    struct Child: Base {
      var y: int;
    }
    impl Child {
      func __init__(x: int, y: int): Base(x = x) { self.y = y; }
      func update(x: int): Base(x = x) {
        self.x = x;
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("Base initializers are only permitted on constructor '__init__'", str(ctx.exception))

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

  def test_struct_field_omitted_type_inference(self):
    """Verifies type inference for struct fields when explicit types are omitted."""
    # 1. Inferred primitive types
    checker = self._check("""
    struct Point {
      var x = 10;
      var y = 20;
      let name = "origin";
    }

    func test(): int {
      let p = Point { x = 5, y = 15, name = "custom" };
      return p.x + p.y;
    }
    """)
    struct_type = checker.symbol_table.lookup_type("Point")
    self.assertEqual(struct_type.fields["x"].field_type.name, "int")
    self.assertEqual(struct_type.fields["y"].field_type.name, "int")
    self.assertEqual(struct_type.fields["name"].field_type.name, "String")

  def test_struct_field_omitted_type_errors(self):
    """Verifies error reporting for struct fields with omitted types."""
    # 1. Missing type and missing default value
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Bad {
        var x;
      }
      """)
    self.assertIn("Struct field 'x' in struct 'Bad' requires an explicit type annotation or a default value.", str(ctx.exception))

    # 2. Inferred from 'none' alone
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Bad {
        var x = none;
      }
      """)
    self.assertIn("Cannot infer type of struct field 'x' from 'none' alone. Specify an explicit type annotation.", str(ctx.exception))

  def test_destructor_valid_definition(self):
    """Verifies that a valid __del__() destructor compiles and marks has_destructor."""
    tc = self._check("""
    struct FileHandle {
      var fd: int;
    }
    impl FileHandle {
      func __del__() {
        if self.fd != -1 {
          self.fd = -1;
        }
      }
    }
    """)
    file_handle_t = tc.symbol_table.lookup_type("FileHandle")
    self.assertIsNotNone(file_handle_t)
    self.assertTrue(file_handle_t.has_destructor)

  def test_destructor_with_parameters_rejected(self):
    """Verifies that __del__ with parameters is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct FileHandle {
        var fd: int;
      }
      impl FileHandle {
        func __del__(self) {}
      }
      """)
    self.assertIn("Destructor '__del__' must take 0 parameters; 'self' is implicitly available.", str(ctx.exception))

  def test_destructor_const_rejected(self):
    """Verifies that const func is rejected as invalid syntax in impl block."""
    with self.assertRaises(SyntaxError):
      self._check("""
      struct FileHandle {
        var fd: int;
      }
      impl FileHandle {
        const func __del__() {}
      }
      """)

  def test_destructor_can_mutate_self(self):
    """Verifies that __del__() has mutable access to self by default."""
    self._check("""
    struct FileHandle {
      var fd: int;
    }
    impl FileHandle {
      func __del__() {
        self.fd = -1;
      }
    }
    """)

  def test_destructor_static_rejected(self):
    """Verifies that static func __del__() is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct FileHandle {
        var fd: int;
      }
      impl FileHandle {
        static func __del__() {}
      }
      """)
    self.assertIn("Destructor '__del__' cannot be static.", str(ctx.exception))

  def test_destructor_non_void_rejected(self):
    """Verifies that non-void __del__() is rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct FileHandle {
        var fd: int;
      }
      impl FileHandle {
        func __del__(): int {
          return 0;
        }
      }
      """)
    self.assertIn("Destructor '__del__' must return void.", str(ctx.exception))

  def test_destructor_manual_call_rejected(self):
    """Verifies that direct manual invocations of __del__() are rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct FileHandle {
        var fd: int;
      }
      impl FileHandle {
        func __del__() {}
      }
      func test() {
        let h = FileHandle { fd = 1 };
        h.__del__();
      }
      """)
    self.assertIn("Destructor '__del__' cannot be manually invoked.", str(ctx.exception))

  def test_unboxed_direct_and_mutual_struct_recursion_rejected(self):
    """Verifies direct, fixed-array, mutual, and generic unboxed struct recursion are rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct BadNode {
        var val: int;
        var next: BadNode?;
      }
      """)
    self.assertIn("Recursive struct 'BadNode' has infinite inline size via field 'next'", str(ctx.exception))

    checker = TypeChecker()
    fixed_st = StructType("FixedRec", {})
    fixed_st.fields["children"] = StructField(
        "children", ArrayType(fixed_st, size=2, is_fixed_size=True), is_mutable=True
    )
    StructLayoutPass.check_unboxed_recursion(checker, [fixed_st])
    self.assertTrue(
        any(
            "Recursive struct 'FixedRec' has infinite inline size via field 'children'" in e
            for e in checker.errors
        )
    )

    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      struct LeftNode {
        var right: RightNode;
      }
      struct RightNode {
        var left: LeftNode?;
      }
      """)
    self.assertIn("has infinite inline size", str(ctx3.exception))

    with self.assertRaises(SemanticError) as ctx4:
      self._check("""
      struct GenRec<T> {
        var val: T;
        var next: GenRec<T>?;
      }
      func test() {
        let g: GenRec<int>? = none;
      }
      """)
    self.assertIn("Recursive struct 'GenRec__int' has infinite inline size via field 'next'", str(ctx4.exception))

  def test_qualified_ancestor_static_dispatch_accepted(self):
    """Verifies single, multi-parent, named-arg, and coroutine ancestor calls."""
    self._check("""
    struct Flyer {
      var alt: int;
    }

    impl Flyer {
      var func ascend(delta: int, bonus: int = 2, extra: int = 5): int {
        self.alt = self.alt + delta + bonus + extra;
        return self.alt;
      }
    }

    struct Echolocation {
      var ping_count: int;
    }

    impl Echolocation {
      func pulse(scale: int): int {
        return self.ping_count * scale;
      }

      func scan_gen(): Coroutine<int> {
        yield self.ping_count;
      }
    }

    struct Bat: Flyer, Echolocation {
      var energy: int;
    }

    impl Bat {
      var func ascend(delta: int, bonus: int = 2, extra: int = 5): int {
        return Flyer.ascend(self, extra = extra, delta = delta);
      }

      func probe(): int {
        let p = Echolocation.pulse(self, 3);
        var gen = Echolocation.scan_gen(self);
        let y = gen.step() ?? 0;
        return p + y;
      }
    }

    func main(): int {
      var b = Bat { alt = 0, ping_count = 4, energy = 10 };
      return b.ascend(10) + b.probe();
    }
    """)

  def test_qualified_ancestor_static_dispatch_errors(self):
    """Verifies negative rules for qualified ancestor static dispatch."""
    # 1. Up-casting remains disallowed.
    with self.assertRaises(SemanticError):
      self._check("""
      struct Base { var x: int; }
      struct Child: Base { var y: int; }
      impl Child {
        func bad(): int {
          let p: Base = self;
          return p.x;
        }
      }
      """)

    # 2. Non-self first argument rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      impl Base {
        func draw(a: int): int { return self.x + a; }
      }
      struct Child: Base { var y: int; }
      impl Child {
        func draw(a: int): int {
          let other = Child { x = 1, y = 2 };
          return Base.draw(other, a);
        }
      }
      """)
    self.assertIn("must pass 'self' as the first positional argument", str(ctx.exception))

    # 3. Immutable func calling var func ancestor rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      impl Base {
        var func bump(v: int) { self.x = self.x + v; }
      }
      struct Child: Base { var y: int; }
      impl Child {
        func inspect() {
          Base.bump(self, 1);
        }
      }
      """)
    self.assertIn("Cannot call mutating ancestor method", str(ctx.exception))

    # 4. Aliasing conflict on Parent.mut(self, self.x).
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Box { var v: int; }
      struct Base { var box: Box; }
      impl Base {
        var func merge(other: Box): int {
          self.box.v = self.box.v + other.v;
          return self.box.v;
        }
      }
      struct Child: Base { var z: int; }
      impl Child {
        var func merge(other: Box): int {
          return Base.merge(self, self.box);
        }
      }
      """)
    self.assertIn("Aliasing conflict", str(ctx.exception))

    # 5. Child.method(self) self-call rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      struct Child: Base { var y: int; }
      impl Child {
        func draw(): int { return Child.draw(self); }
      }
      """)
    self.assertIn("on own struct 'Child'", str(ctx.exception))

    # 6. Unbound Parent.method reference rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      impl Base {
        func draw(): int { return self.x; }
      }
      struct Child: Base { var y: int; }
      impl Child {
        func draw(): int {
          let f = Base.draw;
          return 0;
        }
      }
      """)
    self.assertIn("Cannot reference unbound instance method", str(ctx.exception))

    # 7. Unrelated struct rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Other { var x: int; }
      impl Other {
        func draw(): int { return self.x; }
      }
      struct Child { var y: int; }
      impl Child {
        func draw(): int { return Other.draw(self); }
      }
      """)
    self.assertIn("is not an ancestor of 'Child'", str(ctx.exception))

    # 8. Outside impl method rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      impl Base {
        func draw(): int { return self.x; }
      }
      func main(): int {
        let b = Base { x = 1 };
        return Base.draw(b);
      }
      """)
    self.assertIn("only allowed inside an instance method", str(ctx.exception))

    # 9. Direct __init__ and field access on type receiver rejected.
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      impl Base {
        func __init__(x: int) { self.x = x; }
      }
      struct Child: Base { var y: int; }
      impl Child {
        func reset() {
          Base.__init__(self, 1);
        }
      }
      """)
    self.assertIn("Cannot call '__init__' directly", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Base { var x: int; }
      struct Child: Base { var y: int; }
      impl Child {
        func read_base(): int { return Base.x; }
      }
      """)
    self.assertIn("Cannot access instance field 'x' on type 'Base'", str(ctx.exception))

  def test_explicit_self_parameter_rejected(self):
    with self.assertRaises(SemanticError) as ctx1:
      self._check("""
      struct Counter {
        var value: int = 0;
      }
      impl Counter {
        var func inc(self) {
          self.value += 1;
        }
      }
      """)
    self.assertIn("Explicit 'self' parameter is not permitted", str(ctx1.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      trait HostHandle {
        func decode(self): String;
      }
      """)
    self.assertIn("Explicit 'self' parameter is not permitted", str(ctx2.exception))

    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      func standalone(self) {}
      """)
    self.assertIn("Explicit 'self' parameter is not permitted", str(ctx3.exception))


if __name__ == "__main__":
  unittest.main()
