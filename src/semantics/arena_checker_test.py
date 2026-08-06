"""Unit tests for ArenaChecker in src/semantics/arena_checker.py."""

import unittest
from src.parser.ast import IdentifierNode, StructInitializerNode, CloneNode, LiteralNode
from src.semantics.symbol_table import SymbolTable, VariableSymbol, PrimitiveType
from src.semantics.arena_checker import ArenaChecker


class TestArenaChecker(unittest.TestCase):
  """Unit tests for arena dependency and lifetime scope checks."""

  def test_get_arena_dependency_identifier(self):
    st = SymbolTable()
    sym = VariableSymbol("my_vec", PrimitiveType("int"), is_mutable=False)
    sym.arena_dependency = "arena_a"
    st.define("my_vec", sym)

    dep = ArenaChecker.get_arena_dependency(st, IdentifierNode("my_vec"))
    self.assertEqual(dep, "arena_a")

  def test_get_arena_dependency_struct_initializer(self):
    st = SymbolTable()
    init_node = StructInitializerNode(
        struct_name="Vector",
        fields=[],
        arena_expr=IdentifierNode("arena_b"),
    )
    dep = ArenaChecker.get_arena_dependency(st, init_node)
    self.assertEqual(dep, "arena_b")

  def test_get_arena_dependency_clone_node(self):
    st = SymbolTable()
    clone_node = CloneNode(
        expr=IdentifierNode("my_var"),
        arena_expr=IdentifierNode("arena_c"),
    )
    dep = ArenaChecker.get_arena_dependency(st, clone_node)
    self.assertEqual(dep, "arena_c")

  def test_is_descendant_scope(self):
    st = SymbolTable()
    parent_scope = st.current_scope
    st.enter_scope()
    child_scope = st.current_scope

    self.assertTrue(ArenaChecker.is_descendant_scope(child_scope, parent_scope))
    self.assertFalse(ArenaChecker.is_descendant_scope(parent_scope, child_scope))

  def test_validate_arena_escape(self):
    st = SymbolTable()
    parent_scope = st.current_scope
    arena_sym = VariableSymbol("arena_sub", PrimitiveType("Arena"), is_mutable=False)
    st.enter_scope()
    child_scope = st.current_scope
    st.define("arena_sub", arena_sym)

    val_sym = VariableSymbol("val", PrimitiveType("int"), is_mutable=False)
    val_sym.arena_dependency = "arena_sub"
    st.define("val", val_sym)

    target_sym = VariableSymbol("out", PrimitiveType("int"), is_mutable=False)
    target_sym.scope_defined = parent_scope

    errors = []
    ArenaChecker.validate_arena_escape(st, target_sym, IdentifierNode("val"), errors.append)
    self.assertEqual(len(errors), 1)

    self.assertIn("cannot hold a reference to an object allocated in nested arena", errors[0])

