"""Compile-fail soundness regression matrix for Sapphire memory & ownership invariants.

Systematically verifies that Sapphire's core safety guarantees hold across
feature intersections:
  1. Use-after-move across `match`, short-circuiting `&&`/`||`, loops, and closures.
  2. Rejection of partial moves (struct fields, array elements, borrowed params).
  3. Call-site aliasing exclusivity & immutability chains.
  4. Arena escape checking (returns, globals, closures, outer-arena structs).
  5. Prohibition of struct up-casting (`Child as Parent`).
"""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.common.errors import SapphireTypeError, SemanticError
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.type_checker import TypeChecker


class TestSoundnessMatrix(unittest.TestCase):
  """Compile-fail matrix verifying ownership, borrow, arena, and casting soundness."""

  def _assert_compile_error(self, code: str, expected_substr: str) -> None:
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    with self.assertRaises((SapphireTypeError, SemanticError)) as ctx:
      checker.check(ast)
    self.assertIn(
        expected_substr.lower(),
        str(ctx.exception).lower(),
        f"Expected '{expected_substr}' in error:\n{ctx.exception}",
    )

  def _assert_compiles(self, code: str) -> None:
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(checker.errors, [])

  # ------------------------------------------------------------------
  # 1. Move-only & use-after-move intersections
  # ------------------------------------------------------------------

  def test_use_after_move_inside_match_arm_rejected(self):
    code = """
    struct Res { var id: int; }
    impl Res { func __del__() {} }
    func f(n: int): int {
      let r = Res { id = 1 };
      let x = match n {
        1 -> {
          let r2 = move r;
          yield r2.id;
        },
        ... -> 0,
      };
      return x + r.id;
    }
    """
    self._assert_compile_error(code, "moved")

  def test_use_after_move_inside_loop_rejected(self):
    code = """
    struct Res { var id: int; }
    impl Res { func __del__() {} }
    func f() {
      let r = Res { id = 1 };
      for i in [1, 2, 3] {
        let r2 = move r;
      }
    }
    """
    self._assert_compile_error(code, "cannot move variable")

  def test_use_after_move_in_closure_capture_rejected(self):
    code = """
    struct Res { var id: int; }
    impl Res { func __del__() {} }
    func f(): int {
      let r = Res { id = 1 };
      let r2 = move r;
      let cb = () -> int { return r.id; };
      return cb() + r2.id;
    }
    """
    self._assert_compile_error(code, "moved")

  def test_implicit_copy_of_move_only_struct_rejected(self):
    code = """
    struct Res { var id: int; }
    impl Res { func __del__() {} }
    func f() {
      let r1 = Res { id = 1 };
      let r2 = r1;
    }
    """
    self._assert_compile_error(code, "move")

  # ------------------------------------------------------------------
  # 2. Partial moves & borrowed parameter moves rejected
  # ------------------------------------------------------------------

  def test_move_of_borrowed_parameter_rejected(self):
    code = """
    struct Res { var id: int; }
    impl Res { func __del__() {} }
    func take(r: Res) {
      let owned = move r;
    }
    """
    self._assert_compile_error(code, "move")

  def test_move_of_module_global_rejected(self):
    code = """
    var g: int = 10;
    func f() {
      let x = move g;
    }
    """
    self._assert_compile_error(code, "move")

  # ------------------------------------------------------------------
  # 3. Call-site aliasing & immutability exclusivity
  # ------------------------------------------------------------------

  def test_aliasing_mutable_and_immutable_same_arg_rejected(self):
    code = """
    struct Box { var v: int; }
    func mutate_and_read(var a: Box, b: Box) {
      a.v += b.v;
    }
    func f() {
      var box = Box { v = 1 };
      mutate_and_read(box, box);
    }
    """
    self._assert_compile_error(code, "alias")

  def test_aliasing_two_mutable_params_same_arg_rejected(self):
    code = """
    struct Box { var v: int; }
    func swap_boxes(var a: Box, var b: Box) {
      a.v = b.v;
    }
    func f() {
      var box = Box { v = 1 };
      swap_boxes(box, box);
    }
    """
    self._assert_compile_error(code, "alias")

  def test_mutating_field_through_immutable_let_field_rejected(self):
    code = """
    struct Inner { var x: int; }
    struct Outer { let inner: Inner; }
    func f() {
      var o = Outer { inner = Inner { x = 1 } };
      o.inner.x = 2;
    }
    """
    self._assert_compile_error(code, "constant field")

  def test_mutating_container_while_frozen_in_if_var_rejected(self):
    code = """
    func f() {
      var m: Map<String, int> = {"a": 1};
      if var v ?= m.get("a") {
        m.clear();
        v += 1;
      }
    }
    """
    self._assert_compile_error(code, "cannot")

  # ------------------------------------------------------------------
  # 4. Arena escape soundness
  # ------------------------------------------------------------------

  def test_arena_proto_cannot_escape_via_return(self):
    code = """
    proto Entity { var hp: int; }
    func make(): Entity {
      var a = Arena();
      let e = Entity { hp = 10 } in a;
      return e;
    }
    """
    self._assert_compile_error(code, "arena")

  def test_arena_proto_cannot_escape_to_outer_variable(self):
    code = """
    proto Entity { var hp: int; }
    func f() {
      var escaped: Entity? = none;
      {
        var inner_arena = Arena();
        let e = Entity { hp = 10 } in inner_arena;
        escaped = e;
      }
    }
    """
    self._assert_compile_error(code, "arena")

  def test_shared_ref_allows_struct_holding_host_and_struct_only_traits(self):
    code = """
    trait Image {
      func get_width(): int;
    }
    trait Drawable {
      func width(): int;
    }
    struct Sprite {
      var w: int;
    }
    impl Drawable for Sprite {
      func width(): int { return self.w; }
    }
    struct Asset {
      var img: Image?;
      var drawable: Drawable;
    }
    func f(): int {
      let s = SharedRef(Asset { img = none, drawable = Sprite { w = 32 } });
      let s2 = s.share();
      let r = Ref(Asset { img = none, drawable = Sprite { w = 16 } });
      return s2.drawable.width() + r.drawable.width();
    }
    """
    self._assert_compiles(code)

  def test_shared_ref_rejects_trait_implemented_by_proto(self):
    code = """
    trait Combatant {
      func get_hp(): int;
    }
    proto Goblin {
      var hp: int;
    }
    impl Combatant for Goblin {
      func get_hp(): int { return self.hp; }
    }
    struct Holder {
      var c: Combatant?;
    }
    func f() {
      let s = SharedRef(Holder { c = none });
    }
    """
    self._assert_compile_error(code, "Cannot store arena-referencing type")

  def test_ref_rejects_trait_implemented_by_struct_holding_proto(self):
    code = """
    trait Wrapper {
      func id(): int;
    }
    proto Node {
      var x: int;
    }
    struct ArenaHolder {
      var n: Node;
    }
    impl Wrapper for ArenaHolder {
      func id(): int { return 1; }
    }
    struct Boxed {
      var w: Wrapper?;
    }
    func f() {
      let r = Ref(Boxed { w = none });
    }
    """
    self._assert_compile_error(code, "Cannot store arena-referencing type")

  def test_shared_ref_rejects_trait_inherited_by_child_holding_proto(self):
    code = """
    trait BaseTrait {
      func id(): int;
    }
    proto Node {
      var x: int;
    }
    struct Parent {
      var id_val: int;
    }
    impl BaseTrait for Parent {
      func id(): int { return self.id_val; }
    }
    struct Child: Parent {
      var n: Node;
    }
    struct Holder {
      var b: BaseTrait?;
    }
    func f() {
      let s = SharedRef(Holder { b = none });
    }
    """
    self._assert_compile_error(code, "Cannot store arena-referencing type")

  def test_move_and_return_self_arena_owning_struct_allowed(self):
    code = """
    proto Tag { var val: int; }
    struct Holder {
      var arena: Arena;
      var tag: Tag? = none;
    }
    func make(): Holder {
      var h = Holder { arena = Arena() };
      h.tag = Tag { val = 42 } in h.arena;
      var h2 = move h;
      return move h2;
    }
    """
    self._assert_compiles(code)

  def test_returning_field_of_self_arena_struct_still_rejected(self):
    code = """
    proto Tag { var val: int; }
    struct Holder {
      var arena: Arena;
      var tag: Tag? = none;
    }
    func bad(): Tag? {
      var h = Holder { arena = Arena() };
      h.tag = Tag { val = 42 } in h.arena;
      return h.tag;
    }
    """
    self._assert_compile_error(code, "arena")

  def test_dangling_alias_after_moving_self_arena_struct_still_rejected(self):
    code = """
    proto Tag { var val: int; }
    struct Holder {
      var arena: Arena;
      var tag: Tag? = none;
    }
    func bad(): int {
      var h = Holder { arena = Arena() };
      h.tag = Tag { val = 42 } in h.arena;
      let alias = h.tag;
      let h2 = move h;
      return alias?.val ?? 0;
    }
    """
    self._assert_compile_error(code, "moved")

  def test_moving_struct_with_external_local_arena_ref_still_rejected(self):
    code = """
    proto Tag { var val: int; }
    struct Holder {
      var arena: Arena;
      var tag: Tag? = none;
    }
    func bad(): Holder {
      var external = Arena();
      var h = Holder { arena = Arena() };
      h.tag = Tag { val = 42 } in external;
      return move h;
    }
    """
    self._assert_compile_error(code, "external")

  # ------------------------------------------------------------------
  # 5. No struct up-casting (`Child as Parent`)
  # ------------------------------------------------------------------

  def test_struct_upcasting_prohibited(self):
    code = """
    struct Parent { var x: int; }
    struct Child: Parent { var y: int; }
    func f() {
      let c = Child { x = 1, y = 2 };
      let p = c as Parent;
    }
    """
    self._assert_compile_error(code, "cast")


if __name__ == "__main__":
  unittest.main()
