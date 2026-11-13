"""Unit tests for keyword mangling and collision protection across Python and Lua backends."""

import unittest

from antlr4 import InputStream, CommonTokenStream
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler


class KeywordManglingTest(unittest.TestCase):
  """Verifies that identifiers colliding with target host keywords are safely mangled."""

  def _compile_python(self, source: str) -> str:
    lexer = SapphireLexer(InputStream(source))
    tokens = CommonTokenStream(lexer)
    parser = SapphireParser(tokens)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    transpiler = PythonTranspiler()
    return transpiler.transpile(ast)

  def _compile_lua(self, source: str) -> str:
    lexer = SapphireLexer(InputStream(source))
    tokens = CommonTokenStream(lexer)
    parser = SapphireParser(tokens)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    transpiler = LuaTranspiler()
    return transpiler.transpile(ast)

  def test_python_keywords_mangled(self):
    """Verifies that Python reserved words (def, class, pass, etc.) are mangled with trailing _."""
    source = """
    struct Config {
      var class: int;
    }

    func compute(def: int): int {
      var pass: int = def + 1;
      return pass;
    }

    var result: int = 0;

    func main() {
      let item = Config { class = 42 };
      result = compute(def = item.class);
    }
    """
    py_code = self._compile_python(source)

    # Verify that 'def_', 'class_', and 'pass_' appear in the emitted Python code
    self.assertIn("class_=42", py_code)
    self.assertIn("def compute(def_):", py_code)
    self.assertIn("pass_ = (def_ + 1)", py_code)
    self.assertIn("return pass_", py_code)
    self.assertIn("item.class_", py_code)

    # Verify that the generated Python code is syntactically valid by compiling it
    compiled_py = compile(py_code, "<string>", "exec")
    env = {"__name__": "__main__"}
    exec(compiled_py, env)
    self.assertEqual(env.get("result"), 43)

  def test_lua_keywords_mangled(self):
    """Verifies that Lua reserved words (local, function, end, repeat, until) are mangled."""
    source = """
    struct Worker {
      var end: int;
    }

    func process(local: int): int {
      var repeat: int = local * 2;
      return repeat;
    }

    func test() {
      let w = Worker { end = 10 };
      let total = process(local = w.end);
    }
    """
    lua_code = self._compile_lua(source)

    # Verify that 'end_', 'local_', and 'repeat_' appear in the emitted Lua code
    self.assertIn("end_ = 10", lua_code)
    self.assertIn("function process(local_)", lua_code)
    self.assertIn("local repeat_ = (local_ * 2)", lua_code)
    self.assertIn("return repeat_", lua_code)
    self.assertIn("w.end_", lua_code)

  def test_string_literal_escapes(self):
    """Verifies that newlines and carriage returns inside string literals are escaped."""
    source = """
    let text = "hello\\nworld";
    """
    py_code = self._compile_python(source)
    lua_code = self._compile_lua(source)

    self.assertIn('"hello\\nworld"', py_code)
    self.assertIn('"hello\\nworld"', lua_code)


if __name__ == "__main__":
  unittest.main()
