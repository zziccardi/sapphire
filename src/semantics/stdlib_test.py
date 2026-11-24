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
    # NaN sleep must return immediately
    py_time.sleep(float("nan"))

  def _run_lua(self, script: str) -> str:
    import shutil
    import subprocess
    lua_bin = shutil.which("lua") or shutil.which("luajit") or shutil.which("lua5.1")
    self.assertIsNotNone(lua_bin)
    full_script = f'package.path = "{_LIB_DIR}/?.lua;" .. package.path\n' + script
    proc = subprocess.run(
        [lua_bin, "-"],
        input=full_script,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
      self.fail(f"Lua script failed:\n{proc.stderr}\nScript:\n{script}")
    return proc.stdout.strip()

  def test_testing_module_fixes_python_and_lua(self):
    """Verifies NaN almost_eq failure, Lua standalone TestContext.init, is_none, and deep_eq."""
    import std.testing as py_testing
    ctx = py_testing.TestContext("nan_check")
    py_testing.set_active_context(ctx)
    with self.assertRaises(py_testing.TestFailure):
      py_testing.assert_almost_eq(float("nan"), 0.0)
    py_testing.expect_almost_eq(float("nan"), 0.0)
    self.assertEqual(len(ctx.failures), 2)

    out = self._run_lua("""
      local testing = require("std.testing")
      -- Standalone context creation uses testing.TestContext.init without global error
      testing.set_active_context(nil)
      local ctx = testing.get_active_context()
      assert(ctx ~= nil and ctx.name == "standalone")
      assert(testing.TestContext.new == nil)
      assert(testing.TestCase.new == nil)

      -- Tables are NOT none
      testing.assert_not_none({1, 2})
      testing.assert_not_none({})
      testing.assert_none(nil)

      -- Deep structural equality on arrays and maps
      testing.assert_eq({1, {2, 3}}, {1, {2, 3}})
      testing.assert_ne({1, 2}, {1, 3})
      testing.expect_eq({a = 1, b = {c = 2}}, {a = 1, b = {c = 2}})

      -- NaN must fail assert_almost_eq and expect_almost_eq
      local nan = 0 / 0
      local ok = pcall(testing.assert_almost_eq, nan, 0.0)
      assert(not ok, "assert_almost_eq(nan, 0.0) must fail")
      local before = #ctx.failures
      testing.expect_almost_eq(nan, 0.0)
      assert(#ctx.failures == before + 1, "expect_almost_eq(nan, 0.0) must record failure")
      print("OK")
    """)
    self.assertEqual(out, "OK")

  def test_utf8_validation_and_offset_parity(self):
    """Verifies UTF-8 offset snapping/continuation rejection and _pure_utf8.len RFC 3629 validation."""
    import std.utf8 as py_utf8
    self.assertEqual(py_utf8.offset("café", -1), 4)
    self.assertEqual(py_utf8.offset("café", 0, 5), 4)
    self.assertIsNone(py_utf8.offset("café", 1, 5))

    out = self._run_lua("""
      local u = require("std.utf8")
      local p = u._pure_utf8
      local cafe = "caf" .. string.char(0xC3, 0xA9)
      -- Valid ASCII and multi-byte
      assert(p.len(cafe) == 4)
      -- Reject overlong 2/3/4-byte sequences
      assert(p.len(string.char(0xC0, 0xAF)) == nil)
      assert(p.len(string.char(0xE0, 0x80, 0xAF)) == nil)
      assert(p.len(string.char(0xF0, 0x80, 0x80, 0xAF)) == nil)
      -- Reject UTF-16 surrogates (U+D800)
      assert(p.len(string.char(0xED, 0xA0, 0x80)) == nil)
      -- Reject > U+10FFFF and invalid lead bytes
      assert(p.len(string.char(0xF4, 0x90, 0x80, 0x80)) == nil)
      assert(p.len(string.char(0xF5, 0x80, 0x80, 0x80)) == nil)
      assert(p.len(string.char(0xFF)) == nil)
      -- pcall-safe offset on continuation byte returns nil (no crash)
      assert(u.offset(cafe, 0, 5) == 4)
      assert(u.offset(cafe, 1, 5) == nil)
      assert(u.offset(cafe, -1) == 4)
      print("OK")
    """)
    self.assertEqual(out, "OK")

  def test_time_and_fs_lua_edge_cases(self):
    """Verifies Lua time.sleep(NaN), time.now() epoch with Love2D mock, and fs.remove_file on directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      out = self._run_lua(f"""
        local time_mod = require("std.time")
        local fs_mod = require("std.fs")
        -- NaN sleep returns immediately
        time_mod.sleep(0 / 0)
        -- Mock Love2D uptime timer: time.now() must still return Unix epoch (> 1.5e9)
        _G.love = {{ timer = {{ getTime = function() return 1.25 end }} }}
        local now = time_mod.now()
        assert(now > 1500000000, "Expected epoch timestamp, got " .. tostring(now))
        -- fs.remove_file must refuse to remove a directory
        local removed = fs_mod.remove_file("{tmp_dir}")
        assert(removed == false, "remove_file must return false on directory")
        print("OK")
      """)
      self.assertEqual(out, "OK")
      self.assertTrue(os.path.isdir(tmp_dir))

  def test_love2d_bindings_type_checking(self):
    """Verifies updated Love2D graphics and LoveEngine.joystick bindings."""
    from src.common.errors import SapphireTypeError

    valid_code = """
    import lib.love2d.love2d as love2d;
    import lib.love2d.enums as enums;

    func check() {
      let name = love2d.love.joystick.getName();
      let c = love2d.love.graphics.newCanvas();
      let c2 = love2d.love.graphics.newCanvas(320.0, 240.0);
      love2d.love.graphics.printf("Hello", 0.0, 0.0, 200.0, enums.AlignMode.Center);
      let img = love2d.love.graphics.newImage("sprite.png");
      let q = love2d.love.graphics.newQuad(0.0, 0.0, 16.0, 16.0, 64.0, 64.0);
      love2d.love.graphics.drawImage(img, q, 10.0, 20.0);
      love2d.love.graphics.drawImageAt(img, 10.0, 20.0);
    }
    """
    ast = self._parse_and_check(valid_code)
    self.assertIsNotNone(ast)

    # Nonexistent Image.draw must be rejected
    bad_img_draw = """
    import lib.love2d.love2d as love2d;
    func check() {
      let img = love2d.love.graphics.newImage("sprite.png");
      img.draw(1.0, 2.0);
    }
    """
    with self.assertRaises(SapphireTypeError):
      self._parse_and_check(bad_img_draw)

    # drawImage requires non-optional Quad (not none)
    bad_quad = """
    import lib.love2d.love2d as love2d;
    func check() {
      let img = love2d.love.graphics.newImage("sprite.png");
      love2d.love.graphics.drawImage(img, none, 0.0, 0.0);
    }
    """
    with self.assertRaises(SapphireTypeError):
      self._parse_and_check(bad_quad)

  def test_utf8_python_edge_cases(self):
    """Verifies boundary and error branches in lib/std/utf8.py."""
    import lib.std.utf8 as py_utf8

    # Unpaired surrogate cannot be UTF-8 encoded -> None
    self.assertIsNone(py_utf8.size("\ud800"))
    self.assertEqual(py_utf8.size("café"), 4)

    # Negative start index and out-of-bounds index
    self.assertEqual(py_utf8.offset("café", 0, -1), 4)
    self.assertIsNone(py_utf8.offset("abc", 1, 99))
    self.assertIsNone(py_utf8.offset("abc", 1, -99))

    # Forward and backward step past string boundaries
    self.assertIsNone(py_utf8.offset("ab", 5, 1))
    self.assertIsNone(py_utf8.offset("ab", -5, 1))

    # Empty string sub
    self.assertEqual(py_utf8.sub("", 0, 1), "")
    self.assertEqual(py_utf8.sub("café", 1, 4), "afé")

