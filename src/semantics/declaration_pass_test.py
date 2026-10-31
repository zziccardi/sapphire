"""Unit tests for DeclarationPass in src/semantics/declaration_pass.py."""

import unittest
from src.parser.ast import ParameterNode, IdentifierNode
from src.semantics.declaration_pass import DeclarationPass
from src.semantics.type_checker import TypeChecker


class TestDeclarationPass(unittest.TestCase):
  """Unit tests for parameter default validation and declaration helpers."""

  def test_validate_parameter_defaults_valid(self):
    checker = TypeChecker()
    p1 = ParameterNode(False, "a")
    p2 = ParameterNode(False, "b", default_expr=IdentifierNode("x"))
    DeclarationPass.validate_parameter_defaults(checker, [p1, p2])
    self.assertEqual(len(checker.errors), 0)

  def test_validate_parameter_defaults_invalid_ordering(self):
    checker = TypeChecker()
    p1 = ParameterNode(False, "a", default_expr=IdentifierNode("x"))
    p2 = ParameterNode(False, "b")
    DeclarationPass.validate_parameter_defaults(checker, [p1, p2])
    self.assertEqual(len(checker.errors), 1)
    self.assertIn("cannot follow a parameter with a default value", checker.errors[0])


if __name__ == "__main__":
  unittest.main()
