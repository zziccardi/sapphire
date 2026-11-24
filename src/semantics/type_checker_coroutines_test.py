"""Coroutine, yield, and resume semantic type-checking tests."""

import unittest

from src.parser.ast import (
  LiteralNode,
  YieldNode,
)
from src.semantics.symbol_table import (
  PrimitiveType,
)
from src.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerCoroutines(TypeCheckerTestBase, unittest.TestCase):
  """Coroutine, yield, and resume semantic type-checking tests."""

  def test_match_multiple_yield_values(self):
    """Verifies type checking of match expressions yielding multiple values."""
    # 1. Valid multiple yield values in match returned directly
    self._check("""
    enum Direction { North, South }

    func get_offset(d: Direction): int, int {
      return match d {
        Direction.North -> { yield 0, 1; },
        Direction.South -> { yield 0, -1; },
      };
    }
    """)

    # 2. Unpacking match expression yielding multiple values into variable declaration
    self._check("""
    enum Direction { North }

    func main() {
      let d = Direction.North;
      let dx, dy = match d {
        Direction.North -> { yield 1, 2; },
      };
    }
    """)

    # 3. Type mismatch in multiple yield values
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Direction { North }

      func get_offset(d: Direction): int, int {
        return match d {
          Direction.North -> { yield 0, "invalid"; },
        };
      }
      """)
    self.assertIn("Cannot return value of type 'String' for return value #2 (expected 'int').", str(ctx.exception))

  def test_match_empty_and_single_yield_context(self):
    """Verifies type checking of empty yield statements inside match."""
    self._check("""
    func test_empty_yield(x: int) {
      let r = match x {
        1 -> { yield; },
        ... -> { yield; }
      };
    }
    """)

  def test_coroutine_type_checking(self):
    """Verifies type checking for Coroutine declarations, yields, returns, and methods."""
    # 1. Valid Coroutine<int> and Coroutine<void>
    self._check("""
    func count_down(start: int): Coroutine<int> {
      var current = start;
      while current > 0 {
        yield current;
        current -= 1;
      }
    }

    func patrol(): Coroutine<void> {
      yield;
      return;
    }

    func test_consumer() {
      var co = count_down(5);
      let step_val: int? = co.step();
      let done: bool = co.is_done();
      co.reset();

      var p = patrol();
      p.step();
      let p_done: bool = p.is_done();
    }
    """)

    # 2. Coroutine method on struct
    self._check("""
    struct Agent {
      var speed: int = 10;
    }
    impl Agent {
      var func tick(): Coroutine<int> {
        yield self.speed;
      }
    }
    func test() {
      var a = Agent { speed = 20 };
      var co = a.tick();
      let val = co.step();
    }
    """)

    # 3. Yielding wrong type in Coroutine<int>
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_coro(): Coroutine<int> {
        yield "hello";
      }
      """)
    self.assertIn("Cannot yield value of type 'String' in Coroutine<int>", str(ctx.exception))

    # 4. Bare yield in Coroutine<int>
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_coro(): Coroutine<int> {
        yield;
      }
      """)
    self.assertIn("Must yield a value of type 'int' in Coroutine<int>", str(ctx.exception))

    # 5. Yielding non-void value in Coroutine<void>
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_coro(): Coroutine<void> {
        yield 42;
      }
      """)
    self.assertIn("Cannot yield value of type 'int' in Coroutine<void>", str(ctx.exception))

    # 6. Yield in non-coroutine function
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func regular_func(): int {
        yield 10;
        return 10;
      }
      """)
    self.assertIn("Cannot yield in a function with return type 'int'", str(ctx.exception))

    # 7. Returning value from coroutine
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_return(): Coroutine<int> {
        yield 1;
        return 10;
      }
      """)
    self.assertIn("Cannot return a value from a coroutine", str(ctx.exception))

    # 8. Nested match inside coroutine (yield in match arm vs yield in coroutine)
    self._check("""
    enum Status { Ready, Busy }
    func worker(s: Status): Coroutine<int> {
      let code = match s {
        Status.Ready -> {
          yield 1;
        },
        Status.Busy -> {
          yield 2;
        },
      };
      yield code;
    }
    """)

    # 8b. Statement-level match inside coroutine yielding directly from coroutine
    self._check("""
    enum Status { Ready, Busy }
    func worker_stmt(s: Status): Coroutine<int> {
      match s {
        Status.Ready -> {
          yield 10;
        },
        Status.Busy -> {
          yield 20;
        },
      };
    }
    """)

    # 8c. Statement-level match inside coroutine with wrong yield type raises error
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Ready, Busy }
      func bad_worker_stmt(s: Status): Coroutine<int> {
        match s {
          Status.Ready -> {
            yield "not_an_int";
          },
          Status.Busy -> {
            yield 20;
          },
        };
      }
      """)
    self.assertIn("Cannot yield value of type 'String' in Coroutine<int>", str(ctx.exception))

    # 9. Invalid method on Coroutine
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        var co: Coroutine<int>;
        co.invalid_method();
      }
      """)
    self.assertIn("Coroutine has no method 'invalid_method'", str(ctx.exception))

  def test_coroutine_type_checker_edges(self):
    """Verifies edge cases in coroutine type checking and yield validation."""
    # Bare Coroutine return type without type argument
    self._check("""
    func run(): Coroutine {
      yield;
    }
    """)

    # Top-level yield outside function or match context
    checker = TypeChecker()
    checker.visit_YieldNode(YieldNode([LiteralNode(1, "int")]))
    self.assertTrue(any("Yield statement outside coroutine or match context" in err for err in checker.errors))

    # Mock node with expr attribute when expressions is None
    checker2 = TypeChecker()
    checker2._check_code = lambda code: None
    from src.semantics.symbol_table import CoroutineType, FunctionType
    checker2.current_function = FunctionType([], CoroutineType(PrimitiveType("int")))
    class MockYieldNode:
      expr = LiteralNode(42, "int")
      expressions = None
    checker2.visit_YieldNode(MockYieldNode())

    # Cannot yield multiple values in Coroutine<void>
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_void(): Coroutine<void> {
        yield 1, 2;
      }
      """)
    self.assertIn("Cannot yield 2 values in Coroutine<void>; use bare 'yield;'", str(ctx.exception))

    # Cannot yield multiple values in Coroutine<int>
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_int(): Coroutine<int> {
        yield 1, 2;
      }
      """)
    self.assertIn("Cannot yield multiple values in Coroutine<int>", str(ctx.exception))

  def test_value_producing_match_missing_yield(self):
    """Verifies that missing yield in a block of a value-producing match expression causes a SemanticError."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(x: int): int {
        return match x {
          1 -> 10,
          ... -> {
            let y = 20;
          }
        };
      }
      """)
    self.assertIn("Match case block in value-producing match expression must explicitly yield a value.", str(ctx.exception))

  def test_coroutine_stack_borrow_escapes(self):
    local_step_ok = """
    struct Actor { var hp: int; }
    impl Actor {
      func tick(): Coroutine<void> {
        yield;
      }
    }
    func main() {
      var a = Actor { hp = 100 };
      var co = a.tick();
      co.step();
    }
    """
    self._check(local_step_ok)

    return_coro_borrow_reject = """
    struct Actor { var hp: int; }
    impl Actor {
      func tick(): Coroutine<void> {
        yield;
      }
    }
    struct Wrapper { var co: Coroutine<void>; }
    func make_wrapper(): Wrapper {
      var a = Actor { hp = 100 };
      return Wrapper { co = a.tick() };
    }
    """
    with self.assertRaises(SemanticError) as ctx1:
      self._check(return_coro_borrow_reject)
    self.assertIn("borrowing local variable 'a'", str(ctx1.exception))

    return_coro_arg_reject = """
    struct Packet { var val: int; }
    func stream(p: Packet): Coroutine<int> {
      yield p.val;
    }
    struct StreamHolder { var s: Coroutine<int>; }
    func make_stream(): StreamHolder {
      let pkt = Packet { val = 42 };
      return StreamHolder { s = stream(pkt) };
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(return_coro_arg_reject)
    self.assertIn("borrowing local variable 'pkt'", str(ctx2.exception))

    outer_assign_coro_reject = """
    struct Actor { var hp: int; }
    impl Actor {
      func tick(): Coroutine<void> {
        yield;
      }
    }
    func main() {
      var co: Coroutine<void>;
      {
        var a = Actor { hp = 100 };
        co = a.tick();
      }
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(outer_assign_coro_reject)
    self.assertIn(
        "Coroutine borrowing local variable 'a' cannot escape",
        str(ctx3.exception),
    )

    earlier_decl_coro_reject = """
    struct Actor { var hp: int; }
    impl Actor {
      func tick(): Coroutine<void> {
        yield;
      }
    }
    func main() {
      var co: Coroutine<void>;
      var a = Actor { hp = 100 };
      co = a.tick();
    }
    """
    with self.assertRaises(SemanticError) as ctx4:
      self._check(earlier_decl_coro_reject)
    self.assertIn(
        "Coroutine borrowing local variable 'a' cannot escape",
        str(ctx4.exception),
    )

  def test_coroutine_yield_raii_restriction(self):
    del_across_yield_reject = """
    struct Resource { var id: int; }
    impl Resource {
      func __del__() {}
    }
    func coro(): Coroutine<void> {
      let r = Resource { id = 1 };
      yield;
    }
    """
    with self.assertRaises(SemanticError) as ctx1:
      self._check(del_across_yield_reject)
    self.assertIn(
        "move-only RAII type 'Resource' cannot remain live across 'yield'",
        str(ctx1.exception),
    )

    arena_across_yield_reject = """
    func coro(): Coroutine<void> {
      var a = Arena();
      yield;
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(arena_across_yield_reject)
    self.assertIn(
        "move-only RAII type 'Arena' cannot remain live across 'yield'",
        str(ctx2.exception),
    )

    ref_across_yield_reject = """
    func coro(): Coroutine<void> {
      let r = Ref(10);
      yield;
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(ref_across_yield_reject)
    self.assertIn(
        "move-only RAII type 'Ref<int>' cannot remain live across 'yield'",
        str(ctx3.exception),
    )

    scoped_block_before_yield_ok = """
    struct Resource { var id: int; }
    impl Resource {
      func __del__() {}
    }
    func coro(): Coroutine<void> {
      {
        let r = Resource { id = 1 };
      }
      yield;
    }
    """
    self._check(scoped_block_before_yield_ok)

    moved_before_yield_ok = """
    struct Resource { var id: int; }
    impl Resource {
      func __del__() {}
    }
    func sink(r: Resource) {}
    func coro(): Coroutine<void> {
      let r = Resource { id = 1 };
      sink(move r);
      yield;
    }
    """
    self._check(moved_before_yield_ok)

  def test_coroutine_lifo_drop_order_diagnostic(self):
    """Verifies distinct same-scope LIFO vs outer-scope escape diagnostics."""
    with self.assertRaises(SemanticError) as ctx1:
      self._check("""
      struct Holder { var co: Coroutine<int>? = none; }
      func gen(items: [int]): Coroutine<int> { yield items[0]; }
      func main() {
        var h = Holder {};
        let items = [1, 2];
        h.co = gen(items);
      }
      """)
    self.assertIn("LIFO drop order", str(ctx1.exception))
    self.assertIn("declare 'items' before 'h'", str(ctx1.exception))

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Holder { var co: Coroutine<int>? = none; }
      func gen(items: [int]): Coroutine<int> { yield items[0]; }
      func main() {
        var h = Holder {};
        if true {
          let items = [1, 2];
          h.co = gen(items);
        }
      }
      """)
    self.assertIn("outer-scope variable 'h'", str(ctx2.exception))

  def test_phase3_method_scope_return_escape_and_yield(self):
    """Verifies methods enforce arena/stack-borrow return escape and scope coroutine yield checks."""
    # 1. Method returning local-arena proto must be rejected
    with self.assertRaises(SemanticError) as ctx1:
      self._check("""
      proto Item { var v: int; }
      struct Factory {}
      impl Factory {
        func make(): Item {
          var a = Arena();
          let it = Item { v = 1 } in a;
          return it;
        }
      }
      """)
    self.assertIn("local arena 'a'", str(ctx1.exception))

    # 2. Method returning closure capturing local var must be rejected
    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      struct Maker {}
      impl Maker {
        func make_fn(): () -> int {
          var n = 42;
          return () -> n;
        }
      }
      """)
    self.assertIn("local variable 'n'", str(ctx2.exception))

    # 3. Coroutine method yield must not walk past method scope into globals
    self._check("""
    @extern var GLOBAL_REF: Ref<int>;
    struct Gen {}
    impl Gen {
      func run(): Coroutine<int> {
        yield 1;
      }
    }
    """)


if __name__ == "__main__":
  unittest.main()
