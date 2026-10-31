"""Unit tests for SemanticContext in Sapphire."""

import unittest
from src.parser.ast import IdentifierNode, CallNode
from src.semantics.semantic_context import SemanticContext
from src.semantics.symbol_table import SymbolTable, PrimitiveType


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


if __name__ == "__main__":
  unittest.main()
