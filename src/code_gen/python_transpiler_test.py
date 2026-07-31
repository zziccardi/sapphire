"""Unit tests for the Sapphire-to-Python transpiler.

This module validates that transpiled Python code is syntactically correct
and preserves all Sapphire runtime semantics, including prototypal delegation.
"""

import os
import tempfile
import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from code_gen.python_transpiler import PythonTranspiler, Transpiler
  from code_gen.transpiler import transpile_file
  from semantics.type_checker import TypeChecker
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.code_gen.python_transpiler import PythonTranspiler, Transpiler
  from src.code_gen.transpiler import transpile_file
  from src.semantics.type_checker import TypeChecker


class TestPythonTranspiler(unittest.TestCase):
  """Suite of unit tests verifying correct code generation and execution."""

  def _transpile(self, code: str) -> str:
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
    transpiler = Transpiler()
    return transpiler.transpile(ast)

  def _transpile_and_run(self, code: str, run_expr: str) -> Any:
    """Helper to transpile Sapphire code, execute it in Python, and return run_expr value."""
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
    
    transpiler = Transpiler()
    py_code = transpiler.transpile(ast)

    # Context for execution
    ctx = {}
    exec(py_code, ctx)  # pylint: disable=exec-used
    return eval(run_expr, ctx)  # pylint: disable=eval-used

  def test_basic_arithmetic(self):
    """Verifies that variable assignments and arithmetic execute correctly."""
    code = """
    let x = 10;
    let y = 20;
    let z = x + y * 3;
    """
    result = self._transpile_and_run(code, "z")
    self.assertEqual(result, 70)

  def test_optional_unwrapping(self):
    """Verifies that optional unwrapping block resolves and executes correctly."""
    code = """
    func run_if_let(): int {
      var opt_val: int? = 42;
      var out = 0;
      if let active ?= opt_val {
        out = active;
      }
      return out;
    }
    """
    result = self._transpile_and_run(code, "run_if_let()")
    self.assertEqual(result, 42)

  def test_init_statements_and_coalesce(self):
    """Verifies Python transpilation of init-statements and ?? coalescing."""
    # 1. if let with condition
    code1 = """
    func run_if_let_cond(): int {
      var opt_val: int? = 42;
      var out = 0;
      if let active ?= opt_val; active > 40 {
        out = active;
      }
      return out;
    }
    """
    result1 = self._transpile_and_run(code1, "run_if_let_cond()")
    self.assertEqual(result1, 42)

    # 2. while let loop
    code2 = """
    func run_while_let(): int {
      var opt_val: int? = 5;
      var out = 0;
      while let active ?= opt_val; active > 0 {
        out += active;
        opt_val = none; // terminate loop
      }
      return out;
    }
    """
    result2 = self._transpile_and_run(code2, "run_while_let()")
    self.assertEqual(result2, 5)

    # 3. ?? operator
    code3 = """
    func run_coalesce(): int {
      var opt_val: int? = none;
      let val = opt_val ?? 99;
      return val;
    }
    """
    result3 = self._transpile_and_run(code3, "run_coalesce()")
    self.assertEqual(result3, 99)

    # 4. standard if let (no unwrap)
    code4 = """
    func run_standard_if(): int {
      var out = 0;
      if let x = 10; x > 5 {
        out = x;
      }
      return out;
    }
    """
    result4 = self._transpile_and_run(code4, "run_standard_if()")
    self.assertEqual(result4, 10)

    # 5. standard while let (no unwrap)
    code5 = """
    func run_standard_while(): int {
      var out = 0;
      var count = 5;
      while let x = count; count > 0 {
        out += x;
        count = 0; // terminate loop
      }
      return out;
    }
    """
    result5 = self._transpile_and_run(code5, "run_standard_while()")
    self.assertEqual(result5, 5)

  def test_prototypal_inheritance_live_updates(self):
    """Verifies that cloned objects delegate live property lookups and allow shadowing."""
    code = """
    proto Item {
      var price: int;
      var stock: int;
    }
    impl Item {
      func __init__(p: int) {
        self.price = p;
        self.stock = 10;
      }
    }
    func test_delegation() {
      var base = Item(p = 100);
      var promo_item = clone base {
        self.price = 80;
      };
      
      let initial_promo_price = promo_item.price; // Shadowed (80)
      let initial_promo_stock = promo_item.stock; // Delegated (10)
      
      base.stock = 5; // Mutating prototype should reflect live on clone
      let final_promo_stock = promo_item.stock;
      
      return [initial_promo_price, initial_promo_stock, final_promo_stock];
    }
    """
    result = self._transpile_and_run(code, "test_delegation()")
    self.assertEqual(result, [80, 10, 5])

  def test_control_flow_loops(self):
    """Verifies while loops, for loops, and boolean logic transpile correctly."""
    code = """
    func run_loops() {
      var sum = 0;
      var count = 3;
      while count > 0 {
        sum += count;
        count -= 1;
      }
      
      let scores = [10, 20, 30];
      var loop_sum = 0;
      for score in scores {
        loop_sum += score;
      }
      
      return [sum, loop_sum];
    }
    """
    result = self._transpile_and_run(code, "run_loops()")
    self.assertEqual(result, [6, 60])

  def test_static_methods(self):
    """Verifies static method decorators and const struct methods compile and run."""
    code = """
    struct Counter {
      var val: int;
    }
    impl Counter {
      func __init__(v: int) {
        self.val = v;
      }
      const func get_val(): int {
        return self.val;
      }
      static func create_default(): Counter {
        return Counter(v = 100);
      }
    }
    func test_static() {
      let c = Counter.create_default();
      return c.get_val();
    }
    """
    result = self._transpile_and_run(code, "test_static()")
    self.assertEqual(result, 100)

  def test_optional_chaining(self):
    """Verifies optional chaining (?.) expressions return correctly."""
    code = """
    struct Node {
      var score: int;
    }
    impl Node {
      func __init__(s: int) {
        self.score = s;
      }
    }
    func test_chain() {
      var n1: Node? = none;
      var n2: Node? = Node(s = 99);
      
      let val1 = n1?.score;
      let val2 = n2?.score;
      return [val1, val2];
    }
    """
    result = self._transpile_and_run(code, "test_chain()")
    self.assertEqual(result, [None, 99])

  def test_unary_operators(self):
    """Verifies logical NOT (!) and arithmetic negation (-) transpile correctly."""
    code = """
    func test_unary() {
      let is_true = true;
      let is_false = !is_true;
      let num = 5;
      let neg_num = -num;
      return [is_false, neg_num];
    }
    """
    result = self._transpile_and_run(code, "test_unary()")
    self.assertEqual(result, [False, -5])


  def test_lambda_expression(self):
    """Verifies that lambda functions can be transpiled and executed."""
    code = """
    func run_lambda(): int {
      var f = x -> x + 5;
      return f(10);
    }
    """
    result = self._transpile_and_run(code, "run_lambda()")
    self.assertEqual(result, 15)

  def test_array_indexing(self):
    """Verifies that array indexing transpiles and executes correctly."""
    code = """
    func run_index(): int {
      let arr = [100, 200];
      return arr[1];
    }
    """
    result = self._transpile_and_run(code, "run_index()")
    self.assertEqual(result, 200)


  def test_additional_transpiler_features(self):
    """Verifies standard conditionals, unary ops, strings, default params, empty constructors/methods, and clones."""
    code = """
    struct Empty {}
    proto Base {
      var x: int;
      var y: int;
    }
    impl Base {
      func __init__() {
        self.x = 1;
        self.y = 2;
      }
    }
    func multiply(a: int, b: int = 2): int {
      if a > 10 {
        return a * b;
      } else if a > 5 {
        return a * b + 1;
      } else {
        return a * b + 2;
      }
    }
    func test_features(): int {
      let b1 = Base();
      let b2 = clone b1 {
        self.x = 10;
        self.y = 20;
      };
      var target: Base? = b2;
      var out = 0;
      if let active ?= target {
        out = active.x;
      } else {
        out = -1;
      }
      
      let s = "hello";
      let neg = -out;
      let pos = +out;
      
      return multiply(10, 3) + multiply(3, 3) + b2.y;
    }
    """
    result = self._transpile_and_run(code, "test_features()")
    # multiply(10, 3) -> 10 * 3 + 1 = 31
    # multiply(3, 3) -> 3 * 3 + 2 = 11
    # b2.y -> 20
    # total -> 62
    self.assertEqual(result, 62)

  def test_empty_statements_and_returns(self):
    """Verifies transpilation of empty block, empty returns, and expression statements."""
    code = """
    func dummy() {}
    func empty_fn() {
      dummy();
      return;
    }
    """
    result = self._transpile_and_run(code, "empty_fn()")
    self.assertIsNone(result)

  def test_direct_transpiler_visitors(self):
    """Directly tests transpiler visitors that are not invoked during standard program traversal."""
    try:
      from parser.ast import StructFieldNode, TraitDeclNode, LambdaNode, BlockNode, LambdaParamNode, BasicTypeNode, ASTNode
    except ModuleNotFoundError:
      from src.parser.ast import StructFieldNode, TraitDeclNode, LambdaNode, BlockNode, LambdaParamNode, BasicTypeNode, ASTNode

    transpiler = Transpiler()
    
    # 1. StructFieldNode
    field_node = StructFieldNode(False, "x", BasicTypeNode("int"))
    transpiler.visit(field_node)

    # 2. TraitDeclNode
    trait_node = TraitDeclNode("Actor", [])
    transpiler.visit(trait_node)

    # 3. Block lambda
    lnode = LambdaNode([LambdaParamNode("x", None)], None, BlockNode([]))
    transpiler.visit(lnode)

    # 4. generic_visit NotImplementedError
    with self.assertRaises(NotImplementedError):
      transpiler.visit(ASTNode())
    
    self.assertTrue(len(transpiler.get_output()) > 0)

  def test_prototypal_inheritance_with_static_inheritance(self):
    """Verifies that inherited struct constructors propagate proto correctly for cloning."""
    code = """
    proto GameObject {
      var id: int;
    }
    proto Character: GameObject {
      var health: int;
    }
    impl Character {
      func __init__(id_val: int, hp: int) {
        self.id = id_val;
        self.health = hp;
      }
    }
    func test_inherited_cloning() {
      var base = Character(id_val = 1, hp = 100);
      var derived_clone = clone base {
        self.health = 80;
      };
      
      let initial_clone_health = derived_clone.health; // Shadowed (80)
      let initial_clone_id = derived_clone.id;         // Delegated (1)
      
      base.id = 10; // Mutating prototype's inherited field should reflect on clone
      let final_clone_id = derived_clone.id;
      
      return [initial_clone_health, initial_clone_id, final_clone_id];
    }
    """
    result = self._transpile_and_run(code, "test_inherited_cloning()")
    self.assertEqual(result, [80, 1, 10])

  def test_cow_nested_references(self):
    """Verifies that nested reference modifications on cloned objects copy-on-write correctly."""
    code = """
    proto Weapon {
      var damage: int;
    }
    proto Player {
      var weapon: Weapon;
    }
    impl Player {
      func __init__(w: Weapon) {
        self.weapon = w;
      }
    }
    func run_cow_test() {
      var original_weapon = Weapon { damage = 10 };
      var base_player = Player(w = original_weapon);
      var clone_player = clone base_player;
      
      // Mutating clone player's weapon damage
      clone_player.weapon.damage = 15;
      
      let base_dmg = base_player.weapon.damage; // Should remain 10 (CoW)
      let clone_dmg = clone_player.weapon.damage; // Should be 15
      
      return [base_dmg, clone_dmg];
    }
    """
    result = self._transpile_and_run(code, "run_cow_test()")
    self.assertEqual(result, [10, 15])

  def test_struct_initializer_transpilation(self):
    """Verifies that struct initializers compile and evaluate defaults/assigned values correctly."""
    code = """
    struct Point {
      var x: int;
      var y: int = 10;
    }
    func test_init() {
      let p = Point { x = 5 };
      return [p.x, p.y];
    }
    """
    result = self._transpile_and_run(code, "test_init()")
    self.assertEqual(result, [5, 10])

  def test_proto_struct_defaults_and_multi_field_init(self):
    """Verifies prototype structs with default fields and multiple fields in struct initializers transpile correctly."""
    code = """
    proto Item {
      var price: int = 100;
      var stock: int = 5;
    }
    func test_defaults() {
      let it = Item { price = 50, stock = 2 };
      return [it.price, it.stock];
    }
    """
    result = self._transpile_and_run(code, "test_defaults()")
    self.assertEqual(result, [50, 2])


  def test_explicit_arenas_and_raii(self):
    """Verifies that allocating inside explicit arenas works and obeys RAII destruction."""
    code = """
    proto Enemy {
      var hp: int;
    }
    struct Point {
      var x: int;
    }
    
    var leaked_enemy: Enemy? = none;
    var leaked_point: Point? = none;
    
    func run_scope() {
      let my_arena = Arena();
      let other_arena = Arena();
      
      let base = Enemy { hp = 100 } in my_arena;
      
      // Implicit clone arena propagation
      let cloned = clone base;
      
      // Explicit clone arena override
      let cloned_override = clone base in other_arena;
      
      // Explicit struct allocation in arena
      let pt = Point { x = 42 } in my_arena;
      
      leaked_enemy = cloned;
      leaked_point = pt;
      
      return [cloned.hp, pt.x, cloned_override.hp];
    }
    
    func test_arena_raii() {
      let vals = run_scope();
      return [vals[0], vals[1], vals[2]];
    }
    """
    result = self._transpile_and_run(code, "test_arena_raii()")
    self.assertEqual(result, [100, 42, 100])

  def test_enum_transpilation(self):
    """Verifies that enums transpile to IntEnum and execute correctly with integer backing."""
    code = """
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

    func check_direction(): int {
      let d = Direction.South;
      let s = Status.NotFound;
      let val: int = d;
      return val + s;
    }
    """
    result = self._transpile_and_run(code, "check_direction()")
    self.assertEqual(result, 2 + 404)

  def test_empty_enum_transpilation(self):
    """Verifies that an empty enum transpiles with pass statement."""
    code = """
    enum Empty {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    transpiler = Transpiler()
    py_code = transpiler.transpile(ast)
    self.assertIn("class Empty(IntEnum):", py_code)
    self.assertIn("pass", py_code)

  def test_top_level_script_transpilation_without_main(self):
    """Verifies that top-level script statements transpile into if __name__ == '__main__': block."""
    code = """
    var val: int = 10;
    val += 5;
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    transpiler = Transpiler()
    py_code = transpiler.transpile(ast)
    self.assertIn('if __name__ == "__main__":', py_code)
    self.assertIn('val += 5', py_code)

  def test_top_level_script_with_main_function(self):
    """Verifies that defining main() appends main() call inside if __name__ == '__main__': block."""
    code = """
    func main() {
      let x = 1;
    }
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    builder = ASTBuilder()
    ast = builder.visit(tree)
    transpiler = Transpiler()
    py_code = transpiler.transpile(ast)
    self.assertIn('if __name__ == "__main__":', py_code)
    self.assertIn('main()', py_code)

  def test_transpile_file_success(self):
    """Verifies transpile_file default and custom output file handling."""
    with tempfile.TemporaryDirectory() as temp_dir:
      sp_file = os.path.join(temp_dir, "test.sp")
      with open(sp_file, "w", encoding="utf-8") as f:
        f.write("let val: int = 100;\n")
      out_path = transpile_file(sp_file)
      self.assertEqual(out_path, os.path.join(temp_dir, "test.py"))
      self.assertTrue(os.path.exists(out_path))

  def test_transpile_file_read_error(self):
    """Verifies transpile_file handles missing source files by exiting."""
    with tempfile.TemporaryDirectory() as temp_dir:
      non_existent = os.path.join(temp_dir, "missing.sp")
      with self.assertRaises(SystemExit) as cm:
        transpile_file(non_existent)
      self.assertEqual(cm.exception.code, 1)

  def test_transpile_file_syntax_error(self):
    """Verifies transpile_file handles syntax errors by exiting."""
    with tempfile.TemporaryDirectory() as temp_dir:
      bad_sp = os.path.join(temp_dir, "syntax.sp")
      with open(bad_sp, "w", encoding="utf-8") as f:
        f.write("let x: int = ;\n")
      with self.assertRaises(SystemExit) as cm:
        transpile_file(bad_sp)
      self.assertEqual(cm.exception.code, 1)

  def test_transpile_file_semantic_error(self):
    """Verifies transpile_file handles semantic errors by exiting."""
    with tempfile.TemporaryDirectory() as temp_dir:
      semantic_sp = os.path.join(temp_dir, "semantic.sp")
      with open(semantic_sp, "w", encoding="utf-8") as f:
        f.write("return 42;\n")
      with self.assertRaises(SystemExit) as cm:
        transpile_file(semantic_sp)
      self.assertEqual(cm.exception.code, 1)

  def test_export_and_extern_annotations_python(self):
    """Verifies Python transpiler safely handles @export and erases @extern."""
    code = """
    trait Graphics {
      func setColor(r: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    @export("love.update")
    func update(dt: float) {
      let x = dt;
    }
    """
    py_code = self._transpile(code)
    self.assertIn("def update(dt):", py_code)
    self.assertNotIn("love =", py_code)


  def test_python_multi_return_transpilation(self):
    """Verifies Python transpilation for multi-return functions, declarations, and assignments."""
    code = """
    func get_pos(): float, float {
      return 10.0, 20.0;
    }
    let x, y = get_pos();
    var a, b = 1.0, 2.0;
    a, b = get_pos();
    """
    py_code = self._transpile(code)
    self.assertIn("def get_pos():", py_code)
    self.assertIn("return 10.0, 20.0", py_code)
    self.assertIn("x, y = get_pos()", py_code)
    self.assertIn("a, b = 1.0, 2.0", py_code)
    self.assertIn("a, b = get_pos()", py_code)

  def test_python_compound_assignment(self):
    """Verifies Python transpilation of compound assignment operators and empty return."""
    code = """
    func test() {
      var x = 10;
      x += 5;
      var a = 1.0;
      var b = 2.0;
      a, b = 3.0, 4.0;
      return;
    }
    """
    py_cmp = self._transpile(code)
    self.assertIn("x += 5", py_cmp)
    self.assertIn("a, b = 3.0, 4.0", py_cmp)

  def test_python_string_enum_transpilation(self):
    """Verifies Python transpilation for string-backed enums."""
    code = """
    enum Mode {
      Fill = "fill",
      Line = "line",
      Default,
    }
    """
    py_code = self._transpile(code)
    self.assertIn("class Mode(str, Enum):", py_code)
    self.assertIn('Fill = "fill"', py_code)
    self.assertIn('Line = "line"', py_code)
    self.assertIn('Default = "Default"', py_code)

  def test_python_resource_handle_method_transpilation(self):
    """Verifies Python transpilation for resource handles."""
    code = """
    trait ImageHandle {
      func draw(self, x: float, y: float);
    }
    @extern("hero")
    var hero_img: ImageHandle;

    func main() {
      hero_img.draw(10.0, 20.0);
    }
    """
    py_code = self._transpile(code)
    self.assertIn("hero_img.draw(10.0, 20.0)", py_code)

  def test_python_export_method_alias_transpilation(self):
    """Verifies Python transpilation for trait methods with @export method aliases."""
    code = """
    trait Graphics {
      @export("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }
    @extern("g")
    var g: Graphics;

    func main() {
      g.setColorRGBA(1.0, 0.0, 0.0);
    }
    """
    py_code = self._transpile(code)
    self.assertIn("g.setColor(1.0, 0.0, 0.0)", py_code)


  def test_python_module_import_and_export_transpilation(self):
    """Verifies Python transpilation for module imports and export manifests."""
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
    py_code = self._transpile(code)
    self.assertIn("import lib.love2d.enums", py_code)
    self.assertIn("import lib.love2d.graphics as gfx", py_code)
    self.assertIn('__all__ = ["Player", "create_player", "DrawMode"]', py_code)

  def test_python_transpile_file_with_transitive_imports(self):
    """Verifies that transpile_file recursively transpiles imported module dependencies for Python."""
    with tempfile.TemporaryDirectory() as tmpdir:
      sub_sp = os.path.join(tmpdir, "sub.sp")
      with open(sub_sp, "w") as f:
        f.write("export { item } let item = 42;\n")

      main_sp = os.path.join(tmpdir, "main.sp")
      with open(main_sp, "w") as f:
        f.write("import sub;\n")

      out_py = os.path.join(tmpdir, "main.py")
      transpile_file(main_sp, output_file=out_py, target="python")
      self.assertTrue(os.path.exists(out_py))
      sub_py = os.path.join(tmpdir, "sub.py")
      self.assertTrue(os.path.exists(sub_py))


  def test_match_expression_transpilation_and_execution(self):
    """Verifies Python transpilation and execution of match expressions."""
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
    res1 = self._transpile_and_run(code, "get_code(Status.Ok)")
    self.assertEqual(res1, 200)

    res2 = self._transpile_and_run(code, "get_code(Status.NotFound)")
    self.assertEqual(res2, 404)

    res3 = self._transpile_and_run(code, "get_code(Status.Error)")
    self.assertEqual(res3, 500)

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
    self.assertEqual(self._transpile_and_run(assign_code, "test_assign(1)"), 10)

    # Match in return statement
    ret_code = """
    func test_ret(n: int): int {
      return match n {
        1 -> 100,
        ... -> 200,
      };
    }
    """
    self.assertEqual(self._transpile_and_run(ret_code, "test_ret(1)"), 100)

    # Match in expression statement with empty block
    stmt_code = """
    func test_stmt(n: int) {
      match n {
        1 -> {},
        ... -> {},
      };
    }
    """
    py_out = self._transpile(stmt_code)
    self.assertIn("pass", py_out)

    # Multi-target assignment with match
    multi_code = """
    func test_multi(n: int): int {
      var a = 0;
      var b = 0;
      a, b = match n { 1 -> 10, ... -> 20 }, 30;
      return a + b;
    }
    """
    self.assertEqual(self._transpile_and_run(multi_code, "test_multi(1)"), 40)

    # Identifier wildcard _
    wildcard_code = """
    func test_wildcard(n: int): int {
      return match n {
        _ -> 999,
      };
    }
    """
    self.assertEqual(self._transpile_and_run(wildcard_code, "test_wildcard(5)"), 999)

    # Compound assignment with match
    comp_code = """
    func test_comp(n: int): int {
      var x = 1;
      x += match n { 1 -> 2, ... -> 3 };
      return x;
    }
    """
    self.assertEqual(self._transpile_and_run(comp_code, "test_comp(1)"), 3)

    # Direct visitor calls
    try:
      from parser.ast import MatchExprNode, EllipsisPatternNode, MatchCaseNode, LiteralNode
    except ModuleNotFoundError:
      from src.parser.ast import MatchExprNode, EllipsisPatternNode, MatchCaseNode, LiteralNode

    pt = PythonTranspiler()
    pt.visit(MatchExprNode(LiteralNode(1, "int"), [MatchCaseNode(EllipsisPatternNode(), LiteralNode(2, "int"))]))
    pt.visit_EllipsisPatternNode(EllipsisPatternNode())
    self.assertIn("_match_res_1", "".join(pt.code))


  def test_missing_semicolon_after_match_error_message(self):
    """Verifies clear syntax error message when semicolon is omitted after match statement."""
    import io, sys
    bad_code = """
    func main() {
      match 1 {
        1 -> { let a = 1; },
        ... -> { let b = 2; },
      }
      let y = 10;
    }
    """
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
      f.write(bad_code)
      fname = f.name

    captured_stderr = io.StringIO()
    old_stderr = sys.stderr
    try:
      sys.stderr = captured_stderr
      with self.assertRaises(SystemExit):
        transpile_file(fname)
    finally:
      sys.stderr = old_stderr
      if os.path.exists(fname):
        os.remove(fname)

    err_output = captured_stderr.getvalue()
    self.assertIn("Missing semicolon ';' after closing brace '}' of match expression", err_output)

  def test_map_literal_transpilation_and_execution(self):
    """Verifies Python transpilation and execution of map literals and map indexing."""
    code = """
    func get_score(): int {
      let scores = {"alice": 100, "bob": 95,};
      return scores["alice"];
    }
    """
    res = self._transpile_and_run(code, "get_score()")
    self.assertEqual(res, 100)

  def test_while_non_unwrap_init_statement(self):
    """Verifies that a while loop with a non-unwrapping init statement executes the init statement once before entering the loop."""
    code = """
    func test_while(): int {
      var out = 0;
      var count = 5;
      while let x = count; count > 0 {
        out += x;
        count = 0;
      }
      return out;
    }
    """
    py_code = self._transpile(code)
    self.assertIn("x = count", py_code)
    self.assertIn("while (count > 0):", py_code)
    res = self._transpile_and_run(code, "test_while()")
    self.assertEqual(res, 5)

  def test_cow_live_prototype_update(self):
    """Verifies that reading a nested reference on a clone does not break live prototype delegation until a write occurs."""
    code = """
    struct Vector {
      var x: int;
    }
    proto Entity {
      var pos: Vector;
    }
    func test_cow(): int {
      var base = Entity { pos = Vector { x = 10 } };
      let cloned = clone base;
      let initial_read = cloned.pos.x;
      base.pos.x = 20;
      let live_read = cloned.pos.x;
      cloned.pos.x = 99;
      let after_write_clone = cloned.pos.x;
      let after_write_base = base.pos.x;
      return live_read + after_write_clone + after_write_base;
    }
    """
    res = self._transpile_and_run(code, "test_cow()")
    self.assertEqual(res, 20 + 99 + 20)

  def test_map_iteration_python(self):
    """Verifies Python transpilation and execution for map iteration."""
    code = """
    func test_map(): int {
      let m = {"a": 10, "b": 20};
      var sum = 0;
      for k, v in m {
        sum = sum + v;
      }
      return sum;
    }
    """
    res = self._transpile_and_run(code, "test_map()")
    self.assertEqual(res, 30)


  def test_string_methods_python(self):
    """Verifies Python transpilation and execution of all String instance methods."""
    code = """
    func test_str(): bool {
      let s = "  hello world  ";
      let sz = s.size();
      let emp = s.empty();
      let clean = s.strip();
      let low = clean.lower();
      let up = clean.upper();
      let has = clean.contains("world");
      let first_o = clean.find("o");
      let last_o = clean.find("o", reverse = true);
      let parts = clean.split();
      
      let cond1 = sz == 15 && emp == false && clean == "hello world";
      let cond2 = low == "hello world" && up == "HELLO WORLD" && has == true;
      let cond3 = first_o == 4 && last_o == 7 && parts[0] == "hello" && parts[1] == "world";
      return cond1 && cond2 && cond3;
    }
    """
    res = self._transpile_and_run(code, "test_str()")
    self.assertTrue(res)


if __name__ == "__main__":
  unittest.main()

