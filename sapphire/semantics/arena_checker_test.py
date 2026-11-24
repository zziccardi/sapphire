"""Unit tests for ArenaChecker in src/semantics/arena_checker.py."""

import unittest

from sapphire.parser.ast import (
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
from sapphire.semantics.arena_checker import ArenaChecker
from sapphire.semantics.symbol_table import (
  ArenaType,
  OptionalType,
  PrimitiveType,
  StructField,
  StructType,
  SymbolTable,
  TraitType,
  VariableSymbol,
)


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

  def test_phase3_arena_and_stack_borrow_edge_cases(self):
    from sapphire.parser.ast import YieldNode
    from sapphire.semantics.borrow_checker import BorrowChecker
    from sapphire.semantics.symbol_table import SharedRefType

    st = SymbolTable()
    proto_t = StructType("Goblin", is_prototype=True)
    v1 = VariableSymbol("v1", proto_t, is_mutable=False)
    v1.arena_dep_records = [("a1", 0)]
    st.define("v1", v1)

    # 1. MatchExprNode with YieldNode inside block arm
    match_yield = MatchExprNode(
        LiteralNode(1, "int"),
        [
            MatchCaseNode(
                LiteralNode(1, "int"),
                BlockNode([YieldNode([IdentifierNode("v1")])]),
            )
        ],
    )
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, match_yield), [("a1", 0)]
    )

    # 2. MatchExprNode stack borrow collection
    cb = VariableSymbol("cb", PrimitiveType("none"), is_mutable=False)
    cb.stack_borrow_symbols = {"local_x"}
    st.define("cb", cb)
    match_sb = MatchExprNode(
        LiteralNode(1, "int"),
        [
            MatchCaseNode(
                LiteralNode(1, "int"),
                BlockNode([YieldNode([IdentifierNode("cb")])]),
            )
        ],
    )
    self.assertEqual(
        BorrowChecker.collect_stack_borrow_symbols(st, match_sb), {"local_x"}
    )

    # 3. Multi-var VarDeclNode in lambda captures second expr
    lam_multi = LambdaNode(
        [],
        None,
        BlockNode([
            VarDeclNode(
                False,
                ["x", "y"],
                exprs=[LiteralNode(1, "int"), IdentifierNode("v1")],
            )
        ]),
    )
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, lam_multi), [("a1", 0)]
    )

    # 4. CallNode with callable variable callee carrying arena dep
    fn_var = VariableSymbol("get_v1", PrimitiveType("none"), is_mutable=False)
    fn_var.arena_dep_records = [("a1", 0)]
    st.define("get_v1", fn_var)
    self.assertEqual(
        ArenaChecker.collect_arena_deps(st, CallNode(IdentifierNode("get_v1"), [])),
        [("a1", 0)],
    )

    # 5. Intermediate immutable field in arena chain
    inner_t = StructType("Inner")
    inner_t.fields["arena"] = VariableSymbol("arena", ArenaType(), is_mutable=True)
    outer_t = StructType("Outer")
    outer_t.fields["const_inner"] = VariableSymbol("const_inner", inner_t, is_mutable=False)
    outer_sym = VariableSymbol("o", outer_t, is_mutable=True)
    st.define("o", outer_sym)
    o_id = IdentifierNode("o")
    o_inner = MemberAccessNode(o_id, "const_inner", False)
    o_arena = MemberAccessNode(o_inner, "arena", False)
    fake_checker = type(
        "C", (), {"node_types": {o_id: outer_t, o_inner: inner_t}}
    )()
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, o_arena, errs.append, checker=fake_checker
    )
    self.assertTrue(errs)
    self.assertIn("immutable Arena field 'const_inner'", errs[0])

    # 6. SharedRef-backed arena rejected
    sr_sym = VariableSymbol("sr", SharedRefType(inner_t), is_mutable=True)
    st.define("sr", sr_sym)
    sr_arena = MemberAccessNode(IdentifierNode("sr"), "arena", False)
    fake_sr_checker = type(
        "C", (), {"node_types": {}, "has_shared_ref_base": lambda self, n: True}
    )()
    errs = []
    ArenaChecker.validate_arena_mutability(
        st, sr_arena, errs.append, checker=fake_sr_checker
    )
    self.assertTrue(errs)
    self.assertIn("SharedRef", errs[0])

  def test_closed_world_trait_box_check(self):
    st = SymbolTable()
    host_trait = TraitType("HostImage")
    struct_trait = TraitType("Drawable")
    proto_trait = TraitType("Combatant")
    cycle_trait = TraitType("CyclicTrait")

    sprite = StructType("Sprite")
    sprite.implemented_traits.add("Drawable")
    sprite.implemented_trait_types["Drawable"] = struct_trait
    struct_trait.add_implementor(sprite)

    goblin = StructType("Goblin", is_prototype=True)
    goblin.implemented_traits.add("Combatant")
    goblin.implemented_trait_types["Combatant"] = proto_trait
    proto_trait.add_implementor(goblin)

    cyclic_struct = StructType("CyclicStruct")
    cyclic_struct.fields["next"] = StructField(
        "next", cycle_trait, is_mutable=True
    )
    cyclic_struct.implemented_traits.add("CyclicTrait")
    cyclic_struct.implemented_trait_types["CyclicTrait"] = cycle_trait
    cycle_trait.add_implementor(cyclic_struct)

    st.define_type("HostImage", host_trait)
    st.define_type("Drawable", struct_trait)
    st.define_type("Combatant", proto_trait)
    st.define_type("CyclicTrait", cycle_trait)
    st.define_type("Sprite", sprite)
    st.define_type("Goblin", goblin)
    st.define_type("CyclicStruct", cyclic_struct)

    # Without closed-world context, traits conservatively return True
    self.assertTrue(
        ArenaChecker.type_can_hold_arena_ref(host_trait, is_box_check=True)
    )
    # With closed-world context: host trait (0 impls) and struct-only trait are safe
    self.assertFalse(
        ArenaChecker.type_can_hold_arena_ref(
            host_trait, is_box_check=True, symbol_table=st
        )
    )
    self.assertFalse(
        ArenaChecker.type_can_hold_arena_ref(
            struct_trait, is_box_check=True, symbol_table=st
        )
    )
    # Trait implemented by a proto is rejected
    self.assertTrue(
        ArenaChecker.type_can_hold_arena_ref(
            proto_trait, is_box_check=True, symbol_table=st
        )
    )
    # Cyclic trait <-> struct with no proto terminates and returns False
    self.assertFalse(
        ArenaChecker.type_can_hold_arena_ref(
            cycle_trait, is_box_check=True, symbol_table=st
        )
    )



