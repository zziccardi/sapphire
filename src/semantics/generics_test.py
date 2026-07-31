"""Unit tests for Generics (Parametric Polymorphism) in Sapphire."""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from semantics.type_checker import TypeChecker, SemanticError
  from semantics.symbol_table import GenericTypeParameter, StructType, TraitType, PrimitiveType
  from code_gen.python_transpiler import PythonTranspiler
  from code_gen.lua_transpiler import LuaTranspiler
except ModuleNotFoundError:  # pragma: no cover
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
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
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
    self.assertIn("class Pair__string_int", py_code)
    lua_code = LuaTranspiler().transpile(ast)
    self.assertIn("Pair__string_int", lua_code)

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
    try:
      from parser.ast import BasicTypeNode
    except ImportError:  # pragma: no cover
      from src.parser.ast import BasicTypeNode
    btn = BasicTypeNode("int")
    sub = tc._substitute_ast(btn, {})
    self.assertEqual(sub.name, "int")
