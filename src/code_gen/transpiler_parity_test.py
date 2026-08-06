"""Structural parity tests for Sapphire transpiler backends.

Verifies that all concrete transpiler backends (Python and Lua) remain
structurally symmetric with each other and fully cover every visitable AST
node class. These tests act as a compile-time-style tripwire: adding a new
AST node or visitor to one backend without updating the other will cause an
immediate failure here, long before any semantic regression appears in
production.
"""

import inspect
import unittest

import src.parser.ast as ast_module
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


if __name__ == "__main__":
  unittest.main()
