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
  from code_gen.source_map import SourceMapBuilder
  from semantics.type_checker import TypeChecker
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
  from src.code_gen.source_map import SourceMapBuilder
  from src.semantics.type_checker import TypeChecker


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

    try:
      checker = TypeChecker()
      checker.check(ast)
    except Exception:
      pass

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

  def test_optional_unwrapping(self):
    """Verifies that optional unwrapping transpiles to Lua nil checks."""
    code = """
    func check_opt() {
      var opt_val: int? = 42;
      if let active ?= opt_val {
        let x = active;
      }
    }
    """
    lua_code = self._transpile(code)
    self.assertIn("local _val_active = opt_val", lua_code)
    self.assertIn("if _val_active ~= nil then", lua_code)
    self.assertIn("local active = _val_active", lua_code)

  def test_init_statements_and_coalesce(self):
    """Verifies Lua transpilation of init-statements and ?? coalescing."""
    # 1. if let with condition
    code1 = """
    func check_if_cond() {
      var opt_val: int? = 42;
      if let active ?= opt_val; active > 40 {
        let x = active;
      }
    }
    """
    lua_code1 = self._transpile(code1)
    self.assertIn("local _val_active = opt_val", lua_code1)
    self.assertIn("if _val_active ~= nil and (_val_active > 40) then", lua_code1)

    # 2. while let loop
    code2 = """
    func check_while() {
      var opt_val: int? = 5;
      while let active ?= opt_val; active > 0 {
        opt_val = none;
      }
    }
    """
    lua_code2 = self._transpile(code2)
    self.assertIn("while true do", lua_code2)
    self.assertIn("local _val_active = opt_val", lua_code2)
    self.assertIn("if not (_val_active ~= nil and (_val_active > 0)) then", lua_code2)

    # 3. ?? operator
    code3 = """
    func check_coalesce() {
      var opt_val: int? = none;
      let val = opt_val ?? 99;
    }
    """
    lua_code3 = self._transpile(code3)
    self.assertIn("((function() local _v = opt_val; if _v ~= nil then return _v else return 99 end end)())", lua_code3)

    # 4. standard if let (no unwrap)
    code4 = """
    func check_std_if() {
      if let x = 10; x > 5 {
        let y = x;
      }
    }
    """
    lua_code4 = self._transpile(code4)
    self.assertIn("local x = 10", lua_code4)
    self.assertIn("if (x > 5) then", lua_code4)

    # 5. standard while let (no unwrap)
    code5 = """
    func check_std_while() {
      var count = 5;
      while let x = count; x > 0 {
        count = 0;
      }
    }
    """
    lua_code5 = self._transpile(code5)
    self.assertIn("local x = count", lua_code5)
    self.assertIn("while (x > 0) do", lua_code5)

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
    self.assertIn("Item = {}", lua_code)
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


  def test_lua_multi_return_transpilation(self):
    """Verifies Lua transpilation for multi-return functions, declarations, and assignments."""
    code = """
    func get_pos(): float, float {
      return 10.0, 20.0;
    }
    let x, y = get_pos();
    var a, b = 1.0, 2.0;
    a, b = get_pos();
    """
    output = self._transpile(code)
    self.assertIn("local get_pos", output)
    self.assertIn("function get_pos()", output)
    self.assertIn("return 10.0, 20.0", output)
    self.assertIn("local x, y = get_pos()", output)
    self.assertIn("local a, b = 1.0, 2.0", output)
    self.assertIn("a, b = get_pos()", output)

  def test_lua_compound_assignment(self):
    """Verifies Lua transpilation of compound assignment operators."""
    code = """
    func test() {
      var x = 10;
      x += 5;
      var a = 1.0;
      var b = 2.0;
      a, b = 3.0, 4.0;
    }
    """
    output = self._transpile(code)
    self.assertIn("x = x + 5", output)
    self.assertIn("a, b = 3.0, 4.0", output)

  def test_lua_string_enum_transpilation(self):
    """Verifies Lua transpilation for string-backed enums."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }
    """
    out = self._transpile(code)
    self.assertIn('local Mode = {', out)
    self.assertIn('Fill = "fill"', out)
    self.assertIn('Line = "line"', out)
    self.assertIn('Default = "Default"', out)

  def test_lua_resource_handle_method_transpilation(self):
    """Verifies Lua transpilation for resource handles with colon vs dot calls."""
    code = """
    trait ImageHandle {
      func draw(self, x: float, y: float);
    }
    trait Graphics {
      func rectangle(mode: String, x: float, y: float, w: float, h: float);
    }

    struct Love {
      var graphics: Graphics;
    }

    @extern("love")
    var love: Love;

    @extern("hero")
    var hero_img: ImageHandle;

    func main() {
      love.graphics.rectangle("fill", 10.0, 20.0, 100.0, 50.0);
      hero_img.draw(10.0, 20.0);
    }
    """
    output = self._transpile(code)
    self.assertIn('love.graphics.rectangle("fill", 10.0, 20.0, 100.0, 50.0)', output)
    self.assertIn('hero_img:draw(10.0, 20.0)', output)

  def test_lua_export_method_alias_transpilation(self):
    """Verifies Lua transpilation for trait methods with @export method aliases."""
    code = """
    trait Graphics {
      @export("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }
    struct Love {
      var graphics: Graphics;
    }
    @extern("love")
    var love: Love;

    func main() {
      love.graphics.setColorRGBA(1.0, 0.0, 0.0);
    }
    """
    out = self._transpile(code)
    self.assertIn('love.graphics.setColor(1.0, 0.0, 0.0)', out)


  def test_lua_module_import_and_export_transpilation(self):
    """Verifies Lua 5.1 transpilation for module imports and export manifests."""
    code = """
    import lib.love2d.enums;
    import lib.love2d.graphics as gfx;

    export {
      Player,
      create_player,
      enums.DrawMode,
    }

    struct Player {
      var name: String;
    }

    func create_player(name: String): Player {
      return Player { name = name };
    }
    """
    output = self._transpile(code)
    self.assertIn('local enums = require("lib.love2d.enums")', output)
    self.assertIn('local gfx = require("lib.love2d.graphics")', output)
    self.assertIn('local _M = {}', output)
    self.assertIn('_M.Player = Player', output)
    self.assertIn('_M.create_player = create_player', output)
    self.assertIn('_M.DrawMode = enums.DrawMode', output)
    self.assertIn('return _M', output)


  def test_transpile_file_with_imports(self):
    """Verifies that transpile_file recursively transpiles imported module dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
      sub_sp = os.path.join(tmpdir, "sub.sp")
      with open(sub_sp, "w") as f:
        f.write("import main;\nexport { item } let item = 42;\n")

      main_sp = os.path.join(tmpdir, "main.sp")
      with open(main_sp, "w") as f:
        f.write("import sub;\n")

      out_lua = os.path.join(tmpdir, "main.lua")
      transpile_file(main_sp, output_file=out_lua, target="lua")
      self.assertTrue(os.path.exists(out_lua))
      sub_lua = os.path.join(tmpdir, "sub.lua")
      self.assertTrue(os.path.exists(sub_lua))

  def test_transpile_file_missing_file(self):
    """Verifies SystemExit on missing file input."""
    with self.assertRaises(SystemExit):
      transpile_file("/non_existent_path_xyz_123.sp")


  def test_lua_match_expression_transpilation(self):
    """Verifies generated Lua code for match expressions."""
    code = """
    enum Status { Ok, NotFound, Error }

    func get_code(s: Status): int {
      let code = match s {
        Status.Ok -> 200,
        Status.NotFound -> {
          yield 404;
        },
        ... -> 500,
      };
      return code;
    }
    """
    output = self._transpile(code)
    self.assertIn("local _subj_", output)
    self.assertIn("if _subj_", output)
    self.assertIn("elseif _subj_", output)
    self.assertIn("else", output)
    self.assertIn("_match_res_", output)

    # Match in assignment statement
    assign_code = """
    func test_assign(n: int): int {
      var x = 0;
      x = match n {
        1 -> 10,
        ... -> 20,
      };
      return x;
    }
    """
    lua_out1 = self._transpile(assign_code)
    self.assertIn("x = _match_res_", lua_out1)

    # Match in return statement
    ret_code = """
    func test_ret(n: int): int {
      return match n {
        1 -> 100,
        ... -> 200,
      };
    }
    """
    lua_out2 = self._transpile(ret_code)
    self.assertIn("return _match_res_", lua_out2)

    # Match in expression statement
    stmt_code = """
    func test_stmt(n: int) {
      match n {
        1 -> {},
        ... -> {},
      };
    }
    """
    lua_out3 = self._transpile(stmt_code)
    self.assertIn("if _subj_1 == 1 then", lua_out3)

    # Multi-target assignment with match
    multi_code = """
    func test_multi(n: int): int {
      var a = 0;
      var b = 0;
      a, b = match n { 1 -> 10, ... -> 20 }, 30;
      return a + b;
    }
    """
    lua_out4 = self._transpile(multi_code)
    self.assertIn("_match_res_", lua_out4)

    # Arena destruction inside match return
    arena_ret = """
    struct Item {}
    func test_arena(): Item {
      let a = Arena();
      let item = Item {} in a;
      return match 1 {
        1 -> item,
        ... -> item,
      };
    }
    """
    lua_out5 = self._transpile(arena_ret)
    self.assertIn("a:destroy()", lua_out5)

    # Identifier wildcard _
    wild_code = "func test_w(n: int): int { return match n { _ -> 99 }; }"
    lua_out6 = self._transpile(wild_code)
    self.assertIn("if true then", lua_out6)

    # Compound assignment with match
    comp_code = """
    func test_comp(n: int): int {
      var x = 1;
      x += match n { 1 -> 2, ... -> 3 };
      return x;
    }
    """
    lua_out7 = self._transpile(comp_code)
    self.assertIn("x = x + _match_res_", lua_out7)

    # Direct visitor calls
    try:
      from parser.ast import MatchExprNode, EllipsisPatternNode, MatchCaseNode, LiteralNode
      from code_gen.lua_transpiler import LuaTranspiler
    except ModuleNotFoundError:
      from src.parser.ast import MatchExprNode, EllipsisPatternNode, MatchCaseNode, LiteralNode
      from src.code_gen.lua_transpiler import LuaTranspiler

    lt = LuaTranspiler()
    lt.visit(MatchExprNode(LiteralNode(1, "int"), [MatchCaseNode(EllipsisPatternNode(), LiteralNode(2, "int"))]))
    lt.visit_EllipsisPatternNode(EllipsisPatternNode())
    self.assertIn("_match_res_1", "".join(lt.code))

  def test_lua_map_literal_transpilation(self):
    """Verifies Lua transpilation for map literals and map indexing (without +1 offset)."""
    code = """
    func test() {
      let scores = {"alice": 100, "bob": 95,};
      let score = scores["alice"];
      let arr = [10, 20];
      let elem = arr[0];
    }
    """
    lua_out = self._transpile(code)
    self.assertIn('{["alice"] = 100, ["bob"] = 95}', lua_out)
    self.assertIn('scores["alice"]', lua_out)
    self.assertNotIn('scores["alice"] + 1', lua_out)
    self.assertIn('arr[1]', lua_out)  # Array indexing still gets + 1!

  def test_lua_while_non_unwrap_init_statement(self):
    """Verifies that Lua transpilation emits non-unwrapping while init-statements once before the loop."""
    code = """
    func test_while() {
      while let x = count; count > 0 {
        count = 0;
      }
    }
    """
    lua_out = self._transpile(code)
    self.assertIn("local x = count", lua_out)
    self.assertIn("while (count > 0) do", lua_out)

  def test_lua_map_for_loop(self):
    """Verifies that Lua transpilation converts map for-loops to pairs()."""
    code = """
    func test_map_for() {
      let m = {"a": 1, "b": 2};
      for k, v in m {
        print(k);
      }
    }
    """
    lua_out = self._transpile(code)
    self.assertIn("for k, v in pairs(m) do", lua_out)


  def test_lua_string_methods(self):
    """Verifies Lua transpilation of String methods."""
    code = """
    func test_str() {
      let s = "  hello world  ";
      let sz = s.size();
      let emp = s.empty();
      let clean = s.strip();
      let slashed = "///path///".strip("/");
      let low = clean.lower();
      let up = clean.upper();
      let has = clean.contains("world");
      let pos_fwd = clean.find("o");
      let pos = clean.find("o", reverse = true);
      let parts = clean.split(",");
    }
    """
    lua_out = self._transpile(code)
    self.assertIn("local sz = (#s)", lua_out)
    self.assertIn("local emp = (#s == 0)", lua_out)
    self.assertIn("local clean = _sapphire_string_strip(s)", lua_out)
    self.assertIn('local slashed = _sapphire_string_strip("///path///", "/")', lua_out)
    self.assertIn("local low = string.lower(clean)", lua_out)
    self.assertIn("local up = string.upper(clean)", lua_out)
    self.assertIn('local has = (string.find(clean, "world", 1, true) ~= nil)', lua_out)
    self.assertIn('local pos_fwd = _sapphire_string_find(clean, "o")', lua_out)
    self.assertIn('local pos = _sapphire_string_find(clean, "o", nil, true)', lua_out)
    self.assertIn('local parts = _sapphire_string_split(clean, ",")', lua_out)

  def test_transpile_with_explicit_args(self):
    """Verifies passing source_file and source_map_builder directly to transpile method."""
    input_stream = InputStream("let x = 10;")
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)

    transpiler = LuaTranspiler()
    sm_builder = SourceMapBuilder("direct.sp")
    lua_out = transpiler.transpile(ast, source_file="direct.sp", source_map_builder=sm_builder)
    self.assertEqual(transpiler.source_file, "direct.sp")
    self.assertEqual(transpiler.source_map_builder, sm_builder)

  def test_casting_and_conversions_lua(self):
    """Verifies Lua transpilation of casting (as) and String conversions."""
    code = """
    enum Status { Active = 1 }
    enum LogLevel { Info = "INFO" }

    struct Parent { var hp: int; }
    struct Child: Parent { var mp: int; }

    func test_conv() {
      let f = 10 as float;
      let i = 3.14 as int;
      let b = 1 as bool;
      let str_cast = 10 as String;
      let s1 = String.from(42);
      let s2 = String.from(true);

      let p_int = "123".to_int();
      let p_hex = "FF".to_int(radix = 16);
      let p_float = "3.14".to_float();
      let p_bool = "true".to_bool();

      let e1 = Status.from(1);
      let l1 = LogLevel.from("INFO");

      let c = Child { hp = 100, mp = 50 };
      let parent_cast = c as Parent;
    }
    """
    lua = self._transpile(code)
    self.assertIn("tonumber(10)", lua)
    self.assertIn("math.floor(tonumber(3.14))", lua)
    self.assertIn("(not not 1)", lua)
    self.assertIn("tostring(10)", lua)
    self.assertIn("tostring(42)", lua)
    self.assertIn("tostring(true)", lua)
    self.assertIn("_sapphire_string_to_int(", lua)
    self.assertIn("_sapphire_string_to_float(", lua)
    self.assertIn("_sapphire_string_to_bool(", lua)
    self.assertIn("_sapphire_enum_from(Status", lua)
    self.assertIn("_sapphire_enum_from(LogLevel", lua)

  def test_interpolated_string(self):
    """Verifies transpilation of f-strings to Lua string concatenation."""
    code = """
    func main() {
      let name = "Hero";
      let count = 42;
      let msg = f"Hello {name}, count: {count}!";
      let empty_str = f"";
      let single_lit = f"just text";
      let single_expr = f"{count}";
    }
    """
    lua = self._transpile(code)
    self.assertIn('("Hello " .. tostring(name) .. ", count: " .. tostring(count) .. "!")', lua)
    self.assertIn('local empty_str = ""', lua)
    self.assertIn('local single_lit = "just text"', lua)
    self.assertIn('local single_expr = tostring(count)', lua)


if __name__ == "__main__":
  unittest.main()
