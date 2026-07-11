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
  )
except ModuleNotFoundError:
  from src.semantics.symbol_table import (
      SymbolTable,
      PrimitiveType,
      OptionalType,
      ArrayType,
      NoneType,
      VariableSymbol,
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

    self.assertEqual(arr_int, ArrayType(self.int_type))
    self.assertNotEqual(arr_int, arr_float)

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


if __name__ == "__main__":
  unittest.main()
