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


if __name__ == "__main__":
  unittest.main()
