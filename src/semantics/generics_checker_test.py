"""Unit tests for GenericsChecker in src/semantics/generics_checker.py."""

import unittest

from src.parser.ast import BasicTypeNode
from src.semantics.generics_checker import GenericsChecker
from src.semantics.symbol_table import (
  ArrayType,
  FunctionType,
  MapType,
  OptionalType,
  PrimitiveType,
)


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

  def test_substitute_ast_none_and_non_ast(self):
    self.assertIsNone(GenericsChecker.substitute_ast(None, {}))
    self.assertEqual(GenericsChecker.substitute_ast("literal_string", {}), "literal_string")

  def test_mangle_fixed_array_includes_size(self):
    fixed2 = ArrayType(PrimitiveType("int"), size=2, is_fixed_size=True)
    fixed3 = ArrayType(PrimitiveType("int"), size=3, is_fixed_size=True)
    dyn = ArrayType(PrimitiveType("int"), is_fixed_size=False)
    self.assertEqual(GenericsChecker.mangle_type_name(fixed2), "FixedArr_2_int")
    self.assertEqual(GenericsChecker.mangle_type_name(fixed3), "FixedArr_3_int")
    self.assertEqual(GenericsChecker.mangle_type_name(dyn), "Arr_int")

  def _check_code(self, code: str):
    from antlr4 import CommonTokenStream, InputStream

    from src.parser.ast_builder import ASTBuilder
    from src.parser.gen.SapphireLexer import SapphireLexer
    from src.parser.gen.SapphireParser import SapphireParser
    from src.semantics.type_checker import TypeChecker

    stream = CommonTokenStream(SapphireLexer(InputStream(code)))
    parser = SapphireParser(stream)
    tree = parser.program()
    self.assertEqual(parser.getNumberOfSyntaxErrors(), 0)
    ast = ASTBuilder().visit(tree)
    checker = TypeChecker()
    checker.check(ast)
    return checker

  def test_phase4_generic_monomorphization_and_inference(self):
    from src.common.errors import SemanticError

    # 1. Generic struct implementing trait + impl block with renamed param U
    self._check_code("""
    trait Showable {
      func show(): String;
    }
    struct Box<T> {
      var val: T;
    }
    impl Box<U> {
      func get(): U { return self.val; }
    }
    impl Showable for Box<T> {
      func show(): String { return "box"; }
    }
    func print_it(s: Showable): String { return s.show(); }
    func main() {
      let b = Box<int> { val = 42 };
      let v: int = b.get();
      let s: String = print_it(b);
    }
    """)

    # 2. Compound generic function inference ([T], T?) + move arg without double-move
    self._check_code("""
    func first_elem<T>(arr: [T]): T {
      return arr[0];
    }
    func consume<T>(x: T) {}
    func main() {
      let n: int = first_elem([1, 2, 3]);
      let r = Ref(10);
      consume(move r);
    }
    """)

    # 3. Uninferrable generic type param reports error instead of defaulting to int
    with self.assertRaises(SemanticError) as ctx:
      self._check_code("""
      func make_none<T>(): T? { return none; }
      func main() { let x = make_none(); }
      """)
    self.assertIn("Cannot infer generic type parameter 'T'", str(ctx.exception))

    # 4. Recursive generic instantiation hits depth guard instead of RecursionError
    with self.assertRaises(SemanticError) as ctx:
      self._check_code("""
      struct Wrap<T> { var inner: T; }
      func boom<T>(x: T) {
        let w = Wrap<T> { inner = x };
        boom<Wrap<T>>(w);
      }
      func main() { boom<int>(1); }
      """)
    self.assertIn("Maximum generic monomorphization recursion depth", str(ctx.exception))

    # 5. Generic type-arg arity mismatch
    with self.assertRaises(SemanticError) as ctx:
      self._check_code("""
      struct Pair<A, B> { var a: A; var b: B; }
      func main() { let p = Pair<int> { a = 1, b = 2 }; }
      """)
    self.assertIn("expects 2 type argument(s), got 1", str(ctx.exception))

    # 6. Concrete struct with typo trait type arg is NOT silently skipped
    with self.assertRaises(SemanticError) as ctx:
      self._check_code("""
      trait Producer<T> { func produce(): T; }
      struct Concrete { var x: int; }
      impl Producer<TypoType> for Concrete {
        func produce(): int { return self.x; }
      }
      """)
    self.assertIn("Undefined type 'TypoType'", str(ctx.exception))

    # 7. Calling generic function inside a loop/freeze does not leak caller scope
    self._check_code("""
    func id<T>(x: T): T { return x; }
    func main() {
      var arr = [1, 2, 3];
      for x in arr {
        let y: int = id(x);
      }
    }
    """)
