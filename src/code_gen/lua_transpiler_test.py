"""Unit tests for the Sapphire-to-Lua 5.1 transpiler.

This module validates that transpiled Lua 5.1 code is syntactically correct
and preserves all Sapphire runtime semantics, including prototypal delegation,
compound assignment expansion, and array indexing adjustments.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.ast import (
      ASTNode,
      ArgumentNode,
      BinaryOpNode,
      BlockNode,
      CallNode,
      ExprStmtNode,
      IdentifierNode,
      LambdaNode,
      LambdaParamNode,
      LiteralNode,
      MemberAccessNode,
      StructFieldNode,
      StructInitializerNode,
      TraitDeclNode,
      UnaryOpNode,
  )
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from code_gen.lua_transpiler import LuaTranspiler
  from code_gen.transpiler import transpile_file
except ModuleNotFoundError:
  from src.parser.ast import (
      ASTNode,
      ArgumentNode,
      BinaryOpNode,
      BlockNode,
      CallNode,
      ExprStmtNode,
      IdentifierNode,
      LambdaNode,
      LambdaParamNode,
      LiteralNode,
      MemberAccessNode,
      StructFieldNode,
      StructInitializerNode,
      TraitDeclNode,
      UnaryOpNode,
  )
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.code_gen.lua_transpiler import LuaTranspiler
  from src.code_gen.transpiler import transpile_file


class DummyNode(ASTNode):
  pass


class TestLuaTranspiler(unittest.TestCase):
  """Suite of unit tests verifying correct Lua code generation and execution."""

  def _transpile(self, code: str) -> str:
    """Helper to parse Sapphire code string and return transpiled Lua code."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()

    builder = ASTBuilder()
    ast = builder.visit(tree)

    transpiler = LuaTranspiler()
    return transpiler.transpile(ast)

  def test_generic_visit(self):
    """Verifies generic_visit raises NotImplementedError for unknown AST nodes."""
    transpiler = LuaTranspiler()
    with self.assertRaises(NotImplementedError):
      transpiler.visit(DummyNode())

  def test_direct_visitor_nodes(self):
    """Verifies direct visitor execution for edge-case AST nodes."""
    transpiler = LuaTranspiler()
    transpiler.known_structs.add("Point")

    # StructFieldNode, TraitDeclNode, empty BlockNode, ExprStmtNode
    transpiler.visit(StructFieldNode(False, "x", None))
    transpiler.visit(TraitDeclNode("T", []))
    transpiler.visit(BlockNode([]))
    transpiler.visit(ExprStmtNode(IdentifierNode("x")))

    # BinaryOpNode with right-operand string concatenation
    transpiler.visit(BinaryOpNode(LiteralNode(10, "int"), "+", LiteralNode("items", "string")))

    # CallNode calling struct constructor with multiple args (named & positional)
    transpiler.visit(CallNode(IdentifierNode("Point"), [ArgumentNode("x", LiteralNode(1, "int")), ArgumentNode(None, LiteralNode(2, "int"))]))

    # CallNode static method on struct name vs instance call
    transpiler.visit(CallNode(MemberAccessNode(IdentifierNode("Point"), "create", False), [ArgumentNode(None, LiteralNode(1, "int")), ArgumentNode(None, LiteralNode(2, "int"))]))
    transpiler.visit(CallNode(MemberAccessNode(IdentifierNode("pt"), "get_x", False), []))

    # LambdaNode with expression body
    transpiler.visit(LambdaNode([LambdaParamNode("x")], None, BinaryOpNode(IdentifierNode("x"), "*", LiteralNode(2, "int"))))

    # StructInitializerNode with arena_expr and positional/named fields
    transpiler.visit(StructInitializerNode("Point", [ArgumentNode("x", LiteralNode(1, "int")), ArgumentNode(None, LiteralNode(2, "int"))], arena_expr=IdentifierNode("my_arena")))

    # UnaryOpNode with unary plus
    transpiler.visit(UnaryOpNode("+", LiteralNode(10, "int")))

    output = transpiler.get_output()
    self.assertIn("-- pass", output)
    self.assertIn('10 .. "items"', output)
    self.assertIn("Point.init({x = 1, [2] = 2})", output)
    self.assertIn("Point.create(1, 2)", output)
    self.assertIn("pt:get_x()", output)
    self.assertIn("my_arena:register(Point.init({x = 1, [2] = 2}))", output)
    self.assertIn("(10)", output)

  def test_basic_arithmetic(self):
    """Verifies that variable declarations and arithmetic expressions transpile to Lua."""
    code = """
    let x = 10;
    let y = 20;
    let z = x + y * 3;
    """
    lua_code = self._transpile(code)
    self.assertIn("local x = 10", lua_code)
    self.assertIn("local y = 20", lua_code)
    self.assertIn("local z = (x + (y * 3))", lua_code)

  def test_enum_declaration(self):
    """Verifies enum declarations with custom values transpile to Lua tables."""
    code = """
    enum State {
      Idle,
      Running = 10,
      Jumping
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local State = {", lua_code)
    self.assertIn("Idle = 0", lua_code)
    self.assertIn("Running = 10", lua_code)
    self.assertIn("Jumping = 11", lua_code)

  def test_compound_assignments(self):
    """Verifies that compound assignments (+=, -=) expand to simple assignments in Lua 5.1."""
    code = """
    var val = 10;
    val += 5;
    val -= 2;
    """
    lua_code = self._transpile(code)
    self.assertIn("local val = 10", lua_code)
    self.assertIn("val = val + 5", lua_code)
    self.assertIn("val = val - 2", lua_code)

  def test_swift_style_if_let(self):
    """Verifies that swift-style optional unwrapping transpiles to Lua nil checks."""
    code = """
    func check_opt() {
      var opt_val: int? = 42;
      if let active = opt_val {
        let x = active;
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local _val_active = opt_val", lua_code)
    self.assertIn("if _val_active ~= nil then", lua_code)
    self.assertIn("local active = _val_active", lua_code)

  def test_array_indexing_and_loops(self):
    """Verifies that 0-based array indexing is offset by 1 in Lua table syntax."""
    code = """
    let numbers = [10, 20, 30];
    let first = numbers[0];
    var idx = 1;
    let dynamic_elem = numbers[idx];
    for n in numbers {
      let x = n;
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local numbers = {10, 20, 30}", lua_code)
    self.assertIn("local first = numbers[1]", lua_code)
    self.assertIn("numbers[idx + 1]", lua_code)
    self.assertIn("for _, n in ipairs(numbers) do", lua_code)

  def test_struct_declaration_and_impl(self):
    """Verifies struct constructor generation, field defaults, static methods, and traits."""
    code = """
    trait Damageable {
      func take_damage(dmg: int);
    }
    struct Item {
      var price: int = 100;
    }
    impl Item {
      func __init__(p: int) {
        self.price = p;
      }
      static func create_default(): Item {
        return Item(100);
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local Item = {}", lua_code)
    self.assertIn("function Item.init(kwargs, proto)", lua_code)
    self.assertIn("Item._init_sapphire", lua_code)
    self.assertIn("Item.init({[1] = 100})", lua_code)

  def test_func_default_params_and_void_return(self):
    """Verifies default parameters and void returns transpile cleanly."""
    code = """
    func compute(x: int, y: int = 5): int {
      if x > 0 {
        return x + y;
      } else {
        return 0;
      }
    }
    func void_action() {
      return;
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("if y == nil then y = 5 end", lua_code)
    self.assertIn("return (x + y)", lua_code)
    self.assertIn("return", lua_code)

  def test_arena_scoped_execution(self):
    """Verifies RAII Arena block scoping generates pcall cleanup."""
    code = """
    func run_arena() {
      var local_arena = Arena();
      let val = 42;
      return;
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local local_arena = Arena.init()", lua_code)
    self.assertIn("local_arena:destroy()", lua_code)

  def test_literals_unary_and_string_concat(self):
    """Verifies boolean, none, string literals, string concatenation +, and unary ! ops."""
    code = """
    let is_active = false;
    let opt_name: String? = none;
    let greeting = "Hello " + "World";
    var msg = "Score: " + 10;
    let not_active = !is_active;
    """
    lua_code = self._transpile(code)
    self.assertIn("local is_active = false", lua_code)
    self.assertIn("local opt_name = nil", lua_code)
    self.assertIn('"Hello " .. "World"', lua_code)
    self.assertIn('"Score: " .. 10', lua_code)
    self.assertIn("not is_active", lua_code)

  def test_optional_chaining_and_while_loop(self):
    """Verifies optional chaining and while loops."""
    code = """
    struct Target {
      var hp: int;
    }
    impl Target {
      func set_hp(val: int = 42) {
        self.hp = val;
      }
    }
    func test_opt_chain(t: Target?) {
      let hp_val = t?.hp;
      var count = 3;
      while count > 0 {
        count -= 1;
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("(t ~= nil and t.hp or nil)", lua_code)
    self.assertIn("while (count > 0) do", lua_code)

  def test_prototypal_inheritance_and_clone_variations(self):
    """Verifies clone node transpilation with arena and without initializer block."""
    code = """
    proto Monster {
      var hp: int;
    }
    impl Monster {
      func __init__(h: int) {
        self.hp = h;
      }
    }
    func test_clone() {
      var arena = Arena();
      var base = Monster(h = 100);
      var sub = clone base {
        self.hp = 80;
      };
      var sub2 = clone base in arena;
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("_create_proto_object", lua_code)
    self.assertIn("_clone_helper(base", lua_code)
    self.assertIn("_clone_helper(base, nil, arena)", lua_code)

  def test_lambdas_and_struct_initializer_with_arena(self):
    """Verifies single-expression and block lambdas, and struct initializers with arenas."""
    code = """
    struct Point {
      var x: int;
      var y: int;
    }
    func test_init() {
      let pt = Point { x = 10, y = 20 };
      let doubler = (x: int) -> int { return x * 2; };
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("Point.init({x = 10, y = 20})", lua_code)
    self.assertIn("(function(x)", lua_code)
    self.assertIn("return (x * 2)", lua_code)

  def test_export_annotation_lua(self):
    """Verifies that @export("target.path") transpiles to function target.path(...)."""
    code = """
    @export("love.update")
    func update(dt: float) {
      let step = dt;
    }

    @export
    func global_callback() {
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("function love.update(dt)", lua_code)
    self.assertIn("function global_callback()", lua_code)
    self.assertNotIn("local function update", lua_code)

  def test_extern_annotations_lua(self):
    """Verifies that @extern var omits runtime initialization code."""
    code = """
    trait Graphics {
      func setColor(r: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;
    """
    lua_code = self._transpile(code)
    self.assertNotIn("local love =", lua_code)

  def test_transpile_file_write_error_lua(self):
    """Verifies transpile_file handles Lua target write failure by exiting."""
    with tempfile.TemporaryDirectory() as temp_dir:
      sp_file = os.path.join(temp_dir, "test.sp")
      with open(sp_file, "w", encoding="utf-8") as f:
        f.write("let x: int = 1;\n")
      with self.assertRaises(SystemExit) as cm:
        transpile_file(sp_file, output_file="/invalid_dir_xyz/out.lua", target="lua")
      self.assertEqual(cm.exception.code, 1)

  def test_trait_member_modifiers(self):
    """Verifies parsing and building AST for const and static trait members."""
    code = """
    trait Printable {
      static func create(): Printable;
      const func display(): String;
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    self.assertEqual(ast.declarations[0].members[0].modifier, "static")
    self.assertEqual(ast.declarations[0].members[1].modifier, "const")

  def test_lua_execution_if_available(self):
    """Executes transpiled Lua code using system Lua interpreter if present."""
    lua_bin = shutil.which("lua") or shutil.which("luajit") or shutil.which("lua5.1")
    if not lua_bin:
      self.skipTest("No Lua interpreter found in system PATH.")

    code = """
    func main(): int {
      let x = 10;
      let y = 20;
      let sum = x + y;
      if sum == 30 {
        return 0;
      }
      return 1;
    }
    """
    with tempfile.NamedTemporaryFile(suffix=".sp", mode="w", delete=False) as f:
      f.write(code)
      sp_path = f.name

    lua_path = sp_path[:-3] + ".lua"
    try:
      transpile_file(sp_path, output_file=lua_path, target="lua")
      result = subprocess.run([lua_bin, lua_path], capture_output=True, text=True)
      self.assertEqual(result.returncode, 0)
    finally:
      if os.path.exists(sp_path):
        os.remove(sp_path)
      if os.path.exists(lua_path):
        os.remove(lua_path)


if __name__ == "__main__":
  unittest.main()
