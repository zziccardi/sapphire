"""Structural parity tests for Sapphire transpiler backends.

Verifies that all concrete transpiler backends (Python and Lua) remain
structurally symmetric with each other and fully cover every visitable AST
node class. These tests act as a compile-time-style tripwire: adding a new
AST node or visitor to one backend without updating the other will cause an
immediate failure here, long before any semantic regression appears in
production.
"""

import inspect
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from antlr4 import InputStream, CommonTokenStream
import src.parser.ast as ast_module
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler



# AST node classes that are never dispatched to via the visit_* protocol.
# These are either abstract base nodes, purely structural container nodes,
# or internal nodes whose parent visitor handles them directly.
_EXCLUDED_NODES = {
    # Abstract / marker bases
    "ASTNode",
    "TypeNode",
    "DeclNode",
    "StmtNode",
    "ExprNode",
    # Type annotation nodes (handled inline, never visited standalone)
    "BasicTypeNode",
    "OptionalTypeNode",
    "ArrayTypeNode",
    "MapTypeNode",
    "FunctionTypeNode",
    # Annotation node (processed as an attribute of other nodes)
    "AnnotationNode",
    # Sub-nodes consumed by their parent visitor
    "ParameterNode",
    "ArgumentNode",
    "LambdaParamNode",
    "ExportSpecifierNode",
    "HeaderBindingNode",
    "EnumMemberNode",
    "TraitMemberNode",
    "ImplBlockNode",
    "MatchCaseNode",
    "MapEntryNode",
    # Program root (entry-point; handled by transpile(), not visit())
    "ProgramNode",
}


class VisitorParityTest(unittest.TestCase):
  """Ensures both transpiler backends expose an identical set of AST visitors.

  Two invariants are enforced:

  1. **Parity** — the set of `visit_*` methods on `PythonTranspiler` and
     `LuaTranspiler` must be exactly equal. Any method present in one but
     absent from the other indicates a feature that has drifted out of sync.

  2. **Coverage** — every concrete, visitable `*Node` class defined in
     `parser.ast` must have a corresponding `visit_*` method on *both*
     transpilers. This catches the case where a brand-new AST node is added
     to the grammar but neither backend is updated.
  """

  def test_visitor_method_parity(self):
    """Both transpilers must expose exactly the same set of visit_* methods."""
    py_visitors = {m for m in dir(PythonTranspiler) if m.startswith("visit_")}
    lua_visitors = {m for m in dir(LuaTranspiler) if m.startswith("visit_")}

    self.assertEqual(
        py_visitors,
        lua_visitors,
        "\nVisitor parity mismatch between PythonTranspiler and LuaTranspiler!"
        f"\n  Python-only : {sorted(py_visitors - lua_visitors)}"
        f"\n  Lua-only    : {sorted(lua_visitors - py_visitors)}",
    )

  def test_all_ast_nodes_have_visitors(self):
    """Every visitable *Node class must have a visitor on both transpilers."""
    all_node_names = {
        name
        for name, obj in inspect.getmembers(ast_module, inspect.isclass)
        if (name.endswith("Node") and
            issubclass(obj, ast_module.ASTNode) and
            name not in _EXCLUDED_NODES)
    }

    missing_py = []
    missing_lua = []
    for node_name in sorted(all_node_names):
      visitor = f"visit_{node_name}"
      if not hasattr(PythonTranspiler, visitor):
        missing_py.append(visitor)
      if not hasattr(LuaTranspiler, visitor):
        missing_lua.append(visitor)

    self.assertFalse(
        missing_py,
        f"PythonTranspiler is missing visitors for: {missing_py}",
    )
    self.assertFalse(
        missing_lua,
        f"LuaTranspiler is missing visitors for: {missing_lua}",
    )


class SemanticParityTest(unittest.TestCase):
  """Ensures runtime execution parity across Python and Lua backends."""

  def _execute_both(self, source: str, fn_name: str):
    """Executes fn_name in both Python and Lua backends and returns (py_result, lua_result)."""
    # 1. Python execution
    ast_py = ASTBuilder().visit(
        SapphireParser(CommonTokenStream(SapphireLexer(InputStream(source)))).program()
    )
    TypeChecker().check(ast_py)
    py_code = PythonTranspiler(test_mode=True).transpile(ast_py)
    ctx = {}
    exec(py_code, ctx)  # pylint: disable=exec-used
    py_result = ctx[fn_name]()

    # 2. Lua execution
    lua_bin = shutil.which("lua") or shutil.which("lua5.1")
    if not lua_bin:
      self.skipTest("Lua interpreter not found in PATH.")

    ast_lua = ASTBuilder().visit(
        SapphireParser(CommonTokenStream(SapphireLexer(InputStream(source)))).program()
    )
    TypeChecker().check(ast_lua)
    lua_code = LuaTranspiler(test_mode=True).transpile(ast_lua)
    lib_path = str(pathlib.Path(__file__).parent.parent.parent / "lib")

    driver = (
        f"package.path = \"{lib_path}/?.lua;{lib_path}/?/init.lua;\" .. package.path\n"
        "local __mod = (function()\n"
        f"{lua_code}\n"
        "end)()\n"
        f"local fn = (__mod and __mod.{fn_name}) or {fn_name}\n"
        "print(tostring(fn()))\n"
    )

    with tempfile.NamedTemporaryFile(
        suffix=".lua", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
      tmp.write(driver)
      tmp_path = tmp.name

    try:
      proc = subprocess.run(
          [lua_bin, tmp_path],
          capture_output=True, text=True, timeout=10,
      )
      if proc.returncode != 0:
        self.fail(f"Lua execution failed for {fn_name}: {proc.stderr.strip()}")
      raw = proc.stdout.strip()
      if raw == "true":
        lua_result = True
      elif raw == "false":
        lua_result = False
      elif raw == "nil":
        lua_result = None
      else:
        try:
          lua_result = int(raw)
        except ValueError:
          lua_result = float(raw)
    finally:
      os.unlink(tmp_path)

    return py_result, lua_result

  def test_global_var_mutation_parity(self):
    """Verifies functions mutating global variables execute identically without UnboundLocalError."""
    code = """
    var count: int = 10;
    @test
    func test_inc(): int {
      count = count + 5;
      return count;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_inc")
    self.assertEqual(py_val, 15)
    self.assertEqual(lua_val, 15)

  def test_optional_boolean_false_preservation(self):
    """Verifies accessing an optional boolean field that is false preserves false across backends."""
    code = """
    struct Toggle {
      let is_enabled: bool;
    }
    @test
    func test_false(): bool {
      let t: Toggle? = Toggle { is_enabled = false };
      let res = t?.is_enabled;
      return res == false;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_false")
    self.assertEqual(py_val, True)
    self.assertEqual(lua_val, True)

  def test_optional_chaining_single_evaluation(self):
    """Verifies that optional property access evaluates side-effecting receivers exactly once."""
    code = """
    struct Holder {
      var value: int;
    }
    var eval_count: int = 0;
    func get_holder(): Holder? {
      eval_count = eval_count + 1;
      return Holder { value = 42 };
    }
    @test
    func test_single_eval(): int {
      let v = get_holder()?.value;
      return eval_count;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_single_eval")
    self.assertEqual(py_val, 1)
    self.assertEqual(lua_val, 1)

  def test_arena_return_expression_order(self):
    """Verifies that arena fields can be returned without premature arena teardown."""
    code = """
    proto Item {
      var value: int;
    }
    @test
    func test_arena_return(): int {
      let arena = Arena();
      let item = Item { value = 99 } in arena;
      return item.value;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_arena_return")
    self.assertEqual(py_val, 99)
    self.assertEqual(lua_val, 99)


if __name__ == "__main__":
  unittest.main()
