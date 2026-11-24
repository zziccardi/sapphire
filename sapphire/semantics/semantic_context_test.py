"""Unit tests for SemanticContext in Sapphire."""

import unittest

from sapphire.parser.ast import IdentifierNode
from sapphire.semantics.semantic_context import SemanticContext
from sapphire.semantics.symbol_table import PrimitiveType, SymbolTable


class TestSemanticContext(unittest.TestCase):
  """Tests recording and querying types and state in SemanticContext."""

  def test_context_initialization(self):
    st = SymbolTable()
    ctx = SemanticContext(symbol_table=st)
    self.assertIs(ctx.symbol_table, st)
    self.assertEqual(len(ctx.node_types), 0)
    self.assertEqual(len(ctx.call_resolutions), 0)
    self.assertEqual(len(ctx.errors), 0)

  def test_record_and_get_type(self):
    ctx = SemanticContext()
    ident = IdentifierNode("my_var")
    typ = PrimitiveType("int")

    self.assertIsNone(ctx.get_type(ident))
    self.assertIsNone(ctx.get_type(None))

    ctx.record_type(ident, typ)
    self.assertEqual(ctx.get_type(ident), typ)

    # None node or type ignored
    ctx.record_type(None, typ)
    ctx.record_type(ident, None)
    self.assertEqual(ctx.get_type(ident), typ)

  def test_side_tables_call_closure_and_match(self):
    from sapphire.parser.ast import (
      BlockNode,
      CallNode,
      LambdaNode,
      MatchExprNode,
    )
    from sapphire.semantics.semantic_context import (
      CallResolution,
      ClosureCaptures,
    )

    ctx = SemanticContext()
    call = CallNode(IdentifierNode("f"), [])
    res = CallResolution(kind="array_method", method_name="push")
    self.assertIsNone(ctx.get_call(None))
    self.assertIsNone(ctx.get_call(call))
    ctx.record_call(call, res)
    self.assertEqual(ctx.get_call(call), res)

    lam = LambdaNode([], None, BlockNode([]))
    caps = ClosureCaptures(read={"a"}, mutated={"b"})
    self.assertIsNone(ctx.get_closure_captures(None))
    self.assertIsNone(ctx.get_closure_captures(lam))
    ctx.record_closure_captures(lam, caps)
    self.assertEqual(ctx.get_closure_captures(lam), caps)

    match_node = MatchExprNode(IdentifierNode("x"), [])
    self.assertFalse(ctx.is_exhaustive_match(None))
    self.assertFalse(ctx.is_exhaustive_match(match_node))
    ctx.mark_exhaustive_match(match_node)
    self.assertTrue(ctx.is_exhaustive_match(match_node))


if __name__ == "__main__":
  unittest.main()
