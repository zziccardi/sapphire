"""Unit tests for compile-time constant expression evaluation."""

import unittest
from src.parser.ast import (
    ArrayLiteralNode,
    BinaryOpNode,
    CallNode,
    CastExprNode,
    CloneNode,
    IdentifierNode,
    InterpolatedStringNode,
    LambdaNode,
    LiteralNode,
    MapLiteralNode,
    MemberAccessNode,
    MoveNode,
    StructInitializerNode,
    TernaryExprNode,
    UnaryOpNode,
)
from src.semantics.const_eval import is_constant_expression
from src.semantics.symbol_table import (
    EnumSymbol,
    PrimitiveType,
    StructType,
    SymbolTable,
    VariableSymbol,
)


class TestConstEval(unittest.TestCase):
  """Tests for is_constant_expression."""

  def setUp(self):
    self.table = SymbolTable()

  def test_literals(self):
    self.assertTrue(is_constant_expression(LiteralNode(10, "int"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(3.14, "float"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode("hello", "string"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(True, "bool"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(None, "none"), self.table)[0])

  def test_unary_and_binary_ops(self):
    neg = UnaryOpNode("-", LiteralNode(5, "int"))
    self.assertTrue(is_constant_expression(neg, self.table)[0])

    add = BinaryOpNode(LiteralNode(10, "int"), "+", LiteralNode(20, "int"))
    self.assertTrue(is_constant_expression(add, self.table)[0])

    comp = BinaryOpNode(add, ">", LiteralNode(15, "int"))
    self.assertTrue(is_constant_expression(comp, self.table)[0])

  def test_ternary_and_cast(self):
    ternary = TernaryExprNode(LiteralNode(True, "bool"), LiteralNode(1, "int"), LiteralNode(2, "int"))
    self.assertTrue(is_constant_expression(ternary, self.table)[0])

    cast_expr = CastExprNode(LiteralNode(10, "int"), PrimitiveType("float"))
    self.assertTrue(is_constant_expression(cast_expr, self.table)[0])

  def test_collections(self):
    arr = ArrayLiteralNode([LiteralNode(1, "int"), LiteralNode(2, "int")])
    self.assertTrue(is_constant_expression(arr, self.table)[0])

    m = MapLiteralNode([(LiteralNode("a", "string"), LiteralNode(1, "int"))])
    self.assertTrue(is_constant_expression(m, self.table)[0])

  def test_constant_identifiers(self):
    const_sym = VariableSymbol("MAX_SPEED", PrimitiveType("int"), is_mutable=False)
    const_sym.is_constant_expr = True
    self.table.define("MAX_SPEED", const_sym)

    self.assertTrue(is_constant_expression(IdentifierNode("MAX_SPEED"), self.table)[0])

    # Mutable variable cannot be used in a constant expression
    mut_sym = VariableSymbol("counter", PrimitiveType("int"), is_mutable=True)
    self.table.define("counter", mut_sym)
    ok, err = is_constant_expression(IdentifierNode("counter"), self.table)
    self.assertFalse(ok)
    self.assertIn("not a compile-time constant expression", err)

  def test_prohibited_nodes(self):
    call = CallNode(IdentifierNode("foo"), [])
    ok, err = is_constant_expression(call, self.table)
    self.assertFalse(ok)
    self.assertIn("Function calls cannot be evaluated", err)

    clone_node = CloneNode(IdentifierNode("base"))
    ok, err = is_constant_expression(clone_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Dynamic prototype cloning", err)

    move_node = MoveNode("x")
    ok, err = is_constant_expression(move_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Move expressions cannot be used", err)

    lambda_node = LambdaNode([], None, LiteralNode(0, "int"))
    ok, err = is_constant_expression(lambda_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Lambda expressions cannot be used", err)


if __name__ == "__main__":
  unittest.main()
