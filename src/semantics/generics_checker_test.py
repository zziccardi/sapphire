"""Unit tests for GenericsChecker in src/semantics/generics_checker.py."""

import unittest
from src.parser.ast import BasicTypeNode
from src.semantics.symbol_table import (
    PrimitiveType,
    OptionalType,
    ArrayType,
    MapType,
    FunctionType,
)
from src.semantics.generics_checker import GenericsChecker


class TestGenericsChecker(unittest.TestCase):
  """Unit tests for generic AST substitution and type mangling."""

  def test_substitute_ast_basic_type(self):
    node = BasicTypeNode("T")
    mapping = {"T": BasicTypeNode("int")}
    res = GenericsChecker.substitute_ast(node, mapping)
    self.assertEqual(res.name, "int")

  def test_substitute_ast_nested_type_args(self):
    node = BasicTypeNode("Vector", type_args=[BasicTypeNode("T")])
    mapping = {"T": BasicTypeNode("float")}
    res = GenericsChecker.substitute_ast(node, mapping)
    self.assertEqual(res.name, "Vector")
    self.assertEqual(res.type_args[0].name, "float")

  def test_mangle_type_name(self):
    opt_type = OptionalType(PrimitiveType("int"))
    self.assertEqual(GenericsChecker.mangle_type_name(opt_type), "Opt_int")

    arr_type = ArrayType(PrimitiveType("float"))
    self.assertEqual(GenericsChecker.mangle_type_name(arr_type), "Arr_float")

    map_type = MapType(PrimitiveType("String"), PrimitiveType("bool"))
    self.assertEqual(GenericsChecker.mangle_type_name(map_type), "Map_String_bool")

    fn_type = FunctionType([PrimitiveType("int")], PrimitiveType("void"))
    self.assertEqual(GenericsChecker.mangle_type_name(fn_type), "Fn_int_to_void")
