"""Unit and integration tests for CallVisitorMixin and TypeChecker helpers."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast import (
    ArrayTypeNode,
    BasicTypeNode,
    FunctionTypeNode,
    IdentifierNode,
    MapTypeNode,
    MemberAccessNode,
    OptionalTypeNode,
)
from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.symbol_table import VariableSymbol
from sapphire.semantics.type_checker import TypeChecker
from sapphire.semantics.types import (
    ArrayType,
    CoroutineType,
    FunctionType,
    GenericTypeParameter,
    InferredType,
    MapType,
    NoneType,
    OptionalType,
    PrimitiveType,
    RefType,
    SharedRefType,
    StructField,
    StructType,
    WeakRefType,
)


def _check_code(code: str) -> TypeChecker:
  lexer = SapphireLexer(InputStream(code))
  parser = SapphireParser(CommonTokenStream(lexer))
  ast = ASTBuilder().visitProgram(parser.program())
  checker = TypeChecker()
  checker.check(ast)
  return checker


class TestCallVisitorHelpers(unittest.TestCase):
  """Tests generic unification and type-node reconstruction in CallVisitorMixin."""

  def test_unify_generic_type_all_containers(self):
    checker = TypeChecker()
    t_param = GenericTypeParameter("T")
    k_param = GenericTypeParameter("K")
    v_param = GenericTypeParameter("V")
    int_t = PrimitiveType("int")
    str_t = PrimitiveType("String")
    float_t = PrimitiveType("float")

    # RefType / SharedRefType arg auto-deref into non-ref container param [T]
    inferred = {}
    checker._unify_generic_type(
        ArrayType(t_param), RefType(ArrayType(int_t)), inferred
    )
    self.assertEqual(inferred["T"], int_t)

    # OptionalType -> OptionalType
    inferred = {}
    checker._unify_generic_type(
        OptionalType(t_param), OptionalType(str_t), inferred
    )
    self.assertEqual(inferred["T"], str_t)

    # MapType -> MapType
    inferred = {}
    checker._unify_generic_type(
        MapType(k_param, v_param), MapType(str_t, int_t), inferred
    )
    self.assertEqual(inferred["K"], str_t)
    self.assertEqual(inferred["V"], int_t)

    # RefType, SharedRefType, WeakRefType
    for wrapper in (RefType, SharedRefType, WeakRefType):
      inferred = {}
      checker._unify_generic_type(wrapper(t_param), wrapper(int_t), inferred)
      self.assertEqual(inferred["T"], int_t)

    # CoroutineType
    inferred = {}
    checker._unify_generic_type(
        CoroutineType(t_param), CoroutineType(float_t), inferred
    )
    self.assertEqual(inferred["T"], float_t)

    # FunctionType
    inferred = {}
    checker._unify_generic_type(
        FunctionType([k_param], v_param),
        FunctionType([str_t], int_t),
        inferred,
    )
    self.assertEqual(inferred["K"], str_t)
    self.assertEqual(inferred["V"], int_t)

  def test_type_to_type_node_all_variants(self):
    checker = TypeChecker()
    int_t = PrimitiveType("int")
    str_t = PrimitiveType("String")

    opt_node = checker._type_to_type_node(OptionalType(int_t))
    self.assertIsInstance(opt_node, OptionalTypeNode)

    dyn_arr = checker._type_to_type_node(ArrayType(int_t, is_fixed_size=False))
    self.assertIsInstance(dyn_arr, ArrayTypeNode)
    self.assertIsNone(dyn_arr.size)

    fix_arr = checker._type_to_type_node(
        ArrayType(int_t, is_fixed_size=True, size=4)
    )
    self.assertIsInstance(fix_arr, ArrayTypeNode)
    self.assertEqual(fix_arr.size, 4)

    map_node = checker._type_to_type_node(MapType(str_t, int_t))
    self.assertIsInstance(map_node, MapTypeNode)

    fn_node = checker._type_to_type_node(FunctionType([int_t], str_t))
    self.assertIsInstance(fn_node, FunctionTypeNode)

    ref_node = checker._type_to_type_node(RefType(int_t))
    self.assertEqual(ref_node.name, "Ref")

    sref_node = checker._type_to_type_node(SharedRefType(int_t))
    self.assertEqual(sref_node.name, "SharedRef")

    wref_node = checker._type_to_type_node(WeakRefType(int_t))
    self.assertEqual(wref_node.name, "WeakRef")

    coro_void = checker._type_to_type_node(CoroutineType(NoneType()))
    self.assertEqual(coro_void.name, "Coroutine")
    self.assertEqual(coro_void.type_args, [])

    coro_int = checker._type_to_type_node(CoroutineType(int_t))
    self.assertEqual(coro_int.name, "Coroutine")
    self.assertEqual(len(coro_int.type_args), 1)

    none_node = checker._type_to_type_node(NoneType())
    self.assertIsInstance(none_node, BasicTypeNode)
    self.assertEqual(none_node.name, "void")

  def test_generic_inference_with_maps_and_optionals(self):
    """End-to-end generic call inference for Map<K, V> and T? parameters."""
    code = """
    func map_size<K, V>(m: Map<K, V>): int {
      return m.size();
    }
    func unwrap_or<T>(opt: T?, fallback: T): T {
      return opt ?? fallback;
    }
    func demo(): int {
      let m: Map<String, int> = {"a": 1, "b": 2};
      let o: int? = 42;
      return map_size(m) + unwrap_or(o, 0);
    }
    """
    checker = _check_code(code)
    self.assertEqual(checker.errors, [])


class TestTypeCheckerHelpers(unittest.TestCase):
  """Tests _widen_types, _find_immutable_field_in_chain, has_shared_ref_base, _get_target_symbol."""

  def test_widen_types_matrix(self):
    checker = TypeChecker()
    int_t = PrimitiveType("int")
    float_t = PrimitiveType("float")
    str_t = PrimitiveType("String")
    none_t = NoneType()
    inf_t = InferredType()

    # InferredType on left / right
    self.assertEqual(checker._widen_types(inf_t, int_t), int_t)
    self.assertEqual(checker._widen_types(int_t, inf_t), int_t)

    # Both NoneType
    self.assertEqual(checker._widen_types(none_t, none_t), none_t)

    # Both OptionalType
    self.assertEqual(
        checker._widen_types(OptionalType(int_t), OptionalType(float_t)),
        OptionalType(float_t),
    )

    # ArrayType with NoneType elem and numeric widening
    self.assertEqual(
        checker._widen_types(ArrayType(none_t), ArrayType(int_t)),
        ArrayType(int_t, is_fixed_size=False),
    )
    self.assertEqual(
        checker._widen_types(ArrayType(int_t), ArrayType(none_t)),
        ArrayType(int_t, is_fixed_size=False),
    )
    self.assertEqual(
        checker._widen_types(ArrayType(int_t), ArrayType(float_t)),
        ArrayType(float_t, is_fixed_size=False),
    )

    # MapType with NoneType and value widening
    self.assertEqual(
        checker._widen_types(MapType(none_t, none_t), MapType(str_t, int_t)),
        MapType(str_t, int_t),
    )
    self.assertEqual(
        checker._widen_types(MapType(str_t, int_t), MapType(none_t, none_t)),
        MapType(str_t, int_t),
    )
    self.assertEqual(
        checker._widen_types(MapType(str_t, int_t), MapType(str_t, float_t)),
        MapType(str_t, float_t),
    )

    # Asymmetric compatibility (e.g. StructType implementing TraitType)
    from sapphire.semantics.types import TraitType

    trait_t = TraitType("Drawable")
    st_t = StructType("Sprite")
    st_t.implemented_traits.add("Drawable")
    self.assertEqual(checker._widen_types(st_t, trait_t), trait_t)
    self.assertEqual(checker._widen_types(trait_t, st_t), trait_t)

  def test_immutable_field_chain_shared_ref_base_and_target_symbol(self):
    checker = TypeChecker()
    st = StructType("Holder")
    st.fields["ro"] = StructField("ro", PrimitiveType("int"), is_mutable=False)

    # _find_immutable_field_in_chain unwraps OptionalType and RefType
    recv = IdentifierNode("h")
    access = MemberAccessNode(recv, "ro", False)
    checker.node_types[recv] = OptionalType(RefType(st))
    self.assertEqual(
        checker._find_immutable_field_in_chain(access), ("ro", "Holder")
    )

    # has_shared_ref_base via symbol_table fallback and OptionalType(SharedRefType)
    sr_sym = VariableSymbol(
        "sr", OptionalType(SharedRefType(st)), is_mutable=False
    )
    checker.symbol_table.define("sr", sr_sym)
    sr_ident = IdentifierNode("sr")
    self.assertTrue(checker.has_shared_ref_base(sr_ident))

    # _get_target_symbol recurses through MemberAccessNode
    sr_member = MemberAccessNode(sr_ident, "ro", False)
    self.assertIs(checker._get_target_symbol(sr_member), sr_sym)


if __name__ == "__main__":
  unittest.main()
