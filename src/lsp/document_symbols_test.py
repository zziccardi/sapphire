"""Unit tests for LSP Document Symbol extraction (document_symbols.py)."""

import unittest
from antlr4 import CommonTokenStream, InputStream
from lsprotocol.types import SymbolKind, Range, Position

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.parser.ast import (
    ArrayTypeNode,
    BasicTypeNode,
    EnumDeclNode,
    EnumMemberNode,
    FuncDeclNode,
    FunctionTypeNode,
    ImplBlockNode,
    ImplMemberNode,
    MapTypeNode,
    OptionalTypeNode,
    ParameterNode,
    ProgramNode,
    StructDeclNode,
    StructFieldNode,
    TraitDeclNode,
    TraitMemberNode,
    VarDeclNode,
)
from src.lsp.document_symbols import (
    _create_range,
    _ensure_contained,
    _format_func_signature,
    _format_type_node,
    extract_document_symbols,
)


def _parse_to_ast(source_text: str) -> ProgramNode:
  lexer = SapphireLexer(InputStream(source_text))
  tokens = CommonTokenStream(lexer)
  parser = SapphireParser(tokens)
  return ASTBuilder().visit(parser.program())


class TestDocumentSymbols(unittest.TestCase):

  def test_format_type_node(self):
    self.assertEqual(_format_type_node(None), "")
    self.assertEqual(_format_type_node(BasicTypeNode("int")), "int")
    self.assertEqual(
        _format_type_node(BasicTypeNode("Vector", [BasicTypeNode("float")])),
        "Vector<float>",
    )
    self.assertEqual(
        _format_type_node(OptionalTypeNode(BasicTypeNode("int"))),
        "int?",
    )
    self.assertEqual(
        _format_type_node(ArrayTypeNode(BasicTypeNode("String"))),
        "[String]",
    )
    self.assertEqual(
        _format_type_node(MapTypeNode(BasicTypeNode("String"), BasicTypeNode("int"))),
        "[String: int]",
    )
    self.assertEqual(
        _format_type_node(FunctionTypeNode([BasicTypeNode("int")], [BasicTypeNode("bool")])),
        "(int) -> (bool)",
    )
    # Fallback node
    class DummyNode:
      def __str__(self):
        return "CustomType"
    self.assertEqual(_format_type_node(DummyNode()), "CustomType")

  def test_create_range_and_ensure_contained(self):
    r1 = _create_range(1, 2, 3, 4)
    self.assertEqual(r1.start.line, 0)
    self.assertEqual(r1.start.character, 2)
    self.assertEqual(r1.end.line, 2)
    self.assertEqual(r1.end.character, 4)

    # Edge cases: None or non-positive
    r2 = _create_range(None, None, None, None)
    self.assertEqual(r2.start.line, 0)
    self.assertEqual(r2.start.character, 0)
    self.assertEqual(r2.end.line, 0)
    self.assertEqual(r2.end.character, 1)

    # _ensure_contained clamping start and end
    full = _create_range(5, 5, 10, 10)
    sel_outside_start = _create_range(2, 2, 10, 10)
    _ensure_contained(full, sel_outside_start)
    self.assertEqual(full.start.line, sel_outside_start.start.line)
    self.assertEqual(full.start.character, sel_outside_start.start.character)

    full = _create_range(5, 5, 10, 10)
    sel_outside_start_col = _create_range(5, 2, 10, 10)
    _ensure_contained(full, sel_outside_start_col)
    self.assertEqual(full.start.character, 2)

    full = _create_range(5, 5, 10, 10)
    sel_outside_end = _create_range(5, 5, 15, 15)
    _ensure_contained(full, sel_outside_end)
    self.assertEqual(full.end.line, 14)
    self.assertEqual(full.end.character, 15)

    full = _create_range(5, 5, 10, 10)
    sel_outside_end_col = _create_range(5, 5, 10, 20)
    _ensure_contained(full, sel_outside_end_col)
    self.assertEqual(full.end.character, 20)

  def test_format_func_signature(self):
    sig1 = _format_func_signature([], [])
    self.assertEqual(sig1, "()")

    p1 = ParameterNode(False, "a", BasicTypeNode("int"))
    p2 = ParameterNode(True, "b", BasicTypeNode("String"))
    p3 = ParameterNode(False, "c", None)
    sig2 = _format_func_signature([p1, p2, p3], [BasicTypeNode("bool")])
    self.assertEqual(sig2, "(a: int, var b: String, c): bool")

  def test_extract_document_symbols_invalid_input(self):
    self.assertEqual(extract_document_symbols(None), [])
    self.assertEqual(extract_document_symbols("not an ast"), [])
    empty_ast = ProgramNode(declarations=[])
    self.assertEqual(extract_document_symbols(empty_ast), [])

  def test_extract_struct_and_proto_symbols(self):
    source = """
    struct Point<T>: Base1, Base2 {
      let x: T;
      var y: T;
    }

    proto Enemy {
      var hp: int;
    }
    """
    ast = _parse_to_ast(source)
    symbols = extract_document_symbols(ast)
    self.assertEqual(len(symbols), 2)

    # Struct Point
    pt_sym = symbols[0]
    self.assertEqual(pt_sym.name, "Point")
    self.assertEqual(pt_sym.kind, SymbolKind.Struct)
    self.assertEqual(pt_sym.detail, "<T>: Base1, Base2")
    self.assertEqual(len(pt_sym.children), 2)
    self.assertEqual(pt_sym.children[0].name, "x")
    self.assertEqual(pt_sym.children[0].kind, SymbolKind.Field)
    self.assertEqual(pt_sym.children[0].detail, "T")
    self.assertEqual(pt_sym.children[1].name, "y")
    self.assertEqual(pt_sym.children[1].kind, SymbolKind.Property)
    self.assertEqual(pt_sym.children[1].detail, "T")

    # Proto Enemy
    enemy_sym = symbols[1]
    self.assertEqual(enemy_sym.name, "Enemy")
    self.assertEqual(enemy_sym.kind, SymbolKind.Class)
    self.assertEqual(enemy_sym.detail, "proto")
    self.assertEqual(len(enemy_sym.children), 1)
    self.assertEqual(enemy_sym.children[0].name, "hp")
    self.assertEqual(enemy_sym.children[0].detail, "int")

  def test_extract_enum_symbols(self):
    source = """
    enum Direction {
      North = 1,
      South = "S",
      East,
    }
    """
    ast = _parse_to_ast(source)
    symbols = extract_document_symbols(ast)
    self.assertEqual(len(symbols), 1)

    enum_sym = symbols[0]
    self.assertEqual(enum_sym.name, "Direction")
    self.assertEqual(enum_sym.kind, SymbolKind.Enum)
    self.assertEqual(enum_sym.detail, "enum")
    self.assertEqual(len(enum_sym.children), 3)

    self.assertEqual(enum_sym.children[0].name, "North")
    self.assertEqual(enum_sym.children[0].kind, SymbolKind.EnumMember)
    self.assertEqual(enum_sym.children[0].detail, "= 1")

    self.assertEqual(enum_sym.children[1].name, "South")
    self.assertEqual(enum_sym.children[1].detail, "= S")

    self.assertEqual(enum_sym.children[2].name, "East")
    self.assertIsNone(enum_sym.children[2].detail)

  def test_extract_trait_and_impl_symbols(self):
    source = """
    trait Greeter<T> {
      func greet(target: String): String;
    }

    struct Person {
      let name: String;
    }

    impl Greeter<T> for Person {
      func greet(target: String): String {
        return "Hello " + target;
      }
    }

    impl Person {
      func __init__(name: String) {
        self.name = name;
      }
      func run() {
      }
    }
    """
    ast = _parse_to_ast(source)
    symbols = extract_document_symbols(ast)
    self.assertEqual(len(symbols), 4)

    # 1. Trait Greeter
    trait_sym = symbols[0]
    self.assertEqual(trait_sym.name, "Greeter")
    self.assertEqual(trait_sym.kind, SymbolKind.Interface)
    self.assertEqual(trait_sym.detail, "<T>")
    self.assertEqual(len(trait_sym.children), 1)
    self.assertEqual(trait_sym.children[0].name, "greet")
    self.assertEqual(trait_sym.children[0].kind, SymbolKind.Method)
    self.assertEqual(trait_sym.children[0].detail, "(target: String): String")

    # 2. Struct Person
    struct_sym = symbols[1]
    self.assertEqual(struct_sym.name, "Person")

    # 3. Impl Greeter for Person
    impl1_sym = symbols[2]
    self.assertEqual(impl1_sym.name, "impl Greeter for Person")
    self.assertEqual(impl1_sym.kind, SymbolKind.Namespace)
    self.assertEqual(len(impl1_sym.children), 1)
    self.assertEqual(impl1_sym.children[0].name, "greet")
    self.assertEqual(impl1_sym.children[0].kind, SymbolKind.Method)

    # 4. Impl Person
    impl2_sym = symbols[3]
    self.assertEqual(impl2_sym.name, "impl Person")
    self.assertEqual(len(impl2_sym.children), 2)
    self.assertEqual(impl2_sym.children[0].name, "__init__")
    self.assertEqual(impl2_sym.children[0].kind, SymbolKind.Constructor)
    self.assertEqual(impl2_sym.children[0].detail, "(name: String)")
    self.assertEqual(impl2_sym.children[1].name, "run")
    self.assertEqual(impl2_sym.children[1].kind, SymbolKind.Method)

  def test_extract_function_and_variable_symbols(self):
    source = """
    let PI: float = 3.14159;
    var width: int, height: int = 800, 600;

    func compute(bonus: float): float {
      return bonus * 2.0;
    }
    """
    ast = _parse_to_ast(source)
    symbols = extract_document_symbols(ast)
    self.assertEqual(len(symbols), 4)

    # PI (Constant)
    pi_sym = symbols[0]
    self.assertEqual(pi_sym.name, "PI")
    self.assertEqual(pi_sym.kind, SymbolKind.Constant)
    self.assertEqual(pi_sym.detail, "float")

    # width (Variable)
    w_sym = symbols[1]
    self.assertEqual(w_sym.name, "width")
    self.assertEqual(w_sym.kind, SymbolKind.Variable)
    self.assertEqual(w_sym.detail, "int")

    # height (Variable)
    h_sym = symbols[2]
    self.assertEqual(h_sym.name, "height")
    self.assertEqual(h_sym.kind, SymbolKind.Variable)
    self.assertEqual(h_sym.detail, "int")

    # compute (Function)
    fn_sym = symbols[3]
    self.assertEqual(fn_sym.name, "compute")
    self.assertEqual(fn_sym.kind, SymbolKind.Function)
    self.assertEqual(fn_sym.detail, "(bonus: float): float")

  def test_var_decl_without_bindings_info_fallback(self):
    # Construct VarDeclNode manually without bindings_info
    var_decl = VarDeclNode(is_mutable=False, names=["alpha", "beta"], val_types=[BasicTypeNode("int"), None])
    ast = ProgramNode(declarations=[var_decl])
    symbols = extract_document_symbols(ast)
    self.assertEqual(len(symbols), 2)
    self.assertEqual(symbols[0].name, "alpha")
    self.assertEqual(symbols[0].kind, SymbolKind.Constant)
    self.assertEqual(symbols[0].detail, "int")
    self.assertEqual(symbols[1].name, "beta")
    self.assertEqual(symbols[1].kind, SymbolKind.Constant)
    self.assertIsNone(symbols[1].detail)


if __name__ == "__main__":
  unittest.main()
