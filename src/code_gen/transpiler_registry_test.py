"""Unit tests for TranspilerRegistry in src/code_gen/transpiler_registry.py."""

import unittest
from src.code_gen.transpiler_registry import TranspilerRegistry, TranspilerTarget
from src.common.errors import SapphireTranspileError
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.llvm_transpiler import LLVMTranspiler


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
