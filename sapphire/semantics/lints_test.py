"""Unit and integration tests for semantic lints in src/semantics/lints.py."""

import unittest
from types import SimpleNamespace

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast import (
    ArgumentNode,
    BinaryOpNode,
    BlockNode,
    CallNode,
    GuardStmtNode,
    IdentifierNode,
    IndexExprNode,
    LiteralNode,
    MemberAccessNode,
    UnaryOpNode,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.lints import (
    _collect_contains_in_and_chain,
    _exprs_equal,
    _is_matching_map_get,
    _is_mutable_lvalue,
    _is_rooted_at_matching_index,
    _scan_subtrees_for_map_access,
    check_guard_contains_access,
)
from sapphire.semantics.symbol_table import (
    FunctionSymbol,
    FunctionType,
    MapType,
    OptionalType,
    PrimitiveType,
    RefType,
    SymbolTable,
    TraitType,
)
from sapphire.semantics.type_checker import TypeChecker


def _check_code(code: str) -> TypeChecker:
  lexer = SapphireLexer(InputStream(code))
  parser = SapphireParser(CommonTokenStream(lexer))
  ast = ASTBuilder().visitProgram(parser.program())
  checker = TypeChecker()
  checker.check(ast)
  return checker


class TestLintsHelpers(unittest.TestCase):
  """Unit tests for helper functions in src/semantics/lints.py."""

  def test_exprs_equal_variants(self):
    self.assertFalse(_exprs_equal(None, IdentifierNode("a")))
    self.assertFalse(_exprs_equal(IdentifierNode("a"), LiteralNode(1, "int")))

    m1 = MemberAccessNode(IdentifierNode("s"), "m", False)
    m2 = MemberAccessNode(IdentifierNode("s"), "m", False)
    m3 = MemberAccessNode(IdentifierNode("s"), "m", True)
    self.assertTrue(_exprs_equal(m1, m2))
    self.assertFalse(_exprs_equal(m1, m3))

    i1 = IndexExprNode(IdentifierNode("arr"), LiteralNode(0, "int"))
    i2 = IndexExprNode(IdentifierNode("arr"), LiteralNode(0, "int"))
    i3 = IndexExprNode(IdentifierNode("arr"), LiteralNode(1, "int"))
    self.assertTrue(_exprs_equal(i1, i2))
    self.assertFalse(_exprs_equal(i1, i3))

    u1 = UnaryOpNode("-", IdentifierNode("x"))
    u2 = UnaryOpNode("-", IdentifierNode("x"))
    self.assertTrue(_exprs_equal(u1, u2))

    b1 = BinaryOpNode(IdentifierNode("x"), "+", LiteralNode(1, "int"))
    b2 = BinaryOpNode(IdentifierNode("x"), "+", LiteralNode(1, "int"))
    b3 = BinaryOpNode(IdentifierNode("x"), "-", LiteralNode(1, "int"))
    self.assertTrue(_exprs_equal(b1, b2))
    self.assertFalse(_exprs_equal(b1, b3))

    # Unsupported node type returns False even when types match
    c1 = CallNode(IdentifierNode("f"), [])
    c2 = CallNode(IdentifierNode("f"), [])
    self.assertFalse(_exprs_equal(c1, c2))

  def test_collect_contains_none_condition(self):
    self.assertEqual(_collect_contains_in_and_chain(None, {}), [])

  def test_is_matching_map_get_and_rooted_index(self):
    recv = IdentifierNode("m")
    key = IdentifierNode("k")

    get_call = CallNode(
        MemberAccessNode(IdentifierNode("m"), "get", False),
        [ArgumentNode(None, IdentifierNode("k"))],
    )
    self.assertTrue(_is_matching_map_get(get_call, recv, key))

    nested_idx = IndexExprNode(
        IndexExprNode(IdentifierNode("m"), IdentifierNode("k")),
        LiteralNode(0, "int"),
    )
    self.assertTrue(_is_rooted_at_matching_index(nested_idx, recv, key))

    nested_member = MemberAccessNode(
        IndexExprNode(IdentifierNode("m"), IdentifierNode("k")),
        "val",
        False,
    )
    self.assertTrue(_is_rooted_at_matching_index(nested_member, recv, key))

    self.assertFalse(_is_rooted_at_matching_index(LiteralNode(1, "int"), recv, key))
    self.assertFalse(_is_rooted_at_matching_index(None, recv, key))

  def test_is_mutable_lvalue_edge_cases(self):
    sym_table = SymbolTable()
    sym_table.define(
        "fn",
        FunctionSymbol("fn", FunctionType([], PrimitiveType("void"))),
    )
    checker = SimpleNamespace(symbol_table=sym_table)

    # Non-lvalue expression (e.g. call) returns False
    self.assertFalse(
        _is_mutable_lvalue(checker, CallNode(IdentifierNode("fn"), []))
    )
    # Symbol that is not a VariableSymbol returns False
    self.assertFalse(_is_mutable_lvalue(checker, IdentifierNode("fn")))

  def test_scan_optional_ref_and_trait_mutating_method(self):
    trait_t = TraitType("Mutatable")
    mut_fn = FunctionType([], PrimitiveType("void"))
    mut_fn.ast_decl = SimpleNamespace(modifier="var")
    trait_t.methods["bump"] = mut_fn

    recv = IdentifierNode("m")
    key = IdentifierNode("k")
    idx_expr = IndexExprNode(IdentifierNode("m"), IdentifierNode("k"))
    call = CallNode(MemberAccessNode(idx_expr, "bump", False), [])

    # Test OptionalType + RefType unwrapping on receiver type with TraitType var method
    checker = SimpleNamespace(
        node_types={idx_expr: OptionalType(RefType(trait_t))},
        symbol_table=SymbolTable(),
    )
    has_access, has_mut, has_overwrite, has_recv_mut = (
        _scan_subtrees_for_map_access(checker, [call], recv, key)
    )
    self.assertTrue(has_access)
    self.assertTrue(has_mut)
    self.assertFalse(has_overwrite)
    self.assertFalse(has_recv_mut)

  def test_check_guard_contains_legacy_condition_attribute(self):
    warnings = []
    recv = IdentifierNode("m")
    key = IdentifierNode("k")
    contains_call = CallNode(
        MemberAccessNode(recv, "contains", False),
        [ArgumentNode(None, key)],
    )
    checker = SimpleNamespace(
        node_types={recv: MapType(PrimitiveType("String"), PrimitiveType("int"))},
        symbol_table=SymbolTable(),
        warning=lambda msg, node=None: warnings.append(msg),
    )
    guard_node = GuardStmtNode(
        clauses=[],
        else_block=BlockNode([]),
    )
    guard_node.condition = contains_call
    remaining = [IndexExprNode(IdentifierNode("m"), IdentifierNode("k"))]
    check_guard_contains_access(checker, guard_node, remaining)
    self.assertEqual(len(warnings), 1)
    self.assertIn("guard let v ?=", warnings[0])

  def test_maybe_warn_skips_in_place_mutation_on_immutable_lvalue(self):
    from sapphire.semantics.lints import _maybe_warn_contains_access
    from sapphire.semantics.symbol_table import VariableSymbol

    warnings = []
    sym_table = SymbolTable()
    sym_table.define(
        "m",
        VariableSymbol(
            "m",
            MapType(PrimitiveType("String"), PrimitiveType("int")),
            is_mutable=False,
        ),
    )
    recv = IdentifierNode("m")
    key = IdentifierNode("k")
    contains_call = CallNode(
        MemberAccessNode(recv, "contains", False),
        [ArgumentNode(None, key)],
    )
    # In-place mutation `m[k].push(1)` on immutable `m` must not suggest `if var`
    mut_call = CallNode(
        MemberAccessNode(IndexExprNode(IdentifierNode("m"), IdentifierNode("k")), "push", False),
        [ArgumentNode(None, LiteralNode(1, "int"))],
    )
    checker = SimpleNamespace(
        node_types={},
        symbol_table=sym_table,
        warning=lambda msg, node=None: warnings.append(msg),
    )
    _maybe_warn_contains_access(checker, contains_call, recv, key, [mut_call], "if")
    self.assertEqual(warnings, [])


class TestLintsIntegration(unittest.TestCase):
  """Integration tests triggering map contains lint rules via TypeChecker."""

  def test_if_contains_followed_by_get_warns(self):
    code = """
    func f(m: Map<String, int>, k: String): int {
      if m.contains(k) {
        let v = m.get(k);
        return v ?? 0;
      }
      return 0;
    }
    """
    checker = _check_code(code)
    self.assertEqual(len(checker.errors), 0)
    self.assertTrue(
        any("if let v ?=" in w for w in checker.warnings),
        f"Expected warning, got: {checker.warnings}",
    )

  def test_if_contains_compound_assign_and_field_mutation_warns_var(self):
    code = """
    struct Box {
      var val: int;
    }
    func inc(var m: Map<String, int>, k: String) {
      if m.contains(k) {
        m[k] += 1;
      }
    }
    func set_field(var m: Map<String, Box>, k: String) {
      if m.contains(k) {
        m[k].val = 10;
      }
    }
    """
    checker = _check_code(code)
    self.assertEqual(len(checker.errors), 0)
    var_warnings = [w for w in checker.warnings if "if var v ?=" in w]
    self.assertEqual(len(var_warnings), 2)

  def test_if_contains_other_key_mutation_suppresses_warning(self):
    code = """
    func f(var m: Map<String, int>, k: String) {
      if m.contains(k) {
        let x = m[k];
        m["other"] = x + 1;
      }
    }
    """
    checker = _check_code(code)
    self.assertEqual(len(checker.errors), 0)
    self.assertEqual(checker.warnings, [])

  def test_if_contains_nested_lambda_not_counted_as_access(self):
    code = """
    func f(m: Map<String, int>, k: String) {
      if m.contains(k) {
        let cb = () -> int {
          return m[k];
        };
      }
    }
    """
    checker = _check_code(code)
    self.assertEqual(len(checker.errors), 0)
    self.assertEqual(checker.warnings, [])

  def test_if_contains_immutable_map_with_in_place_mutation_skips_warning(self):
    code = """
    struct Counter {
      var n: int;
    }
    impl Counter {
      var func inc() {
        self.n += 1;
      }
    }
    func make_map(): Map<String, Counter> {
      return {"a": Counter { n = 1 }};
    }
    func f(k: String) {
      let m = make_map();
      if m.contains(k) {
        let c = m[k];
      }
    }
    """
    checker = _check_code(code)
    self.assertEqual(len(checker.errors), 0)
    self.assertTrue(any("if let v ?=" in w for w in checker.warnings))


if __name__ == "__main__":
  unittest.main()
