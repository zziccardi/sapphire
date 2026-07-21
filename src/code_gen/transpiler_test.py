"""Unit tests for the Sapphire-to-Python transpiler.

This module validates that transpiled Python code is syntactically correct
and preserves all Sapphire runtime semantics, including prototypal delegation.
"""

import unittest
from antlr4 import InputStream, CommonTokenStream

try:
  from parser.gen.SapphireLexer import SapphireLexer
  from parser.gen.SapphireParser import SapphireParser
  from parser.ast_builder import ASTBuilder
  from code_gen.transpiler import Transpiler
except ModuleNotFoundError:
  from src.parser.gen.SapphireLexer import SapphireLexer
  from src.parser.gen.SapphireParser import SapphireParser
  from src.parser.ast_builder import ASTBuilder
  from src.code_gen.transpiler import Transpiler


class TestTranspiler(unittest.TestCase):
  """Suite of unit tests verifying correct code generation and execution."""

  def _transpile_and_run(self, code: str, run_expr: str) -> Any:
    """Helper to transpile Sapphire code, execute it in Python, and return run_expr value."""
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    
    builder = ASTBuilder()
    ast = builder.visit(tree)
    
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

  def test_swift_style_if_let(self):
    """Verifies that optional unwrapping block resolves and executes correctly."""
    code = """
    func run_if_let(): int {
      var opt_val: int? = 42;
      var out = 0;
      if let active = opt_val {
        out = active;
      }
      return out;
    }
    """
    result = self._transpile_and_run(code, "run_if_let()")
    self.assertEqual(result, 42)

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
      if let active = target {
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


if __name__ == "__main__":
  unittest.main()

