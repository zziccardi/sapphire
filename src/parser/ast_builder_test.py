"""Unit tests for ASTBuilder visitor defined in ast_builder.py.

This module parses Sapphire source code snippets into ASTs using ANTLR and the
ASTBuilder visitor, verifying the correctness of the translation.
"""

import unittest
from antlr4 import InputStream, CommonTokenStream

from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.parser.ast_builder import ASTBuilder
from src.parser.ast import (
    ProgramNode,
    VarDeclNode,
    LiteralNode,
    BasicTypeNode,
    BinaryOpNode,
    CastExprNode,
    IfNode,
    StructDeclNode,
    StructInitializerNode,
    CloneNode,
    CallNode,
    InterpolatedStringNode,
    IdentifierNode,
    ArrayTypeNode,
    MapTypeNode,
    BreakNode,
    ContinueNode,
)



class TestASTBuilder(unittest.TestCase):
  """Unit tests for ASTBuilder visitor class."""

  def _get_ast(self, code: str) -> ProgramNode:
    """Helper to parse a Sapphire code string and return the Program AST Node."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    tree = parser.program()
    if parser.getNumberOfSyntaxErrors() > 0:
      raise SyntaxError(f"Syntax error while parsing code string:\n{code}")
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

  def test_cast_expression(self):
    """Verifies type cast expressions ('expr as type') are built into CastExprNode."""
    ast = self._get_ast("let f = 10 as float;")
    stmt = ast.declarations[0]
    self.assertIsInstance(stmt, VarDeclNode)
    expr = stmt.exprs[0]
    self.assertIsInstance(expr, CastExprNode)
    self.assertIsInstance(expr.expr, LiteralNode)
    self.assertEqual(expr.expr.value, 10)
    self.assertEqual(expr.target_type.name, "float")

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

  def test_multi_parent_struct_declaration(self):
    """Verifies parsing of multi-parent struct declarations."""
    ast = self._get_ast("""
    struct Position { var x: float; var y: float; }
    struct Health { var hp: int; }
    struct Player: Position, Health { var name: string; }
    """)
    player_decl = ast.declarations[2]
    self.assertEqual(player_decl.name, "Player")
    self.assertEqual(player_decl.parent_names, ["Position", "Health"])
    self.assertEqual(player_decl.parent_name, "Position")
    self.assertEqual(len(player_decl.parent_names_info), 2)
    self.assertEqual(player_decl.parent_names_info[0]["name"], "Position")
    self.assertEqual(player_decl.parent_names_info[1]["name"], "Health")

  def test_dotted_parent_struct_declaration(self):
    """Verifies parsing of struct declarations inheriting from imported modules (e.g. struct Character: entity.Entity)."""
    ast = self._get_ast("""
    struct Character: entity.Entity { var x: float; }
    """)
    char_decl = ast.declarations[0]
    self.assertEqual(char_decl.name, "Character")
    self.assertEqual(char_decl.parent_names, ["entity.Entity"])
    self.assertEqual(char_decl.parent_name, "entity.Entity")
    self.assertEqual(len(char_decl.parent_names_info), 1)
    self.assertEqual(char_decl.parent_names_info[0]["name"], "entity.Entity")

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

  def test_dotted_struct_initializer(self):
    """Verifies parsing of struct initializers using dotted module names (e.g. character.Unit { name = name })."""
    ast = self._get_ast("let u = character.Unit { name = name, stats = stats };")
    decl = ast.declarations[0]
    struct_init = decl.expr
    self.assertIsInstance(struct_init, StructInitializerNode)
    self.assertEqual(struct_init.struct_name, "character.Unit")
    self.assertEqual(len(struct_init.fields), 2)
    self.assertEqual(struct_init.fields[0].name, "name")


  def test_arena_parsing(self):
    """Verifies parsing of struct initializer, constructor call, and clone expressions with explicit arenas."""
    ast = self._get_ast("""
    let x = Point { x = 10 } in my_arena;
    let y = clone base in other_arena;
    let z = Enemy(hp = 100) in third_arena;
    """)
    self.assertEqual(len(ast.declarations), 3)
    
    decl1 = ast.declarations[0]
    self.assertIsInstance(decl1.expr, StructInitializerNode)
    self.assertEqual(decl1.expr.arena_expr.name, "my_arena")
    
    decl2 = ast.declarations[1]
    self.assertIsInstance(decl2.expr, CloneNode)
    self.assertEqual(decl2.expr.arena_expr.name, "other_arena")

    decl3 = ast.declarations[2]
    self.assertIsInstance(decl3.expr, CallNode)
    self.assertEqual(decl3.expr.arena_expr.name, "third_arena")

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
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
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

  def test_trait_export_annotation_parsing(self):
    """Verifies AST construction for trait methods with @export annotations."""
    ast = self._get_ast("""
    trait Graphics {
      @export("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }
    """)
    trait_decl = ast.declarations[0]
    self.assertEqual(len(trait_decl.members[0].annotations), 1)
    self.assertEqual(trait_decl.members[0].annotations[0].name, "export")
    self.assertEqual(trait_decl.members[0].annotations[0].arg, "setColor")


  def test_import_and_export_parsing(self):
    """Verifies AST construction for module imports and explicit export manifest."""
    ast = self._get_ast("""
    import lib.love2d.enums;
    import lib.love2d.graphics as gfx;

    export {
      Image,
      new_image as create_image,
      enums.DrawMode as mode,
    }

    struct Image {
      var handle: int;
    }
    """)
    self.assertEqual(len(ast.imports), 2)
    self.assertEqual(ast.imports[0].path, "lib.love2d.enums")
    self.assertIsNone(ast.imports[0].alias)
    self.assertEqual(ast.imports[1].path, "lib.love2d.graphics")
    self.assertEqual(ast.imports[1].alias, "gfx")

    self.assertIsNotNone(ast.export_block)
    specs = ast.export_block.specifiers
    self.assertEqual(len(specs), 3)
    self.assertEqual(specs[0].symbol, "Image")
    self.assertIsNone(specs[0].alias)
    self.assertEqual(specs[1].symbol, "new_image")
    self.assertEqual(specs[1].alias, "create_image")
    self.assertEqual(specs[2].module_prefix, "enums")
    self.assertEqual(specs[2].symbol, "DrawMode")

  def test_multiple_export_blocks_error(self):
    """Verifies that multiple export blocks raise a SyntaxError."""
    with self.assertRaises(SyntaxError):
      self._get_ast("""
      export { A }
      export { B }
      """)

  def test_export_semicolon_error(self):
    """Verifies that an export block with a trailing semicolon causes a syntax error."""
    input_stream = InputStream("export { A };")
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    parser.program()
    self.assertGreater(parser.getNumberOfSyntaxErrors(), 0)


  def test_match_expression_ast(self):
    """Verifies AST construction for match expressions, match cases, yield statements, and ellipsis patterns."""
    from src.parser.ast import MatchExprNode, MatchCaseNode, YieldNode, EllipsisPatternNode


    ast = self._get_ast("""
    let res = match status {
      HttpStatus.Ok -> "OK",
      HttpStatus.NotFound -> {
        log("Not found");
        yield "Error";
      },
      ... -> "Fallback",
    };
    """)
    decl = ast.declarations[0]
    match_expr = decl.expr
    self.assertIsInstance(match_expr, MatchExprNode)
    self.assertEqual(len(match_expr.cases), 3)

    # Case 0: single expression
    self.assertIsInstance(match_expr.cases[0], MatchCaseNode)

    # Case 1: multi-statement block with yield
    self.assertIsInstance(match_expr.cases[1].body.statements[1], YieldNode)

    # Case 2: ellipsis pattern
    self.assertIsInstance(match_expr.cases[2].pattern, EllipsisPatternNode)

  def test_map_literal_parsing(self):
    """Verifies AST construction for map literals with colons, commas, and trailing commas."""
    from src.parser.ast import MapLiteralNode, MapEntryNode, LiteralNode


    ast = self._get_ast("""
    let scores = {"alice": 100, "bob": 95,};
    """)
    decl = ast.declarations[0]
    map_expr = decl.expr
    self.assertIsInstance(map_expr, MapLiteralNode)
    self.assertEqual(len(map_expr.entries), 2)
    self.assertIsInstance(map_expr.entries[0], MapEntryNode)
    self.assertEqual(map_expr.entries[0].key.value, "alice")
    self.assertEqual(map_expr.entries[0].value.value, 100)
    self.assertEqual(map_expr.entries[1].key.value, "bob")
    self.assertEqual(map_expr.entries[1].value.value, 95)

  def test_map_for_loop_parsing(self):
    """Verifies AST construction for map for-in loop with key, val bindings."""
    from src.parser.ast import ForNode, FuncDeclNode


    ast = self._get_ast("""
    func test() {
      for k, v in my_map {
        print(k);
      }
    }
    """)
    func_decl = ast.declarations[0]
    self.assertIsInstance(func_decl, FuncDeclNode)
    for_node = func_decl.body.statements[0]
    self.assertIsInstance(for_node, ForNode)
    self.assertEqual(for_node.key_var, "k")
    self.assertEqual(for_node.val_var, "v")


  def test_impl_block_generic_type_args(self):
    """Verifies AST construction for generic impl blocks with various type arguments."""
    from src.parser.ast import ImplBlockNode


    ast1 = self._get_ast("impl Trait<int> for Struct<float> {}")
    impl1 = ast1.declarations[0]
    self.assertIsInstance(impl1, ImplBlockNode)
    self.assertEqual(len(impl1.trait_type_args), 1)
    self.assertEqual(len(impl1.struct_type_args), 1)

    ast2 = self._get_ast("impl Trait<int> for Struct {}")
    impl2 = ast2.declarations[0]
    self.assertIsInstance(impl2, ImplBlockNode)
    self.assertEqual(len(impl2.trait_type_args), 1)

    ast3 = self._get_ast("impl Trait for Struct<float> {}")
    impl3 = ast3.declarations[0]
    self.assertIsInstance(impl3, ImplBlockNode)
    self.assertEqual(len(impl3.struct_type_args), 1)

    ast4 = self._get_ast("impl Struct<int> {}")
    impl4 = ast4.declarations[0]
    self.assertIsInstance(impl4, ImplBlockNode)
    self.assertEqual(len(impl4.struct_type_args), 1)

    ast5 = self._get_ast("impl Trait<int, MyCustomArg> for Struct {}")
    impl5 = ast5.declarations[0]
    self.assertIsInstance(impl5, ImplBlockNode)
    self.assertIn("MyCustomArg", impl5.type_params)

  def test_interpolated_string(self):
    """Verifies parsing of Python-style f-strings."""
    ast = self._get_ast('let s = f"Hello {name}!";')
    var_decl = ast.declarations[0]
    self.assertIsInstance(var_decl.exprs[0], InterpolatedStringNode)
    parts = var_decl.exprs[0].parts
    self.assertEqual(len(parts), 3)
    self.assertIsInstance(parts[0], LiteralNode)
    self.assertEqual(parts[0].value, "Hello ")
    self.assertIsInstance(parts[1], IdentifierNode)
    self.assertEqual(parts[1].name, "name")
    self.assertIsInstance(parts[2], LiteralNode)
    self.assertEqual(parts[2].value, "!")

  def test_interpolated_string_escaped_braces_and_nested_quotes(self):
    """Verifies parsing of f-strings with escaped braces and nested quotes."""
    ast = self._get_ast('let s = f"Val: {{lit}} {user.get("id")}";')
    var_decl = ast.declarations[0]
    self.assertIsInstance(var_decl.exprs[0], InterpolatedStringNode)
    parts = var_decl.exprs[0].parts
    self.assertEqual(len(parts), 2)
    self.assertEqual(parts[0].value, "Val: {lit} ")

  def test_interpolated_string_escapes_and_branches(self):
    """Verifies parsing of empty f-string, escape sequences, single brace, and nested expr braces."""
    # Empty
    ast_empty = self._get_ast('let s = f"";')
    self.assertEqual(len(ast_empty.declarations[0].exprs[0].parts), 0)

    # Escape sequences \n \t \r \" \\ \{ \} \x
    ast_esc = self._get_ast('let s = f"a\\nb\\tc\\rd\\"e\\\\f\\{g\\}h\\x";')
    parts = ast_esc.declarations[0].exprs[0].parts
    self.assertEqual(parts[0].value, "a\nb\tc\rd\"e\\f{g}h\\x")

    # Unescaped single closing brace & nested brace in expression
    ast_brace = self._get_ast('let s = f"a}b { {1: 2}[1] }";')
    parts2 = ast_brace.declarations[0].exprs[0].parts
    self.assertEqual(parts2[0].value, "a}b ")

    # Escaped backslash inside expression quotes
    ast_expr_esc = self._get_ast('let s = f" { "\\"hello\\" "} ";')
    parts3 = ast_expr_esc.declarations[0].exprs[0].parts
    self.assertEqual(len(parts3), 3)

    # Direct parse with trailing backslash
    node_trailing = ASTBuilder()._parse_interpolated_string("hello\\")
    self.assertEqual(node_trailing.parts[0].value, "hello\\")

  def test_invalid_struct_initializer_syntax(self):
    """Verifies that malformed struct initializer field syntax without expression raises a clean SyntaxError."""
    class MockToken:
      def getText(self): return "item"
    class MockCtx:
      def IDENTIFIER(self): return MockToken()
      def expression(self): return None
    with self.assertRaises(SyntaxError) as ctx:
      ASTBuilder().visitStructInitField(MockCtx())
    self.assertIn("must be assigned an expression using '='", str(ctx.exception))


  def test_collection_type_annotations(self):
    """Verifies parsing of array [T] and map [K: V] type annotations."""
    ast_arr = self._get_ast('let arr: [int] = [1, 2];')
    decl_arr = ast_arr.declarations[0]
    self.assertIsInstance(decl_arr.val_types[0], ArrayTypeNode)
    self.assertEqual(decl_arr.val_types[0].element_type.name, "int")

    ast_map = self._get_ast('let m: [String: int] = {"a": 1};')
    decl_map = ast_map.declarations[0]
    self.assertIsInstance(decl_map.val_types[0], MapTypeNode)
    self.assertEqual(decl_map.val_types[0].key_type.name, "String")
    self.assertEqual(decl_map.val_types[0].val_type.name, "int")

  def test_break_and_continue_statements(self):
    """Verifies AST construction for break and continue statements."""
    ast = self._get_ast('while true { continue; break; }')
    while_stmt = ast.declarations[0]
    stmts = while_stmt.block.statements
    self.assertIsInstance(stmts[0], ContinueNode)
    self.assertIsInstance(stmts[1], BreakNode)

  def test_impl_trait_prefix(self):
    """Verifies AST building for trait prefix in impl block."""
    ast = self._get_ast('impl pkg.Trait for TargetStruct {}')
    impl = ast.declarations[0]
    self.assertEqual(impl.trait_name, "pkg.Trait")
    self.assertEqual(impl.struct_name, "TargetStruct")

  def test_guard_statement_ast(self):
    """Verifies AST construction for guard statements with semicolon clause separation and multi-variable binding."""
    from src.parser.ast import GuardStmtNode, GuardClauseNode, HeaderBindingNode

    code = """
    func test() {
      guard let x ?= opt; let a, b ?= get_pair(); x > 0 else {
        return;
      }
    }
    """
    ast = self._get_ast(code)
    func_decl = ast.declarations[0]
    guard_node = func_decl.body.statements[0]
    self.assertIsInstance(guard_node, GuardStmtNode)
    self.assertEqual(len(guard_node.clauses), 3)

    # Clause 1: let x ?= opt
    self.assertIsNotNone(guard_node.clauses[0].binding)
    self.assertEqual(guard_node.clauses[0].binding.let_name, "x")
    self.assertEqual(guard_node.clauses[0].binding.let_names, ["x"])

    # Clause 2: let a, b ?= get_pair()
    self.assertIsNotNone(guard_node.clauses[1].binding)
    self.assertEqual(guard_node.clauses[1].binding.let_names, ["a", "b"])

    # Clause 3: x > 0
    self.assertIsNotNone(guard_node.clauses[2].condition)


  def test_struct_field_omitted_type(self):
    """Verifies AST building for struct fields with omitted explicit types when assigned default values."""
    ast = self._get_ast('struct Point { var x = 10; let name = "origin"; }')
    struct_decl = ast.declarations[0]
    self.assertIsInstance(struct_decl, StructDeclNode)
    self.assertEqual(len(struct_decl.fields), 2)
    self.assertTrue(struct_decl.fields[0].is_mutable)
    self.assertEqual(struct_decl.fields[0].name, "x")
    self.assertIsNone(struct_decl.fields[0].field_type)
    self.assertIsInstance(struct_decl.fields[0].default_expr, LiteralNode)

    self.assertFalse(struct_decl.fields[1].is_mutable)
    self.assertEqual(struct_decl.fields[1].name, "name")
    self.assertIsNone(struct_decl.fields[1].field_type)
    self.assertIsInstance(struct_decl.fields[1].default_expr, LiteralNode)


  def test_yield_node_variants_and_to_dict(self):
    from src.parser.ast import YieldNode, LiteralNode
    lit1 = LiteralNode(1, "int")
    node_single = YieldNode(expr=lit1)
    self.assertEqual(node_single.expr, lit1)
    d_single = node_single.to_dict()
    self.assertIn("exprs", d_single)
    self.assertIn("expr", d_single)

    node_single_exprs = YieldNode(exprs=lit1)
    self.assertEqual(node_single_exprs.expr, lit1)

    node_empty = YieldNode()
    self.assertIsNone(node_empty.expr)
    d_empty = node_empty.to_dict()
    self.assertIsNone(d_empty["expr"])


  def test_with_statement_ast(self):
    """Verifies AST construction for with statements with single/multiple clauses, unwrap, and else blocks."""
    from src.parser.ast import WithStmtNode, WithClauseNode, HeaderBindingNode

    code = """
    func test() {
      with let src ?= open("in.txt"); let dst = create("out.txt") {
        let x = 1;
      } else {
        let err = 0;
      }
    }
    """
    ast = self._get_ast(code)
    func_decl = ast.declarations[0]
    with_node = func_decl.body.statements[0]
    self.assertIsInstance(with_node, WithStmtNode)
    self.assertEqual(len(with_node.clauses), 2)

    # Clause 1: let src ?= open("in.txt")
    self.assertIsNotNone(with_node.clauses[0].binding)
    self.assertEqual(with_node.clauses[0].binding.let_name, "src")
    self.assertTrue(with_node.clauses[0].binding.is_unwrap)

    # Clause 2: let dst = create("out.txt")
    self.assertIsNotNone(with_node.clauses[1].binding)
    self.assertEqual(with_node.clauses[1].binding.let_name, "dst")
    self.assertFalse(with_node.clauses[1].binding.is_unwrap)

    # Body and else block
    self.assertIsNotNone(with_node.body)
    self.assertIsNotNone(with_node.else_body)
    self.assertEqual(len(with_node.body.statements), 1)
    self.assertEqual(len(with_node.else_body.statements), 1)

    # Raw expression in with clause
    code_raw = """
    func test() {
      with Arena() {
        let y = 2;
      }
    }
    """
    ast_raw = self._get_ast(code_raw)
    with_raw_node = ast_raw.declarations[0].body.statements[0]
    self.assertIsInstance(with_raw_node, WithStmtNode)
    self.assertEqual(len(with_raw_node.clauses), 1)
    self.assertIsNone(with_raw_node.clauses[0].binding)
    self.assertIsNotNone(with_raw_node.clauses[0].expr)


if __name__ == "__main__":
  unittest.main()

