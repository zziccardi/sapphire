"""Focused Lua 5.1 execution tests for Lua statement emitter edge cases."""

import shutil
import subprocess
import unittest
from antlr4 import CommonTokenStream, InputStream

from src.code_gen.lua_transpiler import LuaTranspiler
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import TypeChecker


class TestLuaStmtEmitter(unittest.TestCase):
  """Tests statement lowering, lifting, writebacks, and RAII in Lua 5.1 codegen."""

  def _transpile_and_run_lua(self, code: str, lua_tail: str) -> str:
    lua_bin = (
        shutil.which("lua") or shutil.which("lua5.1") or shutil.which("luajit")
    )
    if not lua_bin:
      self.skipTest("Lua runtime not found on PATH")
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(checker.errors, [], f"Unexpected errors: {checker.errors}")
    lua_code = LuaTranspiler().transpile(ast) + "\n" + lua_tail + "\n"
    proc = subprocess.run(
        [lua_bin, "-"],
        input=lua_code,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      self.fail(f"Lua execution failed:\n{proc.stderr}\n--- CODE ---\n{lua_code}")
    return proc.stdout.strip()

  def test_optional_chain_call_with_liftable_match_arg_short_circuits(self):
    """Exercises Lua optional-chain call lifting with match arg and short-circuiting."""
    code = """
    var side_effects: int = 0;

    struct Sink {
      var total: int;
    }
    impl Sink {
      var func add(v: int): int {
        self.total += v;
        return self.total;
      }
    }

    func bump(x: int): int {
      side_effects += 1;
      return x * 10;
    }

    func run(present: bool): int {
      side_effects = 0;
      var s: Sink? = present ? Sink { total = 5 } : none;
      let res = s?.add(match 2 {
        1 -> bump(1),
        2 -> bump(2),
        ... -> bump(3),
      });
      return (res ?? -1) * 10 + side_effects;
    }
    """
    out = self._transpile_and_run_lua(code, "print(run(true), run(false))")
    # present=true -> 25*10+1=251; present=false -> (-1)*10+0=-10
    self.assertEqual(out, "251\t-10")

  def test_if_var_unwrap_array_and_map_index_writeback(self):
    """Exercises copy-out/write-back for `if var x ?= arr[0]` and `if var y ?= m["k"]`."""
    code = """
    func run(): int {
      var arr: [int?] = [10, none];
      if var x ?= arr[0] {
        x += 5;
      }
      if var miss ?= arr[1] {
        miss += 99;
      }
      var m: Map<String, int?> = {"k": 20};
      if var y ?= m["k"] {
        y += 7;
      }
      return (arr[0] ?? 0) + (arr[1] ?? 0) + (m["k"] ?? 0);
    }
    """
    out = self._transpile_and_run_lua(code, "print(run())")
    self.assertEqual(out, "42")

  def test_multi_assign_with_destructible_and_index_targets(self):
    """Exercises live destructible teardown + index setter in multi-assignment."""
    code = """
    var drops: int = 0;

    struct Res {
      var id: int;
    }
    impl Res {
      func __del__() {
        drops += self.id;
      }
    }

    func make_pair(id: int, val: int): Res, int {
      return Res { id = id }, val;
    }

    func run(): int {
      drops = 0;
      var arr = [0, 0];
      var m: Map<String, int> = {"a": 0};
      var r = Res { id = 1 };
      r, arr[0] = make_pair(2, 10);
      r, m["a"] = make_pair(4, 20);
      return arr[0] + m["a"] + drops;
    }
    """
    # Before return: old Res(1) dropped on 1st reassign (+1), old Res(2) dropped on 2nd (+2) -> drops=3
    # Result before scope exit: 10 + 20 + 3 = 33
    out = self._transpile_and_run_lua(code, "print(run(), drops)")
    # After run() exits, Res(4) is also dropped -> total drops = 1+2+4 = 7
    self.assertEqual(out, "33\t7")

  def test_match_block_arm_with_while_and_liftable_while_yield(self):
    """Exercises Lua done-flag break for plain and liftable while loops in match arms."""
    code = """
    func run_while(target: int): int {
      return match target {
        1 -> {
          var i = 0;
          while i < 5 {
            if i == 3 {
              yield i * 10;
            }
            i += 1;
          }
          yield -1;
        },
        ... -> {
          var k = 4;
          while match k { 0 -> false, ... -> true } {
            if k == 2 {
              yield k * 100;
            }
            k -= 1;
          }
          yield -2;
        },
      };
    }
    """
    out = self._transpile_and_run_lua(code, "print(run_while(1), run_while(2))")
    self.assertEqual(out, "30\t200")

  def _transpile_lua(self, code: str) -> str:
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(checker.errors, [], f"Unexpected errors: {checker.errors}")
    return LuaTranspiler().transpile(ast)

  def test_direct_range_for_lowers_to_numeric_for(self):
    """Verifies direct for-in-range lowers to native Lua numeric for loops."""
    code = """
    func sum_ranges(dyn_pos: int, dyn_neg: int, dyn_zero: int): int {
      var total = 0;
      for a in range(5) {
        total += a;
      }
      for b in range(2, 6) {
        total += b;
      }
      for c in range(0, 10, 3) {
        total += c;
      }
      for d in range(10, 0, -3) {
        total += d;
      }
      for e in range(0, 6, dyn_pos) {
        total += e;
      }
      for f in range(6, 0, dyn_neg) {
        total += f;
      }
      for g in range(0, 5, dyn_zero) {
        total += 1000;
      }
      for h in range(0, 5, 0) {
        total += 1000;
      }
      let stored = range(1, 5);
      for s in stored {
        total += s;
      }
      return total;
    }
    """
    lua_code = self._transpile_lua(code)
    user_code = lua_code.split("local sum_ranges", 1)[1]
    self.assertIn("for a = 0, (5) - 1 do", user_code)
    self.assertIn("for b = (2), (6) - 1 do", user_code)
    self.assertIn("for c = (0), (10) - 1, 3 do", user_code)
    self.assertIn("for d = (10), (0) + 1, -3 do", user_code)
    self.assertIn("~= 0 then", user_code)
    self.assertIn("local stored = _SP_RT._sapphire_range(1, 5)", user_code)
    self.assertIn("for s in stored do", user_code)
    # 0+1+2+3+4=10, 2+3+4+5=14, 0+3+6+9=18, 10+7+4+1=22,
    # 0+2+4=6, 6+4+2=12, 0, 0, 1+2+3+4=10 => 92
    out = self._transpile_and_run_lua(code, "print(sum_ranges(2, -2, 0))")
    self.assertEqual(out, "92")

  def test_lifted_expressions_emit_zero_iifes_and_preserve_short_circuit(self):
    """Verifies ??, ?:, ?., optional cast, and chained map.get emit zero IIFEs."""
    code = """
    var calls: int = 0;

    struct Box {
      var val: int;
    }
    impl Box {
      func add(x: int): int {
        return self.val + x;
      }
    }

    func bump(x: int): int {
      calls += 1;
      return x;
    }

    func run(present: bool): int {
      calls = 0;
      let b: Box? = present ? Box { val = 10 } : none;
      let field_v = b?.val ?? bump(100);
      let call_v = b?.add(bump(5)) ?? 0;
      let cast_opt: int? = present ? (7 as int?) : none;
      let cast_v = cast_opt ?? 0;
      let grid: [int: [int: int]] = { 0: { 1: 42 } };
      let hit = grid.get(0)?.get(1) ?? -1;
      let miss = grid.get(9)?.get(1) ?? bump(3);
      let flag = present && ((b?.val ?? 0) > 0);
      let flag_v = flag ? 1 : 0;
      return field_v + call_v + cast_v + hit + miss + flag_v + calls * 1000;
    }
    """
    lua_code = self._transpile_lua(code)
    user_code = lua_code.split("local calls = 0", 1)[1]
    self.assertNotIn("(function(", user_code)
    # present=true:
    #   field_v=10 (no bump), call_v=15 (bump #1), cast_v=7,
    #   hit=42, miss=3 (bump #2), flag_v=1, calls=2 => 2078
    # present=false:
    #   field_v=100 (bump #1), call_v=0 (no bump!), cast_v=0,
    #   hit=42, miss=3 (bump #2), flag_v=0, calls=2 => 2145
    out = self._transpile_and_run_lua(code, "print(run(true), run(false))")
    self.assertEqual(out, "2078\t2145")

  def test_luajit_trace_friendly_nested_range_map_coalesce(self):
    """Verifies nested range + map.get + ?? compiles without LuaJIT trace aborts."""
    luajit_bin = shutil.which("luajit")
    if not luajit_bin:
      self.skipTest("luajit not found on PATH")
    code = """
    func bench_grid(): int {
      var grid: [int: [int: int]] = {};
      for y in range(0, 40) {
        var row: [int: int] = {};
        for x in range(0, 40) {
          row[x] = (x + y) % 3;
        }
        grid[y] = row;
      }
      var total = 0;
      for rep in range(0, 20) {
        for y in range(0, 40) {
          for x in range(0, 40) {
            let v = grid.get(y)?.get(x) ?? 0;
            total += v;
          }
        }
      }
      return total;
    }
    """
    lua_code = self._transpile_lua(code) + "\nprint(bench_grid())\n"
    proc = subprocess.run(
        [luajit_bin, "-jv", "-"],
        input=lua_code,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      self.fail(f"LuaJIT execution failed:\n{proc.stderr}")
    self.assertEqual(proc.stdout.strip(), "31980")
    self.assertNotIn("NYI: bytecode FNEW", proc.stderr)
    self.assertNotIn("NYI: bytecode UCLO", proc.stderr)
    self.assertNotIn("inner loop in root trace", proc.stderr)

  def test_array_and_map_for_loops_native_and_stateless(self):
    """Verifies array loops lower to FORL and handle [int?], for var, and continue."""
    code = """
    func run(): int {
      var opts: [int?] = [10, none, 20, 30];
      var sum = 0;
      for v in opts {
        if let n ?= v {
          if n == 20 {
            continue;
          }
          sum += n;
        }
      }
      var nums = [1, 2, 3];
      for var x in nums {
        x = x * 10;
      }
      for x in nums {
        sum += x;
      }
      var m: [String: int?] = {"a": 5, "b": none, "c": 7};
      for k, v in m {
        if let n ?= v {
          sum += n;
        }
      }
      return sum;
    }
    """
    lua_code = self._transpile_lua(code)
    user_code = lua_code.split("local run", 1)[1]
    self.assertNotIn("_sapphire_iter_array", user_code)
    self.assertIn("for _for_idx_", user_code)
    # 10+30=40, 10+20+30=60, 5+7=12 => 112
    out = self._transpile_and_run_lua(code, "print(run())")
    self.assertEqual(out, "112")

  def test_luajit_zero_fnew_nested_array_and_map_iteration(self):
    """Verifies nested array + map iteration produces zero FNEW/UCLO/inner-loop aborts."""
    luajit_bin = shutil.which("luajit")
    if not luajit_bin:
      self.skipTest("luajit not found on PATH")
    code = """
    func run(): int {
      var rows: [[int]] = [];
      for y in range(0, 20) {
        var row: [int] = [];
        for x in range(0, 20) {
          row.push(x + y);
        }
        rows.push(row);
      }
      var m: [int: int] = {};
      for i in range(0, 20) {
        m[i] = i * 2;
      }
      var total = 0;
      for rep in range(0, 10) {
        for row in rows {
          for v in row {
            total += v;
          }
        }
        for k, v in m {
          total += k + v;
        }
      }
      return total;
    }
    """
    lua_code = self._transpile_lua(code) + "\nprint(run())\n"
    proc = subprocess.run(
        [luajit_bin, "-jv", "-"],
        input=lua_code,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      self.fail(f"LuaJIT execution failed:\n{proc.stderr}")
    # sum(x+y for 0..19 x 0..19) = 20*20*19 = 7600; sum(3*i for 0..19) = 570
    # 10 * (7600 + 570) = 81700
    self.assertEqual(proc.stdout.strip(), "81700")
    self.assertNotIn("NYI: bytecode FNEW", proc.stderr)
    self.assertNotIn("NYI: bytecode UCLO", proc.stderr)
    self.assertNotIn("inner loop in root trace", proc.stderr)


if __name__ == "__main__":
  unittest.main()
