"""Unit tests for Sapphire AST nodes defined in ast.py.

This module verifies that the AST node representations, fields, and recursive
serialization to dictionaries work correctly.
"""

import unittest

try:
  from parser.ast import (
      BasicTypeNode,
      LiteralNode,
      VarDeclNode,
      BinaryOpNode,
      IdentifierNode,
  )
except ModuleNotFoundError:
  from src.parser.ast import (
      BasicTypeNode,
      LiteralNode,
      VarDeclNode,
      BinaryOpNode,
      IdentifierNode,
  )


class TestASTNodes(unittest.TestCase):
  """Unit tests for AST node creations and representations."""

  def test_basic_type_node(self):
    """Verifies BasicTypeNode creation and conversion to dictionary."""
    node = BasicTypeNode("int")
    self.assertEqual(node.name, "int")
    
    node_dict = node.to_dict()
    self.assertEqual(node_dict["node_type"], "BasicTypeNode")
    self.assertEqual(node_dict["name"], "int")

  def test_literal_node(self):
    """Verifies LiteralNode creation and conversion to dictionary."""
    node = LiteralNode(42, "int")
    self.assertEqual(node.value, 42)
    self.assertEqual(node.lit_type, "int")

    node_dict = node.to_dict()
    self.assertEqual(node_dict["node_type"], "LiteralNode")
    self.assertEqual(node_dict["value"], 42)
    self.assertEqual(node_dict["lit_type"], "int")

  def test_recursive_serialization(self):
    """Verifies nested ASTNode structures serialize recursively."""
    type_node = BasicTypeNode("int")
    lit_node = LiteralNode(10, "int")
    decl_node = VarDeclNode(
        is_mutable=False, name="x", val_type=type_node, expr=lit_node
    )

    node_dict = decl_node.to_dict()
    self.assertEqual(node_dict["node_type"], "VarDeclNode")
    self.assertFalse(node_dict["is_mutable"])
    self.assertEqual(node_dict["name"], "x")
    
    # Check type node dict
    self.assertEqual(node_dict["val_type"]["node_type"], "BasicTypeNode")
    self.assertEqual(node_dict["val_type"]["name"], "int")

    # Check expression node dict
    self.assertEqual(node_dict["expr"]["node_type"], "LiteralNode")
    self.assertEqual(node_dict["expr"]["value"], 10)
    self.assertEqual(node_dict["expr"]["lit_type"], "int")

  def test_binary_op_node(self):
    """Verifies BinaryOpNode structure and serialization."""
    left = IdentifierNode("a")
    right = LiteralNode(5, "int")
    op_node = BinaryOpNode(left=left, op="+", right=right)

    node_dict = op_node.to_dict()
    self.assertEqual(node_dict["node_type"], "BinaryOpNode")
    self.assertEqual(node_dict["op"], "+")
    self.assertEqual(node_dict["left"]["name"], "a")
    self.assertEqual(node_dict["right"]["value"], 5)

  def test_list_serialization_and_repr(self):
    """Verifies that lists containing AST nodes and non-AST elements serialize, and repr works."""
    try:
      from parser.ast import ProgramNode
    except ModuleNotFoundError:
      from src.parser.ast import ProgramNode

    node = ProgramNode(declarations=[BasicTypeNode("int"), "not-an-ast-node"])
    node_dict = node.to_dict()
    self.assertEqual(node_dict["node_type"], "ProgramNode")
    self.assertEqual(node_dict["declarations"][0]["name"], "int")
    self.assertEqual(node_dict["declarations"][1], "not-an-ast-node")
    self.assertTrue(len(repr(node)) > 0)


if __name__ == "__main__":
  unittest.main()
