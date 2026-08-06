"""Unit tests for Generics (Parametric Polymorphism) in Sapphire."""

import unittest
from antlr4 import InputStream, CommonTokenStream

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.semantics.type_checker import TypeChecker, SemanticError
from src.semantics.symbol_table import GenericTypeParameter, StructType, TraitType, PrimitiveType
from src.code_gen.python_transpiler import PythonTranspiler
from src.code_gen.lua_transpiler import LuaTranspiler



class TestGenerics(unittest.TestCase):
  """Suite of unit tests verifying generic struct and function behavior."""

  def _check(self, code: str):
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    tree = parser.program()
    if parser.getNumberOfSyntaxErrors() > 0:
      raise SyntaxError(f"Syntax error while parsing code string for type checking:\n{code}")
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    return ast

  def test_generic_struct_and_impl(self):
    """Verifies that generic structs and generic impl blocks monomorphize cleanly."""
    code = """
    struct Box<T> {
      var val: T;
    }

    impl Box<T> {
      func __init__(val: T) {
        self.val = val;
      }
    }

    func main() {
      let b1 = Box<int>(val = 42);
      let b2 = Box<int>(val = 100);
    }
    """
    ast = self._check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("class Box__int", py_code)
    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn("Box__int", lua_code)

  def test_generic_function_inference(self):
    """Verifies contextual inference for generic function arguments."""
    code = """
    func identity<T>(val: T): T {
      return val;
    }

    func main() {
      let x = identity(100);
      let y = identity<float>(3.14);
      let z = identity(200);
    }
    """
    ast = self._check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("def identity__int", py_code)
    self.assertIn("def identity__float", py_code)
    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn("function identity__int", lua_code)
    self.assertIn("function identity__float", lua_code)

  def test_generic_struct_initializer(self):
    """Verifies struct initializers with generic type arguments."""
    code = """
    struct Pair<K, V> {
      var key: K;
      var value: V;
    }

    func main() {
      let p = Pair<String, int> {
        key = "score",
        value = 100,
      };
    }
    """
    ast = self._check(code)
    py_code = PythonTranspiler().transpile(ast)
    self.assertIn("class Pair__String_int", py_code)
    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn("Pair__String_int", lua_code)

  def test_generic_trait_declaration_and_impl_variations(self):
    """Verifies generic trait declarations and impl syntax variations."""
    code = """
    trait Container<T> {
      func get(self): T;
    }

    struct Item<T> {
      var val: T;
    }

    struct Simple {
      var count: int;
    }

    impl Container<T> for Item<T> {
      func get(self): T {
        return self.val;
      }
    }

    impl Container<T> for Simple {
      func get(self): T {
        return 0;
      }
    }

    impl Container for Item<T> {
      func get(self): int {
        return 1;
      }
    }

    func main() {}
    """
    ast = self._check(code)

  def test_nested_generic_type_substitution(self):
    """Verifies nested generic type parameter substitution."""
    code = """
    struct Inner<T> {
      var val: T;
    }

    struct Outer<U> {
      var item: Inner<U>;
    }

    func main() {
      let o = Outer<int> {
        item = Inner<int> { val = 10 }
      };
    }
    """
    ast = self._check(code)

  def test_generic_type_errors(self):
    """Verifies errors when invoking generic struct constructor or initializer without type arguments."""
    code1 = """
    struct Box<T> {
      var val: T;
    }
    impl<T> Box<T> {
      func __init__(val: T) { self.val = val; }
    }
    func main() {
      let b = Box(val = 1);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code1)
    self.assertIn("requires explicit type arguments", str(ctx.exception))

    code2 = """
    struct Box<T> {
      var val: T;
    }
    func main() {
      let b = Box { val = 1 };
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code2)
    self.assertIn("requires explicit type arguments", str(ctx.exception))

  def test_generic_symbol_table_helpers(self):
    """Verifies GenericTypeParameter methods and repr output for generic types."""
    gt1 = GenericTypeParameter("T")
    gt2 = GenericTypeParameter("T")
    gt3 = GenericTypeParameter("U")
    self.assertEqual(gt1, gt2)
    self.assertNotEqual(gt1, gt3)
    self.assertNotEqual(gt1, "T")
    self.assertTrue(gt1.is_compatible(gt2))
    self.assertTrue(gt1.is_compatible(gt3))
    self.assertEqual(repr(gt1), "T")

    st = StructType("Box", type_params=["T"])
    self.assertEqual(repr(st), "Box<T>")

    tt = TraitType("Container", type_params=["T"])
    self.assertEqual(repr(tt), "trait Container<T>")

  def test_substitute_ast_helpers(self):
    """Verifies AST substitution on None and non-generic BasicTypeNode."""
    tc = TypeChecker()
    self.assertIsNone(tc._substitute_ast(None, {}))
    from src.parser.ast import BasicTypeNode

    btn = BasicTypeNode("int")
    sub = tc._substitute_ast(btn, {})
    self.assertEqual(sub.name, "int")

  def test_complex_generic_monomorphization(self):
    """Verifies monomorphization for generic structs with optional and primitive types."""
    code = """
    struct Box<T> {
      var item: T;
    }
    func main() {
      let b1 = Box<int?> { item = none };
      let b2 = Box<String> { item = "hello" };
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    self.assertIsNotNone(checker.symbol_table.lookup_type("Box__Opt_int"))
    self.assertIsNotNone(checker.symbol_table.lookup_type("Box__String"))

  def test_mangle_type_name_complex_types(self):
    from src.semantics.symbol_table import ArrayType, MapType, FunctionType, PrimitiveType, StringType

    tc = TypeChecker()
    arr_t = ArrayType(PrimitiveType("int"))
    map_t = MapType(StringType(), PrimitiveType("int"))
    fn_t = FunctionType([PrimitiveType("int")], PrimitiveType("float"))
    self.assertEqual(tc._mangle_type_name(arr_t), "Arr_int")
    self.assertEqual(tc._mangle_type_name(map_t), "Map_String_int")
    self.assertEqual(tc._mangle_type_name(fn_t), "Fn_int_to_float")
