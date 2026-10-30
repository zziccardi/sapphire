"""Unit tests for StructLayoutPass in src/semantics/struct_layout_pass.py."""

import unittest
from src.parser.ast import ProgramNode, StructDeclNode, StructFieldNode, BasicTypeNode
from src.semantics.struct_layout_pass import StructLayoutPass
from src.semantics.type_checker import TypeChecker


class TestStructLayoutPass(unittest.TestCase):
  """Unit tests for struct layout inheritance and circular detection."""

  def test_circular_inheritance_detection(self):
    checker = TypeChecker()
    s_a = StructDeclNode("A", parent_names=["B"])
    s_b = StructDeclNode("B", parent_names=["A"])
    prog = ProgramNode(declarations=[s_a, s_b])

    # Declare them first
    checker._declare_globals(prog)
    StructLayoutPass.resolve_struct_layouts(checker, prog)

    self.assertTrue(any("Circular inheritance detected" in err for err in checker.errors))

  def test_parent_struct_not_found(self):
    checker = TypeChecker()
    s_a = StructDeclNode("A", parent_names=["MissingParent"])
    prog = ProgramNode(declarations=[s_a])

    checker._declare_globals(prog)
    StructLayoutPass.resolve_struct_layouts(checker, prog)

    self.assertTrue(any("Parent struct 'MissingParent' not found" in err for err in checker.errors))


if __name__ == "__main__":
  unittest.main()
