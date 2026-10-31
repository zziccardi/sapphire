"""Unit tests for IntrinsicRegistry in src/code_gen/intrinsics.py."""

import unittest
from unittest.mock import MagicMock
from src.parser.ast import CallNode, IdentifierNode, MemberAccessNode
from src.code_gen.intrinsics import IntrinsicRegistry, is_builtin_module


class TestIntrinsicRegistry(unittest.TestCase):
  """Unit tests for intrinsic registry and built-in module detection."""

  def test_is_builtin_module(self):
    self.assertTrue(is_builtin_module("std.math"))
    self.assertTrue(is_builtin_module("std.math.special"))
    self.assertTrue(is_builtin_module("std.testing"))
    self.assertFalse(is_builtin_module("entities.character"))
    self.assertFalse(is_builtin_module("custom_math"))

  def test_unhandled_call_returns_false(self):
    mock_transpiler = MagicMock()
    custom_call = CallNode(callee=IdentifierNode("custom_function"), arguments=[])
    self.assertFalse(IntrinsicRegistry.try_emit("python", mock_transpiler, custom_call))
    self.assertFalse(IntrinsicRegistry.try_emit("lua", mock_transpiler, custom_call))

  def test_string_size_dispatch(self):
    mock_transpiler = MagicMock()
    member = MemberAccessNode(IdentifierNode("str_var"), "size", False)
    member.is_string_method = True
    call = CallNode(callee=member, arguments=[])

    handled_py = IntrinsicRegistry.try_emit("python", mock_transpiler, call)
    self.assertTrue(handled_py)
    mock_transpiler.emit.assert_any_call("len(")

    mock_transpiler.reset_mock()
    handled_lua = IntrinsicRegistry.try_emit("lua", mock_transpiler, call)
    self.assertTrue(handled_lua)
    mock_transpiler.emit.assert_any_call("(#")


if __name__ == "__main__":
  unittest.main()
