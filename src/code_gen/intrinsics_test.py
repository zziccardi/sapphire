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
    self.assertTrue(is_builtin_module("std.os"))
    self.assertTrue(is_builtin_module("std.fs"))
    self.assertTrue(is_builtin_module("std.time"))
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

  def test_range_python_named_and_positional_variants(self):
    from src.parser.ast import ArgumentNode, LiteralNode
    from src.code_gen.python_transpiler import PythonTranspiler

    def emit_range(args):
      t = PythonTranspiler()
      call = CallNode(callee=IdentifierNode("range"), arguments=args)
      self.assertTrue(IntrinsicRegistry.try_emit("python", t, call))
      return t.get_output()

    # 1 positional arg: range(10)
    self.assertEqual(
        emit_range([ArgumentNode(None, LiteralNode(10, "int"))]),
        "range(10)",
    )
    # 1 positional + named stop: range(1, stop=10)
    self.assertEqual(
        emit_range([
            ArgumentNode(None, LiteralNode(1, "int")),
            ArgumentNode("stop", LiteralNode(10, "int")),
        ]),
        "range(1, 10)",
    )
    # Named start and stop: range(start=2, stop=8)
    self.assertEqual(
        emit_range([
            ArgumentNode("start", LiteralNode(2, "int")),
            ArgumentNode("stop", LiteralNode(8, "int")),
        ]),
        "range(2, 8)",
    )
    # Named stop and step without start (defaults start to 0): range(stop=10, step=2)
    self.assertEqual(
        emit_range([
            ArgumentNode("stop", LiteralNode(10, "int")),
            ArgumentNode("step", LiteralNode(2, "int")),
        ]),
        "range(0, 10, 2)",
    )
    # 2 positional args + named step: range(1, 10, step=3)
    self.assertEqual(
        emit_range([
            ArgumentNode(None, LiteralNode(1, "int")),
            ArgumentNode(None, LiteralNode(10, "int")),
            ArgumentNode("step", LiteralNode(3, "int")),
        ]),
        "range(1, 10, 3)",
    )
    # 3 positional args + 1 named arg so len(node.arguments) == 4 and len(pos_args) == 3
    self.assertEqual(
        emit_range([
            ArgumentNode(None, LiteralNode(0, "int")),
            ArgumentNode(None, LiteralNode(10, "int")),
            ArgumentNode(None, LiteralNode(2, "int")),
            ArgumentNode("start", LiteralNode(0, "int")),
        ]),
        "range(0, 10, 2)",
    )


if __name__ == "__main__":
  unittest.main()
