"""Transpiler runtime benchmark and LuaJIT trace-abort harness.

Compiles representative Sapphire microbenchmarks through the real Python and
Lua 5.1 / LuaJIT transpiler pipelines, verifies cross-backend output parity,
measures steady-state execution time (excluding process startup), records
generated code sizes, and collects `luajit -jv` trace compilation aborts.

Usage:
  pipenv run python testing/perf/bench_transpilers.py
  pipenv run python testing/perf/bench_transpilers.py --save-baseline base.json
  pipenv run python testing/perf/bench_transpilers.py --compare base.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass

REPO_ROOT = os.path.abspath(
  os.path.join(os.path.dirname(__file__), "..", "..")
)
if REPO_ROOT not in sys.path:
  sys.path.insert(0, REPO_ROOT)

from sapphire.code_gen.transpiler import transpile_file  # noqa: E402


@dataclass(frozen=True)
class BenchmarkSpec:
  """Definition of a single Sapphire microbenchmark."""

  name: str
  description: str
  source: str


BENCHMARKS: tuple[BenchmarkSpec, ...] = (
  BenchmarkSpec(
    name="struct_literal_init",
    description="Plain struct literal construction & field reads",
    source="""struct Vector2D {
  var x: float;
  var y: float;
}

func run_bench(): int {
  var acc = 0.0;
  for i in range(40000) {
    let v = Vector2D { x = i as float, y = 2.5 };
    acc += v.x + v.y;
  }
  return acc as int;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="struct_ctor_init",
    description="Struct with __init__ + default args construction",
    source="""struct Entity {
  var id: int;
  var x: float;
  var y: float;
  var hp: int;
}

impl Entity {
  func __init__(id: int, x: float, y: float, hp: int = 100) {
    self.id = id;
    self.x = x;
    self.y = y;
    self.hp = hp;
  }
}

func run_bench(): int {
  var acc = 0;
  for i in range(30000) {
    let e = Entity(id = i, x = 1.0, y = 2.0);
    acc += e.id + e.hp;
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="proto_clone_read",
    description="Proto creation, cloning, override reads & nested CoW",
    source="""struct Stats {
  var atk: int;
  var def: int;
}

proto Unit {
  var id: int;
  var hp: int;
  var stats: Stats;
}

func run_bench(): int {
  var arena = Arena();
  var base = Unit {
    id = 0,
    hp = 50,
    stats = Stats { atk = 12, def = 4 },
  } in arena;
  var acc = 0;
  for i in range(10000) {
    var c = clone base {
      self.id = i;
    };
    acc += c.id + c.hp + c.stats.atk;
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="arena_register",
    description="Arena.register + LIFO destroy at N = 2000",
    source="""proto Item {
  var id: int;
}

func run_bench(): int {
  var arena = Arena();
  var acc = 0;
  for i in range(2000) {
    let item = Item { id = i } in arena;
    acc += item.id;
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="array_index_loop",
    description="Array<int> indexing, compound assign, for-in, push & sort",
    source="""func run_bench(): int {
  var arr: [int] = [];
  for i in range(2000) {
    arr.push((i * 37) % 1000);
  }
  var acc = 0;
  for r in range(15) {
    for i in range(arr.size()) {
      arr[i] += 1;
      acc += arr[i];
    }
    for v in arr {
      acc += v;
    }
  }
  arr.sort(in_place = true);
  acc += arr[0] + arr[-1];
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="array_value_copy",
    description="Array<int> & flat value struct copies on assignment",
    source="""struct Point {
  var x: float;
  var y: float;
}

func run_bench(): int {
  var nums: [int] = [];
  for i in range(400) {
    nums.push(i);
  }
  var pt = Point { x = 3.0, y = 4.0 };
  var acc = 0;
  for i in range(300) {
    let copied_arr = nums;
    let copied_pt = pt;
    acc += copied_arr[0] + copied_arr[399] + (copied_pt.x as int);
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="string_ops",
    description="String + chains, f-strings, size, slice, find & contains",
    source="""func run_bench(): int {
  var acc = 0;
  let hay = "alpha-beta-gamma-delta-epsilon";
  for i in range(4000) {
    let s = "p:" + "a" + "b" + "c";
    let f = f"id={i},s={s}";
    let sub = hay.slice(6, 16);
    if hay.contains("gamma") {
      acc += f.size() + sub.size();
    }
    if let pos ?= hay.find("delta") {
      acc += pos;
    }
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="std_utf8_ops",
    description="std.utf8 size, offset, and sub calls",
    source="""import std.utf8;

func run_bench(): int {
  var acc = 0;
  let text = "Hello, world! Sapphire UTF-8 test";
  for i in range(2000) {
    let n = utf8.size(text) ?? 0;
    let off = utf8.offset(text, 8) ?? 0;
    let sub = utf8.sub(text, 0, 12);
    acc += n + off + sub.size();
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="optionals_casts_div",
    description="Optional chaining ?., ??, as T?, int as float, int / & Map",
    source="""struct Inner {
  var value: int;
}

struct Outer {
  var child: Inner?;
}

func run_bench(): int {
  var m: [String: int] = {"a": 1, "b": 2, "c": 3};
  let box: Outer? = Outer { child = Inner { value = 42 } };
  var acc = 0;
  for i in range(20000) {
    let v = box?.child?.value ?? 0;
    let f = (i as float) + 1.5;
    let q = (i + 100) / 7;
    let opt_q = q as int?;
    if m.contains("b") {
      acc += v + (f as int) + (opt_q ?? 0) + m.size();
    }
  }
  return acc;
}

export { run_bench }
""",
  ),
  BenchmarkSpec(
    name="raii_multi_return",
    description="RAII __del__ lifecycle, multi-return RVO & coroutine step",
    source="""struct Handle {
  var id: int;
}

impl Handle {
  func __del__() {
    self.id = -1;
  }
}

func make_pair(x: int): int, int {
  let h = Handle { id = x };
  return x + 1, x + 2;
}

func counter(n: int): Coroutine<int> {
  for i in range(n) {
    yield i;
  }
}

func run_bench(): int {
  var acc = 0;
  for i in range(10000) {
    let a, b = make_pair(i);
    acc += a + b;
  }
  var c = counter(5000);
  while !c.is_done() {
    if let v ?= c.step() {
      acc += v;
    }
  }
  return acc;
}

export { run_bench }
""",
  ),
)


@dataclass
class TargetResult:
  """Measured metrics for a single benchmark on one target backend."""

  median_ms: float
  min_ms: float
  checksum: str
  code_bytes: int
  code_lines: int
  jit_traces: int = 0
  jit_aborts: int = 0
  jit_abort_reasons: dict[str, int] | None = None


def _run_python_bench(
  mod_dir: str, mod_name: str, runs: int
) -> tuple[list[float], str]:
  driver = (
    "import json, sys, time\n"
    f"sys.path.insert(0, {mod_dir!r})\n"
    f"sys.path.insert(0, {os.path.join(REPO_ROOT, 'sapphire', 'lib')!r})\n"
    f"import {mod_name} as m\n"
    "chk = m.run_bench()\n"
    "times = []\n"
    f"for _ in range({runs}):\n"
    "  t0 = time.perf_counter()\n"
    "  chk = m.run_bench()\n"
    "  times.append((time.perf_counter() - t0) * 1000.0)\n"
    "print(json.dumps({'times': times, 'checksum': str(chk)}))\n"
  )
  proc = subprocess.run(
    [sys.executable, "-c", driver],
    capture_output=True,
    text=True,
    check=True,
  )
  data = json.loads(proc.stdout.strip().splitlines()[-1])
  return [float(t) for t in data["times"]], str(data["checksum"])


def _run_lua_bench(
  luajit_bin: str, mod_dir: str, mod_name: str, runs: int
) -> tuple[list[float], str]:
  std_lib_dir = os.path.join(REPO_ROOT, "sapphire", "lib")
  driver = (
    f"package.path = {mod_dir + '/?.lua;' + std_lib_dir + '/?.lua;'!r}"
    " .. package.path\n"
    "local ok_ffi, ffi = pcall(require, 'ffi')\n"
    "local now\n"
    "if ok_ffi then\n"
    "  ffi.cdef[[\n"
    "    typedef long time_t;\n"
    "    typedef struct { time_t tv_sec; long tv_nsec; } sp_timespec;\n"
    "    int clock_gettime(int clk_id, sp_timespec *tp);\n"
    "  ]]\n"
    "  local ts = ffi.new('sp_timespec')\n"
    "  now = function()\n"
    "    ffi.C.clock_gettime(1, ts)\n"
    "    return tonumber(ts.tv_sec) * 1000.0 + tonumber(ts.tv_nsec) * 1e-6\n"
    "  end\n"
    "else\n"
    "  now = function() return os.clock() * 1000.0 end\n"
    "end\n"
    f"local m = require({mod_name!r})\n"
    "local chk = m.run_bench()\n"
    "local times = {}\n"
    f"for i = 1, {runs} do\n"
    "  local t0 = now()\n"
    "  chk = m.run_bench()\n"
    "  times[i] = now() - t0\n"
    "end\n"
    "io.write('CHECKSUM:' .. string.format('%.0f', chk) .. '\\n')\n"
    "io.write('TIMES:' .. table.concat(times, ',') .. '\\n')\n"
  )
  proc = subprocess.run(
    [luajit_bin, "-e", driver],
    capture_output=True,
    text=True,
    check=True,
  )
  checksum = ""
  times: list[float] = []
  for line in proc.stdout.splitlines():
    if line.startswith("CHECKSUM:"):
      checksum = line.split(":", 1)[1].strip()
    elif line.startswith("TIMES:"):
      times = [float(x) for x in line.split(":", 1)[1].split(",") if x]
  return times, checksum


def _collect_luajit_traces(
  luajit_bin: str, mod_dir: str, mod_name: str
) -> tuple[int, int, dict[str, int]]:
  std_lib_dir = os.path.join(REPO_ROOT, "sapphire", "lib")
  driver = (
    f"package.path = {mod_dir + '/?.lua;' + std_lib_dir + '/?.lua;'!r}"
    " .. package.path\n"
    f"local m = require({mod_name!r})\n"
    "m.run_bench()\n"
    "m.run_bench()\n"
  )
  proc = subprocess.run(
    [luajit_bin, "-jv", "-e", driver],
    capture_output=True,
    text=True,
    check=True,
  )
  traces = 0
  aborts = 0
  reasons: dict[str, int] = {}
  abort_re = re.compile(r"\[TRACE --- .*? -- (.*?)(?:\s+at\s+.*)?\]")
  trace_re = re.compile(r"\[TRACE\s+\d+\s+")
  for line in (proc.stderr + "\n" + proc.stdout).splitlines():
    if trace_re.search(line):
      traces += 1
      continue
    match = abort_re.search(line)
    if match:
      aborts += 1
      reason = match.group(1).strip()
      reasons[reason] = reasons.get(reason, 0) + 1
  return traces, aborts, reasons


def run_suite(
  targets: list[str],
  runs: int,
  name_filter: str | None,
  collect_traces: bool,
) -> dict[str, dict[str, TargetResult]]:
  """Compiles and executes selected benchmarks, returning measured results."""
  luajit_bin = shutil.which("luajit") or shutil.which("lua")
  if "lua" in targets and not luajit_bin:
    raise RuntimeError("Neither 'luajit' nor 'lua' was found on PATH.")

  results: dict[str, dict[str, TargetResult]] = {}
  with tempfile.TemporaryDirectory(prefix="sapphire_perf_") as tmp_dir:
    for spec in BENCHMARKS:
      if name_filter and name_filter not in spec.name:
        continue
      sp_path = os.path.join(tmp_dir, f"{spec.name}.sp")
      with open(sp_path, "w", encoding="utf-8") as f:
        f.write(spec.source)

      bench_results: dict[str, TargetResult] = {}
      if "python" in targets:
        py_path = os.path.join(tmp_dir, f"{spec.name}.py")
        transpile_file(sp_path, py_path, target="python", quiet=True)
        with open(py_path, encoding="utf-8") as f:
          py_src = f.read()
        times, chk = _run_python_bench(tmp_dir, spec.name, runs)
        bench_results["python"] = TargetResult(
          median_ms=statistics.median(times),
          min_ms=min(times),
          checksum=chk,
          code_bytes=len(py_src.encode("utf-8")),
          code_lines=py_src.count("\n"),
        )

      if "lua" in targets and luajit_bin:
        lua_path = os.path.join(tmp_dir, f"{spec.name}.lua")
        transpile_file(sp_path, lua_path, target="lua", quiet=True)
        with open(lua_path, encoding="utf-8") as f:
          lua_src = f.read()
        times, chk = _run_lua_bench(luajit_bin, tmp_dir, spec.name, runs)
        traces, aborts, reasons = (0, 0, {})
        if collect_traces and "luajit" in os.path.basename(luajit_bin):
          traces, aborts, reasons = _collect_luajit_traces(
            luajit_bin, tmp_dir, spec.name
          )
        bench_results["lua"] = TargetResult(
          median_ms=statistics.median(times),
          min_ms=min(times),
          checksum=chk,
          code_bytes=len(lua_src.encode("utf-8")),
          code_lines=lua_src.count("\n"),
          jit_traces=traces,
          jit_aborts=aborts,
          jit_abort_reasons=reasons,
        )

      if "python" in bench_results and "lua" in bench_results:
        py_chk = bench_results["python"].checksum
        lua_chk = bench_results["lua"].checksum
        if py_chk != lua_chk:
          raise AssertionError(
            f"Parity mismatch in '{spec.name}': py={py_chk} vs lua={lua_chk}"
          )
      results[spec.name] = bench_results
  return results


def _format_delta(cur_ms: float, base_ms: float | None) -> str:
  if base_ms is None or cur_ms <= 0:
    return ""
  ratio = base_ms / cur_ms
  return f" ({ratio:.2f}x)"


def _print_report(
  results: dict[str, dict[str, TargetResult]],
  baseline: dict[str, dict[str, dict[str, object]]] | None,
) -> None:
  header = (
    f"{'Benchmark':<21} | {'Py (ms)':>14} | {'LuaJIT (ms)':>14} | "
    f"{'Traces/Aborts':>13} | {'Top Abort Reason'}"
  )
  print(header)
  print("-" * len(header))
  for name, per_target in results.items():
    base_entry = baseline.get(name, {}) if baseline else {}
    py_res = per_target.get("python")
    lua_res = per_target.get("lua")

    py_str = "-"
    if py_res:
      base_py = base_entry.get("python", {}).get("median_ms")
      base_py_f = float(base_py) if isinstance(base_py, (int, float)) else None
      py_str = (
        f"{py_res.median_ms:.2f}"
        f"{_format_delta(py_res.median_ms, base_py_f)}"
      )

    lua_str = "-"
    trace_str = "-"
    top_reason = "-"
    if lua_res:
      base_lua = base_entry.get("lua", {}).get("median_ms")
      base_lua_f = (
        float(base_lua) if isinstance(base_lua, (int, float)) else None
      )
      lua_str = (
        f"{lua_res.median_ms:.2f}"
        f"{_format_delta(lua_res.median_ms, base_lua_f)}"
      )
      trace_str = f"{lua_res.jit_traces}/{lua_res.jit_aborts}"
      if lua_res.jit_abort_reasons:
        reason, count = max(
          lua_res.jit_abort_reasons.items(), key=lambda kv: kv[1]
        )
        top_reason = f"{reason} ({count})"
    print(
      f"{name:<21} | {py_str:>14} | {lua_str:>14} | "
      f"{trace_str:>13} | {top_reason}"
    )


def _serialize_results(
  results: dict[str, dict[str, TargetResult]],
) -> dict[str, dict[str, dict[str, object]]]:
  return {
    name: {tgt: asdict(res) for tgt, res in per_target.items()}
    for name, per_target in results.items()
  }


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
    description="Benchmark Sapphire Python & LuaJIT transpiler output."
  )
  parser.add_argument(
    "--target",
    choices=("all", "python", "lua"),
    default="all",
    help="Target backend(s) to benchmark (default: all).",
  )
  parser.add_argument(
    "--runs",
    type=int,
    default=5,
    help="Timed iterations per benchmark after 1 warmup run (default: 5).",
  )
  parser.add_argument(
    "--filter",
    dest="name_filter",
    default=None,
    help="Only run benchmarks whose name contains this substring.",
  )
  parser.add_argument(
    "--no-trace",
    action="store_true",
    help="Skip luajit -jv trace abort collection.",
  )
  parser.add_argument(
    "--save-baseline",
    default=None,
    help="Write JSON results to this file path.",
  )
  parser.add_argument(
    "--compare",
    default=None,
    help="Compare timings against a previously saved JSON baseline.",
  )
  parser.add_argument(
    "--json",
    action="store_true",
    help="Print machine-readable JSON instead of a summary table.",
  )
  args = parser.parse_args(argv)

  targets = ["python", "lua"] if args.target == "all" else [args.target]
  baseline = None
  if args.compare:
    with open(args.compare, encoding="utf-8") as f:
      baseline = json.load(f)

  results = run_suite(
    targets=targets,
    runs=args.runs,
    name_filter=args.name_filter,
    collect_traces=not args.no_trace,
  )
  payload = _serialize_results(results)

  if args.save_baseline:
    with open(args.save_baseline, "w", encoding="utf-8") as f:
      json.dump(payload, f, indent=2)

  if args.json:
    print(json.dumps(payload, indent=2))
  else:
    _print_report(results, baseline)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
