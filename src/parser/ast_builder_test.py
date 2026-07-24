"""Unit tests for ASTBuilder visitor defined in ast_builder.py.

This module parses Sapphire source code snippets into ASTs using ANTLR and the
ASTBuilder visitor, verifying the correctness of the translation.
"""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from parser.ast import (
      ProgramNode,
      VarDeclNode,
      LiteralNode,
      BasicTypeNode,
      BinaryOpNode,
      IfNode,
      StructDeclNode,
      StructInitializerNode,
      CloneNode,
  )
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.parser.ast import (
      ProgramNode,
      VarDeclNode,
      LiteralNode,
      BasicTypeNode,
      BinaryOpNode,
      IfNode,
      StructDeclNode,
      StructInitializerNode,
      CloneNode,
  )


class TestASTBuilder(unittest.TestCase):
  """Unit tests for ASTBuilder visitor class."""

  def _get_ast(self, code: str) -> ProgramNode:
    """Helper to parse a Sapphire code string and return the Program AST Node."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    return builder.visit(tree)

  def test_variable_declaration(self):
    """Verifies parsing of a simple variable declaration."""
    ast = self._get_ast("let x: int = 42;")
    self.assertIsInstance(ast, ProgramNode)
    self.assertEqual(len(ast.declarations), 1)

    decl = ast.declarations[0]
    self.assertIsInstance(decl, VarDeclNode)
    self.assertFalse(decl.is_mutable)
    self.assertEqual(decl.name, "x")
    
    # Check type
    self.assertIsInstance(decl.val_type, BasicTypeNode)
    self.assertEqual(decl.val_type.name, "int")
    
    # Check expression value
    self.assertIsInstance(decl.expr, LiteralNode)
    self.assertEqual(decl.expr.value, 42)
    self.assertEqual(decl.expr.lit_type, "int")

  def test_mutable_variable_declaration(self):
    """Verifies parsing of a mutable variable declaration without explicit type."""
    ast = self._get_ast('var name = "Sapphire";')
    self.assertEqual(len(ast.declarations), 1)

    decl = ast.declarations[0]
    self.assertIsInstance(decl, VarDeclNode)
    self.assertTrue(decl.is_mutable)
    self.assertEqual(decl.name, "name")
    self.assertIsNone(decl.val_type)

    self.assertIsInstance(decl.expr, LiteralNode)
    self.assertEqual(decl.expr.value, "Sapphire")
    self.assertEqual(decl.expr.lit_type, "string")

  def test_binary_operators(self):
    """Verifies parsing of arithmetic and comparative expression operations."""
    ast = self._get_ast("let result = 10 + 20 * 30;")
    self.assertEqual(len(ast.declarations), 1)

    decl = ast.declarations[0]
    self.assertIsInstance(decl, VarDeclNode)
    expr = decl.expr
    self.assertIsInstance(expr, BinaryOpNode)
    self.assertEqual(expr.op, "+")
    self.assertIsInstance(expr.left, LiteralNode)
    self.assertEqual(expr.left.value, 10)

    self.assertIsInstance(expr.right, BinaryOpNode)
    self.assertEqual(expr.right.op, "*")
    self.assertEqual(expr.right.left.value, 20)
    self.assertEqual(expr.right.right.value, 30)

  def test_struct_declaration(self):
    """Verifies struct declarations are parsed with correct field attributes."""
    code = """
    struct Point {
      let x: float;
      var y: float;
    }
    """
    ast = self._get_ast(code)
    self.assertEqual(len(ast.declarations), 1)

    struct_decl = ast.declarations[0]
    self.assertIsInstance(struct_decl, StructDeclNode)
    self.assertEqual(struct_decl.name, "Point")
    self.assertIsNone(struct_decl.parent_name)
    self.assertEqual(len(struct_decl.fields), 2)

    field1 = struct_decl.fields[0]
    self.assertFalse(field1.is_mutable)
    self.assertEqual(field1.name, "x")
    self.assertEqual(field1.field_type.name, "float")

    field2 = struct_decl.fields[1]
    self.assertTrue(field2.is_mutable)
    self.assertEqual(field2.name, "y")
    self.assertEqual(field2.field_type.name, "float")

  def test_additional_syntax(self):
    """Verifies parsing of standard if/else, multi-parameter lambdas, and other literals/expressions."""
    ast = self._get_ast("""
    func demo() {
      if true {
        let x = 1;
      } else if false {
        let y = 2;
      } else {
        let z = (3);
      }
    }
    """)
    self.assertEqual(len(ast.declarations), 1)

    ast_lambda = self._get_ast("let f = (a: int, b: float) -> int { return a; };")
    self.assertEqual(len(ast_lambda.declarations), 1)

  def test_proto_declaration(self):
    """Verifies that proto declarations are parsed correctly."""
    ast = self._get_ast("""
    proto Enemy {
      var health: int;
    }
    """)
    self.assertEqual(len(ast.declarations), 1)
    struct_decl = ast.declarations[0]
    self.assertIsInstance(struct_decl, StructDeclNode)
    self.assertEqual(struct_decl.name, "Enemy")
    self.assertTrue(struct_decl.is_prototype)

  def test_struct_initializer(self):
    """Verifies parsing of curly-brace struct initializers."""
    ast = self._get_ast("let sword = Weapon { damage = 45, durability = 100, };")
    self.assertEqual(len(ast.declarations), 1)
    decl = ast.declarations[0]
    self.assertIsInstance(decl, VarDeclNode)
    
    struct_init = decl.expr
    self.assertIsInstance(struct_init, StructInitializerNode)
    self.assertEqual(struct_init.struct_name, "Weapon")
    self.assertEqual(len(struct_init.fields), 2)
    self.assertEqual(struct_init.fields[0].name, "damage")
    self.assertEqual(struct_init.fields[0].expr.value, 45)
    self.assertEqual(struct_init.fields[1].name, "durability")
    self.assertEqual(struct_init.fields[1].expr.value, 100)


  def test_arena_parsing(self):
    """Verifies parsing of struct initializer and clone expressions with explicit arenas."""
    ast = self._get_ast("""
    let x = Point { x = 10 } in my_arena;
    let y = clone base in other_arena;
    """)
    self.assertEqual(len(ast.declarations), 2)
    
    decl1 = ast.declarations[0]
    self.assertIsInstance(decl1.expr, StructInitializerNode)
    self.assertEqual(decl1.expr.arena_expr.name, "my_arena")
    
    decl2 = ast.declarations[1]
    self.assertIsInstance(decl2.expr, CloneNode)
    self.assertEqual(decl2.expr.arena_expr.name, "other_arena")

  def test_enum_declaration(self):
    """Verifies parsing of enum declarations with auto and explicit values and trailing commas."""
    ast = self._get_ast("""
    enum Direction {
        North,
        East,
        South,
        West,
    }
    enum Status {
        Ok = 200,
        NotFound = 404,
    }
    """)
    self.assertEqual(len(ast.declarations), 2)

    enum1 = ast.declarations[0]
    self.assertEqual(enum1.name, "Direction")
    self.assertEqual(len(enum1.members), 4)
    self.assertEqual(enum1.members[0].name, "North")
    self.assertIsNone(enum1.members[0].value)

    enum2 = ast.declarations[1]
    self.assertEqual(enum2.name, "Status")
    self.assertEqual(len(enum2.members), 2)
    self.assertEqual(enum2.members[0].name, "Ok")
    self.assertEqual(enum2.members[0].value, 200)
    self.assertEqual(enum2.members[1].name, "NotFound")
    self.assertEqual(enum2.members[1].value, 404)

  def test_multi_return_and_bindings(self):
    """Verifies AST construction for multi-return functions and multi-variable declarations/assignments."""
    ast = self._get_ast("""
    func getPos(): float, float {
      return 10.0, 20.0;
    }
    let x, y = getPos();
    var a: float, b: float = 1.0, 2.0;
    a, b = getPos();
    """)
    self.assertEqual(len(ast.declarations), 4)

    # Multi-return function
    fn = ast.declarations[0]
    self.assertEqual(fn.name, "getPos")
    self.assertEqual(len(fn.return_types), 2)
    self.assertEqual(fn.return_types[0].name, "float")
    self.assertEqual(fn.return_types[1].name, "float")
    ret_stmt = fn.body.statements[0]
    self.assertEqual(len(ret_stmt.expressions), 2)

    # Multi-variable declaration unboxing function call
    var_decl1 = ast.declarations[1]
    self.assertEqual(var_decl1.names, ["x", "y"])
    self.assertEqual(len(var_decl1.exprs), 1)

    # Multi-variable declaration with literal list
    var_decl2 = ast.declarations[2]
    self.assertEqual(var_decl2.names, ["a", "b"])
    self.assertEqual(len(var_decl2.exprs), 2)

    # Multi-variable assignment
    assign_stmt = ast.declarations[3]
    self.assertEqual(len(assign_stmt.targets), 2)
    self.assertEqual(len(assign_stmt.exprs), 1)

  def test_visit_statement_directly(self):
    """Verifies direct invocation of visitStatement on ASTBuilder."""
    input_stream = InputStream("let x = 1;")
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    stmt_ctx = parser.statement()
    builder = ASTBuilder()
    stmt_node = builder.visitStatement(stmt_ctx)
    self.assertIsInstance(stmt_node, VarDeclNode)

  def test_function_type_with_multi_return(self):
    """Verifies parsing of function type signatures returning multiple types."""
    ast = self._get_ast("var fn: (int) -> (float, bool);")
    var_decl = ast.declarations[0]
    self.assertEqual(len(var_decl.val_types[0].return_types), 2)

  def test_string_enum_parsing(self):
    """Verifies AST construction for string-backed enum declarations."""
    ast = self._get_ast("""
    enum DrawMode {
      Fill = "fill",
      Line = "line",
      Default,
    }
    """)
    enum_decl = ast.declarations[0]
    self.assertEqual(enum_decl.name, "DrawMode")
    self.assertEqual(enum_decl.members[0].value, "fill")
    self.assertEqual(enum_decl.members[1].value, "line")
    self.assertIsNone(enum_decl.members[2].value)

  def test_trait_self_parameter_parsing(self):
    """Verifies AST construction for trait declarations with explicit self parameter."""
    ast = self._get_ast("""
    trait ImageHandle {
      func draw(self, x: float, y: float);
      func getWidth(var self): float;
    }
    """)
    trait_decl = ast.declarations[0]
    self.assertEqual(trait_decl.name, "ImageHandle")
    self.assertEqual(len(trait_decl.members), 2)
    self.assertEqual(trait_decl.members[0].parameters[0].name, "self")
    self.assertFalse(trait_decl.members[0].parameters[0].is_mutable)
    self.assertEqual(trait_decl.members[1].parameters[0].name, "self")
    self.assertTrue(trait_decl.members[1].parameters[0].is_mutable)

  def test_trait_extern_annotation_parsing(self):
    """Verifies AST construction for trait methods with @extern annotations."""
    ast = self._get_ast("""
    trait Graphics {
      @extern("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }
    """)
    trait_decl = ast.declarations[0]
    self.assertEqual(len(trait_decl.members[0].annotations), 1)
    self.assertEqual(trait_decl.members[0].annotations[0].name, "extern")
    self.assertEqual(trait_decl.members[0].annotations[0].arg, "setColor")


if __name__ == "__main__":
  unittest.main()
