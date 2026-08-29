"""Unit tests for base_transpiler.py helper functions."""

import unittest
from src.parser.ast import BasicTypeNode, OptionalTypeNode, FuncDeclNode, BlockNode
from src.code_gen.base_transpiler import get_default_value_for_type_node, is_coroutine_func


class TestBaseTranspilerHelpers(unittest.TestCase):
  """Unit tests for helper functions in base_transpiler.py."""

  def test_get_default_value_for_type_node(self):
    """Verifies default ASTNode generation for various types."""
    self.assertIsNone(get_default_value_for_type_node(None))

    opt_node = OptionalTypeNode(BasicTypeNode("int"))
    default_opt = get_default_value_for_type_node(opt_node)
    self.assertIsNotNone(default_opt)
    self.assertEqual(default_opt.value, "none")

    int_node = BasicTypeNode("int")
    default_int = get_default_value_for_type_node(int_node)
    self.assertIsNotNone(default_int)
    self.assertEqual(default_int.value, 0)

    float_node = BasicTypeNode("float")
    default_float = get_default_value_for_type_node(float_node)
    self.assertIsNotNone(default_float)
    self.assertEqual(default_float.value, 0.0)

    bool_node = BasicTypeNode("bool")
    default_bool = get_default_value_for_type_node(bool_node)
    self.assertIsNotNone(default_bool)
    self.assertEqual(default_bool.value, False)

    other_node = BasicTypeNode("String")
    self.assertIsNone(get_default_value_for_type_node(other_node))

  def test_is_coroutine_func(self):
    """Verifies is_coroutine_func detection for AST nodes and edge cases."""
    # None node
    self.assertFalse(is_coroutine_func(None))

    # Standard coroutine with return_types list
    coro_func = FuncDeclNode(
        "my_coro",
        [],
        return_types=[BasicTypeNode("Coroutine")],
        body=BlockNode([]),
    )
    self.assertTrue(is_coroutine_func(coro_func))

    # Non-coroutine func
    normal_func = FuncDeclNode(
        "my_func",
        [],
        return_types=[BasicTypeNode("int")],
        body=BlockNode([]),
    )
    self.assertFalse(is_coroutine_func(normal_func))

    # Mock node with return_type attribute (not in return_types)
    class MockReturnSingle:
      def __init__(self):
        self.return_types = None
        self.return_type = BasicTypeNode("Coroutine")

    self.assertTrue(is_coroutine_func(MockReturnSingle()))

    class MockReturnOther:
      def __init__(self):
        self.return_types = None
        self.return_type = BasicTypeNode("int")

    self.assertFalse(is_coroutine_func(MockReturnOther()))


if __name__ == "__main__":
  unittest.main()
