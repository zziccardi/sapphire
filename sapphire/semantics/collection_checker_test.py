"""Unit tests for collection method checks in collection_checker.py."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.type_checker import SemanticError, TypeChecker


class TestCollectionChecker(unittest.TestCase):
  """Tests collection method immutability, freeze, and aliasing checks."""

  def _check_error(self, source: str) -> str:
    stream = CommonTokenStream(SapphireLexer(InputStream(source)))
    parser = SapphireParser(stream)
    tree = parser.program()
    self.assertEqual(parser.getNumberOfSyntaxErrors(), 0)
    ast = ASTBuilder().visit(tree)
    checker = TypeChecker()
    with self.assertRaises(SemanticError) as ctx:
      checker.check(ast)
    return str(ctx.exception)

  def test_in_place_map_and_filter_on_shared_ref_and_frozen_array(self):
    src_shared = """
    func test(s: SharedRef<[int]>): void {
      s.map(x -> x + 1, in_place=true);
      s.filter(x -> x > 0, in_place=true);
    }
    """
    errs = self._check_error(src_shared)
    self.assertIn(
        "in-place transformation '.map()' through deeply immutable 'SharedRef'",
        errs,
    )
    self.assertIn(
        "in-place transformation '.filter()' through deeply immutable 'SharedRef'",
        errs,
    )

    src_frozen = """
    func test(): void {
      var arr: [int] = [1, 2, 3];
      for x in arr {
        arr.map(y -> y + 1, in_place=true);
        arr.filter(y -> y > 0, in_place=true);
      }
    }
    """
    errs = self._check_error(src_frozen)
    self.assertIn(
        "in-place transformation '.map()' on 'arr' while it is frozen", errs
    )
    self.assertIn(
        "in-place transformation '.filter()' on 'arr' while it is frozen", errs
    )

  def test_sort_clear_remove_on_shared_ref_and_frozen_array(self):
    src_shared = """
    func test(s: SharedRef<[int]>, m: SharedRef<[String: int]>): void {
      s.sort(in_place=true);
      s.clear();
      s.remove(0);
      m.clear();
    }
    """
    errs = self._check_error(src_shared)
    self.assertIn("'.sort()' through deeply immutable 'SharedRef'", errs)
    self.assertIn("method 'clear' through deeply immutable 'SharedRef'", errs)
    self.assertIn("method 'remove' through deeply immutable 'SharedRef'", errs)

    src_frozen = """
    func test(): void {
      var arr: [int] = [3, 1, 2];
      for x in arr {
        arr.sort(in_place=true);
        arr.clear();
        arr.remove(0);
      }
    }
    """
    errs = self._check_error(src_frozen)
    self.assertIn("'.sort()' on 'arr' while it is frozen", errs)
    self.assertIn("method 'clear' on 'arr' while it is frozen", errs)
    self.assertIn("method 'remove' on 'arr' while it is frozen", errs)

  def test_map_insert_aliasing_conflict(self):
    src_alias_val = """
    func test(): void {
      var m: [String: [int]] = {"a": [1, 2]};
      m.insert("b", m["a"]);
    }
    """
    errs = self._check_error(src_alias_val)
    self.assertIn("Aliasing conflict", errs)

    # Also test key aliasing with direct subscript on a nested map
    src_alias_key2 = """
    func test(): void {
      var m: [String: String] = {"a": "b"};
      m.insert(m["a"], "c");
    }
    """
    errs2 = self._check_error(src_alias_key2)
    self.assertIn("Aliasing conflict", errs2)

  def test_dynamic_in_place_variable_enforces_mutability_and_type_preservation(self):
    # Runtime bool variable `in_place = flag` must trigger all in-place checks
    err_const = self._check_error("""
    func test(flag: bool): void {
      let arr = [1, 2, 3];
      arr.reverse(in_place = flag);
    }
    """)
    self.assertIn("constant variable 'arr'", err_const)

    err_fixed = self._check_error("""
    func test(flag: bool): void {
      var arr: [int; 3] = [1, 2, 3];
      arr.filter(x -> x > 1, in_place = flag);
    }
    """)
    self.assertIn("fixed-size array", err_fixed)

    err_type = self._check_error("""
    func test(flag: bool): void {
      var arr = [1, 2, 3];
      arr.map(x -> String.from(x), in_place = flag);
    }
    """)
    self.assertIn("In-place mapping requires closure return type", err_type)

  def test_collection_callbacks_require_function_type_and_exact_arity(self):
    self.assertIn(
        ".map() callback must be a function",
        self._check_error("func t() { let a = [1, 2]; a.map(42); }"),
    )
    self.assertIn(
        ".filter() predicate must be a function",
        self._check_error('func t() { let a = [1, 2]; a.filter("bad"); }'),
    )
    self.assertIn(
        ".reduce() callback must be a function",
        self._check_error("func t() { let a = [1, 2]; a.reduce(0, 42); }"),
    )
    self.assertIn(
        ".sort() comparator must be a function",
        self._check_error("func t() { let a = [1, 2]; a.sort(by = 42); }"),
    )
    self.assertIn(
        ".map() callback must take 1 parameter",
        self._check_error("func t() { let a = [1, 2]; a.map((x: int, y: int) -> x + y); }"),
    )
    self.assertIn(
        ".reduce() callback must take 2 parameters",
        self._check_error("func t() { let a = [1, 2]; a.reduce(0, (x: int) -> x); }"),
    )
    self.assertIn(
        ".sort() comparator must take 2 parameters",
        self._check_error("func t() { let a = [1, 2]; a.sort(by = (x: int) -> x); }"),
    )

  def test_bind_args_rejects_extra_positional_and_unknown_named_args(self):
    self.assertIn(
        "Unknown named argument 'bogus'",
        self._check_error("func t() { let a = [1, 2]; a.sort(bogus = true); }"),
    )
    self.assertIn(
        ".map() takes at most 2 arguments",
        self._check_error("func t() { var a = [1, 2]; a.map(x -> x, false, 99); }"),
    )
    self.assertIn(
        "Duplicate argument 'in_place'",
        self._check_error("func t() { var a = [1, 2]; a.reverse(false, in_place = false); }"),
    )


if __name__ == "__main__":
  unittest.main()
