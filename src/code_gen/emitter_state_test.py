"""Unit tests for EmitterState, OutputBuffer, and scoped buffer management."""

import unittest

from src.code_gen.emitter_state import EmitterState, OutputBuffer
from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.python_transpiler import PythonTranspiler
from src.parser.ast import IdentifierNode


class TestEmitterStateAndBuffers(unittest.TestCase):
  """Tests OutputBuffer, EmitterState, and BaseTranspiler scoped buffers."""

  def test_output_buffer_emit_indent_dedent(self):
    buf = OutputBuffer()
    self.assertEqual(buf.indent_level, 0)
    buf.dedent()
    self.assertEqual(buf.indent_level, 0)
    buf.indent()
    buf.indent()
    self.assertEqual(buf.indent_level, 2)
    buf.dedent()
    self.assertEqual(buf.indent_level, 1)
    buf.emit("a")
    buf.emit("b")
    self.assertEqual(buf.get_output(), "ab")

  def test_emitter_state_defaults_are_isolated_per_instance(self):
    s1 = EmitterState(test_mode=True)
    s2 = EmitterState()
    s1.moved_vars.add("x")
    s1.unwrap_writebacks["k"] = ("attr", "obj", "f")
    self.assertTrue(s1.test_mode)
    self.assertFalse(s2.test_mode)
    self.assertNotIn("x", s2.moved_vars)
    self.assertEqual(s2.unwrap_writebacks, {})
    self.assertIn("Arena", s2.structs_with_destructor)

  def test_push_pop_and_scoped_buffer_isolation_python(self):
    pt = PythonTranspiler()
    self.assertTrue(pt.is_root_buffer)
    pt.emit("root_a")
    pt.newline()
    self.assertEqual(pt._py_lineno, 2)

    pt.push_buffer()
    self.assertFalse(pt.is_root_buffer)
    pt.emit("nested")
    pt.newline()
    # Captured buffer newlines must not advance root line numbering
    self.assertEqual(pt._py_lineno, 2)
    captured = pt.pop_buffer()
    self.assertEqual(captured, "nested\n")
    self.assertTrue(pt.is_root_buffer)
    self.assertEqual(pt.get_output(), "root_a\n")

    with self.assertRaises(RuntimeError):
      pt.pop_buffer()

  def test_scoped_buffer_restores_on_exception(self):
    lt = LuaTranspiler()
    lt.emit("prefix")
    with self.assertRaises(ValueError):
      with lt.scoped_buffer():
        lt.emit("partial")
        raise ValueError("boom")
    self.assertTrue(lt.is_root_buffer)
    self.assertEqual(lt.get_output(), "prefix")

  def test_capture_expr_shares_state_across_backends(self):
    pt = PythonTranspiler()
    pt._identifier_map["x"] = "_x_1"
    self.assertEqual(pt.capture_expr(IdentifierNode("x")), "_x_1")

    lt = LuaTranspiler()
    lt._identifier_map["y"] = "_y_1"
    self.assertEqual(lt.capture_expr(IdentifierNode("y")), "_y_1")


if __name__ == "__main__":
  unittest.main()
