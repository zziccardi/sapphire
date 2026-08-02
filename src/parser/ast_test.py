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

  def test_array_type_node(self):
    try:
      from parser.ast import ArrayTypeNode
    except ModuleNotFoundError:
      from src.parser.ast import ArrayTypeNode
    node = ArrayTypeNode(BasicTypeNode("int"))
    self.assertEqual(node.element_type.name, "int")
    node_dict = node.to_dict()
    self.assertEqual(node_dict["node_type"], "ArrayTypeNode")
    self.assertEqual(node_dict["element_type"]["name"], "int")

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

  def test_positioning_keys_skipped(self):
    """Verifies that positioning attributes are skipped in to_dict serialization."""
    node = BasicTypeNode("int")
    node.start_line = 12
    node.start_column = 34
    node_dict = node.to_dict()
    self.assertNotIn("start_line", node_dict)
    self.assertNotIn("start_column", node_dict)

  def test_node_properties_and_backward_compatibility_to_dict(self):
    """Verifies backward compatible properties and to_dict methods on AST nodes."""
    try:
      from parser.ast import (
          ASTNode, FunctionTypeNode, FuncDeclNode, TraitMemberNode, VarDeclNode,
          AssignmentNode, ReturnNode, IdentifierNode, LiteralNode, BasicTypeNode,
          ExprStmtNode
      )
    except ModuleNotFoundError:
      from src.parser.ast import (
          ASTNode, FunctionTypeNode, FuncDeclNode, TraitMemberNode, VarDeclNode,
          AssignmentNode, ReturnNode, IdentifierNode, LiteralNode, BasicTypeNode,
          ExprStmtNode
      )

    fn_type = FunctionTypeNode([BasicTypeNode("int")], BasicTypeNode("float"))
    self.assertEqual(fn_type.return_type.name, "float")

    func_decl = FuncDeclNode("f", [], return_type=BasicTypeNode("int"))
    self.assertEqual(func_decl.return_type.name, "int")

    func_decl_none = FuncDeclNode("f", [])
    self.assertIsNone(func_decl_none.return_type)

    trait_mem = TraitMemberNode("m", [], return_type=BasicTypeNode("int"))
    self.assertEqual(trait_mem.return_type.name, "int")

    trait_mem_none = TraitMemberNode("m", [])
    self.assertIsNone(trait_mem_none.return_type)

    var_node = VarDeclNode(False, name="x", val_type=BasicTypeNode("int"))
    self.assertEqual(var_node.name, "x")
    self.assertEqual(var_node.val_type.name, "int")
    self.assertIsNone(var_node.expr)

    var_empty = VarDeclNode(False)
    self.assertEqual(var_empty.name, "")

    assign_node = AssignmentNode(IdentifierNode("x"), "=", LiteralNode(5, "int"))
    self.assertEqual(assign_node.target.name, "x")
    self.assertEqual(assign_node.expr.value, 5)
    assign_dict = assign_node.to_dict()
    self.assertEqual(assign_dict["target"]["name"], "x")

    assign_empty = AssignmentNode([], "=", [])
    self.assertIsNone(assign_empty.to_dict()["target"])
    self.assertIsNone(assign_empty.to_dict()["expr"])

    ret_node = ReturnNode(LiteralNode(10, "int"))
    self.assertEqual(ret_node.expr.value, 10)
    ret_dict = ret_node.to_dict()
    self.assertEqual(ret_dict["expr"]["value"], 10)

    ret_empty = ReturnNode()
    self.assertIsNone(ret_empty.expr)
    self.assertIsNone(ret_empty.to_dict()["expr"])

    class DummySingleReturnTypeNode(ASTNode):
      return_type = BasicTypeNode("int")

    trait_single_type = TraitMemberNode("m", [], return_types=BasicTypeNode("int"))
    self.assertEqual(trait_single_type.return_types[0].name, "int")

    assign_target_kw = AssignmentNode(targets=None, op="=", exprs=None, target=IdentifierNode("x"), expr=LiteralNode(1, "int"))
    self.assertEqual(assign_target_kw.target.name, "x")
    self.assertEqual(assign_target_kw.expr.value, 1)

    ret_expr_kw = ReturnNode(exprs=None, expr=LiteralNode(1, "int"))
    self.assertEqual(ret_expr_kw.expr.value, 1)

    expr_stmt = ExprStmtNode(LiteralNode(1, "int"))
    self.assertEqual(expr_stmt.expr.value, 1)

  def test_struct_decl_node_parent_name(self):
    """Verifies StructDeclNode parent_name and parent_names initialization and property setter."""
    try:
      from parser.ast import StructDeclNode
    except ModuleNotFoundError:
      from src.parser.ast import StructDeclNode

    node1 = StructDeclNode("Child", parent_name="Parent1")
    self.assertEqual(node1.parent_name, "Parent1")
    self.assertEqual(node1.parent_names, ["Parent1"])

    node2 = StructDeclNode("Child", parent_names="Parent2")
    self.assertEqual(node2.parent_name, "Parent2")

    node3 = StructDeclNode("Child")
    self.assertIsNone(node3.parent_name)

    node3.parent_name = "Parent3"
    self.assertEqual(node3.parent_names, ["Parent3"])
    self.assertEqual(node3.parent_name, "Parent3")

    node3.parent_name = None
    self.assertEqual(node3.parent_names, [])
    self.assertIsNone(node3.parent_name)


if __name__ == "__main__":
  unittest.main()
