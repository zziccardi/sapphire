"""Control flow, match, guard, and optional unwrapping semantic tests."""

import unittest

from src.semantics.type_checker import SemanticError
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerControlFlow(TypeCheckerTestBase, unittest.TestCase):
  """Control flow, match, guard, and optional unwrapping semantic tests."""

  def test_type_mismatch(self):
    """Enforces that assigning an incompatible type fails at compile time."""
    code = """
    func test() {
      let x: int = "hello";
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot assign expression of type 'String' to variable 'x' of type 'int'", str(context.exception))

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

    # 2. while loop with condition
    code2 = """
    func test() {
      var count: int = 0;
      while count < 5 {
        count += 1;
      }
    }
    """
    self._check(code2)

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

  def test_range_call_type_mismatch_error(self):
    """Enforces integer arguments for range()."""
    code = """
    func test() {
      let r = range("0", "10");
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Argument type mismatch at position 1. Expected 'int', got 'String'", str(context.exception))

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
        ... -> "Generic Error"
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
        }
      };
    }
    """
    self._check(valid_code)

    non_exhaustive = """
    enum Status { Ok, NotFound, Error }
    func test_bad(s: Status) {
      let x = match s {
        Status.Ok -> 1
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

    # Identifier pattern error (underscore or arbitrary identifier rejected)
    with self.assertRaises(SemanticError) as ctx:
      self._check("func i(v: int): String { return match v { _ -> \"ok\" }; }")
    self.assertIn("Undefined identifier '_'", str(ctx.exception))

    # Incompatible pattern type
    with self.assertRaises(SemanticError) as ctx:
      self._check("func i(v: int) { let x = match v { \"bad\" -> 1, ... -> 0 }; }")
    self.assertIn("Pattern type 'String' is incompatible with subject type 'int'", str(ctx.exception))

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
        Status.NotFound -> 2
      };
    }
    """)

    # Invalid enum member access pattern
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Ok, NotFound }
      enum Other { Bad }
      func test_enum_mismatch(s: Status) {
        let x = match s {
          Other.Bad -> 1,
          ... -> 0
        };
      }
      """)
    self.assertIn("not a valid variant of enum 'Status'", str(ctx.exception))

    # Undefined identifier in enum pattern
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Ok }
      func test_enum_undef(s: Status) {
        let x = match s {
          UnknownVariant -> 1,
          ... -> 0
        };
      }
      """)
    self.assertIn("Undefined identifier 'UnknownVariant'", str(ctx.exception))

    # Non-enum literal in enum pattern
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      enum Status { Ok }
      func test_enum_lit(s: Status) {
        let x = match s {
          123 -> 1,
          ... -> 0
        };
      }
      """)
    self.assertIn("not a valid variant of enum 'Status'", str(ctx.exception))

    # Non-bool literal in bool pattern
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_bool_lit(b: bool) {
        let x = match b {
          123 -> 1,
          ... -> 0
        };
      }
      """)
    self.assertIn("Bool match pattern must be 'true' or 'false'", str(ctx.exception))

    # Optional pattern with value match and incompatible type
    self._check("""
    func test_opt_val(v: int?): int {
      return match v {
        10 -> 1,
        none -> 0,
        ... -> 2
      };
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test_opt_incompat(v: int?) {
        let x = match v {
          "string_pat" -> 1,
          ... -> 0
        };
      }
      """)
    self.assertIn("is incompatible with optional inner type 'int'", str(ctx.exception))

    # Struct member pattern type mismatch
    with self.assertRaises(SemanticError):
      self._check("""
      struct Item { var id: int; }
      func test_item(i: Item) {
        let x = match i {
          i.id -> 1,
          ... -> 0
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
          ... -> 0
        };
      }
      """)

    # Enum identifier pattern matching enum type name
    self._check("""
    enum Status { Active, Inactive }
    func test_enum_name(s: Status): int {
      return match s {
        Status -> 1,
        ... -> 0
      };
    }
    func test_enum_bare(s: Status): int {
      return match s {
        Active -> 1,
        Inactive -> 2
      };
    }
    """)

    # Optional type wrapping fallback in match return
    self._check("""
    func test_opt_fall(n: int): int? {
      return match n {
        1 -> 10,
        ... -> none
      };
    }
    """)

    # Arena return escaping error
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Item {}
      func test_arena_escape(): Item {
        var a = Arena();
        return Item {} in a;
      }
      """)
    self.assertIn("Cannot return a reference to an object allocated in local arena", str(ctx.exception))

  def test_break_and_continue_type_checking(self):
    """Verifies valid usage of break/continue in loops and error when used outside loops."""
    # Valid usage inside while and for loops
    self._check("""
    func test() {
      var i = 0;
      while i < 10 {
        i += 1;
        if i % 2 == 0 {
          continue;
        }
        if i > 5 {
          break;
        }
      }

      let arr = [1, 2, 3];
      for x in arr {
        if x == 2 {
          continue;
        }
        break;
      }
    }
    """)

    # Error: break outside loop
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        break;
      }
      """)
    self.assertIn("'break' statement outside of loop.", str(ctx.exception))

    # Error: continue outside loop
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        continue;
      }
      """)
    self.assertIn("'continue' statement outside of loop.", str(ctx.exception))

  def test_guard_statement_type_checking(self):
    """Verifies type checking, scope promotion, and control-flow termination enforcement for guard statements."""
    # 1. Valid guard statement with scope promotion
    self._check("""
    func test(opt: int?, flag: bool): int {
      guard let x ?= opt; flag && x > 0 else {
        return 0;
      }
      return x * 2; // 'x' is promoted to outer scope as non-optional int
    }
    """)

    # 2. Guard else block fails to terminate control flow
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(opt: int?): int {
        guard let x ?= opt else {
          let dummy = 1;
        }
        return x;
      }
      """)
    self.assertIn("Guard else block must terminate control flow (via return, break, or continue).", str(ctx.exception))

    # 3. Guard unwrapping non-optional type
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test(num: int) {
        guard let x ?= num else {
          return;
        }
      }
      """)
    self.assertIn("Cannot unwrap non-optional type 'int' in guard clause.", str(ctx.exception))

    # 4. Guard condition must be bool
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func test() {
        guard 123 else {
          return;
        }
      }
      """)
    self.assertIn("Guard condition must be of type 'bool', got 'int'.", str(ctx.exception))

    # 5. Guard with non-unwrap binding, multi-variable destructuring, and nested if termination in else
    self._check("""
    func test(opt: int?, flag: bool, arr: [int]): int {
      guard
        let x = 5;
        let a, b = arr;
        opt != none
      else {
        if flag {
          return 0;
        } else {
          return -1;
        }
      }
      return x + a + b;
    }
    """)

  def test_struct_field_default_expr_type_mismatch(self):
    """Verifies error reporting when struct field default expression type does not match explicit annotation."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Point {
        var x: int = "invalid_string";
      }
      """)
    self.assertIn("Default expression of type 'String' is not compatible with field 'x' of type 'int'.", str(ctx.exception))

  def test_optional_chaining_method_call_returns_optional(self):
    """Verifies that invoking a method via optional chaining '?.' returns an optional type."""
    code_valid = """
    struct Player {
      var name: String;
    }
    impl Player {
      func get_name(): String {
        return self.name;
      }
    }
    func test() {
      let p: Player? = none;
      let name: String? = p?.get_name();
    }
    """
    ast = self._check(code_valid)
    self.assertEqual(len(ast.errors), 0)

    code_invalid = """
    struct Player {
      var name: String;
    }
    impl Player {
      func get_name(): String {
        return self.name;
      }
    }
    func test() {
      let p: Player? = none;
      let name: String = p?.get_name();
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code_invalid)
    self.assertIn("Cannot assign expression of type 'String?' to variable 'name' of type 'String'.", str(ctx.exception))

  def test_guard_var_allows_disjoint_mutating_method(self):
    """Verifies field-disjoint var func calls succeed during guard var unwrap."""
    self._check("""
    struct Enemy {
      var x: int = 0;
    }
    impl Enemy {
      var func step(nx: int) { self.x = nx; }
    }
    struct Controller {
      var active_enemy: Enemy? = none;
      var index: int = 0;
      var in_progress: bool = false;
    }
    impl Controller {
      var func clear_turn() {
        self.index = 0;
        self.in_progress = false;
      }
      var func set_enemy(e: Enemy?) {
        self.active_enemy = e;
        self.clear_turn();
      }
      var func advance_path() {
        guard var e ?= self.active_enemy else { return; }
        e.step(5);
        self.clear_turn();
      }
    }
    """)

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct Enemy { var x: int = 0; }
      struct Controller {
        var active_enemy: Enemy? = none;
        var index: int = 0;
      }
      impl Controller {
        var func clear_turn() { self.index = 0; }
        var func set_enemy(e: Enemy?) {
          self.active_enemy = e;
          self.clear_turn();
        }
        var func advance_path() {
          guard var e ?= self.active_enemy else { return; }
          self.set_enemy(none);
          e.step(5);
        }
      }
      """)
    self.assertIn(
        "Cannot invoke mutating method 'set_enemy' on 'self' while it is frozen",
        str(ctx.exception),
    )

    # After the last use of `e`, non-lexical lifetime unfreezes `self`.
    self._check("""
    struct Enemy { var x: int = 0; }
    impl Enemy {
      var func step(nx: int) { self.x = nx; }
    }
    struct Controller {
      var active_enemy: Enemy? = none;
    }
    impl Controller {
      var func set_enemy(e: Enemy?) {
        self.active_enemy = e;
      }
      var func advance_path() {
        guard var e ?= self.active_enemy else { return; }
        e.step(5);
        self.set_enemy(none);
      }
    }
    """)

  def test_mutable_unwrap_requires_mutable_lvalue(self):
    """Verifies if var / guard var lvalue rules and container .get() borrows."""
    with self.assertRaises(SemanticError) as ctx1:
      self._check("""
      func get_opt(): int? { return 1; }
      func main() {
        if var v ?= get_opt() {
          v = 2;
        }
      }
      """)
    self.assertIn("requires a mutable lvalue", str(ctx1.exception))

    # Mutable map.get(k) and arr.get(i) are allowed, freeze the container while
    # live, and unfreeze via NLL after the unwrapped binding's last use.
    self._check("""
    func main() {
      var m: [String: int] = {"a": 1};
      guard var v ?= m.get("a") else { return; }
      v += 1;
      m.remove("b");

      var arr: [int] = [10, 20];
      if var elem ?= arr.get(0) {
        elem += 5;
      }
      arr.push(30);
    }
    """)

    with self.assertRaises(SemanticError) as ctx2:
      self._check("""
      func main() {
        var m: [String: int] = {"a": 1};
        if var v ?= m.get("a") {
          m.remove("a");
          let y = v;
        }
      }
      """)
    self.assertIn("while it is frozen (active 'if var' unwrap)", str(ctx2.exception))

    with self.assertRaises(SemanticError) as ctx3:
      self._check("""
      func main() {
        let immut_m: [String: int] = {"a": 1};
        if var v ?= immut_m.get("a") {
          v = 2;
        }
      }
      """)
    self.assertIn("requires a mutable source lvalue", str(ctx3.exception))

    with self.assertRaises(SemanticError) as ctx4:
      self._check("""
      func main() {
        let opt: int? = 1;
        if var v ?= opt {
          v = 2;
        }
      }
      """)
    self.assertIn("requires a mutable source lvalue", str(ctx4.exception))

  def test_optional_chain_flattens_nested_optional(self):
    code = """
    struct Inner { var name: String? = none; }
    func get_name(x: Inner?): String {
      return x?.name ?? "default";
    }
    """
    self._check(code)

  def test_if_var_post_last_use_and_field_disjoint_unfreezing(self):
    code_ok = """
    struct Session { var step: int = 0; }
    impl Session {
      var func advance() { self.step = self.step + 1; }
    }
    struct Runner {
      var session: Session? = none;
      var done: bool = false;
    }
    impl Runner {
      var func finish() {
        self.session = none;
        self.done = true;
      }
      var func update() {
        if var s ?= self.session {
          s.advance();
          self.finish();
        }
      }
    }
    """
    self._check(code_ok)

  def test_if_var_terminating_early_return_branch_unfreezing(self):
    code_ok = """
    struct Session { var choices: [int] = [1, 2]; }
    struct Dialogue { var session: Session? = none; var active: bool = true; }
    impl Dialogue {
      var func choose(idx: int): int {
        if var s ?= self.session {
          if idx < 0 || idx >= s.choices.size() {
            self.session = none;
            self.active = false;
            return -1;
          }
          return s.choices[idx];
        }
        return -1;
      }
    }
    """
    self._check(code_ok)

    code_non_terminating = """
    struct Session { var choices: [int] = [1, 2]; }
    struct Dialogue { var session: Session? = none; }
    impl Dialogue {
      var func choose(idx: int): int {
        if var s ?= self.session {
          if idx < 0 {
            self.session = none;
          }
          return s.choices[0];
        }
        return -1;
      }
    }
    """
    with self.assertRaises(SemanticError):
      self._check(code_non_terminating)

  def test_multi_pattern_match_arm_semantics(self):
    code_ok = """
    enum Dir { Up, Down, Left, Right }
    func axis(d: Dir): String {
      return match d {
        Dir.Up, Dir.Down -> "vertical",
        Dir.Left, Dir.Right -> "horizontal",
      };
    }
    """
    self._check(code_ok)

    code_non_exhaustive = """
    enum Dir { Up, Down, Left, Right }
    func axis(d: Dir): String {
      return match d {
        Dir.Up, Dir.Down -> "vertical",
        Dir.Left -> "horizontal",
      };
    }
    """
    with self.assertRaises(SemanticError):
      self._check(code_non_exhaustive)

  def test_destructor_explicit_void_and_optional_return_type(self):
    """Verifies __del__(): void succeeds and __del__(): int? raises SemanticError without AttributeError."""
    self._check("""
    struct Clean { var x: int; }
    impl Clean {
      func __del__(): void {}
    }
    """)
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct BadDel { var x: int; }
      impl BadDel {
        func __del__(): int? { return none; }
      }
      """)
    self.assertIn("Destructor '__del__' must return void.", str(ctx.exception))

  def test_phase4_control_flow_scoping_and_match_exhaustiveness(self):
    """Verifies Phase 4 if/guard else scoping, multi-name if-let, and match rules."""
    # 1. `if let` binding must NOT be visible in `else`
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(opt: int?): int {
        if let v ?= opt {
          return v;
        } else {
          return v;
        }
      }
      """)
    self.assertIn("Undefined identifier 'v'", str(ctx.exception))

    # 2. `guard let` binding must NOT be visible in `else`
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(opt: int?): int {
        guard let v ?= opt else {
          return v;
        }
        return v;
      }
      """)
    self.assertIn("Undefined identifier 'v'", str(ctx.exception))

    # 3. Multi-name `if let a, b = pair(); ...` unpacks MultiReturnType
    self._check("""
    func pair(): int, String { return 1, "ok"; }
    func f(): int {
      if let a, b = pair(); a > 0 {
        let s: String = b;
        return a;
      }
      return 0;
    }
    """)
    with self.assertRaises(SemanticError):
      self._check("""
      func pair(): int, String { return 1, "ok"; }
      func f() {
        if let a, b, c = pair(); a > 0 {}
      }
      """)

    # 4. `match` on int? is NOT exhaustive without `...`
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(opt: int?): int {
        return match opt {
          none -> 0,
          1 -> 1,
        };
      }
      """)
    self.assertIn("not exhaustive", str(ctx.exception))

    # 5. `match` on Enum? IS exhaustive with `none` + all variants
    self._check("""
    enum Dir { Up, Down }
    func f(opt: Dir?): int {
      return match opt {
        none -> 0,
        Dir.Up -> 1,
        Dir.Down -> 2,
      };
    }
    """)

    # 6. `match` on open type `int` requires `...`
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(n: int): int {
        return match n {
          1 -> 10,
          2 -> 20,
        };
      }
      """)
    self.assertIn("not exhaustive", str(ctx.exception))

    # 7. Value-producing `match` block arm must yield on ALL paths
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func f(n: int): int {
        return match n {
          1 -> {
            if false { yield 10; }
          },
          ... -> 20,
        };
      }
      """)
    self.assertIn("must explicitly yield a value", str(ctx.exception))

    # 8. `match` subject clears `expected_type` (e.g. matching array inside int return)
    self._check("""
    func f(): int {
      return match [1, 2].size() {
        2 -> 10,
        ... -> 0,
      };
    }
    """)


if __name__ == "__main__":
  unittest.main()
