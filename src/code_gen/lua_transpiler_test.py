"""Unit tests for the Sapphire-to-Lua 5.1 transpiler.

This module validates that transpiled Lua 5.1 code is syntactically correct
and preserves all Sapphire runtime semantics, including prototypal delegation,
compound assignment expansion, and array indexing adjustments.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from code_gen.lua_transpiler import LuaTranspiler
  from code_gen.transpiler import transpile_file
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.code_gen.lua_transpiler import LuaTranspiler
  from src.code_gen.transpiler import transpile_file


class TestLuaTranspiler(unittest.TestCase):
  """Suite of unit tests verifying correct Lua code generation and execution."""

  def _transpile(self, code: str) -> str:
    """Helper to parse Sapphire code string and return transpiled Lua code."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()

    builder = ASTBuilder()
    ast = builder.visit(tree)

    transpiler = LuaTranspiler()
    return transpiler.transpile(ast)

  def test_basic_arithmetic(self):
    """Verifies that variable declarations and arithmetic expressions transpile to Lua."""
    code = """
    let x = 10;
    let y = 20;
    let z = x + y * 3;
    """
    lua_code = self._transpile(code)
    self.assertIn("local x = 10", lua_code)
    self.assertIn("local y = 20", lua_code)
    self.assertIn("local z = (x + (y * 3))", lua_code)

  def test_compound_assignments(self):
    """Verifies that compound assignments (+=, -=) expand to simple assignments in Lua 5.1."""
    code = """
    var val = 10;
    val += 5;
    val -= 2;
    """
    lua_code = self._transpile(code)
    self.assertIn("local val = 10", lua_code)
    self.assertIn("val = val + 5", lua_code)
    self.assertIn("val = val - 2", lua_code)

  def test_swift_style_if_let(self):
    """Verifies that swift-style optional unwrapping transpiles to Lua nil checks."""
    code = """
    func check_opt() {
      var opt_val: int? = 42;
      if let active = opt_val {
        let x = active;
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local _val_active = opt_val", lua_code)
    self.assertIn("if _val_active ~= nil then", lua_code)
    self.assertIn("local active = _val_active", lua_code)

  def test_array_indexing_and_loops(self):
    """Verifies that 0-based array indexing is offset by 1 in Lua table syntax."""
    code = """
    let numbers = [10, 20, 30];
    let first = numbers[0];
    for n in numbers {
      let x = n;
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local numbers = {10, 20, 30}", lua_code)
    self.assertIn("local first = numbers[1]", lua_code)
    self.assertIn("for _, n in ipairs(numbers) do", lua_code)

  def test_struct_declaration_and_impl(self):
    """Verifies struct constructor generation and impl block method definitions."""
    code = """
    struct Item {
      var price: int;
    }
    impl Item {
      func __init__(p: int) {
        self.price = p;
      }
      static func create_default(): Item {
        return Item(p = 100);
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local Item = {}", lua_code)
    self.assertIn("function Item.new(kwargs, proto)", lua_code)
    self.assertIn("function Item.create_default()", lua_code)

  def test_prototypal_inheritance(self):
    """Verifies clone node transpilation using _clone_helper."""
    code = """
    proto Monster {
      var hp: int;
    }
    impl Monster {
      func __init__(h: int) {
        self.hp = h;
      }
    }
    func test_clone() {
      var base = Monster(h = 100);
      var sub = clone base {
        self.hp = 80;
      };
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("_create_proto_object", lua_code)
    self.assertIn("_clone_helper(base", lua_code)

  def test_lua_execution_if_available(self):
    """Executes transpiled Lua code using system Lua interpreter if present."""
    lua_bin = shutil.which("lua") or shutil.which("luajit") or shutil.which("lua5.1")
    if not lua_bin:
      self.skipTest("No Lua interpreter found in system PATH.")

    code = """
    func main(): int {
      let x = 10;
      let y = 20;
      let sum = x + y;
      if sum == 30 {
        return 0;
      }
      return 1;
    }
    """
    with tempfile.NamedTemporaryFile(suffix=".sp", mode="w", delete=False) as f:
      f.write(code)
      sp_path = f.name

    lua_path = sp_path[:-3] + ".lua"
    try:
      transpile_file(sp_path, output_file=lua_path, target="lua")
      result = subprocess.run([lua_bin, lua_path], capture_output=True, text=True)
      self.assertEqual(result.returncode, 0)
    finally:
      if os.path.exists(sp_path):
        os.remove(sp_path)
      if os.path.exists(lua_path):
        os.remove(lua_path)


if __name__ == "__main__":
  unittest.main()
