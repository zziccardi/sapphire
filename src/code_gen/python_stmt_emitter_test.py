"""Focused execution tests for Python statement emitter edge cases."""

import unittest

from antlr4 import CommonTokenStream, InputStream

from src.code_gen.python_transpiler import PythonTranspiler
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import TypeChecker


class TestPythonStmtEmitter(unittest.TestCase):
  """Tests statement lowering, lifting, writebacks, and closures in Python codegen."""

  def _transpile_and_run(self, code: str, call_expr: str):
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(checker.errors, [], f"Unexpected errors: {checker.errors}")
    py_code = PythonTranspiler().transpile(ast)
    ns = {}
    exec(py_code, ns)
    return eval(call_expr, ns)

  def test_block_lambda_mutating_nonlocals_through_control_flow(self):
    """Exercises _find_assigned_nonlocals across if/for/while/guard/nested lambdas."""
    code = """
    var g_total: int = 0;

    func run(opt: int?): [int] {
      var acc: int = 0;
      let cb = (flag: bool) -> int {
        let inner = (x: int) -> int { return x + 1; };
        if flag {
          if let v ?= opt {
            acc += inner(v);
          } else {
            acc += 1;
          }
        }
        for i in [1, 2, 3] {
          acc += i;
        }
        var n = 2;
        while n > 0 {
          acc += 1;
          n -= 1;
        }
        guard let v2 ?= opt else {
          return acc;
        }
        guard v2 > 0 else {
          return acc;
        }
        g_total += v2;
        return acc;
      };
      let r = cb(true);
      return [r, acc, g_total];
    }
    """
    # acc: inner(5)=6 + (1+2+3)=6 + 2 = 14; g_total = 5
    self.assertEqual(self._transpile_and_run(code, "run(5)"), [14, 14, 5])

  def test_lifted_lambda_captures_loop_vars_with_inner_blocks(self):
    """Exercises _find_captured_loop_vars and _make_ factory wrapper emission."""
    code = """
    func run(): [int] {
      var fns: [() -> int] = [];
      for idx in [10, 20, 30] {
        let fn = () -> int {
          let offset = 1;
          let helper = (k: int) -> int { return k + idx; };
          return helper(offset);
        };
        fns.push(fn);
      }
      return [fns[0](), fns[1](), fns[2]()];
    }
    """
    self.assertEqual(self._transpile_and_run(code, "run()"), [11, 21, 31])

  def test_optional_chain_call_with_liftable_match_arg_short_circuits(self):
    """Exercises optional-chain call lifting with match argument and short-circuiting."""
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

    func run(present: bool): [int] {
      side_effects = 0;
      var s: Sink? = present ? Sink { total = 5 } : none;
      let res = s?.add(match 2 {
        1 -> bump(1),
        2 -> bump(2),
        ... -> bump(3),
      });
      return [res ?? -1, side_effects];
    }
    """
    self.assertEqual(self._transpile_and_run(code, "run(True)"), [25, 1])
    self.assertEqual(self._transpile_and_run(code, "run(False)"), [-1, 0])

  def test_int_div_assign_on_member_and_index_targets(self):
    """Exercises `/=` integer division assignment on struct fields and array elements."""
    code = """
    struct Box {
      var value: int;
    }

    func run(): [int] {
      var b = Box { value = 25 };
      b.value /= 4;
      var arr = [19, -7];
      arr[0] /= 3;
      arr[1] /= 2;
      return [b.value, arr[0], arr[1]];
    }
    """
    # Sapphire integer division truncates toward zero: 25/4=6, 19/3=6, -7/2=-3
    self.assertEqual(self._transpile_and_run(code, "run()"), [6, 6, -3])

  def test_if_var_unwrap_index_writeback(self):
    """Exercises copy-out / write-back for `if var x ?= arr[0]`."""
    code = """
    func run(): [int] {
      var arr: [int?] = [10, none];
      if var x ?= arr[0] {
        x += 5;
      }
      if var y ?= arr[1] {
        y += 99;
      }
      return [arr[0] ?? -1, arr[1] ?? -1];
    }
    """
    self.assertEqual(self._transpile_and_run(code, "run()"), [15, -1])

  def test_match_block_arm_with_while_and_liftable_while_yield(self):
    """Exercises done-flag break injection for plain and liftable while loops in match arms."""
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
    self.assertEqual(self._transpile_and_run(code, "run_while(1)"), 30)
    self.assertEqual(self._transpile_and_run(code, "run_while(2)"), 200)


if __name__ == "__main__":
  unittest.main()
