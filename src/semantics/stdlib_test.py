"""Unit tests for std.os, std.fs, and std.time standard library modules."""

import os
import sys
import tempfile
import unittest
from antlr4 import CommonTokenStream, InputStream

from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.python_transpiler import PythonTranspiler
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import TypeChecker

_LIB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "lib")
)
if _LIB_DIR not in sys.path:
  sys.path.insert(0, _LIB_DIR)


class TestStdlibModules(unittest.TestCase):
  """Suite verifying type checking, codegen, and runtime for stdlib modules."""

  def _parse_and_check(self, code: str):
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    tree = parser.program()
    if parser.getNumberOfSyntaxErrors() > 0:
      raise SyntaxError(f"Syntax error while parsing code:\n{code}")
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    return ast

  def test_os_module_transpilation_and_runtime(self):
    code = """
    import std.os as os;

    func main() {
      let a = os.args();
      os.set_env("SP_TEST_KEY", "sp_val");
      let val = os.get_env("SP_TEST_KEY");
      let missing = os.get_env("SP_TEST_MISSING_KEY");
    }
    """
    ast = self._parse_and_check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("import std.os as os", py_code)

    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn('local os = require("std.os")', lua_code)

    import std.os as py_os
    self.assertIsInstance(py_os.args(), list)
    py_os.set_env("SP_UNIT_KEY", "unit_val")
    self.assertEqual(py_os.get_env("SP_UNIT_KEY"), "unit_val")
    self.assertIsNone(py_os.get_env("SP_NONEXISTENT_KEY_XYZ"))
    with self.assertRaises(SystemExit):
      py_os.exit(42)

  def test_fs_module_transpilation_and_runtime(self):
    code = """
    import std.fs as fs;

    func main() {
      let ok = fs.write_file("dummy.txt", "content");
      let c = fs.read_file("dummy.txt");
      let e = fs.exists("dummy.txt");
      let r = fs.remove_file("dummy.txt");
    }
    """
    ast = self._parse_and_check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("import std.fs as fs", py_code)

    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn('local fs = require("std.fs")', lua_code)

    import std.fs as py_fs
    with tempfile.TemporaryDirectory() as tmp_dir:
      tmp_file = os.path.join(tmp_dir, "test.txt")
      self.assertFalse(py_fs.exists(tmp_file))
      self.assertIsNone(py_fs.read_file(tmp_file))
      self.assertTrue(py_fs.write_file(tmp_file, "hello"))
      self.assertTrue(py_fs.exists(tmp_file))
      self.assertEqual(py_fs.read_file(tmp_file), "hello")
      self.assertTrue(py_fs.remove_file(tmp_file))
      self.assertFalse(py_fs.exists(tmp_file))

    # Error handling branch coverage
    bad_path = "/nonexistent_dir_xyz/test.txt"
    self.assertFalse(py_fs.write_file(bad_path, "data"))
    self.assertFalse(py_fs.remove_file(bad_path))

  def test_time_module_transpilation_and_runtime(self):
    code = """
    import std.time as time;

    func main() {
      let t = time.now();
      time.sleep(0.001);
    }
    """
    ast = self._parse_and_check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("import std.time as time", py_code)

    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn('local time = require("std.time")', lua_code)

    import std.time as py_time
    t1 = py_time.now()
    self.assertGreater(t1, 0.0)
    py_time.sleep(0.001)
    t2 = py_time.now()
    self.assertGreaterEqual(t2, t1)
    # Test zero sleep branch
    py_time.sleep(0.0)
