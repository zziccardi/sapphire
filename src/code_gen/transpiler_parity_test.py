"""Structural parity tests for Sapphire transpiler backends.

Verifies that all concrete transpiler backends (Python and Lua) remain
structurally symmetric with each other and fully cover every visitable AST
node class. These tests act as a compile-time-style tripwire: adding a new
AST node or visitor to one backend without updating the other will cause an
immediate failure here, long before any semantic regression appears in
production.
"""

import inspect
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from antlr4 import CommonTokenStream, InputStream

import src.parser.ast as ast_module
from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.python_transpiler import PythonTranspiler
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import TypeChecker

# AST node classes that are never dispatched to via the visit_* protocol.
# These are either abstract base nodes, purely structural container nodes,
# or internal nodes whose parent visitor handles them directly.
_EXCLUDED_NODES = {
    # Abstract / marker bases
    "ASTNode",
    "TypeNode",
    "DeclNode",
    "StmtNode",
    "ExprNode",
    # Type annotation nodes (handled inline, never visited standalone)
    "BasicTypeNode",
    "OptionalTypeNode",
    "ArrayTypeNode",
    "MapTypeNode",
    "FunctionTypeNode",
    # Annotation node (processed as an attribute of other nodes)
    "AnnotationNode",
    # Sub-nodes consumed by their parent visitor
    "ParameterNode",
    "ArgumentNode",
    "LambdaParamNode",
    "ExportSpecifierNode",
    "HeaderBindingNode",
    "EnumMemberNode",
    "TraitMemberNode",
    "ImplBlockNode",
    "MatchCaseNode",
    "MapEntryNode",
    # Program root (entry-point; handled by transpile(), not visit())
    "ProgramNode",
}


class VisitorParityTest(unittest.TestCase):
  """Ensures both transpiler backends expose an identical set of AST visitors.

  Two invariants are enforced:

  1. **Parity** — the set of `visit_*` methods on `PythonTranspiler` and
     `LuaTranspiler` must be exactly equal. Any method present in one but
     absent from the other indicates a feature that has drifted out of sync.

  2. **Coverage** — every concrete, visitable `*Node` class defined in
     `parser.ast` must have a corresponding `visit_*` method on *both*
     transpilers. This catches the case where a brand-new AST node is added
     to the grammar but neither backend is updated.
  """

  def test_visitor_method_parity(self):
    """Both transpilers must expose exactly the same set of visit_* methods."""
    py_visitors = {m for m in dir(PythonTranspiler) if m.startswith("visit_")}
    lua_visitors = {m for m in dir(LuaTranspiler) if m.startswith("visit_")}

    self.assertEqual(
        py_visitors,
        lua_visitors,
        "\nVisitor parity mismatch between PythonTranspiler and LuaTranspiler!"
        f"\n  Python-only : {sorted(py_visitors - lua_visitors)}"
        f"\n  Lua-only    : {sorted(lua_visitors - py_visitors)}",
    )

  def test_all_ast_nodes_have_visitors(self):
    """Every visitable *Node class must have a visitor on both transpilers."""
    all_node_names = {
        name
        for name, obj in inspect.getmembers(ast_module, inspect.isclass)
        if (name.endswith("Node") and
            issubclass(obj, ast_module.ASTNode) and
            name not in _EXCLUDED_NODES)
    }

    missing_py = []
    missing_lua = []
    for node_name in sorted(all_node_names):
      visitor = f"visit_{node_name}"
      if not hasattr(PythonTranspiler, visitor):
        missing_py.append(visitor)
      if not hasattr(LuaTranspiler, visitor):
        missing_lua.append(visitor)

    self.assertFalse(
        missing_py,
        f"PythonTranspiler is missing visitors for: {missing_py}",
    )
    self.assertFalse(
        missing_lua,
        f"LuaTranspiler is missing visitors for: {missing_lua}",
    )


class SemanticParityTest(unittest.TestCase):
  """Ensures runtime execution parity across Python and Lua backends."""

  def _execute_both(self, source: str, fn_name: str):
    """Executes fn_name in both Python and Lua backends and returns (py_result, lua_result)."""
    # 1. Python execution
    ast_py = ASTBuilder().visit(
        SapphireParser(CommonTokenStream(SapphireLexer(InputStream(source)))).program()
    )
    TypeChecker().check(ast_py)
    py_code = PythonTranspiler(test_mode=True).transpile(ast_py)
    ctx = {}
    exec(py_code, ctx)  # pylint: disable=exec-used
    py_result = ctx[fn_name]()

    # 2. Lua execution
    lua_bin = (
        shutil.which("lua")
        or shutil.which("luajit")
        or shutil.which("lua5.1")
    )
    if not lua_bin:
      self.skipTest("Lua interpreter not found in PATH.")

    ast_lua = ASTBuilder().visit(
        SapphireParser(CommonTokenStream(SapphireLexer(InputStream(source)))).program()
    )
    TypeChecker().check(ast_lua)
    lua_code = LuaTranspiler(test_mode=True).transpile(ast_lua)
    lib_path = str(pathlib.Path(__file__).parent.parent.parent / "lib")

    driver = (
        f"package.path = \"{lib_path}/?.lua;{lib_path}/?/init.lua;\" .. package.path\n"
        "local __mod = (function()\n"
        f"{lua_code}\n"
        "end)()\n"
        f"local fn = (__mod and __mod.{fn_name}) or {fn_name}\n"
        "print(tostring(fn()))\n"
    )

    with tempfile.NamedTemporaryFile(
        suffix=".lua", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
      tmp.write(driver)
      tmp_path = tmp.name

    try:
      proc = subprocess.run(
          [lua_bin, tmp_path],
          capture_output=True, text=True, timeout=10,
      )
      if proc.returncode != 0:
        self.fail(f"Lua execution failed for {fn_name}: {proc.stderr.strip()}")
      raw = proc.stdout.strip()
      if raw == "true":
        lua_result = True
      elif raw == "false":
        lua_result = False
      elif raw == "nil":
        lua_result = None
      else:
        try:
          lua_result = int(raw)
        except ValueError:
          try:
            lua_result = float(raw)
          except ValueError:
            lua_result = raw
    finally:
      os.unlink(tmp_path)

    return py_result, lua_result

  def test_global_var_mutation_parity(self):
    """Verifies functions mutating global variables execute identically without UnboundLocalError."""
    code = """
    var count: int = 10;
    @test
    func test_inc(): int {
      count = count + 5;
      return count;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_inc")
    self.assertEqual(py_val, 15)
    self.assertEqual(lua_val, 15)

  def test_optional_boolean_false_preservation(self):
    """Verifies accessing an optional boolean field that is false preserves false across backends."""
    code = """
    struct Toggle {
      let is_enabled: bool;
    }
    @test
    func test_false(): bool {
      let t: Toggle? = Toggle { is_enabled = false };
      let res = t?.is_enabled;
      return res == false;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_false")
    self.assertEqual(py_val, True)
    self.assertEqual(lua_val, True)

  def test_optional_chaining_single_evaluation(self):
    """Verifies that optional property access evaluates side-effecting receivers exactly once."""
    code = """
    struct Holder {
      var value: int;
    }
    var eval_count: int = 0;
    func get_holder(): Holder? {
      eval_count = eval_count + 1;
      return Holder { value = 42 };
    }
    @test
    func test_single_eval(): int {
      let v = get_holder()?.value;
      return eval_count;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_single_eval")
    self.assertEqual(py_val, 1)
    self.assertEqual(lua_val, 1)

  def test_arena_return_expression_order(self):
    """Verifies that arena fields can be returned without premature arena teardown."""
    code = """
    proto Item {
      var value: int;
    }
    @test
    func test_arena_return(): int {
      var arena = Arena();
      let item = Item { value = 99 } in arena;
      return item.value;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_arena_return")
    self.assertEqual(py_val, 99)
    self.assertEqual(lua_val, 99)

  def test_inherited_struct_destructor_and_positional_super_init(self):
    """Verifies Child.__del__ runs auto-teardown on Parent.__del__ and positional Parent.__init__."""
    code = """
    var teardown_order: int = 0;
    struct Parent {
      var p_val: int;
    }
    impl Parent {
      func __init__(v: int) {
        self.p_val = v;
      }
      func __del__() {
        teardown_order = teardown_order * 10 + 1;
      }
    }
    struct Child: Parent {
      var c_val: int;
    }
    impl Child {
      func __init__(v: int): Parent(v) {
        self.c_val = v + 1;
      }
      func __del__() {
        teardown_order = teardown_order * 10 + 2;
      }
    }
    @test
    func test_inherited_del(): int {
      {
        let c = Child(10);
      }
      return teardown_order;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_inherited_del")
    self.assertEqual(py_val, 21)
    self.assertEqual(lua_val, 21)

  def test_global_mutation_with_map_loop_if_let_and_guard(self):
    """Verifies global var tracking with map loops, if-let, and guard-let."""
    code = """
    var g_sum: int = 0;
    @test
    func test_globals(): int {
      let m: [String: int] = {"a": 1, "b": 2};
      for k, v in m {
        g_sum = g_sum + v;
      }
      let opt: int? = 10;
      if let x ?= opt {
        g_sum = g_sum + x;
      }
      guard let y ?= opt else {
        return -1;
      }
      g_sum = g_sum + y;
      return g_sum;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_globals")
    self.assertEqual(py_val, 23)
    self.assertEqual(lua_val, 23)

  def test_guard_var_in_place_mutation_and_nll_unfreeze(self):
    """Verifies guard var mutates in-place and unfreezes after last use."""
    code = """
    struct Enemy {
      var x: int = 0;
    }
    impl Enemy {
      var func step(nx: int) {
        self.x = nx;
      }
    }
    struct Controller {
      var active_enemy: Enemy? = none;
      var turn_cleared: bool = false;
    }
    impl Controller {
      var func clear_turn() {
        self.turn_cleared = true;
      }
      var func set_enemy(target: Enemy?) {
        self.active_enemy = target;
      }
      var func advance_and_read(): int {
        guard var e ?= self.active_enemy else {
          return -1;
        }
        e.step(7);
        self.clear_turn();
        if let updated ?= self.active_enemy {
          let res = updated.x;
          self.set_enemy(none);
          return res;
        }
        return -2;
      }
    }
    @test
    func test_guard_var_nll(): int {
      var ctrl = Controller { active_enemy = Enemy { x = 1 } };
      let res = ctrl.advance_and_read();
      if ctrl.turn_cleared && ctrl.active_enemy == none {
        return res;
      }
      return -3;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_guard_var_nll")
    self.assertEqual(py_val, 7)
    self.assertEqual(lua_val, 7)

  def test_container_get_mutable_unwrap_writeback_parity(self):
    """Verifies if var / guard var on map.get() and arr.get() mutate in-place."""
    code = """
    @test
    func test_container_get_unwrap(): int {
      var counts: [String: int] = {"hits": 4};
      if var count ?= counts.get("hits") {
        count += 3;
      }

      var grid: [int: [int: bool]] = {2: {3: true, 4: true}};
      guard var row ?= grid.get(2) else {
        return -1;
      }
      row.remove(3);

      var nums: [int] = [10, 20];
      if var n ?= nums.get(1) {
        n = 25;
      }

      let has_3 = grid[2].contains(3);
      if !has_3 {
        return counts["hits"] + nums[1];
      }
      return -2;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_container_get_unwrap")
    self.assertEqual(py_val, 32)
    self.assertEqual(lua_val, 32)

  def test_all_e2e_tests_have_expectations(self):
    """Ensures every @test function in testing/e2e/*_test.sp is in EXPECTATIONS."""
    import re

    from testing.e2e._expectations import EXPECTATIONS

    e2e_dir = pathlib.Path(__file__).resolve().parent.parent.parent / "testing" / "e2e"
    missing = {}
    for path in sorted(e2e_dir.glob("*_test.sp")):
      text = path.read_text(encoding="utf-8")
      fns = re.findall(r"@test\s+func\s+(\w+)\s*\(", text)
      registered = set(EXPECTATIONS.get(path.name, {}).keys())
      unregistered = [fn for fn in fns if fn not in registered]
      if unregistered:
        missing[path.name] = unregistered
    self.assertEqual(
        missing, {},
        f"Unregistered @test functions in testing/e2e/: {missing}",
    )

  def test_optional_array_and_map_none_elements_parity(self):
    """Verifies [T?] arrays and [K: V?] maps preserve none elements identically in Python and Lua."""
    code = """
    @test
    func test_opt_collections(): int {
      var arr: [int?] = [10, none, 30, none];
      arr.push(none);
      arr.push(50);
      let popped = arr.pop();
      var sum = 0;
      var nones = 0;
      for item in arr {
        if let v ?= item {
          sum += v;
        } else {
          nones += 1;
        }
      }
      let has_none = arr.contains(none);
      let s0 = arr.size();

      var m: [String: int?] = {"a": 1, "b": none};
      m["c"] = none;
      let ms = m.size();
      let has_b = m.contains("b");
      let bv = m["b"] ?? 7;

      if has_none && has_b && popped == 50 {
        return sum + nones * 100 + s0 * 1000 + ms * 10000 + bv;
      }
      return -1;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_opt_collections")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 40 + 300 + 5000 + 30000 + 7)

  def test_optional_defaults_and_struct_proto_none_overrides_parity(self):
    """Verifies explicit none overrides defaults in functions, constructors, structs, and protos."""
    code = """
    func greet(name: String? = "World", title: String? = "Dr"): String {
      let n = name ?? "NONE";
      let t = title ?? "NOTITLE";
      return t + ":" + n;
    }

    struct OptBox {
      var a: int?;
      var b: int;
    }
    impl OptBox {
      func __init__(a: int? = 99, b: int = 1) {
        self.a = a;
        self.b = b;
      }
    }

    struct Config {
      var name: String? = "default";
    }

    proto Node {
      var tag: String? = "base";
    }

    @test
    func test_none_overrides(): String {
      let g1 = greet();
      let g2 = greet(none);
      let g3 = greet(title = "Ms");
      let g4 = greet(none, none);

      let b1 = OptBox(none, 42);
      let b2 = OptBox(b = 7);
      let cfg = Config { name = none };

      var arena = Arena();
      let p = Node {} in arena;
      var c = clone p in arena;
      c.tag = none;

      let s_b1 = String.from(b1.a ?? -1) + "," + String.from(b1.b);
      let s_b2 = String.from(b2.a ?? -1) + "," + String.from(b2.b);
      let s_cfg = cfg.name ?? "NIL";
      let s_p = p.tag ?? "NIL";
      let s_c = c.tag ?? "NIL";
      return g1 + "|" + g2 + "|" + g3 + "|" + g4 + "|" + s_b1 + "|" + s_b2 + "|" + s_cfg + "|" + s_p + "|" + s_c;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_none_overrides")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(
        py_val,
        "Dr:World|Dr:NONE|Ms:World|NOTITLE:NONE|-1,42|99,7|NIL|base|NIL",
    )

  def test_cow_proxy_and_smart_ref_collections_and_raii_parity(self):
    """Verifies CoW proxy collections, Ref/SharedRef collections, SharedRef(Ref(false)), and WeakRef expiry."""
    code = """
    var destroyed: int = 0;

    struct Tracked {
      var id: int;
    }
    impl Tracked {
      func __del__() {
        destroyed += self.id;
      }
    }

    proto Bag {
      var items: [int] = [1, 2];
      var scores: [String: int] = {"a": 10};
    }

    @test
    func test_cow_and_refs(): int {
      var arena = Arena();
      let p = Bag {} in arena;
      var c = clone p in arena;
      c.items.push(3);
      c.scores.insert("b", 20);
      c.scores.remove("a");

      let p_sz = p.items.size();
      let c_sz = c.items.size();
      let p_has_a = p.scores.get("a") ?? 0;
      let c_has_a = c.scores.get("a") ?? 0;
      let c_b = c.scores.get("b") ?? 0;

      let r_arr = Ref([10, 20, 30]);
      let r_map = Ref({"k": 5});
      let r_bool = Ref(false);
      let s_bool = SharedRef(move r_bool);

      var weak: WeakRef<Tracked>? = none;
      var alive_before = 0;
      {
        let sr1 = SharedRef(Tracked { id = 7 });
        let sr2 = sr1.share();
        weak = sr1.downgrade();
        if let up ?= weak?.upgrade() {
          alive_before = up.id;
        }
      }
      var alive_after = 0;
      if let up2 ?= weak?.upgrade() {
        alive_after = up2.id;
      }

      if p_sz == 2 && c_sz == 3 && p_has_a == 10 && c_has_a == 0 && c_b == 20 && alive_after == 0 {
        return r_arr.size() + r_map.size() + r_arr[1] + alive_before + destroyed * 100;
      }
      return -1;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_cow_and_refs")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 3 + 1 + 20 + 7 + 700)

  def test_structural_equality_and_value_copy_semantics_parity(self):
    """Verifies structural ==/!= on arrays/maps and shallow value copy on assignment."""
    code = """
    struct Point {
      var x: int = 0;
      var y: int = 0;
    }

    @test
    func test_val_semantics(): int {
      var a1 = [1, 2, 3];
      var a2 = a1;
      let eq1 = (a1 == a2);
      a2[0] = 99;
      let neq1 = (a1 != a2);

      var m1 = {"k": 10};
      var m2 = m1;
      let eq2 = (m1 == m2);
      m2["k"] = 20;
      let neq2 = (m1 != m2);

      var p1 = Point { x = 5, y = 6 };
      var p2 = p1;
      p2.x = 50;

      if eq1 && neq1 && eq2 && neq2 {
        return a1[0] + m1["k"] + p1.x + p2.x;
      }
      return -1;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_val_semantics")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 1 + 10 + 5 + 50)

  def test_casts_utf8_strings_and_enum_from_parity(self):
    """Verifies casts, UTF-8 String helpers, strict to_int/to_float, and Enum.from order."""
    code = """
    enum Mix {
      First = "Second",
      Second = "Other"
    }

    enum AutoStr {
      Alpha,
      Beta = "B"
    }

    @test
    func test_casts_and_strings(): int {
      let b0 = 0 as bool;
      let b1 = 1 as bool;
      let i_neg = -3.9 as int;
      let f_true = true as float;
      let i_false = false as int;
      let opt_i: int? = 5 as int?;

      let u = "café";
      let u_sz = u.size();
      let u_sl = u.slice(-1);
      let f_neg = "abc".find("b", -2) ?? -1;
      let f_emp_rev = "abc".find("", reverse = true) ?? -1;
      let stripped = "abc".strip("");
      let bad_i = "3.14".to_int() ?? -9;
      let bad_f = "0x10".to_float() ?? -9.0;

      let m_val = Mix.from("Second");
      let auto_a = AutoStr.Alpha;

      if !b0 && b1 && i_neg == -3 && f_true == 1.0 && i_false == 0
         && opt_i == 5 && u_sz == 4 && u_sl == "é" && f_neg == 1
         && f_emp_rev == 3 && stripped == "abc" && bad_i == -9
         && bad_f == -9.0 && m_val == Mix.First && auto_a == AutoStr.from("Alpha") {
        return 1;
      }
      return 0;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_casts_and_strings")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 1)

  def test_dead_code_after_terminators_and_multi_return_raii_parity(self):
    """Verifies dead code after return/break/continue, multi-return with RAII, and bounded multi-yield match."""
    code = """
    var del_count: int = 0;

    struct Guard {
      var id: int;
    }
    impl Guard {
      func __del__() {
        del_count += 1;
      }
    }

    func pair_vals(): int, int? {
      return 11, none;
    }

    func with_raii_multi(): int, int? {
      let g = Guard { id = 1 };
      return pair_vals();
      let dead = 99;
    }

    @test
    func test_terminators_and_multi(): int {
      var acc = 0;
      for i in range(5) {
        if i == 1 {
          continue;
          acc += 100;
        }
        if i == 3 {
          break;
          acc += 200;
        }
        acc += i;
      }
      let a, b = with_raii_multi();
      let no_int: int? = none;
      let opt_one: int? = 1;
      let x, y = match a {
        11 -> { yield 20, no_int; },
        ... -> { yield 0, opt_one; }
      };
      return acc + a + (b ?? 5) + x + (y ?? 3) + del_count * 100;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_terminators_and_multi")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 2 + 11 + 5 + 20 + 3 + 100)

  def test_lambda_clone_guard_and_diamond_raii_parity(self):
    """Verifies lambda return RAII isolation, clone RAII cleanup, guard/if-cond RAII, and diamond __del__."""
    code = """
    var log: [String] = [];

    struct Base {}
    impl Base {
      func __del__() {
        log.push("Base");
      }
    }
    struct Left: Base {}
    struct Right: Base {}
    struct Diamond: Left, Right {}

    struct Res {
      var tag: String;
    }
    impl Res {
      func __del__() {
        log.push(self.tag);
      }
    }

    proto P {
      var x: int = 1;
    }

    func make_opt_res(tag: String): Res? {
      return Res { tag = tag };
    }

    func test_guard_raii(): int {
      guard let r ?= make_opt_res("G") else {
        return 0;
      }
      return 1;
    }

    @test
    func test_raii_edge_cases(): String {
      {
        let outer = Res { tag = "Outer" };
        let fn = (x: int) -> int {
          return x + 1;
        };
        let v = fn(10);
        log.push("AfterLam:" + String.from(v));
      }
      {
        var arena = Arena();
        let p = P {} in arena;
        let c = clone p {
          let tmp = Res { tag = "CloneTmp" };
          self.x = 2;
        } in arena;
        log.push("AfterClone:" + String.from(c.x));
      }
      {
        let d = Diamond {};
      }
      if let r ?= make_opt_res("IfFail"); false {
        log.push("Unreachable");
      }
      test_guard_raii();
      return log.join(",");
    }
    """
    py_val, lua_val = self._execute_both(code, "test_raii_edge_cases")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(
        py_val,
        "AfterLam:11,Outer,CloneTmp,AfterClone:2,Base,IfFail,G",
    )

  def test_match_lifting_gauntlet_parity(self):
    """Verifies match lifting in subjects, arms, while, guard, if-let, short-circuits, early yield, and lambdas."""
    code = """
    @test
    func test_match_gauntlet(): int {
      // Match in match subject + nested match in arm
      let a = match (match 1 { 1 -> 2, ... -> 0 }) {
        2 -> match 3 { 3 -> 30, ... -> 0 },
        ... -> 0
      };

      // Early yield in block arm with if and for loop
      let b = match 1 {
        1 -> {
          var s = 0;
          for i in range(5) {
            if i == 2 {
              yield s + 100;
            }
            s += i;
          }
          yield 999;
        },
        ... -> { yield 0; }
      };

      // Match in while condition
      var n = 3;
      var w_sum = 0;
      while (match n { 0 -> false, ... -> true }) {
        w_sum += n;
        n -= 1;
      }

      // Match in short-circuit ?? and ternary (skipped branch must not run side-effect)
      var side = 0;
      let opt_v: int? = 5;
      let c = opt_v ?? (match 1 { 1 -> { side += 1; yield 99; }, ... -> { yield 0; } });
      let d = true ? 7 : (match 1 { 1 -> { side += 1; yield 88; }, ... -> { yield 0; } });

      // Match in shorthand lambda
      let f = (x: int) -> match x { 1 -> 10, ... -> 20 };

      // Match in if-let condition
      var if_res = 0;
      let m_opt: int? = 4;
      if let v ?= m_opt; (match v { 4 -> true, ... -> false }) {
        if_res = v;
      }

      return a + b + w_sum + c + d + f(1) + if_res + side * 1000;
    }
    """
    py_val, lua_val = self._execute_both(code, "test_match_gauntlet")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(py_val, 30 + 101 + 6 + 5 + 7 + 10 + 4)

  def test_string_ops_fn_fields_coro_fields_single_eval_and_writebacks_parity(self):
    """Verifies string +=/+, fn-typed struct fields, coro struct/opt fields, single-eval, and if/for var writebacks."""
    code = """
    func gen(start: int): Coroutine<int> {
      yield start;
      yield start + 1;
    }

    struct Holder {
      var cb: (int) -> int;
      var co: Coroutine<int>;
      var opt_val: int?;
    }

    var eval_count: int = 0;
    func bump_idx(): int {
      eval_count += 1;
      return 0;
    }

    @test
    func test_misc_parity(): String {
      var s = "hi";
      s += " ";
      s += "there";
      let s2 = "sum=" + (1 + 2) + ":" + false;

      let h = Holder {
        cb = (x: int) -> x * 3,
        co = gen(10),
        opt_val = 5
      };
      let cb_res = h.cb(4);
      let co1 = h.co.step() ?? 0;
      var opt_co: Coroutine<int>? = gen(20);
      let co2 = opt_co?.step() ?? 0;

      // Non-call expression statements
      42;
      cb_res + co1;

      // Single-evaluation compound assignment on indexed array
      var arr = [10, 20];
      arr[bump_idx()] += 5;

      // Plain var, struct field, multi-binding if var, and for var writebacks
      var opt_num: int? = 3;
      if var n ?= opt_num {
        n += 7;
      }
      var mh = Holder { cb = (x: int) -> x, co = gen(0), opt_val = 8 };
      if var fv ?= mh.opt_val {
        fv += 2;
      }
      var a_opt: int? = 1;
      var b_opt: int? = 2;
      if var x ?= a_opt; var y ?= b_opt {
        x += 10;
        y += 20;
      }
      for var elem in arr {
        elem += 1;
      }
      var mp = {"a": 1, "b": 2};
      for var k, v in mp {
        v += 10;
      }

      return s + "|" + s2 + "|" + String.from(cb_res) + "|" + String.from(co1)
        + "|" + String.from(co2) + "|" + String.from(eval_count)
        + "|" + String.from(arr[0]) + "," + String.from(arr[1])
        + "|" + String.from(opt_num ?? 0) + "|" + String.from(mh.opt_val ?? 0)
        + "|" + String.from(a_opt ?? 0) + "," + String.from(b_opt ?? 0)
        + "|" + String.from(mp["a"]) + "," + String.from(mp["b"]);
    }
    """
    py_val, lua_val = self._execute_both(code, "test_misc_parity")
    self.assertEqual(py_val, lua_val)
    self.assertEqual(
        py_val,
        "hi there|sum=3:false|12|10|20|1|16,21|10|10|11,22|11,12",
    )


if __name__ == "__main__":
  unittest.main()
