"""Trait conformance, inheritance, and Dynamic<Trait> semantic tests."""

import unittest

from sapphire.semantics.type_checker import SemanticError
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerTraits(TypeCheckerTestBase, unittest.TestCase):
  """Trait conformance, inheritance, and Dynamic<Trait> semantic tests."""

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

  def test_trait_self_parameter_type_checking(self):
    """Verifies argument checking for trait methods without explicit self."""
    code = """
    trait ImageHandle {
      func draw(x: float, y: float);
      var func getWidth(): float;
    }

    @extern
    var img: ImageHandle;

    func main() {
      img.draw(10.0, 20.0);
      let w = img.getWidth();
    }
    """
    self._check(code)

  def test_implicit_trait_subtyping(self):
    """Verifies that structs implementing a trait are assignable to trait parameters and return types."""
    # 1. Valid trait subtyping for parameters and return types
    code_valid = """
    trait Printable {
      func print_self();
    }

    struct Point {
      var x: int;
    }

    impl Printable for Point {
      func print_self() {}
    }

    func display(p: Printable) : Printable {
      p.print_self();
      return p;
    }

    func main() {
      let pt = Point { x = 10 };
      let res = display(pt);
    }
    """
    self._check(code_valid)

    # 2. Invalid trait subtyping (struct does not implement trait)
    code_invalid = """
    trait Printable {
      func print_self();
    }

    struct NonPrintable {
      var x: int;
    }

    func display(p: Printable) {
      p.print_self();
    }

    func main() {
      let np = NonPrintable { x = 5 };
      display(np);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_invalid)
    self.assertIn("Argument type mismatch at position 1. Expected 'trait Printable', got 'NonPrintable'.", str(ctx.exception))

    # 3. Optional trait subtyping
    code_optional = """
    trait Describable {
      func describe();
    }

    struct Item {
      var id: int;
    }

    impl Describable for Item {
      func describe() {}
    }

    func process(item: Describable?) : Describable? {
      return item;
    }

    func main() {
      let it: Item? = Item { id = 1 };
      let res = process(it);
    }
    """
    self._check(code_optional)

    # 4. Heterogeneous Trait Collection ([Describable])
    code_collection = """
    trait Describable {
      func describe();
    }

    struct ItemA {
      var id: int;
    }

    struct ItemB {
      var name: String;
    }

    impl Describable for ItemA {
      func describe() {}
    }

    impl Describable for ItemB {
      func describe() {}
    }

    func main() {
      let a = ItemA { id = 1 };
      let b = ItemB { name = "B" };
      let items: [Describable] = [a, b];
      for i in items {
        i.describe();
      }
    }
    """
    self._check(code_collection)

    # 5. Invalid element type in trait collection
    code_invalid_elem = """
    trait Describable {
      func describe();
    }

    struct ItemA {
      var id: int;
    }

    impl Describable for ItemA {
      func describe() {}
    }

    func main() {
      let a = ItemA { id = 1 };
      let items: [Describable] = [a, 42];
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_invalid_elem)
    self.assertIn("Array element of type 'int' is not compatible with expected element type 'trait Describable'.", str(ctx.exception))

  def test_impl_method_multiple_return_values(self):
    """Verifies that impl methods returning multiple values type check correctly and enforce return counts/types."""
    # 1. Valid multiple return values from impl method
    self._check("""
    struct Entity {
      var tile_x = 0;
      var tile_y = 0;
    }

    impl Entity {
      func get_tile_position(): int, int {
        return self.tile_x, self.tile_y;
      }
    }
    """)

    # 2. Return count mismatch in impl method (providing 1 value when 2 expected)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Entity {
        var tile_x = 0;
      }

      impl Entity {
        func get_tile_position(): int, int {
          return self.tile_x;
        }
      }
      """)
    self.assertIn("Function expected 2 return value(s), but return statement provided 1 value(s).", str(ctx.exception))

    # 3. Return type mismatch in impl method
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Entity {
        var tile_x = 0;
      }

      impl Entity {
        func get_tile_position(): int, int {
          return self.tile_x, "invalid";
        }
      }
      """)
    self.assertIn("Cannot return value of type 'String' for return value #2 (expected 'int').", str(ctx.exception))

  def test_default_parameter_ordering_trait(self):
    """Verifies that non-default parameters following default parameters in trait methods raise a semantic error."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      trait BadTrait {
        func bad_method(opt: int = 0, req: int);
      }
      """)
    self.assertIn("Parameter without a default value 'req' cannot follow a parameter with a default value.", str(ctx.exception))

  def test_nominal_trait_conformance_and_inheritance(self):
    """Verifies that trait conformance requires explicit nominal impl (or inherited parent impl)."""
    # 1. Structural match without impl Trait for Struct is rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      trait Speaker {
        func speak(): String;
      }
      struct Duck {
        var name: String;
      }
      impl Duck {
        func speak(): String {
          return "quack";
        }
      }
      func hear(s: Speaker): String {
        return s.speak();
      }
      func test() {
        let d = Duck { name = "Donald" };
        hear(d);
      }
      """)
    self.assertIn("Argument type mismatch at position 1. Expected 'trait Speaker', got 'Duck'.", str(ctx.exception))

    # 2. Child struct inheriting from parent that nominally implements trait is accepted
    self._check("""
    trait Speaker {
      func speak(): String;
    }
    struct BaseAnimal {
      var name: String;
    }
    impl Speaker for BaseAnimal {
      func speak(): String {
        return self.name;
      }
    }
    struct Dog: BaseAnimal {
      var breed: String;
    }
    func hear(s: Speaker): String {
      return s.speak();
    }
    func test() {
      let d = Dog { name = "Rex", breed = "Husky" };
      let res = hear(d);
    }
    """)

  def test_nested_trait_map_and_array_literal_expected_type(self):
    self._check("""
    trait Greeter {
      func greet(): int;
    }
    struct BotA {}
    impl Greeter for BotA {
      func greet(): int { return 1; }
    }
    struct BotB {}
    impl Greeter for BotB {
      func greet(): int { return 2; }
    }
    struct Other {}

    func main() {
      let grid: [int: [int: Greeter]] = {
        1: {2: BotA {}},
        3: {4: BotB {}},
      };
      let rows: [[Greeter]] = [[BotA {}], [BotB {}]];
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      trait Greeter {
        func greet(): int;
      }
      struct BotA {}
      impl Greeter for BotA {
        func greet(): int { return 1; }
      }
      struct Other {}
      func main() {
        let grid: [int: [int: Greeter]] = {
          1: {2: BotA {}},
          3: {4: Other {}},
        };
      }
      """)
    self.assertIn("Inconsistent value types in map literal.", str(ctx.exception))

  def test_phase3_function_mutability_traits_aliasing_nll_and_scanners(self):
    """Verifies FunctionType param_mutabilities, trait modifiers/receivers, var primitives, closure aliasing, proto_ancestors, NLL, and scanners."""
    # 1. FunctionType.is_compatible enforces param_mutabilities
    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      func mutate(var b: Box) { b.x = 99; }
      func test() {
        let f: (Box) -> void = mutate;
      }
      """)

    # 2. Trait immutable method cannot be implemented as var func
    with self.assertRaises(SemanticError):
      self._check("""
      trait Reader { func read(): int; }
      struct S { var x: int; }
      impl Reader for S {
        var func read(): int { self.x += 1; return self.x; }
      }
      """)

    # 3. TraitType receiver enforces var func mutability
    with self.assertRaises(SemanticError):
      self._check("""
      trait Mutator { var func inc(); }
      func bad(m: Mutator) {
        m.inc();
      }
      """)

    # 4. var primitive param immutability & aliasing (while 1 var + 1 value copy allowed)
    with self.assertRaises(SemanticError):
      self._check("""
      func inc(var x: int) { x += 1; }
      func test() {
        let c = 1;
        inc(c);
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      func swap_int(var a: int, var b: int) {
        let t = a;
        a = b;
        b = t;
      }
      func test() {
        var v = 1;
        swap_int(v, v);
      }
      """)

    self._check("""
    func add_to(var a: int, delta: int) { a += delta; }
    func test() {
      var v = 1;
      add_to(v, v);
    }
    """)

    # 5. Closure-captured var aliasing at call site rejected
    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      func test() {
        var b = Box { x = 1 };
        let f = (other: Box) -> {
          b.x = other.x + 1;
        };
        f(b);
      }
      """)

    # 6. proto_ancestors propagated on let c2 = c1;
    with self.assertRaises(SemanticError):
      self._check("""
      proto Enemy { var hp: int; }
      func clash(var base: Enemy, other: Enemy) {
        base.hp = other.hp + 1;
      }
      func test() {
        var a = Arena();
        var base = Enemy { hp = 10 } in a;
        let c1 = clone base;
        let c2 = c1;
        clash(base, c2);
      }
      """)

    # 7. Inner-loop break must not unfreeze outer if var
    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      func test(cond: bool) {
        var opt: Box? = Box { x = 1 };
        if var b ?= opt {
          while cond {
            if cond {
              opt = none;
              break;
            }
          }
          let v = b.x;
        }
      }
      """)

    # 8. NLL keeps unwrap frozen when captured in closure
    with self.assertRaises(SemanticError):
      self._check("""
      struct Box { var x: int; }
      func test() {
        var opt: Box? = Box { x = 1 };
        if var b ?= opt {
          let cb = () -> b.x;
          opt = none;
          let v = cb();
        }
      }
      """)

    # 9. Global reentrancy catches method receiver (g.push) and higher-order cb()
    with self.assertRaises(SemanticError):
      self._check("""
      var G: [int] = [1, 2];
      func mutate_g(arr: [int]) {
        G.push(3);
      }
      func test() {
        mutate_g(G);
      }
      """)

    with self.assertRaises(SemanticError):
      self._check("""
      var G: [int] = [1, 2];
      func clear_g() { G.clear(); }
      func call_cb(arr: [int], cb: () -> void) {
        cb();
      }
      func test() {
        call_cb(G, clear_g);
      }
      """)

    # 10. Lambda stack-borrow scanner respects block-scoped shadowing
    with self.assertRaises(SemanticError):
      self._check("""
      func leak(): () -> int {
        var x = 10;
        return () -> int {
          if false {
            let x = 0;
          }
          return x;
        };
      }
      """)

  def test_trait_inheritance_partial_override_and_multiparent_conflict(self):
    """Verifies transitive trait inheritance, partial overrides, and multi-parent conflicts."""
    # 1. Transitive inheritance + partial override in Child
    self._check("""
    trait Entity {
      func id(): int;
      func tag(): String;
    }
    struct Base {
      var eid: int = 1;
    }
    impl Entity for Base {
      func id(): int { return self.eid; }
      func tag(): String { return "base"; }
    }
    struct Mid: Base {}
    struct Leaf: Mid {}
    impl Entity for Leaf {
      func tag(): String { return "leaf"; }
    }
    func inspect(e: Entity): int {
      let _t = e.tag();
      return e.id();
    }
    func main() {
      let m = Mid {};
      let l = Leaf { eid = 7 };
      let _a = inspect(m);
      let _b = inspect(l);
    }
    """)

    # 2. Multi-parent conflict on same trait method without override -> error
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      trait Greeter {
        func greet(): String;
      }
      struct A {}
      impl Greeter for A {
        func greet(): String { return "A"; }
      }
      struct B {}
      impl Greeter for B {
        func greet(): String { return "B"; }
      }
      struct C: A, B {}
      """)
    self.assertIn("Ambiguous inherited trait method 'greet'", str(ctx.exception))

    # 3. Disambiguating multi-parent conflict via override -> valid
    self._check("""
    trait Greeter {
      func greet(): String;
    }
    struct A {}
    impl Greeter for A {
      func greet(): String { return "A"; }
    }
    struct B {}
    impl Greeter for B {
      func greet(): String { return "B"; }
    }
    struct C: A, B {}
    impl Greeter for C {
      func greet(): String { return A.greet(self); }
    }
    """)

  def test_trait_default_methods_semantics(self):
    """Verifies default trait method bodies, self typing, strict override placement, and precedence."""
    # 1. Default method calling required trait method and var func default
    self._check("""
    trait Counter {
      func get(): int;
      var func add(n: int);
      func doubled(): int {
        return self.get() * 2;
      }
      var func bump() {
        self.add(1);
      }
    }
    struct Box {
      var v: int = 0;
    }
    impl Counter for Box {
      func get(): int { return self.v; }
      var func add(n: int) { self.v += n; }
    }
    func use_box() {
      var b = Box { v = 5 };
      b.bump();
      let d = b.doubled();
    }
    """)

    # 2. Immutable default method calling var func on self is rejected
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      trait BadMut {
        var func mutate();
        func bad() {
          self.mutate();
        }
      }
      """)
    self.assertIn("Cannot invoke mutating method 'mutate' on constant variable 'self'", str(ctx.exception))

    # 3. Broken default body is rejected even with ZERO implementors
    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      trait Broken {
        func value(): int {
          return "not_an_int";
        }
      }
      """)
    self.assertIn("Cannot return value of type 'String' for return value #1 (expected 'int').", str(ctx2.exception))

    # 4. Overriding a trait default in inherent `impl Struct` is rejected
    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      trait Hook {
        func on_enter() {}
      }
      struct State {}
      impl State {
        func on_enter() {}
      }
      impl Hook for State {}
      """)
    self.assertIn("conflicts with default method of trait 'Hook'", str(ctx3.exception))

    # 5. Overriding a trait default in `impl Trait for Struct` succeeds
    self._check("""
    trait Hook {
      func on_enter() {}
    }
    struct State {}
    impl Hook for State {
      func on_enter() {}
    }
    """)

    # 6. Multi-parent inheriting the same trait default does not conflict
    self._check("""
    trait Hook {
      func on_enter() {}
    }
    struct P1 {}
    impl Hook for P1 {}
    struct P2 {}
    impl Hook for P2 {}
    struct Child: P1, P2 {}
    """)


if __name__ == "__main__":
  unittest.main()
