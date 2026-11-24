"""Unit tests for base_transpiler.py helper functions."""

import unittest

from src.code_gen.base_transpiler import (
  get_default_value_for_type_node,
  is_coroutine_func,
)
from src.parser.ast import (
  BasicTypeNode,
  BlockNode,
  FuncDeclNode,
  OptionalTypeNode,
)


class TestBaseTranspilerHelpers(unittest.TestCase):
  """Unit tests for helper functions in base_transpiler.py."""

  def test_get_default_value_for_type_node(self):
    """Verifies default ASTNode generation for various types."""
    self.assertIsNone(get_default_value_for_type_node(None))

    opt_node = OptionalTypeNode(BasicTypeNode("int"))
    default_opt = get_default_value_for_type_node(opt_node)
    self.assertIsNotNone(default_opt)
    self.assertEqual(default_opt.value, "none")

    int_node = BasicTypeNode("int")
    default_int = get_default_value_for_type_node(int_node)
    self.assertIsNotNone(default_int)
    self.assertEqual(default_int.value, 0)

    float_node = BasicTypeNode("float")
    default_float = get_default_value_for_type_node(float_node)
    self.assertIsNotNone(default_float)
    self.assertEqual(default_float.value, 0.0)

    bool_node = BasicTypeNode("bool")
    default_bool = get_default_value_for_type_node(bool_node)
    self.assertIsNotNone(default_bool)
    self.assertEqual(default_bool.value, False)

    other_node = BasicTypeNode("String")
    self.assertIsNone(get_default_value_for_type_node(other_node))

  def test_is_coroutine_func(self):
    """Verifies is_coroutine_func detection for AST nodes and edge cases."""
    # None node
    self.assertFalse(is_coroutine_func(None))

    # Standard coroutine with return_types list
    coro_func = FuncDeclNode(
        "my_coro",
        [],
        return_types=[BasicTypeNode("Coroutine")],
        body=BlockNode([]),
    )
    self.assertTrue(is_coroutine_func(coro_func))

    # Non-coroutine func
    normal_func = FuncDeclNode(
        "my_func",
        [],
        return_types=[BasicTypeNode("int")],
        body=BlockNode([]),
    )
    self.assertFalse(is_coroutine_func(normal_func))

    # Mock node with return_type attribute (not in return_types)
    class MockReturnSingle:
      def __init__(self):
        self.return_types = None
        self.return_type = BasicTypeNode("Coroutine")

    self.assertTrue(is_coroutine_func(MockReturnSingle()))

    class MockReturnOther:
      def __init__(self):
        self.return_types = None
        self.return_type = BasicTypeNode("int")

    self.assertFalse(is_coroutine_func(MockReturnOther()))

  def test_extract_type_name_and_return_type_names(self):
    """Verifies extract_type_name and get_return_type_names helpers."""
    from src.code_gen.base_transpiler import (
      extract_type_name,
      get_return_type_names,
    )
    from src.code_gen.python_transpiler import PythonTranspiler
    from src.parser.ast import LiteralNode
    from src.semantics.symbol_table import StructType

    self.assertIsNone(extract_type_name(None))

    class SingleReturnFunc:
      def __init__(self):
        self.return_types = []
        self.return_type = BasicTypeNode("Resource")

    self.assertEqual(get_return_type_names(SingleReturnFunc()), ["Resource"])

    transpiler = PythonTranspiler()
    transpiler.structs_with_destructor.add("Resource")
    self.assertIsNone(transpiler._expr_destructible_struct(None))

    expr = LiteralNode(0, "int")
    expr.inferred_type = StructType("Resource")
    self.assertEqual(transpiler._expr_destructible_struct(expr), "Resource")

  def test_next_temp_name_initializes_counters(self):
    """Verifies _next_temp_name lazily initializes counters and increments per prefix."""
    from src.code_gen.python_transpiler import PythonTranspiler

    transpiler = PythonTranspiler()
    if hasattr(transpiler, "_temp_name_counters"):
      delattr(transpiler, "_temp_name_counters")
    self.assertEqual(transpiler._next_temp_name(), "_sp_tmp_1")
    self.assertEqual(transpiler._next_temp_name(), "_sp_tmp_2")
    self.assertEqual(transpiler._next_temp_name("_custom"), "_custom_1")

  def test_type_needs_destructor_paths(self):
    """Verifies _type_needs_destructor for None, methods, cycles, and nested fields."""
    from src.code_gen.python_transpiler import PythonTranspiler
    from src.semantics.types import (
        ArenaType,
        FunctionType,
        OptionalType,
        PrimitiveType,
        RefType,
        SharedRefType,
        StructField,
        StructMethod,
        StructType,
    )

    transpiler = PythonTranspiler()
    self.assertIsNone(transpiler._type_needs_destructor(None))
    self.assertEqual(transpiler._type_needs_destructor(ArenaType()), "Arena")
    self.assertEqual(
        transpiler._type_needs_destructor(RefType(PrimitiveType("int"))), "Ref"
    )
    self.assertEqual(
        transpiler._type_needs_destructor(SharedRefType(PrimitiveType("int"))),
        "SharedRef",
    )
    self.assertEqual(
        transpiler._type_needs_destructor(OptionalType(ArenaType())), "Arena"
    )

    # Struct with __del__ method not yet in structs_with_destructor
    direct_dtor = StructType("DirectDtor")
    direct_dtor.methods["__del__"] = StructMethod(
        "__del__", FunctionType([], PrimitiveType("void")), None
    )
    self.assertEqual(
        transpiler._type_needs_destructor(direct_dtor), "DirectDtor"
    )

    # Prototype structs never need stack destructors
    proto_st = StructType("ProtoThing", is_prototype=True)
    proto_st.methods["__del__"] = StructMethod(
        "__del__", FunctionType([], PrimitiveType("void")), None
    )
    self.assertIsNone(transpiler._type_needs_destructor(proto_st))

    # Nested struct field requiring destructor
    wrapper = StructType("Wrapper")
    wrapper.fields["res"] = StructField(
        name="res", field_type=direct_dtor, is_mutable=False
    )
    self.assertEqual(transpiler._type_needs_destructor(wrapper), "Wrapper")

    # Cycle detection prevents infinite recursion
    cyclic = StructType("Cyclic")
    cyclic.fields["next"] = StructField(
        name="next", field_type=cyclic, is_mutable=False
    )
    self.assertIsNone(transpiler._type_needs_destructor(cyclic))

  def test_expr_destructible_struct_fallbacks(self):
    """Verifies _expr_destructible_struct for MultiReturnType and untyped AST nodes."""
    from src.code_gen.python_transpiler import PythonTranspiler
    from src.parser.ast import (
        CallNode,
        EllipsisPatternNode,
        IdentifierNode,
        LiteralNode,
        MatchCaseNode,
        MatchExprNode,
        MemberAccessNode,
        MoveNode,
        StructInitializerNode,
        TernaryExprNode,
        YieldNode,
    )
    from src.semantics.types import MultiReturnType, PrimitiveType, StructType

    transpiler = PythonTranspiler()
    transpiler.structs_with_destructor.add("Res")
    transpiler.func_return_types["make_res"] = ["int", "Res"]
    transpiler.method_return_types[("Factory", "build")] = ["Res"]
    transpiler.variable_types["factory"] = "Factory"
    transpiler.variable_types["r_unmangled"] = "Res"
    transpiler.variable_types[transpiler._mangle_name("from")] = "Res"

    # MultiReturnType in-bounds and out-of-bounds
    multi_expr = LiteralNode(0, "int")
    multi_expr.inferred_type = MultiReturnType(
        [PrimitiveType("int"), StructType("Res")]
    )
    self.assertIsNone(
        transpiler._expr_destructible_struct(multi_expr, return_index=0)
    )
    self.assertEqual(
        transpiler._expr_destructible_struct(multi_expr, return_index=1), "Res"
    )
    self.assertIsNone(
        transpiler._expr_destructible_struct(multi_expr, return_index=5)
    )

    # StructInitializerNode
    self.assertEqual(
        transpiler._expr_destructible_struct(StructInitializerNode("Res", [])),
        "Res",
    )
    self.assertIsNone(
        transpiler._expr_destructible_struct(
            StructInitializerNode("Plain", [])
        )
    )

    # CallNode with IdentifierNode (constructor & function return)
    self.assertEqual(
        transpiler._expr_destructible_struct(
            CallNode(IdentifierNode("Res"), [])
        ),
        "Res",
    )
    self.assertEqual(
        transpiler._expr_destructible_struct(
            CallNode(IdentifierNode("make_res"), []), return_index=1
        ),
        "Res",
    )
    self.assertIsNone(
        transpiler._expr_destructible_struct(
            CallNode(IdentifierNode("make_res"), []), return_index=0
        )
    )

    # CallNode with MemberAccessNode (share / upgrade / method_return_types)
    share_access = MemberAccessNode(IdentifierNode("sr"), "share", False)
    share_access.is_shared_ref_share = True
    self.assertEqual(
        transpiler._expr_destructible_struct(CallNode(share_access, [])),
        "SharedRef",
    )

    upgrade_access = MemberAccessNode(IdentifierNode("wr"), "upgrade", False)
    upgrade_access.is_weak_ref_upgrade = True
    self.assertEqual(
        transpiler._expr_destructible_struct(CallNode(upgrade_access, [])),
        "SharedRef",
    )

    method_access = MemberAccessNode(IdentifierNode("factory"), "build", False)
    self.assertEqual(
        transpiler._expr_destructible_struct(CallNode(method_access, [])),
        "Res",
    )

    # IdentifierNode and MoveNode (mangled and unmangled)
    self.assertEqual(
        transpiler._expr_destructible_struct(IdentifierNode("from")), "Res"
    )
    self.assertEqual(
        transpiler._expr_destructible_struct(MoveNode("r_unmangled")), "Res"
    )
    self.assertIsNone(
        transpiler._expr_destructible_struct(IdentifierNode("unknown_var"))
    )

    # Fallback with unmangled name when mangled name differs
    transpiler.variable_types.pop(transpiler._mangle_name("from"))
    transpiler.variable_types["from"] = "Res"
    self.assertEqual(
        transpiler._expr_destructible_struct(IdentifierNode("from")), "Res"
    )

    # TernaryExprNode
    ternary = TernaryExprNode(
        LiteralNode(True, "bool"),
        LiteralNode(0, "int"),
        StructInitializerNode("Res", []),
    )
    self.assertEqual(transpiler._expr_destructible_struct(ternary), "Res")

    # MatchExprNode with BlockNode + YieldNode
    match_block = MatchExprNode(
        IdentifierNode("x"),
        [
            MatchCaseNode(
                EllipsisPatternNode(),
                BlockNode([YieldNode([StructInitializerNode("Res", [])])]),
            )
        ],
    )
    self.assertEqual(transpiler._expr_destructible_struct(match_block), "Res")

    # MatchExprNode with direct expression body
    match_expr = MatchExprNode(
        IdentifierNode("x"),
        [MatchCaseNode(EllipsisPatternNode(), StructInitializerNode("Res", []))],
    )
    self.assertEqual(transpiler._expr_destructible_struct(match_expr), "Res")

  def test_is_owned_unwrap_expr_and_register_binding_destructibles(self):
    """Verifies _is_owned_unwrap_expr and _register_binding_destructibles."""
    from src.code_gen.base_transpiler import BaseTranspiler
    from src.code_gen.python_transpiler import PythonTranspiler
    from src.parser.ast import (
        CallNode,
        IdentifierNode,
        LiteralNode,
        MemberAccessNode,
        MoveNode,
        StructInitializerNode,
    )

    self.assertTrue(BaseTranspiler._is_owned_unwrap_expr(MoveNode("r")))
    self.assertFalse(BaseTranspiler._is_owned_unwrap_expr(IdentifierNode("r")))

    arr_get = MemberAccessNode(IdentifierNode("arr"), "get", False)
    arr_get.is_array_method = True
    self.assertFalse(BaseTranspiler._is_owned_unwrap_expr(CallNode(arr_get, [])))
    self.assertTrue(
        BaseTranspiler._is_owned_unwrap_expr(StructInitializerNode("Res", []))
    )

    transpiler = PythonTranspiler()
    transpiler.structs_with_destructor.add("Res")
    transpiler.variable_types["r"] = "Res"

    # Non-destructible expression registers nothing
    block1 = BlockNode([])
    self.assertEqual(
        transpiler._register_binding_destructibles(
            LiteralNode(1, "int"), ["a"], block1, is_unwrap=False
        ),
        [],
    )

    # Borrowed unwrap registers nothing
    block2 = BlockNode([])
    self.assertEqual(
        transpiler._register_binding_destructibles(
            IdentifierNode("r"), ["a"], block2, is_unwrap=True
        ),
        [],
    )

    # Owned unwrap registers destructible bindings on then_block
    block3 = BlockNode([])
    registered = transpiler._register_binding_destructibles(
        MoveNode("r"), ["a", "b"], block3, is_unwrap=True
    )
    self.assertEqual(registered, ["a", "b"])
    self.assertEqual(block3._block_destructibles, ["a", "b"])
    self.assertEqual(transpiler.variable_types["a"], "Res")
    self.assertEqual(transpiler.variable_types["b"], "Res")

  def test_init_subclass_enforces_abstract_methods_at_definition_time(self):
    """Concrete BaseTranspiler subclasses fail at definition time if incomplete."""
    from abc import ABC, abstractmethod

    from src.code_gen.base_transpiler import BaseTranspiler

    with self.assertRaises(TypeError) as ctx:
      class IncompleteTranspiler(BaseTranspiler):
        pass

    self.assertIn("IncompleteTranspiler", str(ctx.exception))
    self.assertIn("transpile", str(ctx.exception))

    # Intermediate abstract bases can opt out via allow_abstract=True or ABC.
    class AbstractHelperA(BaseTranspiler, allow_abstract=True):
      @abstractmethod
      def extra_hook(self):
        pass

    class AbstractHelperB(BaseTranspiler, ABC):
      pass

    with self.assertRaises(TypeError) as ctx2:
      class MissingExtraHook(AbstractHelperA):
        pass

    self.assertIn("extra_hook", str(ctx2.exception))
    self.assertTrue(issubclass(AbstractHelperB, BaseTranspiler))


if __name__ == "__main__":
  unittest.main()
