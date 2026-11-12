"""Unit tests for ArenaChecker in src/semantics/arena_checker.py."""

import unittest
from src.parser.ast import IdentifierNode, StructInitializerNode, CloneNode, LiteralNode, CallNode
from src.semantics.symbol_table import (
    ArenaType,
    OptionalType,
    PrimitiveType,
    StructType,
    SymbolTable,
    VariableSymbol,
)
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

  def test_get_arena_dependency_call_node(self):
    st = SymbolTable()
    call_node = CallNode(
        callee=IdentifierNode("Enemy"),
        arguments=[],
        arena_expr=IdentifierNode("arena_call"),
    )
    dep = ArenaChecker.get_arena_dependency(st, call_node)
    self.assertEqual(dep, "arena_call")

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
    arena_sym = VariableSymbol("arena_sub", ArenaType(), is_mutable=True)
    st.enter_scope()
    child_scope = st.current_scope
    st.define("arena_sub", arena_sym)

    proto_t = StructType("Goblin", is_prototype=True)
    val_sym = VariableSymbol("val", proto_t, is_mutable=False)
    val_sym.arena_dep_records = [("arena_sub", 0)]
    val_sym.arena_dependency = "arena_sub"
    st.define("val", val_sym)

    target_sym = VariableSymbol("out", proto_t, is_mutable=False)
    target_sym.scope_defined = parent_scope

    errors = []
    ArenaChecker.validate_arena_escape(st, target_sym, IdentifierNode("val"), errors.append)
    self.assertEqual(len(errors), 1)
    self.assertIn("cannot hold a reference to an object allocated in nested arena", errors[0])

  def test_validate_arena_escape_no_dep_and_missing_sym(self):
    st = SymbolTable()
    proto_t = StructType("Goblin", is_prototype=True)
    target_sym = VariableSymbol("out", proto_t, is_mutable=False)
    errors = []

    # 1. No arena dependency on expression node
    sym_nodep = VariableSymbol("nodep", proto_t, is_mutable=False)
    st.define("nodep", sym_nodep)
    ArenaChecker.validate_arena_escape(st, target_sym, IdentifierNode("nodep"), errors.append)
    self.assertEqual(len(errors), 0)

    # 2. Arena dependency references missing symbol in symbol table
    val_sym = VariableSymbol("val", proto_t, is_mutable=False)
    val_sym.arena_dep_records = [("nonexistent_arena", 0)]
    val_sym.arena_dependency = "nonexistent_arena"
    st.define("val", val_sym)

    ArenaChecker.validate_arena_escape(st, target_sym, IdentifierNode("val"), errors.append)
    self.assertEqual(len(errors), 0)

  def test_same_scope_lifo_and_mutability_checks(self):
    st = SymbolTable()
    proto_t = StructType("Goblin", is_prototype=True)
    out_sym = VariableSymbol("out", OptionalType(proto_t), is_mutable=True)
    st.define("out", out_sym)
    late_arena = VariableSymbol("late_arena", ArenaType(), is_mutable=True)
    st.define("late_arena", late_arena)

    val_sym = VariableSymbol("val", proto_t, is_mutable=False)
    val_sym.arena_dep_records = [("late_arena", 0)]
    st.define("val", val_sym)

    errors = []
    ArenaChecker.validate_arena_escape(st, out_sym, IdentifierNode("val"), errors.append)
    self.assertEqual(len(errors), 1)
    self.assertIn("later-declared arena", errors[0])

    # Immutable arena fails mutability validation
    immut_arena = VariableSymbol("immut_a", ArenaType(), is_mutable=False)
    st.define("immut_a", immut_arena)
    mut_errors = []
    ArenaChecker.validate_arena_mutability(st, IdentifierNode("immut_a"), mut_errors.append)
    self.assertEqual(len(mut_errors), 1)
    self.assertIn("immutable Arena 'immut_a'", mut_errors[0])

    # Primitive field cannot retain arena deps
    int_sym = VariableSymbol("count", PrimitiveType("int"), is_mutable=False)
    st.define("count", int_sym)
    int_errors = []
    ArenaChecker.validate_arena_escape(st, int_sym, IdentifierNode("val"), int_errors.append)
    self.assertEqual(len(int_errors), 0)
    self.assertEqual(int_sym.arena_dep_records, [])


