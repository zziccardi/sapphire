"""Unit tests for Sapphire type system and symbol table in symbol_table.py.

This module verifies type compatibility rules, lexical scope resolution,
shadowing, and error handling for the Sapphire symbol table.
"""

import unittest

try:
  from semantics.symbol_table import (
      SymbolTable,
      PrimitiveType,
      OptionalType,
      ArrayType,
      NoneType,
      VariableSymbol,
      FunctionType,
      StructType,
      TraitType,
      EnumType,
      Type,
  )
except ModuleNotFoundError:
  from src.semantics.symbol_table import (
      SymbolTable,
      PrimitiveType,
      OptionalType,
      ArrayType,
      NoneType,
      VariableSymbol,
      FunctionType,
      StructType,
      TraitType,
      EnumType,
      Type,
  )


class TestSymbolTable(unittest.TestCase):
  """Unit tests for the SymbolTable and Sapphire Type System."""

  def setUp(self):
    self.sym_tab = SymbolTable()
    self.int_type = PrimitiveType("int")
    self.float_type = PrimitiveType("float")
    self.string_type = PrimitiveType("string")
    self.bool_type = PrimitiveType("bool")

  def test_primitive_type_equality(self):
    """Verifies that primitive types equal only their identical type counterparts."""
    self.assertEqual(self.int_type, PrimitiveType("int"))
    self.assertNotEqual(self.int_type, self.float_type)
    self.assertNotEqual(self.int_type, self.string_type)

  def test_type_compatibility_primitives(self):
    """Verifies assignment compatibility of primitive types."""
    # int is compatible with float
    self.assertTrue(self.int_type.is_compatible(self.float_type))
    # float is NOT compatible with int
    self.assertFalse(self.float_type.is_compatible(self.int_type))
    # int is not compatible with string
    self.assertFalse(self.int_type.is_compatible(self.string_type))

  def test_optional_compatibility(self):
    """Verifies assignment compatibility rules regarding optional types (null safety)."""
    opt_int = OptionalType(self.int_type)
    opt_float = OptionalType(self.float_type)

    # T is compatible with T?
    self.assertTrue(self.int_type.is_compatible(opt_int))
    # T? is NOT compatible with T
    self.assertFalse(opt_int.is_compatible(self.int_type))

    # none is compatible with any optional T?
    self.assertTrue(NoneType().is_compatible(opt_int))
    self.assertTrue(NoneType().is_compatible(opt_float))
    # none is NOT compatible with non-optionals
    self.assertFalse(NoneType().is_compatible(self.int_type))

    # Compatible primitives inside optionals (int -> float?)
    self.assertTrue(self.int_type.is_compatible(opt_float))

  def test_array_compatibility(self):
    """Verifies assignment compatibility of array types."""
    arr_int = ArrayType(self.int_type)
    arr_float = ArrayType(self.float_type)
    arr_int_size = ArrayType(self.int_type, size=3)

    self.assertEqual(arr_int, ArrayType(self.int_type))
    self.assertNotEqual(arr_int, arr_float)
    self.assertEqual(arr_int_size, ArrayType(self.int_type, size=3))
    self.assertNotEqual(arr_int, arr_int_size)
    self.assertTrue(arr_int_size.is_compatible(arr_int))
    self.assertTrue(arr_int.is_compatible(arr_int_size))

  def test_lexical_scoping(self):
    """Verifies that nested scopes resolve identifiers and support shadowing."""
    # Define in global scope
    var_a = VariableSymbol("a", self.int_type, is_mutable=False)
    self.sym_tab.define("a", var_a)

    self.assertEqual(self.sym_tab.lookup("a"), var_a)

    # Enter nested scope
    self.sym_tab.enter_scope()
    self.assertEqual(self.sym_tab.lookup("a"), var_a)  # Resolves to parent scope

    # Shadow 'a' in nested scope
    var_a_shadowed = VariableSymbol("a", self.string_type, is_mutable=True)
    self.sym_tab.define("a", var_a_shadowed)
    self.assertEqual(self.sym_tab.lookup("a"), var_a_shadowed)  # Resolves to current scope

    # Exit nested scope
    self.sym_tab.exit_scope()
    self.assertEqual(self.sym_tab.lookup("a"), var_a)  # Restored to original

  def test_exit_global_scope_fails(self):
    """Verifies that exiting the global scope raises a RuntimeError."""
    with self.assertRaises(RuntimeError):
      self.sym_tab.exit_scope()

  def test_type_formatting_and_non_comparisons(self):
    """Verifies repr strings and comparing types/symbols with incompatible classes or objects."""
    # Lookup non-existent
    self.assertIsNone(self.sym_tab.lookup("non-existent-symbol"))
    self.assertIsNone(self.sym_tab.lookup_type("NonExistentType"))

    # PrimitiveType non-equality with other classes
    self.assertFalse(self.int_type == 42)
    self.assertFalse(self.int_type == PrimitiveType("float"))

    # Type __eq__ fallback
    self.assertFalse(Type() == "not-a-type")

    # OptionalType repr and non-equality
    opt_int = OptionalType(self.int_type)
    self.assertEqual(repr(opt_int), "int?")
    self.assertFalse(opt_int == self.int_type)
    self.assertTrue(opt_int == OptionalType(self.int_type))

    # FunctionType non-equality
    func_type = FunctionType([self.int_type], self.float_type)
    self.assertFalse(func_type == self.int_type)
    
    # FunctionType repr with var parameter
    func_type_var = FunctionType([self.int_type], self.float_type, [True])
    self.assertEqual(repr(func_type_var), "(var int) -> float")

    # StructType __eq__ and __repr__
    st1 = StructType("A")
    st2 = StructType("B")
    self.assertFalse(st1 == st2)
    self.assertFalse(st1 == self.int_type)
    self.assertEqual(repr(st1), "A")

    # TraitType __eq__ and __repr__
    tr1 = TraitType("T1")
    tr2 = TraitType("T2")
    self.assertFalse(tr1 == tr2)
    self.assertFalse(tr1 == self.int_type)
    self.assertEqual(repr(tr1), "trait T1")

    # NoneType repr
    self.assertEqual(repr(NoneType()), "none")

    # ArrayType repr and non-equality
    arr = ArrayType(self.int_type)
    self.assertEqual(repr(arr), "[int]")
    arr_sized = ArrayType(self.int_type, size=5)
    self.assertEqual(repr(arr_sized), "[int; 5]")
    self.assertFalse(arr == self.int_type)

    # EnumType __eq__, __repr__, and compatibility
    e1 = EnumType("Color", {"Red": 0})
    e2 = EnumType("Status", {"Ok": 200})
    self.assertEqual(e1, EnumType("Color"))
    self.assertFalse(e1 == e2)
    self.assertFalse(e1 == "not an EnumType")
    self.assertEqual(repr(e1), "Color")
    self.assertFalse(self.int_type.is_compatible(e1))
    self.assertTrue(e1.is_compatible(self.int_type))

  def test_multi_return_type_methods(self):
    """Verifies MultiReturnType repr, equality, and FunctionType.return_types property."""
    try:
      from semantics.symbol_table import MultiReturnType, FunctionType, PrimitiveType
    except ModuleNotFoundError:
      from src.semantics.symbol_table import MultiReturnType, FunctionType, PrimitiveType

    m1 = MultiReturnType([PrimitiveType("float"), PrimitiveType("float")])
    m2 = MultiReturnType([PrimitiveType("float"), PrimitiveType("float")])
    self.assertEqual(m1, m2)
    self.assertFalse(m1 == "not a MultiReturnType")
    self.assertEqual(repr(m1), "(float, float)")

    fn_multi = FunctionType([], [PrimitiveType("int"), PrimitiveType("float")])
    self.assertEqual(fn_multi.return_types, [PrimitiveType("int"), PrimitiveType("float")])

    fn_single = FunctionType([], PrimitiveType("int"))
    self.assertEqual(fn_single.return_types, [PrimitiveType("int")])

    fn_void = FunctionType([], PrimitiveType("none"))
    self.assertEqual(fn_void.return_types, [])

    fn_empty_list = FunctionType([], [])
    self.assertEqual(fn_empty_list.return_types, [])

  def test_module_symbol_and_type(self):
    """Verifies ModuleType repr and ModuleSymbol lookup_export."""
    try:
      from semantics.symbol_table import ModuleType, ModuleSymbol, PrimitiveType, VariableSymbol
    except ModuleNotFoundError:
      from src.semantics.symbol_table import ModuleType, ModuleSymbol, PrimitiveType, VariableSymbol

    mod_t = ModuleType("lib.love2d.enums")
    self.assertEqual(repr(mod_t), "module(lib.love2d.enums)")

    sym_x = VariableSymbol("x", PrimitiveType("int"), is_mutable=False)
    mod_sym = ModuleSymbol("enums", "lib.love2d.enums", exports={"x": sym_x})
    self.assertEqual(mod_sym.lookup_export("x"), sym_x)
    self.assertIsNone(mod_sym.lookup_export("y"))

  def test_map_type_methods(self):
    """Verifies MapType __eq__, __repr__, and is_compatible methods."""
    try:
      from semantics.symbol_table import MapType, PrimitiveType, OptionalType
    except ModuleNotFoundError:
      from src.semantics.symbol_table import MapType, PrimitiveType, OptionalType

    m1 = MapType(PrimitiveType("string"), PrimitiveType("int"))
    m2 = MapType(PrimitiveType("string"), PrimitiveType("int"))
    m3 = MapType(PrimitiveType("int"), PrimitiveType("int"))

    self.assertEqual(m1, m2)
    self.assertNotEqual(m1, m3)
    self.assertFalse(m1 == "not a MapType")
    self.assertEqual(repr(m1), "[string: int]")

    self.assertTrue(m1.is_compatible(m2))
    self.assertTrue(m1.is_compatible(OptionalType(m2)))
    self.assertFalse(m1.is_compatible(PrimitiveType("int")))


if __name__ == "__main__":
  unittest.main()
