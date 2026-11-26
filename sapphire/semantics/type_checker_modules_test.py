"""Module import, export, extern, and global semantic tests."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from sapphire.parser.ast_builder import ASTBuilder
from sapphire.parser.gen.SapphireLexer import SapphireLexer
from sapphire.parser.gen.SapphireParser import SapphireParser
from sapphire.semantics.symbol_table import (
  PrimitiveType,
  StructField,
  StructType,
  VariableSymbol,
)
from sapphire.semantics.type_checker import SemanticError, TypeChecker
from testing.test_utils import TypeCheckerTestBase


class TestTypeCheckerModules(TypeCheckerTestBase, unittest.TestCase):
  """Module import, export, extern, and global semantic tests."""

  def test_module_level_constant_expressions(self):
    """Verifies valid compile-time constant expressions at module scope."""
    code = """
    let MAX_SPEED: int = 100 + 20 * 2;
    let PI = 3.14159;
    let TITLE = f"Game v{1}";
    let STATUS = true ? "ACTIVE" : "IDLE";
    let NUMBERS = [1, 2, 3];
    let CONFIG = {"timeout": 30};

    struct Point {
      var x: float;
      var y: float;
    }

    let ORIGIN = Point { x = 0.0, y = 0.0 };

    func main() {
      let speed = MAX_SPEED;
    }
    """
    self._check(code)

  def test_module_level_dynamic_initialization_rejected(self):
    """Verifies that dynamic function calls are rejected in module-level initializers."""
    code = """
    func get_default(): int {
      return 42;
    }

    let BAD_VAL = get_default();
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("must be initialized with a compile-time constant expression", str(context.exception))

  def test_module_level_mutable_export_rejected(self):
    """Verifies that exporting mutable module-level variables is prohibited."""
    code = """
    export {
      my_count,
    }

    var my_count = 0;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Cannot export mutable module-level variable", str(context.exception))

  def test_extern_and_export_type_checking(self):
    """Verifies that @extern var and trait signatures permit type-safe calls and reject invalid arguments."""
    code = """
    trait Graphics {
      func rectangle(mode: String, x: float, y: float, w: float, h: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.rectangle(mode = "fill", x = 10.0, y = 20.0, w = 100.0, h = 50.0);
    }
    """
    self._check(code)

    bad_code = """
    trait Graphics {
      func rectangle(mode: String, x: float, y: float, w: float, h: float);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.rectangle(mode = 123, x = 10.0, y = 20.0, w = 100.0, h = 50.0);
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(bad_code)
    self.assertIn("Argument type mismatch at position 1. Expected 'String', got 'int'.", str(context.exception))

    invalid_member_code = """
    trait Graphics {
      func rectangle(mode: String);
    }

    struct LoveEngine {
      var graphics: Graphics;
    }

    @extern("love")
    var love: LoveEngine;

    func main() {
      love.graphics.non_existent();
    }
    """
    with self.assertRaises(SemanticError) as context:
      self._check(invalid_member_code)
    self.assertIn("Trait 'Graphics' has no member 'non_existent'.", str(context.exception))

  def test_extern_var_redefinition(self):
    """Verifies redefinition error for duplicate @extern var identifiers."""
    code = """
    @extern
    var love: int;

    @extern
    var love: float;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code)
    self.assertIn("Redefinition of identifier 'love'.", str(context.exception))

  def test_extern_var_invalid_declaration(self):
    """Verifies semantic errors for @extern variable declarations with initializers or missing type annotations."""
    code_init = """
    @extern
    let love = 123;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_init)
    self.assertIn("An '@extern' variable declaration cannot have an initializer expression.", str(context.exception))

    code_missing_type = """
    @extern
    var love;
    """
    with self.assertRaises(SemanticError) as context:
      self._check(code_missing_type)
    self.assertIn("An '@extern' variable declaration for 'love' requires an explicit type annotation.", str(context.exception))

  def test_trait_export_method_type_checking(self):
    """Verifies type checking for trait methods annotated with @export."""
    code = """
    trait Graphics {
      @export("setColor")
      func setColorRGBA(r: float, g: float, b: float);
    }

    @extern
    var g: Graphics;

    func main() {
      g.setColorRGBA(1.0, 0.0, 0.0);
    }
    """
    self._check(code)

  def test_module_export_manifest_validation(self):
    """Verifies that export manifests with valid definitions and re-exported symbols type check clean."""
    code = """
    import lib.love2d.enums;

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
    self._check(code)

  def test_undefined_export_symbol_error(self):
    """Verifies that exporting an undefined symbol raises a SemanticError."""
    code = """
    export {
      NonExistentSymbol,
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("Exported symbol 'NonExistentSymbol' is not defined in module.", str(ctx.exception))

  def test_undefined_export_symbol_with_defined_structs(self):
    """Verifies that exporting an undefined symbol in a module with other defined structs raises a SemanticError."""
    code = """
    export {
      PathNode,
      Enemy,
      create_enemy_archetype,
    }

    struct PathNode {
      let x: int;
      let y: int;
    }

    struct Enemy {
      var id: int = 0;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code)
    self.assertIn("Exported symbol 'create_enemy_archetype' is not defined in module.", str(ctx.exception))

  def test_module_export_errors_and_type_resolution(self):
    """Verifies module type resolution and export error branches."""
    from sapphire.semantics.symbol_table import (
      ModuleSymbol,
      PrimitiveType,
    )


    # 1. Export from non-imported module
    with self.assertRaises(SemanticError):
      self._check("""
      export {
        unimported.Symbol
      }
      """)

    # 2. Export non-existent symbol from imported module with populated exports
    code = """
    import lib.love2d.enums;
    export {
      enums.MissingSymbol
    }
    """
    checker = TypeChecker()
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker._declare_imports(ast)
    enums_sym = checker.symbol_table.lookup("enums")
    if isinstance(enums_sym, ModuleSymbol):
      enums_sym.exports["DrawMode"] = VariableSymbol("DrawMode", PrimitiveType("int"), is_mutable=False)

    with self.assertRaises(SemanticError):
      checker.check(ast)

  def test_module_qualified_type_and_member_access(self):
    """Verifies type resolution for dot-qualified types (enums.DrawMode) and member access."""
    from sapphire.semantics.symbol_table import (
      EnumType,
      ModuleSymbol,
    )


    code = """
    import lib.love2d.enums;

    var mode: enums.DrawMode;
    let mode_val = enums.DrawMode;
    """
    checker = TypeChecker()
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker._declare_imports(ast)
    enums_sym = checker.symbol_table.lookup("enums")
    if isinstance(enums_sym, ModuleSymbol):
      enums_sym.exports["DrawMode"] = EnumType("DrawMode")

    checker.check(ast)

    # Unknown exported member on imported module must raise SemanticError
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      import lib.love2d.enums;
      func f() {
        let missing = enums.NonExistent;
      }
      """)
    self.assertIn("has no exported member 'NonExistent'", str(ctx.exception))

  def test_real_file_module_import(self):
    """Verifies that type checking graphics.sp automatically resolves lib.love2d.enums."""
    import os
    graphics_path = os.path.join("sapphire", "lib", "love2d", "graphics.sp")
    with open(graphics_path, encoding="utf-8") as f:
      code = f.read()

    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker(source_file_path=graphics_path)
    checker.check(ast)
    self.assertEqual(len(checker.errors), 0)

  def test_unqualified_module_type_rejected(self):
    """Verifies that using an unqualified type from an imported module raises an error."""
    code = """
    import lib.love2d.enums;
    func test(mode: DrawMode) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    with self.assertRaises(SemanticError) as cm:
      checker.check(ast)
    self.assertIn("Undefined type 'DrawMode'", str(cm.exception))

  def test_qualified_module_type_accepted(self):
    """Verifies that using a dot-qualified type from an imported module succeeds."""
    code = """
    import lib.love2d.enums;
    func test(mode: enums.DrawMode) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(len(checker.errors), 0)

  def test_reexport_module_specifier(self):
    """Verifies re-exporting a symbol from an imported module."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      mod_a = os.path.join(tmpdir, "mod_a.sp")
      with open(mod_a, "w") as f:
        f.write("import lib.love2d.enums as e;\nexport {\n  e.DrawMode,\n}\n")

      code = "import mod_a;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)
      mod_a_sym = checker.symbol_table.lookup("mod_a")
      self.assertIsNotNone(mod_a_sym)
      self.assertIn("DrawMode", mod_a_sym.exports)

  def test_qualified_type_fallback_struct(self):
    """Verifies that referencing an unexported dot-qualified module type raises a semantic error."""
    code = """
    import lib.love2d.enums;
    func test(s: enums.CustomStruct) {}
    """
    input_stream = InputStream(code)
    lexer = SapphireLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = SapphireParser(stream)
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    with self.assertRaises(SemanticError) as cm:
      checker.check(ast)
    self.assertIn("Module 'enums' does not export type 'CustomStruct'.", str(cm.exception))

  def test_module_import_with_error(self):
    """Verifies imported module syntax and semantic errors propagate to importer."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      invalid_sp = os.path.join(tmpdir, "invalid.sp")
      with open(invalid_sp, "w") as f:
        f.write("let x: int = true;\n")

      code = "import invalid;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      with self.assertRaises(SemanticError) as ctx:
        checker.check(ast)
      self.assertIn("invalid.sp", str(ctx.exception))
      self.assertIn("Cannot assign expression of type 'bool'", str(ctx.exception))

      syntax_err_sp = os.path.join(tmpdir, "syntax_err.sp")
      with open(syntax_err_sp, "w") as f:
        f.write("func {\n")

      code2 = "import syntax_err;\n"
      input_stream2 = InputStream(code2)
      lexer2 = SapphireLexer(input_stream2)
      stream2 = CommonTokenStream(lexer2)
      parser2 = SapphireParser(stream2)
      tree2 = parser2.program()
      ast2 = ASTBuilder().visit(tree2)

      checker2 = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      with self.assertRaises(SemanticError) as ctx2:
        checker2.check(ast2)
      self.assertIn("syntax_err.sp", str(ctx2.exception))
      self.assertIn("Syntax Error:", str(ctx2.exception))

  def test_import_module_without_export_block(self):
    """Verifies importing a module without explicit export manifest exports all top-level types and symbols."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      no_exp = os.path.join(tmpdir, "no_exp.sp")
      with open(no_exp, "w") as f:
        f.write("struct CustomItem {}\n")

      code = "import no_exp;\nvar item: no_exp.CustomItem;\n"
      input_stream = InputStream(code)
      lexer = SapphireLexer(input_stream)
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)

  def test_global_variable_omitted_type_inference(self):
    """Verifies type inference for variables declared outside functions."""
    checker = self._check("""
    let GLOBAL_OFFSET = 100;
    var global_flag = true;

    func get_total(x: int): int {
      if global_flag {
        return x + GLOBAL_OFFSET;
      }
      return x;
    }
    """)
    offset_sym = checker.symbol_table.lookup("GLOBAL_OFFSET")
    self.assertEqual(offset_sym.symbol_type.name, "int")
    flag_sym = checker.symbol_table.lookup("global_flag")
    self.assertEqual(flag_sym.symbol_type.name, "bool")

  def test_global_variable_omitted_type_errors(self):
    """Verifies error reporting for global variables without explicit type and initial value."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      let global_x;
      """)
    self.assertIn("Variable 'global_x' requires an explicit type annotation or an initial value.", str(ctx.exception))

  def test_imported_parent_struct_inheritance(self):
    """Verifies that structs statically inheriting from imported module structs (e.g. struct Character: entity.Entity) inherit fields properly."""
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.ast_builder import ASTBuilder
    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser
    from sapphire.semantics.symbol_table import (
      ModuleSymbol,
      PrimitiveType,
      StructField,
      StructType,
    )

    code = """
    struct Character: entity.Entity {
      var x: float = 0.0;
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    mod_sym = ModuleSymbol("entity", "game/entities/entity.sp")
    entity_struct = StructType("Entity")
    entity_struct.fields["entity_id"] = StructField("entity_id", PrimitiveType("int"), True)
    mod_sym.exports["Entity"] = entity_struct
    checker.symbol_table.define("entity", mod_sym)

    checker.check(ast)
    char_struct = checker.symbol_table.lookup_type("Character")
    self.assertIsNotNone(char_struct)
    self.assertIn("entity_id", char_struct.fields)
    self.assertIn("x", char_struct.fields)

  def test_import_non_existent_module_error(self):
    """Verifies that attempting to import a non-existent module raises a SemanticError."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      import game.entities.enums;
      """)
    self.assertIn("Cannot resolve imported module 'game.entities.enums'. Module file not found.", str(ctx.exception))

  def test_invalid_prefix_import_error(self):
    """Regression test: verifies that importing with invalid path prefix (e.g. game.entities.character when only character.sp exists) fails with a compiler error."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      char_sp = os.path.join(tmpdir, "character.sp")
      with open(char_sp, "w") as f:
        f.write("export { Character }\nstruct Character {}\n")

      enemy_sp = os.path.join(tmpdir, "enemy.sp")
      code = "import game.entities.character;\n"

      lexer = SapphireLexer(InputStream(code))
      parser = SapphireParser(CommonTokenStream(lexer))
      tree = parser.program()
      ast = ASTBuilder().visit(tree)

      checker = TypeChecker(source_file_path=enemy_sp)
      with self.assertRaises(SemanticError) as ctx:
        checker.check(ast)
      self.assertIn("Cannot resolve imported module 'game.entities.character'. Module file not found.", str(ctx.exception))

      code_valid = "import character;\n"
      lexer_v = SapphireLexer(InputStream(code_valid))
      parser_v = SapphireParser(CommonTokenStream(lexer_v))
      tree_v = parser_v.program()
      ast_v = ASTBuilder().visit(tree_v)
      checker_v = TypeChecker(source_file_path=enemy_sp)
      checker_v.check(ast_v)

  def test_imported_module_struct_initializer(self):
    """Verifies type checking of struct initializers using dotted imported module struct names (e.g. character.Unit { name = name })."""
    from sapphire.semantics.symbol_table import (
      ModuleSymbol,
      StringType,
      StructField,
      StructType,
    )

    code = """
    func test_init() {
      let u = character.Unit { name = "Hero" };
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker()
    mod_sym = ModuleSymbol("character", "game/entities/character.sp")
    unit_struct = StructType("Unit")
    unit_struct.fields["name"] = StructField("name", StringType(), False)
    mod_sym.exports["Unit"] = unit_struct
    checker.symbol_table.define("character", mod_sym)

    checker.check(ast)

  def test_host_module_trait_implementation_static_methods(self):
    """Verifies that methods implementing traits with static func are treated as static methods."""
    self._check("""
    trait CustomStaticTrait {
      static func clear(r: float, g: float, b: float);
    }
    struct MockCustom {}
    impl CustomStaticTrait for MockCustom {
      func clear(r: float, g: float, b: float) {}
    }
    """)

  def test_encapsulation_invariant_struct_cross_module(self):
    """Verifies that direct field mutations on imported structs with __init__ are rejected."""
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.ast_builder import ASTBuilder
    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser
    from sapphire.semantics.symbol_table import (
      FunctionType,
      ModuleSymbol,
      PrimitiveType,
      StructField,
      StructMethod,
      StructType,
    )

    code = """
    func test() {
      var w = weapon.Weapon();
      w.damage = 100;
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker(source_file_path="main.sp")
    mod_sym = ModuleSymbol("weapon", "lib/weapon.sp")
    weapon_struct = StructType("Weapon", defining_module="lib/weapon.sp", is_imported=True)
    weapon_struct.fields["damage"] = StructField("damage", PrimitiveType("int"), is_mutable=True)
    init_sig = FunctionType([], PrimitiveType("none"), has_self=True, param_names=["self"])
    weapon_struct.methods["__init__"] = StructMethod("__init__", init_sig, modifier=None)
    mod_sym.exports["Weapon"] = weapon_struct
    checker.symbol_table.define("weapon", mod_sym)

    with self.assertRaises(SemanticError) as ctx:
      checker.check(ast)
    self.assertIn("Cannot mutate field 'damage' of encapsulated struct 'Weapon' outside its defining module; mutate via methods instead.", str(ctx.exception))

  def test_encapsulation_pod_struct_cross_module_allowed(self):
    """Verifies that POD structs (no __init__) allow cross-module field mutation on var bindings."""
    from antlr4 import CommonTokenStream, InputStream

    from sapphire.parser.ast_builder import ASTBuilder
    from sapphire.parser.gen.SapphireLexer import SapphireLexer
    from sapphire.parser.gen.SapphireParser import SapphireParser
    from sapphire.semantics.symbol_table import (
      ModuleSymbol,
      PrimitiveType,
      StructField,
      StructType,
    )

    code = """
    func test() {
      var p = math.Point { x = 1.0 };
      p.x = 10.0;
    }
    """
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    tree = parser.program()
    ast = ASTBuilder().visit(tree)

    checker = TypeChecker(source_file_path="main.sp")
    mod_sym = ModuleSymbol("math", "lib/math.sp")
    point_struct = StructType("Point", defining_module="lib/math.sp", is_imported=True)
    point_struct.fields["x"] = StructField("x", PrimitiveType("float"), is_mutable=True)
    mod_sym.exports["Point"] = point_struct
    checker.symbol_table.define("math", mod_sym)

    checker.check(ast)

  def test_module_var_global_reentrancy(self):
    direct_access_reject = """
    struct Player { var hp: int; }
    var g_player = Player { hp = 100 };
    func update(p: Player) {
      g_player.hp = 0;
    }
    func main() {
      update(g_player);
    }
    """
    with self.assertRaises(SemanticError) as ctx1:
      self._check(direct_access_reject)
    self.assertIn(
        "callee accesses 'g_player' in its call graph", str(ctx1.exception)
    )

    transitive_access_reject = """
    struct Player { var hp: int; }
    var g_player = Player { hp = 100 };
    func helper() {
      g_player.hp = 50;
    }
    func update(p: Player) {
      helper();
    }
    func main() {
      update(g_player);
    }
    """
    with self.assertRaises(SemanticError) as ctx2:
      self._check(transitive_access_reject)
    self.assertIn(
        "callee accesses 'g_player' in its call graph", str(ctx2.exception)
    )

    exported_global_reject = """
    struct Player { var hp: int; }
    var g_player = Player { hp = 100 };
    export {
      g_player
    }
    func inspect(p: Player) {}
    func main() {
      inspect(g_player);
    }
    """
    with self.assertRaises(SemanticError) as ctx3:
      self._check(exported_global_reject)
    self.assertIn(
        "Cannot pass exported mutable global 'g_player' by reference",
        str(ctx3.exception),
    )

    dynamic_callee_reject = """
    struct Player { var hp: int; }
    var g_player = Player { hp = 100 };
    func main() {
      var cb: (Player) -> void = p -> {};
      cb(g_player);
    }
    """
    with self.assertRaises(SemanticError) as ctx4:
      self._check(dynamic_callee_reject)
    self.assertIn(
        "Cannot pass mutable global 'g_player' by reference to dynamic",
        str(ctx4.exception),
    )

    non_aliasing_method_ok = """
    struct Button { var id: String; }
    impl Button {
      func render() {
        print(self.id);
      }
    }
    var submit_btn = Button { id = "btn" };
    func main() {
      submit_btn.render();
    }
    """
    self._check(non_aliasing_method_ok)

    non_aliasing_func_ok = """
    struct Player { var hp: int; }
    var g_player = Player { hp = 100 };
    func inspect(p: Player) {
      let h = p.hp;
    }
    func main() {
      inspect(g_player);
    }
    """
    self._check(non_aliasing_func_ok)

    let_global_borrow_ok = """
    struct Config { let port: int; }
    let g_cfg = Config { port = 8080 };
    func run_server(c: Config) {}
    func main() {
      run_server(g_cfg);
    }
    """
    self._check(let_global_borrow_ok)

    primitive_var_global_value_ok = """
    var g_count = 10;
    func inc(x: int) {}
    func main() {
      inc(g_count);
    }
    """
    self._check(primitive_var_global_value_ok)

  def test_qualified_import_diagnostic(self):
    """Verifies helpful diagnostics for full package paths of imported modules."""
    # 1. Qualified call std.os.args()
    code1 = """
    import std.os;

    func main() {
      let a = std.os.args();
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code1)
    err = str(ctx.exception)
    self.assertIn(
        "Undefined identifier 'std'. Module 'std.os' was imported as 'os'. "
        "Did you mean 'os.args()'?",
        err,
    )

    # 2. Qualified module access without call std.os
    code2 = """
    import std.os;

    func main() {
      let m = std.os;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code2)
    err = str(ctx.exception)
    self.assertIn(
        "Undefined identifier 'std'. Module 'std.os' was imported as 'os'. "
        "Did you mean 'os'?",
        err,
    )

    # 3. Aliased import std.math as m
    code3 = """
    import std.math as m;

    func main() {
      let val = std.math.abs(-5);
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code3)
    err = str(ctx.exception)
    self.assertIn(
        "Undefined identifier 'std'. Module 'std.math' was imported as 'm'. "
        "Did you mean 'm.abs()'?",
        err,
    )

    # 4. Multiple modules under prefix std used as raw identifier
    code4 = """
    import std.os;
    import std.fs;

    func main() {
      let x = std;
    }
    """
    with self.assertRaises(SemanticError) as ctx:
      self._check(code4)
    err = str(ctx.exception)
    self.assertIn(
        "Undefined identifier 'std'. Modules under 'std' are imported by "
        "their module name directly",
        err,
    )

  def test_module_let_constants_in_struct_and_param_defaults(self):
    """Verifies same-file module let constants in struct field and parameter defaults."""
    code = """
    let STANDING_FRAME: int = 1;
    let SCALED_FRAME = STANDING_FRAME + 2;

    struct Point {
      var x: int = STANDING_FRAME;
      var y = SCALED_FRAME;
    }

    let ORIGIN = Point {};

    struct Character {
      var frame: int = STANDING_FRAME;
      var inferred_frame = SCALED_FRAME;
      var pos: Point = ORIGIN;
    }

    impl Character {
      func reset(frame: int = STANDING_FRAME, y: int = SCALED_FRAME): int {
        return frame + y;
      }
    }

    trait Resettable {
      func reset_to(frame: int = STANDING_FRAME);
    }

    func reset_global(frame: int = STANDING_FRAME): int {
      return frame;
    }
    """
    self._check(code)

  def test_imported_let_constants_in_struct_and_param_defaults(self):
    """Verifies imported module let constants in struct field and parameter defaults."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
      consts_sp = os.path.join(tmpdir, "consts.sp")
      with open(consts_sp, "w", encoding="utf-8") as f:
        f.write(
            "export {\n"
            "  DEFAULT_SPEED,\n"
            "}\n"
            "let DEFAULT_SPEED: float = 120.0;\n"
        )

      code = """
      import consts;

      struct Mover {
        var speed: float = consts.DEFAULT_SPEED;
      }

      impl Mover {
        func boost(extra: float = consts.DEFAULT_SPEED): float {
          return self.speed + extra;
        }
      }

      func get_default_speed(speed: float = consts.DEFAULT_SPEED): float {
        return speed;
      }
      """
      lexer = SapphireLexer(InputStream(code))
      stream = CommonTokenStream(lexer)
      parser = SapphireParser(stream)
      ast = ASTBuilder().visit(parser.program())
      checker = TypeChecker(source_file_path=os.path.join(tmpdir, "main.sp"))
      checker.check(ast)
      self.assertEqual(checker.errors, [])

  def test_forward_ref_module_let_constants_rejected(self):
    """Verifies forward references to later module let constants are rejected."""
    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      struct BadStruct {
        var x: int = LATER;
      }
      let LATER: int = 1;
      """)
    self.assertIn("Undefined identifier 'LATER'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      let EARLIER: int = LATER + 1;
      let LATER: int = 1;
      """)
    self.assertIn("Undefined identifier 'LATER'", str(ctx.exception))

    with self.assertRaises(SemanticError) as ctx:
      self._check("""
      func bad_fn(x: int = LATER): int {
        return x;
      }
      let LATER: int = 1;
      """)
    self.assertIn("Undefined identifier 'LATER'", str(ctx.exception))

  def test_module_exported_struct_constant_field_access(self):
    """Verifies chained field access on exported module struct values."""
    from sapphire.semantics.symbol_table import (
      ModuleSymbol,
      StructSymbol,
      Symbol,
    )

    stats_struct = StructType("Stats")
    stats_struct.fields["hp"] = StructField(
        "hp", PrimitiveType("int"), is_mutable=False
    )
    unit_struct = StructType("Unit")
    unit_struct.fields["stats"] = StructField(
        "stats", stats_struct, is_mutable=False
    )
    mod_sym = ModuleSymbol("units", "units.sp")
    mod_sym.exports["Unit"] = StructSymbol("Unit", unit_struct)
    mod_sym.exports["ELENA_UNIT"] = Symbol("ELENA_UNIT", unit_struct)

    code = """
    func read_hp(): int {
      return units.ELENA_UNIT.stats.hp;
    }
    """
    stream = CommonTokenStream(SapphireLexer(InputStream(code)))
    ast = ASTBuilder().visit(SapphireParser(stream).program())
    checker = TypeChecker()
    checker.symbol_table.define("units", mod_sym)
    checker.check(ast)

    bad_code = """
    func bad(): Stats {
      return units.Unit.stats;
    }
    """
    bad_stream = CommonTokenStream(SapphireLexer(InputStream(bad_code)))
    bad_ast = ASTBuilder().visit(SapphireParser(bad_stream).program())
    bad_checker = TypeChecker()
    bad_checker.symbol_table.define("units", mod_sym)
    with self.assertRaises(SemanticError) as ctx:
      bad_checker.check(bad_ast)
    self.assertIn("Cannot access instance field 'stats' on type 'Unit'",
                  str(ctx.exception))

  def test_struct_type_alias_static_method_and_const(self):
    """Verifies static func and static let resolution on struct type aliases."""
    from sapphire.semantics.symbol_table import (
      FunctionType,
      ModuleSymbol,
      StructMethod,
      StructSymbol,
      Symbol,
    )

    unit_struct = StructType("Unit")
    unit_struct.fields["hp"] = StructField(
      "hp", PrimitiveType("int"), is_mutable=True
    )
    unit_struct.static_fields["MAX_HP"] = StructField(
      "MAX_HP", PrimitiveType("int"), is_mutable=False, is_static=True
    )
    create_sig = FunctionType(
      [PrimitiveType("int")], unit_struct, param_names=["hp"]
    )
    unit_struct.methods["create"] = StructMethod(
      "create", create_sig, modifier="static"
    )
    mod_sym = ModuleSymbol("units", "units.sp")
    mod_sym.exports["Unit"] = StructSymbol("Unit", unit_struct)
    mod_sym.exports["ELENA_UNIT"] = Symbol("ELENA_UNIT", unit_struct)

    code = """
    let Unit = units.Unit;
    let Unit2 = Unit;

    func make_default(): int {
      let LocalUnit = units.Unit;
      let a = Unit.create(10);
      let b = Unit2.create(20);
      let c = LocalUnit.create(Unit.MAX_HP);
      return a.hp + b.hp + c.hp;
    }
    """
    stream = CommonTokenStream(SapphireLexer(InputStream(code)))
    ast = ASTBuilder().visit(SapphireParser(stream).program())
    checker = TypeChecker()
    checker.symbol_table.define("units", mod_sym)
    checker.check(ast)

    # Value constants of struct type must NOT be treated as type aliases.
    bad_code = """
    let ELENA = units.ELENA_UNIT;

    func bad(): Unit {
      return ELENA.create(10);
    }
    """
    bad_stream = CommonTokenStream(SapphireLexer(InputStream(bad_code)))
    bad_ast = ASTBuilder().visit(SapphireParser(bad_stream).program())
    bad_checker = TypeChecker()
    bad_checker.symbol_table.define("units", mod_sym)
    with self.assertRaises(SemanticError) as ctx:
      bad_checker.check(bad_ast)
    self.assertIn(
      "Cannot call static method 'create' on an instance of 'Unit'",
      str(ctx.exception),
    )


if __name__ == "__main__":
  unittest.main()
