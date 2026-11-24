"""Differential property-based parity tests comparing Python and Lua 5.1 backends.

Uses a deterministic seeded PRNG (`random.Random`) to synthesize valid,
type-checked Sapphire programs across four high-risk semantic domains:
  1. Arithmetic, precedence, unary ops, and negative int division/modulo.
  2. Short-circuiting `&&`/`||`, ternaries with `false`/`0`/`none`, and side effects.
  3. `match` expressions (including block arms with `yield`), `if let`/`if var`,
     optional chaining (`?.`), and nil coalescing (`??`).
  4. Containers (`[int?]`, `Map<String, int?>`), negative indexing, and `if var`
     copy-out/write-back mutations.

Each generated program is parsed, strictly type-checked, transpiled to both
Python and Lua 5.1, executed, and asserted to produce identical output.
"""

import io
import random
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from typing import List, Tuple

from antlr4 import CommonTokenStream, InputStream

from src.code_gen.lua_transpiler import LuaTranspiler
from src.code_gen.python_transpiler import PythonTranspiler
from src.parser.ast_builder import ASTBuilder
from src.parser.gen.SapphireLexer import SapphireLexer
from src.parser.gen.SapphireParser import SapphireParser
from src.semantics.type_checker import TypeChecker


_DEFAULT_SEED = 20261122


def _gen_int_expr(rng: random.Random, depth: int = 0) -> str:
  """Generates a well-typed Sapphire `int` expression (guaranteed no div-by-zero)."""
  if depth >= 3 or (depth > 0 and rng.random() < 0.35):
    return str(rng.choice([-13, -7, -3, -2, -1, 0, 1, 2, 3, 5, 7, 11]))

  kind = rng.choice(["binop", "unary", "divmod", "ternary"])
  if kind == "unary":
    sub = _gen_int_expr(rng, depth + 1)
    return f"(-({sub}))"
  if kind == "divmod":
    lhs = _gen_int_expr(rng, depth + 1)
    # Non-zero divisor (including negatives to stress truncation toward zero)
    divisor = rng.choice([-7, -3, -2, -1, 1, 2, 3, 5, 7])
    op = rng.choice(["/", "%"])
    return f"(({lhs}) {op} ({divisor}))"
  if kind == "ternary":
    cond = _gen_bool_expr(rng, depth + 1)
    t_br = _gen_int_expr(rng, depth + 1)
    f_br = _gen_int_expr(rng, depth + 1)
    return f"(({cond}) ? ({t_br}) : ({f_br}))"

  lhs = _gen_int_expr(rng, depth + 1)
  rhs = _gen_int_expr(rng, depth + 1)
  op = rng.choice(["+", "-", "*"])
  return f"(({lhs}) {op} ({rhs}))"


def _gen_bool_expr(rng: random.Random, depth: int = 0) -> str:
  """Generates a well-typed Sapphire `bool` expression."""
  if depth >= 3 or (depth > 0 and rng.random() < 0.4):
    return rng.choice(["true", "false"])

  kind = rng.choice(["cmp", "logic", "not", "ternary_bool"])
  if kind == "not":
    return f"(!({_gen_bool_expr(rng, depth + 1)}))"
  if kind == "cmp":
    lhs = _gen_int_expr(rng, depth + 1)
    rhs = _gen_int_expr(rng, depth + 1)
    op = rng.choice(["==", "!=", "<", "<=", ">", ">="])
    return f"(({lhs}) {op} ({rhs}))"
  if kind == "ternary_bool":
    c = _gen_bool_expr(rng, depth + 1)
    # Deliberately mix `false` in the true branch to catch Lua `a and b or c` bugs
    t_br = rng.choice(["false", _gen_bool_expr(rng, depth + 1)])
    f_br = _gen_bool_expr(rng, depth + 1)
    return f"(({c}) ? ({t_br}) : ({f_br}))"

  lhs = _gen_bool_expr(rng, depth + 1)
  rhs = _gen_bool_expr(rng, depth + 1)
  op = rng.choice(["&&", "||"])
  return f"(({lhs}) {op} ({rhs}))"


def _gen_short_circuit_expr(rng: random.Random, depth: int = 0) -> str:
  """Generates boolean expressions calling `probe(id, ret)` to test short-circuiting."""
  if depth >= 3 or (depth > 0 and rng.random() < 0.45):
    tag = rng.randint(1, 9)
    val = rng.choice(["true", "false"])
    return f"probe({tag}, {val})"

  kind = rng.choice(["and", "or", "not", "ternary"])
  if kind == "not":
    return f"(!({_gen_short_circuit_expr(rng, depth + 1)}))"
  if kind == "ternary":
    c = _gen_short_circuit_expr(rng, depth + 1)
    t_br = _gen_short_circuit_expr(rng, depth + 1)
    f_br = _gen_short_circuit_expr(rng, depth + 1)
    return f"(({c}) ? ({t_br}) : ({f_br}))"
  op = "&&" if kind == "and" else "||"
  lhs = _gen_short_circuit_expr(rng, depth + 1)
  rhs = _gen_short_circuit_expr(rng, depth + 1)
  return f"(({lhs}) {op} ({rhs}))"


class TestDifferentialParity(unittest.TestCase):
  """Property-based differential parity tests across Python and Lua 5.1."""

  @classmethod
  def setUpClass(cls):
    cls.lua_bin = (
        shutil.which("lua") or shutil.which("lua5.1") or shutil.which("luajit")
    )
    if not cls.lua_bin:
      raise unittest.SkipTest("Lua runtime not found on PATH")

  def _run_both_backends(
      self, code: str, case_names: List[str], seed: int
  ) -> Tuple[List[str], List[str]]:
    """Compiles *code*, executes every function in *case_names* on Python & Lua."""
    lexer = SapphireLexer(InputStream(code))
    parser = SapphireParser(CommonTokenStream(lexer))
    ast = ASTBuilder().visitProgram(parser.program())
    checker = TypeChecker()
    checker.check(ast)
    self.assertEqual(
        checker.errors,
        [],
        f"Generated program failed type-checking (seed={seed}):\n{checker.errors}\n{code}",
    )

    py_code = PythonTranspiler().transpile(ast)
    lua_code = LuaTranspiler().transpile(ast)

    # Execute Python
    py_ns = {}
    py_out = []
    with redirect_stdout(io.StringIO()):
      exec(py_code, py_ns)
      for name in case_names:
        val = py_ns[name]()
        py_out.append(self._normalize_py(val))

    # Execute Lua in a single subprocess invocation (normalize IEEE-754 -0.0 -> 0)
    lua_calls = "\n".join(
        f'local _r = {name}(); if _r == 0 then _r = 0 end; print("{name}=" .. tostring(_r))'
        for name in case_names
    )
    full_lua = lua_code + "\n" + lua_calls + "\n"
    proc = subprocess.run(
        [self.lua_bin, "-"],
        input=full_lua,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      self.fail(
          f"Lua execution failed (seed={seed}):\n{proc.stderr}\n--- SAPPHIRE ---\n{code}"
      )

    lua_lines = proc.stdout.strip().splitlines()
    self.assertEqual(
        len(lua_lines),
        len(case_names),
        f"Unexpected Lua output line count (seed={seed}):\n{proc.stdout}",
    )
    lua_out = [line.split("=", 1)[1] for line in lua_lines]
    return py_out, lua_out

  @staticmethod
  def _normalize_py(val) -> str:
    if val is None:
      return "nil"
    if isinstance(val, bool):
      return "true" if val else "false"
    if isinstance(val, int):
      return str(val)
    return str(val)

  def _assert_parity(
      self, code: str, cases: List[Tuple[str, str]], seed: int
  ) -> None:
    names = [name for name, _ in cases]
    py_out, lua_out = self._run_both_backends(code, names, seed)
    for (name, src), py_v, lua_v in zip(cases, py_out, lua_out):
      if py_v != lua_v:
        self.fail(
            f"Python/Lua parity mismatch in {name} (seed={seed}):\n"
            f"  Python: {py_v}\n"
            f"  Lua   : {lua_v}\n"
            f"--- CASE SOURCE ---\n{src}"
        )

  def test_differential_arithmetic_and_booleans(self):
    """Generates 40 random arithmetic/division/modulo/boolean expressions."""
    rng = random.Random(_DEFAULT_SEED)
    cases: List[Tuple[str, str]] = []
    funcs: List[str] = []

    for i in range(25):
      expr = _gen_int_expr(rng)
      fn_name = f"case_int_{i}"
      fn_src = f"func {fn_name}(): int {{\n  return {expr};\n}}"
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    for i in range(15):
      expr = _gen_bool_expr(rng)
      fn_name = f"case_bool_{i}"
      fn_src = f"func {fn_name}(): bool {{\n  return {expr};\n}}"
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    code = "\n\n".join(funcs) + "\n"
    self._assert_parity(code, cases, _DEFAULT_SEED)

  def test_differential_short_circuit_and_side_effects(self):
    """Generates 30 random short-circuiting boolean/ternary trees with side-effect logs."""
    rng = random.Random(_DEFAULT_SEED + 1)
    header = """
var trace_acc: int = 0;

func probe(tag: int, result: bool): bool {
  trace_acc = trace_acc * 10 + tag;
  return result;
}
"""
    cases: List[Tuple[str, str]] = []
    funcs: List[str] = [header]

    for i in range(30):
      expr = _gen_short_circuit_expr(rng)
      fn_name = f"case_sc_{i}"
      fn_src = (
          f"func {fn_name}(): int {{\n"
          f"  trace_acc = 0;\n"
          f"  let res = {expr};\n"
          f"  return trace_acc * 2 + (res ? 1 : 0);\n"
          f"}}"
      )
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    code = "\n\n".join(funcs) + "\n"
    self._assert_parity(code, cases, _DEFAULT_SEED + 1)

  def test_differential_match_optionals_and_chaining(self):
    """Generates 30 random programs combining match+yield, optionals, `?.`, and `??`."""
    rng = random.Random(_DEFAULT_SEED + 2)
    header = """
struct Node {
  var val: int;
  var next_val: int?;
}
impl Node {
  func add(x: int): int {
    return self.val + x;
  }
}
"""
    cases: List[Tuple[str, str]] = []
    funcs: List[str] = [header]

    for i in range(30):
      subj = rng.choice([0, 1, 2, 3, 4])
      opt_init = rng.choice(["none", "0", "7", "-5"])
      node_present = rng.choice([True, False])
      node_val = rng.choice([0, 3, -4, 10])
      node_next = rng.choice(["none", "0", "9"])
      fallback = rng.choice([0, -1, 42])
      use_block_arm = rng.choice([True, False])

      if use_block_arm:
        arm1 = (
            "1, 2 -> {\n"
            "      var acc = 1;\n"
            "      if let u ?= opt_x {\n"
            "        acc += u;\n"
            "        yield acc * 2;\n"
            "      }\n"
            "      yield acc + 10;\n"
            "    },"
        )
      else:
        arm1 = "1, 2 -> (opt_x ?? -3) + 5,"

      node_expr = (
          f"Node {{ val = {node_val}, next_val = {node_next} }}"
          if node_present
          else "none"
      )
      fn_name = f"case_opt_{i}"
      fn_src = (
          f"func {fn_name}(): int {{\n"
          f"  let opt_x: int? = {opt_init};\n"
          f"  let n: Node? = {node_expr};\n"
          f"  let m_val = match {subj} {{\n"
          f"    0 -> (opt_x ?? {fallback}),\n"
          f"    {arm1}\n"
          f"    ... -> (n?.add(3) ?? {fallback}),\n"
          f"  }};\n"
          f"  let c_val = n?.next_val ?? {fallback};\n"
          f"  return m_val * 100 + c_val;\n"
          f"}}"
      )
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    code = "\n\n".join(funcs) + "\n"
    self._assert_parity(code, cases, _DEFAULT_SEED + 2)

  def test_differential_containers_negative_index_and_writebacks(self):
    """Generates 30 random programs mutating `[int?]` & `Map<String, int?>` via write-backs."""
    rng = random.Random(_DEFAULT_SEED + 3)
    cases: List[Tuple[str, str]] = []
    funcs: List[str] = []

    for i in range(30):
      arr_vals = [rng.choice(["none", "0", "3", "-2", "8"]) for _ in range(4)]
      map_a = rng.choice(["none", "0", "5", "-4"])
      map_b = rng.choice(["none", "0", "9", "-1"])
      idx1 = rng.choice([0, 1, 2, 3, -1, -2, -4])
      idx2 = rng.choice([0, 1, -1, -3])
      key1 = rng.choice(['"a"', '"b"', '"missing"'])
      key2 = rng.choice(['"a"', '"b"'])
      delta1 = rng.choice([-3, 0, 4, 7])
      delta2 = rng.choice([-5, 1, 6])

      fn_name = f"case_cont_{i}"
      fn_src = (
          f"func {fn_name}(): int {{\n"
          f"  var arr: [int?] = [{', '.join(arr_vals)}];\n"
          f'  var m: Map<String, int?> = {{"a": {map_a}, "b": {map_b}}};\n'
          f"  let plain_arr = [10, 20, 30, 40];\n"
          f'  let plain_map: Map<String, int> = {{"a": 5, "b": 9}};\n'
          f"  if var v ?= arr[{idx1}] {{\n"
          f"    v += {delta1};\n"
          f"  }}\n"
          f"  if var mv ?= m[{key2}] {{\n"
          f"    mv += {delta2};\n"
          f"  }}\n"
          f"  let g_arr = plain_arr.get({idx2}) ?? -100;\n"
          f"  let g_map = plain_map.get({key1}) ?? -200;\n"
          f"  var sum = 0;\n"
          f"  for x in arr {{\n"
          f"    sum += (x ?? 1);\n"
          f"  }}\n"
          f'  sum += (m["a"] ?? 2) + (m["b"] ?? 3);\n'
          f"  return sum * 1000 + g_arr * 10 + g_map;\n"
          f"}}"
      )
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    code = "\n\n".join(funcs) + "\n"
    self._assert_parity(code, cases, _DEFAULT_SEED + 3)

  def test_differential_raii_moves_and_drop_flags(self):
    """Generates 20 random RAII programs with conditional moves, reassignments, and early returns."""
    rng = random.Random(_DEFAULT_SEED + 4)
    header = """
var drop_log: int = 0;

struct Token {
  var id: int;
}
impl Token {
  func __del__() {
    drop_log = drop_log * 10 + self.id;
  }
}

func consume(t: Token): int {
  return t.id;
}
"""
    cases: List[Tuple[str, str]] = []
    funcs: List[str] = [header]

    for i in range(20):
      cond1 = rng.choice(["true", "false"])
      cond2 = rng.choice(["true", "false"])
      early_ret = rng.choice([True, False])
      reassign = rng.choice([True, False])

      use_fn_consume_a = rng.choice([True, False])
      use_fn_consume_c = rng.choice([True, False])

      lines = [
          "  drop_log = 0;",
          "  var a = Token { id = 1 };",
          "  var b = Token { id = 2 };",
          "  var out = 0;",
          f"  if {cond1} {{",
          (
              "    out += consume(move a);"
              if use_fn_consume_a
              else "    let moved_a = move a;\n    out += moved_a.id;"
          ),
          "  }",
      ]
      if reassign:
        lines.append("  b = Token { id = 3 };")
      if early_ret:
        lines.extend([
            f"  if {cond2} {{",
            "    var c = Token { id = 4 };",
            (
                "    return out + consume(move c);"
                if use_fn_consume_c
                else "    out += c.id;\n    return out;"
            ),
            "  }",
        ])
      else:
        lines.extend([
            f"  if {cond2} {{",
            "    var c = Token { id = 4 };",
            (
                "    out += consume(move c);"
                if use_fn_consume_c
                else "    let moved_c = move c;\n    out += moved_c.id;"
            ),
            "  }",
        ])
      lines.append("  return out;")

      fn_name = f"case_raii_{i}"
      helper_name = f"helper_raii_{i}"
      fn_src = (
          f"func {helper_name}(): int {{\n"
          + "\n".join(lines)
          + "\n}\n"
          + f"func {fn_name}(): int {{\n"
          + f"  let r = {helper_name}();\n"
          + "  return drop_log * 100 + r;\n"
          + "}"
      )
      cases.append((fn_name, fn_src))
      funcs.append(fn_src)

    code = "\n\n".join(funcs) + "\n"
    self._assert_parity(code, cases, _DEFAULT_SEED + 4)


if __name__ == "__main__":
  unittest.main()
