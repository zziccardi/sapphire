"""Unit tests for collection method checks in collection_checker.py."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import SemanticError, TypeChecker


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

    src_alias_key = """
    func test(): void {
      var m: [[int]: int] = {[1]: 2};
      var k: [int] = [1];
      m.insert(m.keys()[0], 3);
    }
    """
    # Also test key aliasing with direct subscript on a nested map
    src_alias_key2 = """
    func test(): void {
      var m: [String: String] = {"a": "b"};
      m.insert(m["a"], "c");
    }
    """
    errs2 = self._check_error(src_alias_key2)
    self.assertIn("Aliasing conflict", errs2)


if __name__ == "__main__":
  unittest.main()
