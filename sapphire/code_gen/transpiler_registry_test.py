"""Unit tests for TranspilerRegistry in src/code_gen/transpiler_registry.py."""

import unittest

from sapphire.code_gen.llvm_transpiler import LLVMTranspiler
from sapphire.code_gen.lua_transpiler import LuaTranspiler
from sapphire.code_gen.python_transpiler import PythonTranspiler
from sapphire.code_gen.transpiler_registry import (
  TranspilerRegistry,
)
from sapphire.common.errors import SapphireTranspileError


class TestTranspilerRegistry(unittest.TestCase):
  """Unit tests verifying target registration, retrieval, and error handling."""

  def test_registered_targets(self):
    py_target = TranspilerRegistry.get("python")
    self.assertEqual(py_target.display_name, "Python")
    self.assertEqual(py_target.default_extension, ".py")
    self.assertEqual(py_target.transpiler_cls, PythonTranspiler)

    lua_target = TranspilerRegistry.get("lua5.1")
    self.assertEqual(lua_target.display_name, "Lua 5.1")
    self.assertEqual(lua_target.default_extension, ".lua")
    self.assertEqual(lua_target.transpiler_cls, LuaTranspiler)

    llvm_target = TranspilerRegistry.get("llvmir")
    self.assertEqual(llvm_target.display_name, "LLVM IR")
    self.assertEqual(llvm_target.default_extension, ".ll")
    self.assertEqual(llvm_target.transpiler_cls, LLVMTranspiler)

  def test_unsupported_target_raises_error(self):
    with self.assertRaises(SapphireTranspileError) as ctx:
      TranspilerRegistry.get("unknown_target")
    self.assertIn("Unsupported compilation target 'unknown_target'", str(ctx.exception))

  def test_list_targets(self):
    targets = TranspilerRegistry.list_targets()
    self.assertIn("python", targets)
    self.assertIn("lua", targets)
    self.assertIn("llvm", targets)

  def test_create_isolated_registry(self):
    reg = TranspilerRegistry.create_isolated()
    self.assertEqual(reg.list_targets(), [])

    @reg.register("dummy", "Dummy", ".dum")
    class DummyTranspiler:
      pass

    self.assertEqual(reg.get("dummy").transpiler_cls, DummyTranspiler)
    self.assertEqual(reg.list_targets(), ["dummy"])
    with self.assertRaises(SapphireTranspileError):
      reg.get("python")
    with self.assertRaises(SapphireTranspileError):
      TranspilerRegistry.get("dummy")

    copied = TranspilerRegistry.create_isolated(copy_defaults=True)
    self.assertIn("python", copied.list_targets())

  def test_scoped_context_manager_restores_global_registry(self):
    before = TranspilerRegistry.list_targets()
    with TranspilerRegistry.scoped() as scoped_reg:
      @scoped_reg.register(["temp_a", "temp_b"], "Temp", ".tmp")
      class TempTranspiler:
        pass

      self.assertEqual(scoped_reg.get("temp_a").transpiler_cls, TempTranspiler)
      self.assertIn("temp_b", scoped_reg.list_targets())

    self.assertEqual(TranspilerRegistry.list_targets(), before)

    with TranspilerRegistry.scoped(clear=True) as cleared_reg:
      self.assertEqual(cleared_reg.list_targets(), [])

    self.assertEqual(TranspilerRegistry.list_targets(), before)
