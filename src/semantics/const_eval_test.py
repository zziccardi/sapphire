"""Unit tests for compile-time constant expression evaluation."""

import unittest

from src.parser.ast import (
  ArgumentNode,
  ArrayLiteralNode,
  ASTNode,
  BinaryOpNode,
  CallNode,
  CastExprNode,
  CloneNode,
  IdentifierNode,
  InterpolatedStringNode,
  LambdaNode,
  LiteralNode,
  MapLiteralNode,
  MemberAccessNode,
  MoveNode,
  StructInitializerNode,
  TernaryExprNode,
  UnaryOpNode,
)
from src.semantics.const_eval import is_constant_expression
from src.semantics.symbol_table import (
  EnumSymbol,
  EnumType,
  FunctionSymbol,
  ModuleSymbol,
  PrimitiveType,
  StructType,
  SymbolTable,
  VariableSymbol,
)


class TestConstEval(unittest.TestCase):
  """Tests for is_constant_expression."""

  def setUp(self):
    self.table = SymbolTable()

  def test_literals(self):
    self.assertTrue(is_constant_expression(LiteralNode(10, "int"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(3.14, "float"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode("hello", "string"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(True, "bool"), self.table)[0])
    self.assertTrue(is_constant_expression(LiteralNode(None, "none"), self.table)[0])

  def test_unary_and_binary_ops(self):
    neg = UnaryOpNode("-", LiteralNode(5, "int"))
    self.assertTrue(is_constant_expression(neg, self.table)[0])

    add = BinaryOpNode(LiteralNode(10, "int"), "+", LiteralNode(20, "int"))
    self.assertTrue(is_constant_expression(add, self.table)[0])

    comp = BinaryOpNode(add, ">", LiteralNode(15, "int"))
    self.assertTrue(is_constant_expression(comp, self.table)[0])

  def test_ternary_and_cast(self):
    ternary = TernaryExprNode(LiteralNode(True, "bool"), LiteralNode(1, "int"), LiteralNode(2, "int"))
    self.assertTrue(is_constant_expression(ternary, self.table)[0])

    cast_expr = CastExprNode(LiteralNode(10, "int"), PrimitiveType("float"))
    self.assertTrue(is_constant_expression(cast_expr, self.table)[0])

  def test_collections(self):
    arr = ArrayLiteralNode([LiteralNode(1, "int"), LiteralNode(2, "int")])
    self.assertTrue(is_constant_expression(arr, self.table)[0])

    m = MapLiteralNode([(LiteralNode("a", "string"), LiteralNode(1, "int"))])
    self.assertTrue(is_constant_expression(m, self.table)[0])

  def test_constant_identifiers(self):
    const_sym = VariableSymbol("MAX_SPEED", PrimitiveType("int"), is_mutable=False)
    const_sym.is_constant_expr = True
    self.table.define("MAX_SPEED", const_sym)

    self.assertTrue(is_constant_expression(IdentifierNode("MAX_SPEED"), self.table)[0])

    # Mutable variable cannot be used in a constant expression
    mut_sym = VariableSymbol("counter", PrimitiveType("int"), is_mutable=True)
    self.table.define("counter", mut_sym)
    ok, err = is_constant_expression(IdentifierNode("counter"), self.table)
    self.assertFalse(ok)
    self.assertIn("not a compile-time constant expression", err)

  def test_prohibited_nodes(self):
    call = CallNode(IdentifierNode("foo"), [])
    ok, err = is_constant_expression(call, self.table)
    self.assertFalse(ok)
    self.assertIn("Function calls cannot be evaluated", err)

    clone_node = CloneNode(IdentifierNode("base"))
    ok, err = is_constant_expression(clone_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Dynamic prototype cloning", err)

    move_node = MoveNode("x")
    ok, err = is_constant_expression(move_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Move expressions cannot be used", err)

    lambda_node = LambdaNode([], None, LiteralNode(0, "int"))
    ok, err = is_constant_expression(lambda_node, self.table)
    self.assertFalse(ok)
    self.assertIn("Lambda expressions cannot be used", err)

    range_node = ASTNode()
    ok, err = is_constant_expression(range_node, self.table)
    self.assertFalse(ok)
    self.assertIn("not permitted", err)

  def test_enums_types_and_member_access(self):
    self.table.define_type("Color", EnumType("Color", {"Red": 0}))
    self.assertTrue(
        is_constant_expression(IdentifierNode("Color"), self.table)[0]
    )

    enum_sym = EnumSymbol("Dir", EnumType("Dir", {"Up": 0}))
    self.table.define("Dir", enum_sym)
    self.assertTrue(
        is_constant_expression(IdentifierNode("Dir"), self.table)[0]
    )
    self.assertTrue(
        is_constant_expression(
            MemberAccessNode(IdentifierNode("Dir"), "Up", False), self.table
        )[0]
    )

    mod_sym = ModuleSymbol("m", SymbolTable())
    self.table.define("m", mod_sym)
    self.assertTrue(
        is_constant_expression(
            MemberAccessNode(IdentifierNode("m"), "PI", False), self.table
        )[0]
    )

    fn_sym = FunctionSymbol("fn", [], PrimitiveType("void"))
    self.table.define("fn", fn_sym)
    ok, err = is_constant_expression(IdentifierNode("fn"), self.table)
    self.assertFalse(ok)
    self.assertIn("cannot be used as a value", err)

    const_pt = VariableSymbol("PT", PrimitiveType("int"), is_mutable=False)
    const_pt.is_constant_expr = True
    self.table.define("PT", const_pt)
    self.assertTrue(
        is_constant_expression(
            MemberAccessNode(
                MemberAccessNode(IdentifierNode("PT"), "nested", False),
                "x",
                False,
            ),
            self.table,
        )[0]
    )
    ok, _ = is_constant_expression(
        MemberAccessNode(
            MemberAccessNode(IdentifierNode("missing"), "nested", False),
            "x",
            False,
        ),
        self.table,
    )
    self.assertFalse(ok)

  def test_error_propagation_in_compound_expressions(self):
    bad = CallNode(IdentifierNode("foo"), [])
    self.assertFalse(
        is_constant_expression(UnaryOpNode("~", LiteralNode(1, "int")), self.table)[0]
    )
    self.assertFalse(
        is_constant_expression(
            BinaryOpNode(bad, "+", LiteralNode(1, "int")), self.table
        )[0]
    )
    self.assertFalse(
        is_constant_expression(
            BinaryOpNode(LiteralNode(1, "int"), "+", bad), self.table
        )[0]
    )
    self.assertFalse(
        is_constant_expression(
            TernaryExprNode(bad, LiteralNode(1, "int"), LiteralNode(2, "int")),
            self.table,
        )[0]
    )
    self.assertFalse(
        is_constant_expression(
            TernaryExprNode(LiteralNode(True, "bool"), bad, LiteralNode(2, "int")),
            self.table,
        )[0]
    )
    self.assertFalse(
        is_constant_expression(
            TernaryExprNode(LiteralNode(True, "bool"), LiteralNode(1, "int"), bad),
            self.table,
        )[0]
    )
    self.assertTrue(
        is_constant_expression(
            InterpolatedStringNode([LiteralNode("x=", "string"), LiteralNode(1, "int")]),
            self.table,
        )[0]
    )
    self.assertFalse(
        is_constant_expression(InterpolatedStringNode([bad]), self.table)[0]
    )
    self.assertFalse(
        is_constant_expression(ArrayLiteralNode([bad]), self.table)[0]
    )
    self.assertFalse(
        is_constant_expression(
            MapLiteralNode([(bad, LiteralNode(1, "int"))]), self.table
        )[0]
    )
    self.assertFalse(
        is_constant_expression(
            MapLiteralNode([(LiteralNode("a", "string"), bad)]), self.table
        )[0]
    )

  def test_struct_initializer_validation(self):
    proto_st = StructType("Goblin", {}, is_prototype=True)
    self.table.define_type("Goblin", proto_st)
    ok, err = is_constant_expression(
        StructInitializerNode("Goblin", []), self.table
    )
    self.assertFalse(ok)
    self.assertIn("Prototype struct", err)

    init_st = StructType("WithInit", {})
    init_st.methods["__init__"] = FunctionSymbol(
        "__init__", [], PrimitiveType("void")
    )
    self.table.define_type("WithInit", init_st)
    ok, err = is_constant_expression(
        StructInitializerNode("WithInit", []), self.table
    )
    self.assertFalse(ok)
    self.assertIn("__init__", err)

    plain_st = StructType("Point", {})
    self.table.define_type("Point", plain_st)
    bad = CallNode(IdentifierNode("foo"), [])
    ok, _ = is_constant_expression(
        StructInitializerNode("Point", [ArgumentNode("x", bad)]), self.table
    )
    self.assertFalse(ok)

  def test_phase4_div_by_zero_omitted_defaults_and_mutable_module_member(self):
    from src.parser.ast import StructDeclNode, StructFieldNode

    # 1. Literal division and modulo by zero (including -0 and 0.0)
    for op in ("/", "%"):
      ok, err = is_constant_expression(
          BinaryOpNode(LiteralNode(1, "int"), op, LiteralNode(0, "int")),
          self.table,
      )
      self.assertFalse(ok)
      self.assertIn("Division or modulo by zero", err)
    ok, err = is_constant_expression(
        BinaryOpNode(
            LiteralNode(1.0, "float"),
            "/",
            UnaryOpNode("-", LiteralNode(0.0, "float")),
        ),
        self.table,
    )
    self.assertFalse(ok)
    self.assertIn("Division or modulo by zero", err)

    # 2. Omitted struct field with non-constant default expression
    bad_default = CallNode(IdentifierNode("runtime_fn"), [])
    cfg_decl = StructDeclNode(
        "Cfg",
        fields=[
            StructFieldNode(
                is_mutable=False,
                name="x",
                field_type=None,
                default_expr=bad_default,
            ),
        ],
    )
    cfg_st = StructType("Cfg", {}, ast_decl=cfg_decl)
    self.table.define_type("Cfg", cfg_st)
    ok, err = is_constant_expression(
        StructInitializerNode("Cfg", []), self.table
    )
    self.assertFalse(ok)
    self.assertIn("Default value of omitted field 'x'", err)
    # Explicitly overriding the non-constant default with a constant succeeds
    ok_override, _ = is_constant_expression(
        StructInitializerNode("Cfg", [ArgumentNode("x", LiteralNode(5, "int"))]),
        self.table,
    )
    self.assertTrue(ok_override)

    # 3. Mutable imported @extern var is rejected while imported let const is accepted
    mod = ModuleSymbol("ext_mod", "ext_mod")
    mut_var = VariableSymbol("g", PrimitiveType("int"), is_mutable=True)
    const_var = VariableSymbol("C", PrimitiveType("int"), is_mutable=False)
    const_var.is_constant_expr = True
    mod.exports["g"] = mut_var
    mod.exports["C"] = const_var
    self.table.define("ext_mod", mod)

    ok_mut, err_mut = is_constant_expression(
        MemberAccessNode(IdentifierNode("ext_mod"), "g", False), self.table
    )
    self.assertFalse(ok_mut)
    self.assertIn("not a compile-time constant", err_mut)

    ok_const, _ = is_constant_expression(
        MemberAccessNode(IdentifierNode("ext_mod"), "C", False), self.table
    )
    self.assertTrue(ok_const)


if __name__ == "__main__":
  unittest.main()
