"""Unit tests for ArenaChecker in src/semantics/arena_checker.py."""

import unittest
from src.parser.ast import (
    ArrayLiteralNode,
    BinaryOpNode,
    BlockNode,
    CallNode,
    CastExprNode,
    CloneNode,
    ExprStmtNode,
    IdentifierNode,
    LambdaNode,
    LambdaParamNode,
    LiteralNode,
    MapEntryNode,
    MapLiteralNode,
    MatchCaseNode,
    MatchExprNode,
    MemberAccessNode,
    MoveNode,
    ReturnNode,
    StructInitializerNode,
    TernaryExprNode,
    UnaryOpNode,
    VarDeclNode,
)
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

  def test_validate_arena_mutability_variants(self):
    st = SymbolTable()
    # MoveNode arena target
    errs = []
    ArenaChecker.validate_arena_mutability(st, MoveNode("a"), errs.append)
    self.assertIn("moved Arena", errs[0])

    # Moved IdentifierNode
    moved_a = VariableSymbol("moved_a", ArenaType(), is_mutable=True)
    moved_a.is_moved = True
    st.define("moved_a", moved_a)
    errs = []
    ArenaChecker.validate_arena_mutability(st, IdentifierNode("moved_a"), errs.append)
    self.assertIn("moved Arena", errs[0])

    # MemberAccessNode without root identifier
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, MemberAccessNode(LiteralNode(1, "int"), "arena", False), errs.append
    )
    self.assertIn("not a temporary expression", errs[0])

    # MemberAccessNode with moved root
    holder = VariableSymbol("holder", StructType("H"), is_mutable=True)
    holder.is_moved = True
    st.define("holder", holder)
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, MemberAccessNode(IdentifierNode("holder"), "arena", False), errs.append
    )
    self.assertIn("moved Arena owner", errs[0])

    # MemberAccessNode with immutable root
    immut_holder = VariableSymbol("immut_h", StructType("H"), is_mutable=False)
    st.define("immut_h", immut_holder)
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, MemberAccessNode(IdentifierNode("immut_h"), "arena", False), errs.append
    )
    self.assertIn("immutable binding", errs[0])

    # MemberAccessNode with immutable Arena field on mutable root
    box_t = StructType("Box")
    box_t.fields["arena"] = VariableSymbol("arena", ArenaType(), is_mutable=False)
    mut_box = VariableSymbol("mut_box", box_t, is_mutable=True)
    st.define("mut_box", mut_box)
    recv = IdentifierNode("mut_box")
    fake_checker = type("C", (), {"node_types": {recv: box_t}})()
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, MemberAccessNode(recv, "arena", False), errs.append, checker=fake_checker
    )
    self.assertIn("immutable Arena field", errs[0])

    # Temporary expression
    errs = []
    ArenaChecker.validate_arena_mutability(st, LiteralNode(1, "int"), errs.append)
    self.assertIn("not a temporary expression", errs[0])

  def test_collect_arena_deps_compound_and_lambda_expressions(self):
    st = SymbolTable()
    proto_t = StructType("Goblin", is_prototype=True)
    v1 = VariableSymbol("v1", proto_t, is_mutable=False)
    v1.arena_dependency = "a1"
    st.define("v1", v1)

    v2 = VariableSymbol("v2", proto_t, is_mutable=False)
    v2.arena_dep_records = [("a2", 0)]
    st.define("v2", v2)

    # MapLiteralNode, TernaryExprNode, BinaryOpNode(??), UnaryOpNode, CastExprNode
    m = MapLiteralNode([MapEntryNode(IdentifierNode("v1"), IdentifierNode("v2"))])
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, m), [("a1", 0), ("a2", 0)]
    )
    tern = TernaryExprNode(
        LiteralNode(True, "bool"), IdentifierNode("v1"), IdentifierNode("v2")
    )
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, tern), [("a1", 0), ("a2", 0)]
    )
    coal = BinaryOpNode(IdentifierNode("v1"), "??", IdentifierNode("v2"))
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, coal), [("a1", 0), ("a2", 0)]
    )
    cast = CastExprNode(UnaryOpNode("-", IdentifierNode("v1")), PrimitiveType("int"))
    self.assertEqual(ArenaChecker.collect_arena_deps(st, cast), [("a1", 0)])

    # MatchExprNode with BlockNode cases (ReturnNode and ExprStmtNode)
    match_expr = MatchExprNode(
        LiteralNode(1, "int"),
        [
            MatchCaseNode(
                LiteralNode(1, "int"),
                BlockNode([ReturnNode([IdentifierNode("v1")])]),
            ),
            MatchCaseNode(
                LiteralNode(2, "int"),
                BlockNode([ExprStmtNode(IdentifierNode("v2"))]),
            ),
        ],
    )
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, match_expr), [("a1", 0), ("a2", 0)]
    )

    # Lambda capturing IdentifierNode, MoveNode, VarDeclNode, and nested LambdaNode
    lam = LambdaNode(
        [LambdaParamNode("p")],
        None,
        BlockNode([
            VarDeclNode(False, ["local_v"], exprs=IdentifierNode("v1")),
            ExprStmtNode(
                LambdaNode(
                    [LambdaParamNode("inner_p")],
                    None,
                    MoveNode("v2"),
                )
            ),
        ]),
    )
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, lam), [("a1", 0), ("a2", 0)]
    )


